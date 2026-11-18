"""Owns the provider, subscriptions, candles, chains, the bias engine and tick fan-out."""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Literal

import httpx

from tradedisha.auth import AuthService
from tradedisha.clock import (
    IST,
    DrivenClock,
    MarketClock,
    MarketStatus,
    epoch_ms_now,
    ist_to_ms,
    load_calendar,
)
from tradedisha.config import Settings, hours_enforced
from tradedisha.engine.bias_engine import BiasComputed, BiasEngine
from tradedisha.engine.bullion_desk import BullionDesk
from tradedisha.engine.outcomes import Outcome, OutcomeTracker
from tradedisha.engine.paper import PaperTrade, PaperTradeManager, Price
from tradedisha.engine.signals import Signal, SignalEngine
from tradedisha.events import EventBus, FeedHealthChanged
from tradedisha.feed.bus import StampedTick, TickBus
from tradedisha.feed.provider import FeedHealth, MarketDataProvider, Tick
from tradedisha.feed.replay import ReplayProvider
from tradedisha.feed.synthetic import SyntheticProvider, SyntheticUniverse
from tradedisha.feed.upstox import UpstoxProvider, fetch_ltp
from tradedisha.indicators import IndicatorResult
from tradedisha.indicators.macro import (
    MacroSeries,
    bullion_macro_indicators,
    index_macro_indicators,
)
from tradedisha.instruments.models import Instrument, ResolvedIndex
from tradedisha.instruments.resolve import INDEX_SPOT_NAMES, ResolutionError, resolve_index
from tradedisha.instruments.synthetic_master import SPEC, build_synthetic_master
from tradedisha.instruments.upstox_master import (
    load_upstox_master,
    master_path,
    mcx_master_path,
    read_commodities,
    read_master,
)
from tradedisha.market import bullion as bullion_mod
from tradedisha.market import macro as macro_mod
from tradedisha.market.backfill import (
    apply_baseline,
    fetch_52w_range,
    fetch_intraday_candles,
    fetch_option_chain,
)
from tradedisha.market.bullion import BullionTracker
from tradedisha.market.candles import MINUTE_MS, Candle, CandleBuilder, CandleStore
from tradedisha.market.chain_manager import ChainManager, SubscriptionChange
from tradedisha.market.flow import FlowReading, FlowTracker
from tradedisha.market.macro import MacroTracker, build_view
from tradedisha.market.stats import (
    VIX_KEY,
    IndexStats,
    compute_stats,
    market_wide_keys,
    sector_quotes,
)
from tradedisha.metrics.latency import LatencyTracker
from tradedisha.parameters.model import ParameterSet
from tradedisha.store.ticks import FeedEventLog, TickStore

log = logging.getLogger(__name__)

# MCX and NSE currency: side markets with their own trackers (spec §6.6, §6.8)
SIDE_MARKET_SEGMENTS = ("MCX_FO|", "NCD_FO|")


@dataclass
class LatestPrices:
    """Last LTP and timestamp per instrument key; what the WS hub reads."""

    ltp: dict[str, float] = field(default_factory=dict)
    ts: dict[str, int] = field(default_factory=dict)
    close_prev: dict[str, float] = field(default_factory=dict)

    def update(self, t: Tick) -> None:
        self.ltp[t.key] = t.ltp
        self.ts[t.key] = t.ts
        if t.close_prev is not None:
            self.close_prev[t.key] = t.close_prev


def parse_drop_ranges(specs: list[str], day: date) -> list[tuple[int, int]]:
    """`"10:05:00-10:07:30"` on the replay day -> (start_ms, end_ms). For fault injection."""
    out: list[tuple[int, int]] = []
    for spec in specs:
        lo, hi = (time.fromisoformat(part.strip()) for part in spec.split("-", 1))
        out.append(
            (
                ist_to_ms(datetime.combine(day, lo, tzinfo=IST)),
                ist_to_ms(datetime.combine(day, hi, tzinfo=IST)),
            )
        )
    return out


def _spot_key(master: list[Instrument], index: str) -> str:
    wanted = INDEX_SPOT_NAMES.get(index, index)
    for inst in master:
        if inst.instrument_type == "INDEX" and inst.name == wanted:
            return inst.instrument_key
    raise ResolutionError(f"spot instrument for {index} not in master")


BullionState = Literal["live", "stale", "closed", "holiday"]


class FeedSession:
    """Start -> resolve instruments -> connect provider -> subscribe -> pump ticks -> stop."""

    bullion_desk: BullionDesk | None = None  # bullion bias, signals, paper (§9a)
    macro: MacroTracker | None = None  # dollar legs and crude, live feed only (§6.8)

    def __init__(
        self,
        settings: Settings,
        conn: sqlite3.Connection,
        clock: MarketClock,
        *,
        bus: EventBus,
        latency: LatencyTracker,
        params: Callable[[], ParameterSet],
        driven_clock: DrivenClock | None = None,
        auth: AuthService | None = None,
    ) -> None:
        self.settings = settings
        self.auth = auth
        self.started = False
        self.enforce_hours = hours_enforced(settings)
        self.range_52w: dict[str, tuple[float, float]] = {}  # index -> (high, low) to yesterday
        self.gap_since: int | None = None  # start of the feed outage in progress, if any
        self.last_gap: tuple[int, int] | None = None  # (start, end) of the last finished one
        self.http_transport: httpx.AsyncBaseTransport | None = None  # tests inject a fake
        self._was_live = False
        # Latest tick time per exchange. Liveness is judged on the index keys alone, so MCX
        # ticks (which run to 23:30) never hide an NSE outage, and the other way round.
        self.last_index_tick_ts: int | None = None
        self._health_key: tuple[object, ...] | None = None
        self._start_lock = asyncio.Lock()
        self.feed_ended = asyncio.Event()  # set when the provider has no more ticks (replay)
        self.clock = clock
        self.mcx_clock = clock.with_hours(
            market_open=settings.mcx_open,
            market_close=settings.mcx_close,
            calendar=load_calendar(settings.mcx_holidays_file),
        )
        self.events = bus
        self.latency = latency
        self.params = params
        # The version number of `params()`, when whoever built the session versions them.
        self.config_version: Callable[[], int | None] = lambda: None
        self.tick_bus = TickBus()
        self.tick_store = TickStore(conn)
        self.feed_log = FeedEventLog(conn)
        self.prices = LatestPrices()
        self.master: list[Instrument] = []
        self.resolved: dict[str, ResolvedIndex] = {}
        self.bullion: BullionTracker | None = None  # GOLD / SILVER, live feed only (§6.6)
        self.bullion_candle_listeners: list[Callable[[str, Candle], None]] = []
        self.candles = CandleBuilder()
        self.candle_store = CandleStore(conn)
        self.chains: ChainManager | None = None
        self.bias: BiasEngine | None = None
        self.signals: SignalEngine | None = None
        self.shadow_signals: SignalEngine | None = None  # the entry rule that is not live
        self.flow: FlowTracker | None = None
        self.flow_listeners: list[Callable[[FlowReading], None]] = []
        self.paper: PaperTradeManager | None = None
        self.outcomes: OutcomeTracker | None = None
        self.provider: MarketDataProvider | None = None
        self.replay_day: date | None = None
        self.candle_listeners: list[Callable[[Candle], None]] = []
        self.bias_listeners: list[Callable[[BiasComputed], None]] = []
        self.signal_listeners: list[Callable[[Signal], None]] = []
        self.trade_listeners: list[Callable[[PaperTrade], None]] = []
        self._driven_clock = driven_clock
        self._conn = conn
        self._tasks: list[asyncio.Task[None]] = []
        self._last_health: FeedHealth | None = None
        self._sub_changes: asyncio.Queue[SubscriptionChange] = asyncio.Queue()
        self.tick_bus.subscribe(self._on_tick)
        self.candles.on_close(self._on_candle_close)

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        """Idempotent: the Upstox login callback calls this once a token exists."""
        async with self._start_lock:
            if not self.started:
                await self._start()
                self.started = True

    async def _start(self) -> None:
        # Everything that can fail on the network happens first, so a failed start leaves
        # nothing half-wired and can simply be tried again.
        today, master, spots = await self._load_instruments()
        self.master = master
        for index in self.settings.indices:
            self.resolved[index] = resolve_index(
                self.master, index, today, spots[index], strike_window=self.settings.strike_window
            )
        self.chains = ChainManager(
            master=self.master,
            resolved=self.resolved,
            today=today,
            strike_window=self.settings.strike_window,
            recenter_strikes=self.settings.recenter_strikes,
            conn=self._conn,
            events=self.events,
            on_subscription_change=self._sub_changes.put_nowait,
        )
        self.tick_bus.subscribe(self.chains.on_tick)
        self.bias = BiasEngine(
            candles=self.candles,
            chains=self.chains.chains,
            resolved=self.resolved,
            params=self.params,
            conn=self._conn,
            on_bias=self._on_bias,
            macro=self.index_macro,
        )
        enforce = self.enforce_hours
        self.signals = self._signal_engine(shadow=False)
        self.shadow_signals = self._signal_engine(shadow=True)
        self.bias_listeners.append(self.signals.on_bias)
        self.bias_listeners.append(self.shadow_signals.on_bias)
        # After the chain, so a flow reading sees the quote that came with the same tick.
        self.flow = FlowTracker(
            params=self.params,
            resolved=self.resolved,
            chains=self.chains.chains,
            on_flow=self._on_flow,
        )
        self.tick_bus.subscribe(self.flow.on_tick)
        self.outcomes = OutcomeTracker(
            params=self.params,
            conn=self._conn,
            spot_keys={i: r.spot.instrument_key for i, r in self.resolved.items()},
            spot_before=self._spot_before,
            on_outcome=self._on_outcome,
        )
        self.tick_bus.subscribe(self.outcomes.on_tick)
        self.paper = PaperTradeManager(
            clock=self.clock,
            params=self.params,
            conn=self._conn,
            signals=self.signals,
            price=self._price,
            feed_live=self.feed_live,
            enforce_hours=enforce,
            last_recorded=self._last_recorded,
            on_trade=self._on_trade,
        )
        self.tick_bus.subscribe(self.paper.on_tick)
        self.bias_listeners.append(self.paper.on_bias)
        await self._backfill()
        tracker: BullionTracker | None = None
        if self.settings.feed_provider == "upstox":
            tracker = await self._load_bullion(today)
        elif self.settings.feed_provider == "replay" and self.settings.replay_bullion:
            tracker = await self._load_recorded_bullion(self.replay_day or self._replay_day())
        if tracker is not None:
            self.attach_bullion(tracker)
        macro: MacroTracker | None = None
        if self.settings.feed_provider == "upstox":
            macro = await self._load_macro(today)
        elif self.settings.feed_provider == "replay" and self.settings.replay_bullion:
            macro = await self._load_recorded_macro(self.replay_day or self._replay_day())
        if macro is not None:
            self.attach_macro(macro)
        self.provider = self._build_provider()
        await self.provider.connect()
        keys = [k for r in self.resolved.values() for k in r.all_keys]
        keys += market_wide_keys(self.settings)  # India VIX and the sector indices
        keys.extend(sorted(self.bullion_keys))
        keys.extend(sorted(self.macro_keys))
        await self.provider.subscribe(keys)
        self.feed_log.write(
            epoch_ms_now(), "session_start", f"provider={self.provider.name} keys={len(keys)}"
        )
        self._tasks = [
            asyncio.create_task(self._pump(), name="feed-pump"),
            asyncio.create_task(self._housekeeping(), name="feed-housekeeping"),
            asyncio.create_task(self._apply_subscription_changes(), name="feed-resubscribe"),
        ]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        if self.provider is not None:
            await self.provider.close()
        self.tick_store.flush()
        self.bullion_tick_store.flush()
        if self.outcomes is not None:
            self.outcomes.flush()
        self.feed_log.write(
            epoch_ms_now(), "session_stop", f"ticks_written={self.tick_store.written}"
        )

    # -- internals ---------------------------------------------------------

    def _replay_day(self) -> date:
        if self.settings.replay_date:
            return date.fromisoformat(self.settings.replay_date)
        days = self.tick_store.recorded_days()
        if not days:
            raise RuntimeError("replay requested but no recorded ticks exist")
        return days[0]

    async def _load_instruments(self) -> tuple[date, list[Instrument], dict[str, float]]:
        """The day to resolve for, the instrument master, and a spot price per index."""
        s = self.settings
        today = self.clock.today()
        if s.feed_provider == "upstox":
            token = self.auth.token if self.auth is not None else None
            if token is None:
                raise RuntimeError("Upstox login required before the live feed can start")
            master = await load_upstox_master(s.data_dir, today, s.indices)
            spot_keys = {i: _spot_key(master, i) for i in s.indices}
            async with httpx.AsyncClient(timeout=15) as client:
                ltp = await fetch_ltp(client, token, list(spot_keys.values()))
            return today, master, {i: ltp[k] for i, k in spot_keys.items()}
        if s.feed_provider == "replay":
            self.replay_day = self._replay_day()
            recorded = master_path(s.data_dir, self.replay_day)
            if recorded.exists():  # a recorded live session: use that day's real instruments
                master = await asyncio.to_thread(read_master, recorded, list(s.indices))
                spots: dict[str, float] = {}
                for index in s.indices:
                    first = self.tick_store.first_tick(self.replay_day, _spot_key(master, index))
                    if first is not None:
                        spots[index] = first.ltp
                if len(spots) == len(s.indices):
                    return self.replay_day, master, spots
        return (
            today,
            build_synthetic_master(today),
            {i: float(SPEC[i]["base"]) for i in s.indices},
        )

    def _build_provider(self) -> MarketDataProvider:
        s = self.settings
        if s.feed_provider == "synthetic":
            universes = [
                SyntheticUniverse.from_master(self.master, r) for r in self.resolved.values()
            ]
            return SyntheticProvider(
                universes,
                ticks_per_second=s.synthetic_ticks_per_second,
                seed=s.synthetic_seed,
                clock_ms=self.clock.now_ms,
                trend_per_tick=s.synthetic_trend_per_tick,
            )
        if s.feed_provider == "replay":
            day = self.replay_day or self._replay_day()
            self.replay_day = day
            return ReplayProvider(
                self.tick_store,
                day,
                speed=s.replay_speed,
                clock=self._driven_clock,
                drop_ranges=parse_drop_ranges(s.replay_drop, day),
                extra=(
                    self.bullion_tick_store
                    if self.bullion is not None or self.macro is not None
                    else None
                ),
            )
        auth = self.auth
        if auth is None:
            raise RuntimeError("the upstox feed needs an AuthService")
        return UpstoxProvider(token=lambda: auth.token, on_unauthorized=auth.mark_expired)

    async def _pump(self) -> None:
        assert self.provider is not None
        async for tick in self.provider.ticks():
            t_in = epoch_ms_now()
            self.tick_bus.publish(StampedTick(tick, t_in))
        self.feed_ended.set()
        await self._publish_health()

    def _on_tick(self, st: StampedTick) -> None:
        t = st.tick
        if self.is_side_market(t.key):  # bullion and macro have their own candles (§6.6, §6.8)
            self.prices.update(t)
            if self.settings.feed_provider != "replay":
                self.bullion_tick_store.add(t)  # its own table: never stretches an NSE replay
            return
        prev = self.last_index_tick_ts
        if prev is None or t.ts > prev:
            self.last_index_tick_ts = t.ts
        if (
            prev is not None
            and t.ts - prev > self.settings.feed_live_max_tick_age_ms
            and self.gap_since is None
            and self.expecting_ticks()
        ):
            # A silence the half-second timer did not catch (fast replay, a stalled loop).
            self.last_gap = (prev, t.ts)
            self.feed_log.write(epoch_ms_now(), "feed_gap", f"gap_ms={t.ts - prev}")
            if self.paper is not None:
                self.paper.mark_gap()
        self.prices.update(t)
        if self.settings.feed_provider != "replay":
            self.tick_store.add(t)
            self.latency.record("src_to_in", st.t_in - t.ts, at_ms=st.t_in)
        if t.key in self._candle_keys():
            self.candles.apply(t)

    def _candle_keys(self) -> set[str]:
        keys: set[str] = set()
        for r in self.resolved.values():
            keys.add(r.spot.instrument_key)
            keys.add(r.future.instrument_key)
        return keys

    def _on_candle_close(self, c: Candle) -> None:
        self.candle_store.write(c)
        for fn in self.candle_listeners:
            fn(c)

    def _on_bias(self, b: BiasComputed) -> None:
        for fn in self.bias_listeners:
            fn(b)

    def _on_signal(self, s: Signal) -> None:
        if self.outcomes is not None:
            self.outcomes.on_signal(s)
        for fn in self.signal_listeners:
            fn(s)

    def _signal_engine(self, *, shadow: bool) -> SignalEngine:
        assert self.chains is not None
        return SignalEngine(
            clock=self.clock,
            params=self.params,
            resolved=self.resolved,
            chains=self.chains.chains,
            conn=self._conn,
            feed_live=self.feed_live,
            enforce_hours=self.enforce_hours,
            market_open=self.settings.market_open,
            market_close=self.settings.market_close,
            risk_free_rate=self.settings.risk_free_rate,
            on_signal=self._on_signal,
            shadow=shadow,
            config_version=self.config_version,
        )

    def _on_flow(self, reading: FlowReading) -> None:
        for engine in (self.signals, self.shadow_signals):
            if engine is not None:
                engine.on_flow(reading.index, reading.ts, reading.score)
        for fn in self.flow_listeners:
            fn(reading)

    def _on_outcome(self, o: Outcome) -> None:
        """A result or a closed horizon: send the signal out again so screens show it."""
        if o.result == "open" or self.signals is None:
            return  # the signal itself is announced just after its outcome starts
        s = self.signals.store.get(o.signal_id)
        if s is not None:
            for fn in self.signal_listeners:
                fn(s)

    def _spot_before(self, index: str, before_ms: int) -> float | None:
        """Spot at the close of the last whole minute that ended by `before_ms`."""
        r = self.resolved.get(index)
        if r is None:
            return None
        for c in reversed(self.candles.closed(r.spot.instrument_key)):
            if c.minute_ts + MINUTE_MS <= before_ms:
                return c.close
        return None

    def _on_trade(self, t: PaperTrade) -> None:
        for fn in self.trade_listeners:
            fn(t)

    def _price(self, key: str) -> Price | None:
        ltp = self.prices.ltp.get(key)
        return None if ltp is None else Price(ltp, self.prices.ts[key])

    def _last_recorded(self, key: str, before_ms: int) -> Price | None:
        t = self.tick_store.last_tick_before(key, before_ms)
        return None if t is None else Price(t.ltp, t.ts)

    def feed_live(self) -> bool:
        """The index feed is delivering: connected, and an NSE tick arrived recently."""
        last = self.last_index_tick_ts
        if self.health().state != "connected" or last is None:
            return False
        return self.clock.now_ms() - last <= self.settings.feed_live_max_tick_age_ms

    def bullion_status(self) -> tuple[BullionState, int | None] | None:
        """MCX session state for the BULLION tab, and since when prices are stale.

        Display only (spec §6.6): it never stops signals or paper trades. None without bullion.
        """
        b = self.bullion
        if b is None:
            return None
        market: MarketStatus = self.mcx_clock.status()
        if market == "holiday":
            return "holiday", None
        if market != "live":
            return "closed", None
        last = b.last_tick_ts
        fresh = (
            self.health().state == "connected"
            and last is not None
            and self.clock.now_ms() - last <= self.settings.bullion_live_max_tick_age_ms
        )
        if fresh:
            return "live", None
        return "stale", b.gap_since or last

    # -- late start and outages --------------------------------------------

    async def _backfill(self) -> None:
        """Upstox only: today's candles and opening OI, so a late start is not a blind one.

        Every part may fail on its own; whatever is missing is logged and the app carries
        on, warming up from live data as it did before backfill existed.
        """
        if self.settings.feed_provider != "upstox" or self.auth is None:
            return
        token = self.auth.token
        if token is None or self.chains is None:
            return
        now = self.clock.now_ms()
        this_minute = now - now % MINUTE_MS
        open_ms, _ = self.clock.session_bounds()
        late = now > open_ms + MINUTE_MS
        today = self.clock.today()
        notes: list[str] = []
        async with httpx.AsyncClient(timeout=20, transport=self.http_transport) as client:
            for index, r in self.resolved.items():
                counts: list[str] = []
                for inst in (r.spot, r.future):
                    key = inst.instrument_key
                    try:
                        got = await fetch_intraday_candles(
                            client, token, key, before_ms=this_minute
                        )
                        candles = [c for c in got if c.minute_ts >= open_ms]
                        self.candle_store.write_many(candles)
                    except Exception as exc:
                        log.warning("candle backfill failed for %s: %s", key, type(exc).__name__)
                        candles = self.candle_store.read(key, open_ms, this_minute)
                        counts.append("failed")
                    self.candles.seed(key, candles)
                    counts.append(str(len(candles)))
                if self.bias is not None:
                    self.bias.warm(index)
                chain = self.chains.chains[index]
                if late:
                    chain.oi_baseline = "partial"  # until the snapshot says otherwise
                try:
                    snaps = await fetch_option_chain(
                        client, token, r.spot.instrument_key, r.options_expiry
                    )
                    legs = apply_baseline(chain, snaps)
                    counts.append(f"baseline={legs}/{len(chain.keys())}")
                except Exception as exc:
                    log.warning("OI baseline failed for %s: %s", index, type(exc).__name__)
                    counts.append("baseline=failed")
                try:
                    found = await fetch_52w_range(client, token, r.spot.instrument_key, today)
                    if found is not None:
                        self.range_52w[index] = found
                    counts.append("52w=ok" if found else "52w=empty")
                except Exception as exc:
                    log.warning("52-week range failed for %s: %s", index, type(exc).__name__)
                    counts.append("52w=failed")
                notes.append(f"{index} candles={'/'.join(counts[:-2])} {counts[-2]} {counts[-1]}")
        self.feed_log.write(epoch_ms_now(), "backfill", "; ".join(notes))
        log.info("backfill: %s", "; ".join(notes))

    async def _baseline_new_strikes(self, change: SubscriptionChange) -> None:
        """Strikes that entered the window on a re-centre need an opening OI too."""
        if self.settings.feed_provider != "upstox" or self.auth is None or self.chains is None:
            return
        token = self.auth.token
        chain = self.chains.chains.get(change.index)
        r = self.resolved.get(change.index)
        if token is None or chain is None or r is None:
            return
        try:
            async with httpx.AsyncClient(timeout=20, transport=self.http_transport) as client:
                snaps = await fetch_option_chain(
                    client, token, r.spot.instrument_key, r.options_expiry
                )
            apply_baseline(chain, snaps, only=set(change.add))
        except Exception as exc:
            chain.oi_baseline = "partial"
            log.warning("OI baseline for new strikes failed: %s", type(exc).__name__)

    def index_stats(self, index: str) -> IndexStats:
        """Day statistics for the details view (spec §7.4)."""
        r = self.resolved[index]
        spot_key = r.spot.instrument_key
        day_start = ist_to_ms(datetime.combine(self.clock.today(), time(0, 0), tzinfo=IST))
        day = [c for c in self.candles.closed(spot_key) if c.minute_ts >= day_start]
        forming = self.candles.current(spot_key)
        if forming is not None and forming.minute_ts >= day_start:
            day.append(forming)
        return compute_stats(
            index,
            spot=self.prices.ltp.get(spot_key),
            fut=self.prices.ltp.get(r.future.instrument_key),
            prev_close=self.prices.close_prev.get(spot_key),
            candles=day,
            range_52w=self.range_52w.get(index),
            vix=self.prices.ltp.get(VIX_KEY),
            vix_prev_close=self.prices.close_prev.get(VIX_KEY),
            updated_ts=self.prices.ts.get(spot_key),
            sectors=sector_quotes(
                self.settings.sector_indices.get(index, []),
                self.prices.ltp,
                self.prices.close_prev,
            ),
        )

    @property
    def bullion_keys(self) -> frozenset[str]:
        return self.bullion.keys if self.bullion is not None else frozenset()

    @property
    def macro_keys(self) -> frozenset[str]:
        return self.macro.keys if self.macro is not None else frozenset()

    def is_side_market(self, key: str) -> bool:
        """MCX and currency keys: never the index candles, index liveness or `ticks`.

        Judged by segment as well as by the trackers' keys, so a replayed MCX or currency
        tick whose tracker did not load still stays out of the index pipeline.
        """
        return (
            key.startswith(SIDE_MARKET_SEGMENTS)
            or key in self.bullion_keys
            or key in self.macro_keys
        )

    # -- macro evidence (spec §6.8, §8.6) ---------------------------------------

    def macro_view(self, minute_ts: int) -> dict[str, MacroSeries]:
        return build_view(
            self.macro,
            self.bullion,
            upto_minute_ts=minute_ts,
            now_ms=self.clock.now_ms(),
            max_age_ms=self.params().macro.max_age_seconds * 1000,
        )

    def index_macro(self, minute_ts: int) -> list[IndicatorResult]:
        """The index bias's macro group; nothing when neither tracker is loaded."""
        if self.macro is None and self.bullion is None:
            return []
        return index_macro_indicators(self.macro_view(minute_ts), self.params().macro)

    def bullion_macro(self, minute_ts: int) -> list[IndicatorResult]:
        """The bullion bias's macro group: the dollar; nothing without the currency feed."""
        if self.macro is None:
            return []
        return bullion_macro_indicators(self.macro_view(minute_ts), self.params().macro)

    async def _load_macro(self, today: date) -> MacroTracker | None:
        """Currency and crude contracts and today's candles; every step fails soft."""
        token = self.auth.token if self.auth is not None else None
        contracts = await macro_mod.load_macro_contracts(
            self.settings.data_dir, today, transport=self.http_transport
        )
        if not contracts or token is None:
            return None
        tracker = MacroTracker(contracts)
        try:
            async with httpx.AsyncClient(timeout=20, transport=self.http_transport) as client:
                await macro_mod.backfill(client, token, tracker, self.clock.now_ms())
        except Exception as exc:
            log.warning("macro backfill failed: %s", type(exc).__name__)
        return tracker

    async def _load_recorded_macro(self, day: date) -> MacroTracker | None:
        contracts = await macro_mod.recorded_macro_contracts(self.settings.data_dir, day)
        return MacroTracker(contracts) if contracts else None

    def attach_macro(self, tracker: MacroTracker) -> None:
        self.macro = tracker
        self.tick_bus.subscribe(tracker.on_tick)

    async def _load_bullion(self, today: date) -> BullionTracker | None:
        """Gold and silver contracts, their start-of-day data and today's candles (§6.6).

        Nothing here can stop the index feed: every step fails soft.
        """
        token = self.auth.token if self.auth is not None else None
        contracts = await bullion_mod.load_contracts(
            self.settings.data_dir, today, transport=self.http_transport
        )
        if not contracts or token is None:
            return None
        async with httpx.AsyncClient(timeout=20, transport=self.http_transport) as client:
            contracts = await bullion_mod.enrich(client, token, contracts, today)
            tracker = BullionTracker(contracts, on_candle=self._on_bullion_candle)
            await bullion_mod.backfill(client, token, tracker, self.clock.now_ms())
        return tracker

    async def _load_recorded_bullion(self, day: date) -> BullionTracker | None:
        """Replay: that day's contracts from its cached MCX file; no network, no backfill."""
        path = mcx_master_path(self.settings.data_dir, day)
        if not await asyncio.to_thread(path.exists):
            log.warning("no MCX instrument file for %s: bullion is not replayed", day)
            return None
        contracts = bullion_mod.contracts_from(
            await asyncio.to_thread(read_commodities, path, bullion_mod.METALS), day
        )
        if not contracts:
            return None
        return BullionTracker(contracts, on_candle=self._on_bullion_candle)

    def attach_bullion(self, tracker: BullionTracker) -> None:
        """Wire the bullion tracker and its trading desk onto the tick bus."""
        self.bullion = tracker
        self.tick_bus.subscribe(tracker.on_tick)
        # Stored keyed by the MCX key, so they survive a restart; never the shared builder.
        tracker.candles.on_close(self.candle_store.write)
        desk = BullionDesk(
            tracker=tracker,
            clock=self.mcx_clock,
            params=self.params,
            conn=self._conn,
            feed_live=self.bullion_live,
            enforce_hours=self.enforce_hours,
            price=self._price,
            last_recorded=self._last_recorded_bullion,
            on_bias=self._on_bias,
            on_signal=self._on_bullion_signal,
            on_trade=self._on_trade,
            config_version=self.config_version,
            macro=self.bullion_macro,
        )
        self.bullion_desk = desk
        self.tick_bus.subscribe(desk.on_tick)

    @functools.cached_property
    def bullion_tick_store(self) -> TickStore:
        return TickStore(self._conn, table="bullion_ticks")

    def _last_recorded_bullion(self, key: str, before_ms: int) -> Price | None:
        t = self.bullion_tick_store.last_tick_before(key, before_ms)
        return None if t is None else Price(t.ltp, t.ts)

    def bullion_live(self) -> bool:
        status = self.bullion_status()
        return status is not None and status[0] == "live"

    def _on_bullion_signal(self, s: Signal) -> None:
        """Bullion signals skip the outcome yardstick: it scores NSE spot moves."""
        for fn in self.signal_listeners:
            fn(s)

    def _on_bullion_candle(self, metal: str, c: Candle) -> None:
        for fn in self.bullion_candle_listeners:
            fn(metal, c)

    def expecting_ticks(self) -> bool:
        """Silence outside market hours is not an outage."""
        return not self.enforce_hours or self.clock.status() == "live"

    def _track_gap(self) -> None:
        """Record when the feed goes quiet during the session, and for how long."""
        self._track_bullion_gap()
        now = self.clock.now_ms()
        live = self.feed_live()
        if live:
            self._was_live = True
            if self.gap_since is not None:
                self.last_gap = (self.gap_since, now)
                self.feed_log.write(
                    epoch_ms_now(), "feed_gap_end", f"gap_ms={now - self.gap_since}"
                )
                log.warning("feed back after %.1f s", (now - self.gap_since) / 1000)
                self.gap_since = None
            return
        if self.gap_since is None:
            if not self._was_live or not self.expecting_ticks():
                return
            last = self.last_index_tick_ts
            self.gap_since = last if last is not None else now
            self.feed_log.write(epoch_ms_now(), "feed_gap_start", f"last_tick_ts={last}")
            log.warning("feed gap: no ticks since %s", last)
        elif not self.expecting_ticks():
            # The market closed during the outage; nothing more will come today.
            self.feed_log.write(epoch_ms_now(), "feed_gap_end", "market_closed")
            self.gap_since = None
            self._was_live = False

    def _track_bullion_gap(self) -> None:
        """Log MCX outages to `feed_events`. Nothing else reacts: bullion is display only."""
        b = self.bullion
        status = self.bullion_status()
        if b is None or status is None:
            return
        state = status[0]
        if state == "live":
            b.was_live = True
            if b.gap_since is not None:
                gap = self.clock.now_ms() - b.gap_since
                self.feed_log.write(epoch_ms_now(), "bullion_gap_end", f"gap_ms={gap}")
                b.gap_since = None
        elif state == "stale":
            if b.gap_since is None and b.was_live:
                last = b.last_tick_ts
                b.gap_since = last if last is not None else self.clock.now_ms()
                if self.bullion_desk is not None:
                    self.bullion_desk.paper.mark_gap()
                self.feed_log.write(epoch_ms_now(), "bullion_gap_start", f"last_tick_ts={last}")
        else:  # MCX closed: an outage in progress ends with the session
            if b.gap_since is not None:
                self.feed_log.write(epoch_ms_now(), "bullion_gap_end", "market_closed")
            b.gap_since = None
            b.was_live = False

    async def _apply_subscription_changes(self) -> None:
        while True:
            change = await self._sub_changes.get()
            if self.provider is None:
                continue
            if change.add:
                await self.provider.subscribe(change.add)
            if change.remove:
                await self.provider.unsubscribe(change.remove)
            if change.add:
                await self._baseline_new_strikes(change)
            self.feed_log.write(
                epoch_ms_now(),
                "recentre",
                f"{change.index} +{len(change.add)} -{len(change.remove)}",
            )

    async def _housekeeping(self) -> None:
        last_minute = None
        while True:
            await asyncio.sleep(0.5)
            self.tick_store.flush()
            self.bullion_tick_store.flush()
            self.candles.flush_stale(self.clock.now_ms())
            if self.bullion is not None:
                self.bullion.candles.flush_stale(self.clock.now_ms())
            if self.bullion_desk is not None:
                for lag in self.bullion_desk.housekeeping(self.clock.now_ms()):
                    self.latency.record("bullion_eval_lag", lag, at_ms=epoch_ms_now())
            for engine in (self.signals, self.shadow_signals):
                if engine is not None:
                    engine.tick(self.clock.now_ms())
            if self.paper is not None:
                self.paper.tick(self.clock.now_ms())
            if self.outcomes is not None:
                self.outcomes.tick(self.clock.now_ms())
            self._track_gap()
            await self._publish_health()
            minute = epoch_ms_now() // 60_000
            if minute != last_minute:
                last_minute = minute
                self.latency.persist_minute(self._conn, minute * 60_000)

    async def _publish_health(self) -> None:
        if self.provider is None:
            return
        h = self.provider.health()
        # Anything the status banner depends on counts as a change worth pushing.
        key = (
            h.state,
            h.subscribed,
            h.reconnects,
            self.feed_live(),
            self.clock.status(),
            self.gap_since,
            self.bullion_status(),
            self.auth.state() if self.auth is not None else None,
        )
        if key != self._health_key:
            self._health_key = key
            self._last_health = h
            await self.events.publish(
                FeedHealthChanged(h.state, h.last_tick_ts, h.reconnects, h.subscribed, h.provider)
            )

    def health(self) -> FeedHealth:
        if self.provider is None:
            return FeedHealth("disconnected", None, 0, 0, self.settings.feed_provider)
        return self.provider.health()

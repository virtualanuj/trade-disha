"""Owns the provider, subscriptions, candles, chains, the bias engine and tick fan-out."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time

import httpx

from tradedisha.auth import AuthService
from tradedisha.clock import IST, DrivenClock, MarketClock, epoch_ms_now, ist_to_ms
from tradedisha.config import Settings, hours_enforced
from tradedisha.engine.bias_engine import BiasComputed, BiasEngine
from tradedisha.engine.paper import PaperTrade, PaperTradeManager, Price
from tradedisha.engine.signals import Signal, SignalEngine
from tradedisha.events import EventBus, FeedHealthChanged
from tradedisha.feed.bus import StampedTick, TickBus
from tradedisha.feed.provider import FeedHealth, MarketDataProvider, Tick
from tradedisha.feed.replay import ReplayProvider
from tradedisha.feed.synthetic import SyntheticProvider, SyntheticUniverse
from tradedisha.feed.upstox import UpstoxProvider, fetch_ltp
from tradedisha.instruments.models import Instrument, ResolvedIndex
from tradedisha.instruments.resolve import INDEX_SPOT_NAMES, ResolutionError, resolve_index
from tradedisha.instruments.synthetic_master import SPEC, build_synthetic_master
from tradedisha.instruments.upstox_master import load_upstox_master, master_path, read_master
from tradedisha.market.backfill import (
    apply_baseline,
    fetch_52w_range,
    fetch_intraday_candles,
    fetch_option_chain,
)
from tradedisha.market.candles import MINUTE_MS, Candle, CandleBuilder, CandleStore
from tradedisha.market.chain_manager import ChainManager, SubscriptionChange
from tradedisha.market.stats import VIX_KEY, IndexStats, compute_stats
from tradedisha.metrics.latency import LatencyTracker
from tradedisha.parameters.model import ParameterSet
from tradedisha.store.ticks import FeedEventLog, TickStore

log = logging.getLogger(__name__)


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


class FeedSession:
    """Start -> resolve instruments -> connect provider -> subscribe -> pump ticks -> stop."""

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
        self._prev_tick_ts: int | None = None
        self._health_key: tuple[object, ...] | None = None
        self._start_lock = asyncio.Lock()
        self.clock = clock
        self.events = bus
        self.latency = latency
        self.params = params
        self.tick_bus = TickBus()
        self.tick_store = TickStore(conn)
        self.feed_log = FeedEventLog(conn)
        self.prices = LatestPrices()
        self.master: list[Instrument] = []
        self.resolved: dict[str, ResolvedIndex] = {}
        self.candles = CandleBuilder()
        self.candle_store = CandleStore(conn)
        self.chains: ChainManager | None = None
        self.bias: BiasEngine | None = None
        self.signals: SignalEngine | None = None
        self.paper: PaperTradeManager | None = None
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
        )
        enforce = self.enforce_hours
        self.signals = SignalEngine(
            clock=self.clock,
            params=self.params,
            resolved=self.resolved,
            chains=self.chains.chains,
            conn=self._conn,
            feed_live=self.feed_live,
            enforce_hours=enforce,
            market_open=self.settings.market_open,
            market_close=self.settings.market_close,
            risk_free_rate=self.settings.risk_free_rate,
            on_signal=self._on_signal,
        )
        self.bias_listeners.append(self.signals.on_bias)
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
        self.provider = self._build_provider()
        await self.provider.connect()
        keys = [k for r in self.resolved.values() for k in r.all_keys]
        if self.settings.feed_provider != "synthetic":  # the generated market has no VIX
            keys.append(VIX_KEY)
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
        await self._publish_health()

    def _on_tick(self, st: StampedTick) -> None:
        t = st.tick
        prev = self._prev_tick_ts
        if prev is None or t.ts > prev:
            self._prev_tick_ts = t.ts
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
        for fn in self.signal_listeners:
            fn(s)

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
        h = self.health()
        if h.state != "connected" or h.last_tick_ts is None:
            return False
        return self.clock.now_ms() - h.last_tick_ts <= self.settings.feed_live_max_tick_age_ms

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
        )

    def expecting_ticks(self) -> bool:
        """Silence outside market hours is not an outage."""
        return not self.enforce_hours or self.clock.status() == "live"

    def _track_gap(self) -> None:
        """Record when the feed goes quiet during the session, and for how long."""
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
            last = self.health().last_tick_ts
            self.gap_since = last if last is not None else now
            self.feed_log.write(epoch_ms_now(), "feed_gap_start", f"last_tick_ts={last}")
            log.warning("feed gap: no ticks since %s", last)
        elif not self.expecting_ticks():
            # The market closed during the outage; nothing more will come today.
            self.feed_log.write(epoch_ms_now(), "feed_gap_end", "market_closed")
            self.gap_since = None
            self._was_live = False

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
            self.candles.flush_stale(self.clock.now_ms())
            if self.signals is not None:
                self.signals.tick(self.clock.now_ms())
            if self.paper is not None:
                self.paper.tick(self.clock.now_ms())
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

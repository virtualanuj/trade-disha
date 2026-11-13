"""Owns the provider, subscriptions, candles, chains, the bias engine and tick fan-out."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import httpx

from tradedisha.auth import AuthService
from tradedisha.clock import DrivenClock, MarketClock, epoch_ms_now
from tradedisha.config import Settings
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
from tradedisha.market.candles import Candle, CandleBuilder, CandleStore
from tradedisha.market.chain_manager import ChainManager, SubscriptionChange
from tradedisha.metrics.latency import LatencyTracker
from tradedisha.parameters.model import ParameterSet
from tradedisha.store.ticks import FeedEventLog, TickStore

log = logging.getLogger(__name__)


@dataclass
class LatestPrices:
    """Last LTP and timestamp per instrument key; what the WS hub reads."""

    ltp: dict[str, float] = field(default_factory=dict)
    ts: dict[str, int] = field(default_factory=dict)

    def update(self, t: Tick) -> None:
        self.ltp[t.key] = t.ltp
        self.ts[t.key] = t.ts


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
        enforce = self.settings.enforce_signal_hours
        if enforce is None:
            enforce = self.settings.feed_provider != "synthetic"
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
        self.provider = self._build_provider()
        await self.provider.connect()
        keys = [k for r in self.resolved.values() for k in r.all_keys]
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
                self.tick_store, day, speed=s.replay_speed, clock=self._driven_clock
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

    async def _apply_subscription_changes(self) -> None:
        while True:
            change = await self._sub_changes.get()
            if self.provider is None:
                continue
            if change.add:
                await self.provider.subscribe(change.add)
            if change.remove:
                await self.provider.unsubscribe(change.remove)
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
            await self._publish_health()
            minute = epoch_ms_now() // 60_000
            if minute != last_minute:
                last_minute = minute
                self.latency.persist_minute(self._conn, minute * 60_000)

    async def _publish_health(self) -> None:
        if self.provider is None:
            return
        h = self.provider.health()
        changed = self._last_health is None or (h.state, h.subscribed, h.reconnects) != (
            self._last_health.state,
            self._last_health.subscribed,
            self._last_health.reconnects,
        )
        if changed:
            self._last_health = h
            await self.events.publish(
                FeedHealthChanged(h.state, h.last_tick_ts, h.reconnects, h.subscribed, h.provider)
            )

    def health(self) -> FeedHealth:
        if self.provider is None:
            return FeedHealth("disconnected", None, 0, 0, self.settings.feed_provider)
        return self.provider.health()

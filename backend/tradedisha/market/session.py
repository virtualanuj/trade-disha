"""Owns the provider, the subscription set, and the tick fan-out for one process."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import date

from tradedisha.clock import DrivenClock, MarketClock, epoch_ms_now
from tradedisha.config import Settings
from tradedisha.events import EventBus, FeedHealthChanged
from tradedisha.feed.bus import StampedTick, TickBus
from tradedisha.feed.provider import FeedHealth, MarketDataProvider, Tick
from tradedisha.feed.replay import ReplayProvider
from tradedisha.feed.synthetic import SyntheticProvider
from tradedisha.instruments.models import ResolvedIndex
from tradedisha.instruments.resolve import resolve_index
from tradedisha.instruments.synthetic_master import SPEC, build_synthetic_master
from tradedisha.metrics.latency import LatencyTracker
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


class FeedSession:
    """Start → resolve instruments → connect provider → subscribe → pump ticks → stop."""

    def __init__(
        self,
        settings: Settings,
        conn: sqlite3.Connection,
        clock: MarketClock,
        *,
        bus: EventBus,
        latency: LatencyTracker,
        driven_clock: DrivenClock | None = None,
    ) -> None:
        self.settings = settings
        self.clock = clock
        self.events = bus
        self.latency = latency
        self.tick_bus = TickBus()
        self.tick_store = TickStore(conn)
        self.feed_log = FeedEventLog(conn)
        self.prices = LatestPrices()
        self.resolved: dict[str, ResolvedIndex] = {}
        self.provider: MarketDataProvider | None = None
        self.replay_day: date | None = None
        self._driven_clock = driven_clock
        self._conn = conn
        self._tasks: list[asyncio.Task[None]] = []
        self._last_health: FeedHealth | None = None
        self.tick_bus.subscribe(self._on_tick)

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        today = self.clock.today()
        master = build_synthetic_master(today)
        for index in self.settings.indices:
            base = float(SPEC[index]["base"])
            self.resolved[index] = resolve_index(
                master, index, today, base, strike_window=self.settings.strike_window
            )
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

    def _build_provider(self) -> MarketDataProvider:
        s = self.settings
        if s.feed_provider == "synthetic":
            return SyntheticProvider(
                list(self.resolved.values()),
                ticks_per_second=s.synthetic_ticks_per_second,
                seed=s.synthetic_seed,
                clock_ms=self.clock.now_ms,
            )
        if s.feed_provider == "replay":
            days = self.tick_store.recorded_days()
            if s.replay_date:
                day = date.fromisoformat(s.replay_date)
            elif days:
                day = days[0]
            else:
                raise RuntimeError("replay requested but no recorded ticks exist")
            self.replay_day = day
            return ReplayProvider(
                self.tick_store, day, speed=s.replay_speed, clock=self._driven_clock
            )
        raise RuntimeError("upstox provider needs an account and is not implemented yet")

    async def _pump(self) -> None:
        assert self.provider is not None
        async for tick in self.provider.ticks():
            t_in = epoch_ms_now()
            self.tick_bus.publish(StampedTick(tick, t_in))
        await self._publish_health()

    def _on_tick(self, st: StampedTick) -> None:
        self.prices.update(st.tick)
        if self.settings.feed_provider != "replay":
            self.tick_store.add(st.tick)
            self.latency.record("src_to_in", st.t_in - st.tick.ts, at_ms=st.t_in)

    async def _housekeeping(self) -> None:
        last_minute = None
        while True:
            await asyncio.sleep(0.5)
            self.tick_store.flush()
            await self._publish_health()
            minute = epoch_ms_now() // 60_000
            if minute != last_minute:
                last_minute = minute
                self.latency.persist_minute(self._conn, minute * 60_000)

    async def _publish_health(self) -> None:
        if self.provider is None:
            return
        h = self.provider.health()
        changed = self._last_health is None or (
            h.state,
            h.subscribed,
            h.reconnects,
        ) != (self._last_health.state, self._last_health.subscribed, self._last_health.reconnects)
        if changed:
            self._last_health = h
            await self.events.publish(
                FeedHealthChanged(h.state, h.last_tick_ts, h.reconnects, h.subscribed, h.provider)
            )

    def health(self) -> FeedHealth:
        if self.provider is None:
            return FeedHealth("disconnected", None, 0, 0, self.settings.feed_provider)
        return self.provider.health()

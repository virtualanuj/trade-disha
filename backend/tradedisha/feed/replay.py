"""Replays recorded ticks from the database, driving the market clock as it goes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import date

from tradedisha.clock import DrivenClock
from tradedisha.feed.provider import FeedHealth, Tick
from tradedisha.store.ticks import TickStore


class ReplayProvider:
    """`speed` is a multiple of real time; 0 means as fast as possible."""

    name = "replay"

    def __init__(
        self,
        store: TickStore,
        day: date,
        *,
        speed: float = 1.0,
        clock: DrivenClock | None = None,
        drop_ranges: list[tuple[int, int]] | None = None,
    ) -> None:
        self._store = store
        self._day = day
        self._speed = speed
        self._clock = clock
        self._drop = drop_ranges or []
        self._subscribed: set[str] = set()
        self._closed = False
        self._last_ts: int | None = None
        self._state = "disconnected"
        self.emitted = 0

    async def connect(self) -> None:
        self._state = "connected"

    async def subscribe(self, keys: list[str]) -> None:
        self._subscribed.update(keys)

    async def unsubscribe(self, keys: list[str]) -> None:
        self._subscribed.difference_update(keys)

    async def close(self) -> None:
        self._closed = True
        self._state = "disconnected"

    def health(self) -> FeedHealth:
        return FeedHealth(
            self._state,  # type: ignore[arg-type]
            self._last_ts,
            0,
            len(self._subscribed),
            self.name,
        )

    def _dropped(self, ts: int) -> bool:
        return any(lo <= ts < hi for lo, hi in self._drop)

    async def ticks(self) -> AsyncIterator[Tick]:
        rows = self._store.read_day(self._day)
        prev_ts: int | None = None
        for tick in rows:
            if self._closed:
                return
            if self._subscribed and tick.key not in self._subscribed:
                continue
            if self._speed > 0 and prev_ts is not None and tick.ts > prev_ts:
                await asyncio.sleep((tick.ts - prev_ts) / 1000 / self._speed)
            elif self.emitted % 200 == 0:
                await asyncio.sleep(0)  # let other tasks run during fast replay
            prev_ts = tick.ts
            if self._clock is not None:
                self._clock.set_ms(tick.ts)
            if self._dropped(tick.ts):
                continue
            self._last_ts = tick.ts
            self.emitted += 1
            yield tick
        self._state = "disconnected"

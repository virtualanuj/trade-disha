"""A random-walk market-data source for development and tests.

Spot indices follow a mean-reverting random walk; futures track spot plus a small basis;
options are priced from intrinsic value plus a time-value term that shrinks with
moneyness, so the chain looks plausible on screen. Nothing here is a model of the market.
"""

from __future__ import annotations

import asyncio
import math
import random
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from tradedisha.clock import epoch_ms_now
from tradedisha.feed.provider import FeedHealth, Tick
from tradedisha.instruments.models import ResolvedIndex


@dataclass
class _Underlying:
    price: float
    anchor: float
    vol_per_tick: float
    volume: int = 0
    fut_key: str = ""
    options: list[tuple[str, float, str]] = field(default_factory=list)  # key, strike, CE/PE
    oi: dict[str, int] = field(default_factory=dict)


class SyntheticProvider:
    """Emits ticks for every subscribed key at roughly `ticks_per_second` per instrument."""

    name = "synthetic"

    def __init__(
        self,
        resolved: list[ResolvedIndex],
        *,
        ticks_per_second: float = 2.0,
        seed: int | None = None,
        clock_ms: Callable[[], int] = epoch_ms_now,
    ) -> None:
        self._rng = random.Random(seed)
        self._interval = 1.0 / max(ticks_per_second, 0.01)
        self._clock_ms = clock_ms
        self._subscribed: set[str] = set()
        self._state: FeedHealth = FeedHealth("disconnected", None, 0, 0, self.name)
        self._last_ts: int | None = None
        self._closed = False
        self._under: dict[str, _Underlying] = {}
        self._key_owner: dict[str, tuple[str, str]] = {}  # key -> (index, role)
        for r in resolved:
            u = _Underlying(
                price=r.atm, anchor=r.atm, vol_per_tick=r.strike_step * 0.004, fut_key=""
            )
            u.fut_key = r.future.instrument_key
            self._key_owner[r.spot.instrument_key] = (r.index, "spot")
            self._key_owner[r.future.instrument_key] = (r.index, "fut")
            for pair in r.strikes:
                u.options.append((pair.ce.instrument_key, pair.strike, "CE"))
                u.options.append((pair.pe.instrument_key, pair.strike, "PE"))
                for k in (pair.ce.instrument_key, pair.pe.instrument_key):
                    self._key_owner[k] = (r.index, "opt")
                    u.oi[k] = self._rng.randint(50_000, 2_000_000)
            self._under[r.index] = u
            self._under[r.index].options = u.options

    # -- provider protocol -------------------------------------------------

    async def connect(self) -> None:
        self._set_state("connected")

    async def subscribe(self, keys: list[str]) -> None:
        self._subscribed.update(k for k in keys if k in self._key_owner)
        self._set_state(self._state.state)

    async def unsubscribe(self, keys: list[str]) -> None:
        self._subscribed.difference_update(keys)
        self._set_state(self._state.state)

    async def close(self) -> None:
        self._closed = True
        self._set_state("disconnected")

    def health(self) -> FeedHealth:
        return FeedHealth(
            self._state.state,
            self._last_ts,
            self._state.reconnects,
            len(self._subscribed),
            self.name,
        )

    def _is_closed(self) -> bool:
        return self._closed

    async def ticks(self) -> AsyncIterator[Tick]:
        while not self._is_closed():
            if not self._subscribed:
                await asyncio.sleep(self._interval)
                continue
            keys = list(self._subscribed)
            self._rng.shuffle(keys)
            # Spread this round's ticks evenly across the interval.
            gap = self._interval / len(keys)
            for key in keys:
                yield self._make_tick(key)
                await asyncio.sleep(gap)
                if self._is_closed():
                    return

    # -- internals ---------------------------------------------------------

    def _set_state(self, state: str) -> None:
        self._state = FeedHealth(
            state,  # type: ignore[arg-type]
            self._last_ts,
            self._state.reconnects,
            len(self._subscribed),
            self.name,
        )

    def _make_tick(self, key: str) -> Tick:
        index, role = self._key_owner[key]
        u = self._under[index]
        ts = int(self._clock_ms())
        self._last_ts = ts
        if role == "spot":
            u.price = self._step(u)
            return Tick(key=key, ts=ts, ltp=round(u.price, 2))
        if role == "fut":
            basis = u.anchor * 0.0015
            u.volume += self._rng.randint(50, 400)
            ltp = round(u.price + basis + self._rng.uniform(-1, 1), 2)
            return Tick(key=key, ts=ts, ltp=ltp, volume=u.volume, oi=u.oi.get(key))
        strike, kind = next((s, k) for kk, s, k in u.options if kk == key)
        ltp = self._option_price(u.price, strike, kind, u.anchor)
        u.oi[key] = max(0, u.oi[key] + self._rng.randint(-2_000, 2_500))
        iv = round(12 + 6 * abs(strike - u.price) / u.anchor * 100, 2)
        return Tick(
            key=key,
            ts=ts,
            ltp=ltp,
            oi=u.oi[key],
            bid=round(ltp - 0.05, 2),
            ask=round(ltp + 0.05, 2),
            iv=iv,
        )

    def _step(self, u: _Underlying) -> float:
        pull = (u.anchor - u.price) * 0.002
        return u.price + pull + self._rng.gauss(0, u.vol_per_tick)

    def _option_price(self, spot: float, strike: float, kind: str, anchor: float) -> float:
        intrinsic = max(0.0, spot - strike) if kind == "CE" else max(0.0, strike - spot)
        dist = abs(spot - strike) / anchor
        time_value = anchor * 0.006 * math.exp(-((dist * 100) ** 2) / 2)
        noise = self._rng.uniform(-0.5, 0.5)
        return round(max(0.05, intrinsic + time_value + noise) * 20) / 20

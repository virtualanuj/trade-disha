"""A random-walk market-data source for development and tests.

Spot indices follow a mean-reverting random walk; futures track spot plus a small basis;
options are priced from intrinsic value plus a time-value term that shrinks with
moneyness, so the chain looks plausible on screen. Nothing here is a model of the market.

The provider knows the whole listed chain at the resolved expiry (not just the subscribed
window) so re-centring can subscribe strikes that were not in the initial window.
"""

from __future__ import annotations

import asyncio
import math
import random
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from tradedisha.clock import epoch_ms_now
from tradedisha.feed.provider import FeedHealth, FeedState, Tick
from tradedisha.instruments.models import Instrument, ResolvedIndex


@dataclass(frozen=True)
class SyntheticUniverse:
    """Everything the generator needs to know about one index."""

    index: str
    spot_key: str
    fut_key: str
    anchor: float
    step: float
    options: tuple[tuple[str, float, str], ...]  # (key, strike, CE|PE)

    @classmethod
    def from_master(cls, master: list[Instrument], r: ResolvedIndex) -> SyntheticUniverse:
        opts = tuple(
            (i.instrument_key, float(i.strike), i.instrument_type)
            for i in master
            if i.name == r.index
            and i.instrument_type in ("CE", "PE")
            and i.expiry == r.options_expiry
            and i.strike is not None
        )
        return cls(
            r.index, r.spot.instrument_key, r.future.instrument_key, r.atm, r.strike_step, opts
        )

    @classmethod
    def from_resolved(cls, r: ResolvedIndex) -> SyntheticUniverse:
        """Window-only universe; enough for tests that never re-centre."""
        opts = tuple(
            (leg.instrument_key, p.strike, kind)
            for p in r.strikes
            for leg, kind in ((p.ce, "CE"), (p.pe, "PE"))
        )
        return cls(
            r.index, r.spot.instrument_key, r.future.instrument_key, r.atm, r.strike_step, opts
        )


@dataclass
class _Underlying:
    price: float
    anchor: float
    vol_per_tick: float
    drift: float = 0.0
    volume: int = 0
    oi: dict[str, int] = field(default_factory=dict)


class SyntheticProvider:
    """Emits ticks for every subscribed key at roughly `ticks_per_second` per instrument."""

    name = "synthetic"

    def __init__(
        self,
        universes: list[SyntheticUniverse],
        *,
        ticks_per_second: float = 2.0,
        seed: int | None = None,
        clock_ms: Callable[[], int] = epoch_ms_now,
        trend_per_tick: float = 0.0,
    ) -> None:
        self._rng = random.Random(seed)
        self._interval = 1.0 / max(ticks_per_second, 0.01)
        self._clock_ms = clock_ms
        self._subscribed: set[str] = set()
        self._state: FeedState = "disconnected"
        self._last_ts: int | None = None
        self._closed = False
        self._under: dict[str, _Underlying] = {}
        self._key_owner: dict[str, tuple[str, str]] = {}  # key -> (index, role)
        self._opt_meta: dict[str, tuple[float, str]] = {}  # key -> (strike, kind)
        for u in universes:
            under = _Underlying(
                price=u.anchor,
                anchor=u.anchor,
                vol_per_tick=u.step * 0.004,
                drift=trend_per_tick * u.step,
            )
            self._key_owner[u.spot_key] = (u.index, "spot")
            self._key_owner[u.fut_key] = (u.index, "fut")
            for key, strike, kind in u.options:
                self._key_owner[key] = (u.index, "opt")
                self._opt_meta[key] = (strike, kind)
                under.oi[key] = self._rng.randint(50_000, 2_000_000)
            self._under[u.index] = under

    # -- provider protocol -------------------------------------------------

    async def connect(self) -> None:
        self._state = "connected"

    async def subscribe(self, keys: list[str]) -> None:
        unknown = [k for k in keys if k not in self._key_owner]
        if unknown:
            raise KeyError(f"unknown instrument keys: {unknown[:3]}")
        self._subscribed.update(keys)

    async def unsubscribe(self, keys: list[str]) -> None:
        self._subscribed.difference_update(keys)

    async def close(self) -> None:
        self._closed = True
        self._state = "disconnected"

    def health(self) -> FeedHealth:
        return FeedHealth(self._state, self._last_ts, 0, len(self._subscribed), self.name)

    def _is_closed(self) -> bool:
        return self._closed

    async def ticks(self) -> AsyncIterator[Tick]:
        while not self._is_closed():
            if not self._subscribed:
                await asyncio.sleep(self._interval)
                continue
            keys = list(self._subscribed)
            self._rng.shuffle(keys)
            gap = self._interval / len(keys)
            for key in keys:
                if key not in self._subscribed:
                    continue  # unsubscribed mid-round
                yield self._make_tick(key)
                await asyncio.sleep(gap)
                if self._is_closed():
                    return

    # -- internals ---------------------------------------------------------

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
            return Tick(key=key, ts=ts, ltp=ltp, volume=u.volume)
        strike, kind = self._opt_meta[key]
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
        pull = (u.anchor - u.price) * 0.002 if u.drift == 0 else 0.0
        return u.price + pull + u.drift + self._rng.gauss(0, u.vol_per_tick)

    def _option_price(self, spot: float, strike: float, kind: str, anchor: float) -> float:
        intrinsic = max(0.0, spot - strike) if kind == "CE" else max(0.0, strike - spot)
        dist = abs(spot - strike) / anchor
        time_value = anchor * 0.006 * math.exp(-((dist * 100) ** 2) / 2)
        noise = self._rng.uniform(-0.5, 0.5)
        return round(max(0.05, intrinsic + time_value + noise) * 20) / 20

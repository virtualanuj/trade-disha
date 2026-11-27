"""The chart's other intervals (E27): 10 s and 30 s bars built from ticks, 5 m bars from the
1-minute candles, and the chart's lines over each. Display only: the bias, signals and
paper trades read the 1-minute candles alone (spec §7.1).

Each chart is a name (an index or a metal) with a price key and a volume key: an index's
spot and its near future (whose VWAP and net volume the chart shows), a metal's near
future for both. Only those keys are read, so side markets never reach the index candles.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.indicators.chart import ChartPoint, aggregate, overlay_series
from tradedisha.market.candles import MINUTE_MS, Candle, CandleBuilder
from tradedisha.parameters.model import ParameterSet

Interval = Literal["10s", "30s", "1m", "5m"]
Role = Literal["price", "vol"]
INTERVALS: dict[str, int] = {"10s": 10_000, "30s": 30_000, "1m": MINUTE_MS, "5m": 5 * MINUTE_MS}
FIVE_MIN = INTERVALS["5m"]
# a full MCX day (09:00 to 23:30) of each
_CAPS = {"10s": 5_400, "30s": 1_800}


@dataclass(frozen=True)
class ChartBar:
    """One closed bar, for the `chart_bar` frame; `overlay` on price bars only."""

    name: str
    interval: Interval
    role: Role
    candle: Candle
    overlay: ChartPoint | None


@dataclass(frozen=True)
class _Chart:
    price_key: str
    vol_key: str


class ChartBars:
    def __init__(
        self,
        params: Callable[[], ParameterSet],
        minutes: Callable[[str], list[Candle]],
        emit: Callable[[ChartBar], None],
    ) -> None:
        self._params = params
        self._minutes = minutes  # a key's closed 1-minute candles
        self._emit = emit
        self._charts: dict[str, _Chart] = {}
        self._roles: dict[str, list[tuple[str, Role]]] = {}
        self._seeding = False
        self._builders: dict[str, CandleBuilder] = {
            "10s": self._builder("10s"),
            "30s": self._builder("30s"),
        }

    def _builder(self, interval: Interval) -> CandleBuilder:
        b = CandleBuilder(bar_ms=INTERVALS[interval], max_history=_CAPS[interval])
        b.on_close(lambda c: self._closed(interval, c))
        return b

    def add(self, name: str, price_key: str, vol_key: str) -> None:
        self._charts[name] = _Chart(price_key, vol_key)
        for key, role in ((price_key, "price"), (vol_key, "vol")):
            self._roles.setdefault(key, []).append((name, role))  # type: ignore[arg-type]

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(self._roles)

    # -- input -----------------------------------------------------------------------

    def on_tick(self, st: StampedTick) -> None:
        if st.tick.key in self._roles:
            for b in self._builders.values():
                b.apply(st.tick)

    def seed(self, ticks: Iterable[Tick]) -> None:
        """Replay stored ticks (oldest first) so a restart keeps the day; nothing is sent."""
        self._seeding = True
        try:
            for t in ticks:
                if t.key in self._roles:
                    for b in self._builders.values():
                        b.apply(t)
        finally:
            self._seeding = False

    def flush_stale(self, now_ms: int) -> None:
        for b in self._builders.values():
            b.flush_stale(now_ms)

    def on_minute_close(self, c: Candle) -> None:
        """A 1-minute candle closed: send the 5-minute bar it completes, if it does."""
        if c.key not in self._roles or (c.minute_ts + MINUTE_MS) % FIVE_MIN:
            return
        block = [
            m for m in self._minutes(c.key) if m.minute_ts // FIVE_MIN == c.minute_ts // FIVE_MIN
        ]
        if block:
            self._closed("5m", aggregate(block, FIVE_MIN)[-1])

    # -- queries -----------------------------------------------------------------------

    def bars(self, name: str, interval: str) -> tuple[list[Candle], list[Candle], list[ChartPoint]]:
        """Closed price bars, closed volume bars and the lines at each price bar."""
        chart = self._charts[name]
        price = self._series(chart.price_key, interval)
        vol = price if chart.vol_key == chart.price_key else self._series(chart.vol_key, interval)
        return price, vol, overlay_series(price, vol, self._params().trend)

    def _series(self, key: str, interval: str) -> list[Candle]:
        if interval in self._builders:
            return self._builders[interval].closed(key)
        minutes = self._minutes(key)
        if interval == "1m" or not minutes:
            return minutes
        # only whole 5-minute blocks: the last one is still forming until its fifth minute
        end = (minutes[-1].minute_ts + MINUTE_MS) // FIVE_MIN * FIVE_MIN
        return aggregate([m for m in minutes if m.minute_ts < end], FIVE_MIN)

    # -- output ------------------------------------------------------------------------

    def _closed(self, interval: Interval, c: Candle) -> None:
        if self._seeding:
            return
        for name, role in self._roles.get(c.key, []):
            overlay = None
            if role == "price":
                _, _, lines = self.bars(name, interval)
                overlay = lines[-1] if lines and lines[-1].minute_ts == c.minute_ts else None
            self._emit(ChartBar(name, interval, role, c, overlay))

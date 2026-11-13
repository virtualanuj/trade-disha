"""Day statistics for one index, for the details view. Spec §7.4.

Display only: no indicator, signal or paper trade reads these.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from tradedisha.market.candles import Candle

VIX_KEY = "NSE_INDEX|India VIX"


@dataclass(frozen=True)
class IndexStats:
    index: str
    day_open: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    range_pos: float | None = None  # 0 at the day's low, 1 at the day's high
    prev_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    fut_premium: float | None = None  # futures LTP minus spot LTP
    vix: float | None = None
    vix_change_pct: float | None = None
    updated_ts: int | None = None


def _pct(value: float | None, base: float | None) -> float | None:
    if value is None or not base:
        return None
    return round((value - base) / base * 100, 2)


def compute_stats(  # noqa: PLR0913 -- one argument per source of the view
    index: str,
    *,
    spot: float | None,
    fut: float | None,
    prev_close: float | None,
    candles: Iterable[Candle],
    range_52w: tuple[float, float] | None,
    vix: float | None,
    vix_prev_close: float | None,
    updated_ts: int | None,
) -> IndexStats:
    """`candles` are today's spot candles in time order, the forming one last.

    `range_52w` is (high, low) for the year up to yesterday; today's extremes widen it, so
    a new 52-week high or low shows the moment it is made.
    """
    day = list(candles)
    day_open = day[0].open if day else None
    day_high = max((c.high for c in day), default=None)
    day_low = min((c.low for c in day), default=None)
    if spot is not None:  # the latest tick may be ahead of the candle being formed
        day_high = spot if day_high is None else max(day_high, spot)
        day_low = spot if day_low is None else min(day_low, spot)

    range_pos = None
    if spot is not None and day_high is not None and day_low is not None and day_high > day_low:
        range_pos = round((spot - day_low) / (day_high - day_low), 4)

    high_52w = low_52w = None
    if range_52w is not None:
        high_52w, low_52w = range_52w
        if day_high is not None:
            high_52w = max(high_52w, day_high)
        if day_low is not None:
            low_52w = min(low_52w, day_low)

    return IndexStats(
        index=index,
        day_open=day_open,
        day_high=day_high,
        day_low=day_low,
        range_pos=range_pos,
        prev_close=prev_close,
        change=round(spot - prev_close, 2) if spot is not None and prev_close else None,
        change_pct=_pct(spot, prev_close),
        high_52w=high_52w,
        low_52w=low_52w,
        fut_premium=round(fut - spot, 2) if fut is not None and spot is not None else None,
        vix=vix,
        vix_change_pct=_pct(vix, vix_prev_close),
        updated_ts=updated_ts,
    )

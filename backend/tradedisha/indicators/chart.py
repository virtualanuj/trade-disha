"""The chart at other intervals (E27): 5-minute bars from 1-minute candles, and the chart's
lines worked out over a whole series of bars. Pure; display only, never the bias."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from tradedisha.indicators.series import ema, supertrend, vwap_series
from tradedisha.market.candles import Candle
from tradedisha.parameters.model import Trend


@dataclass(frozen=True)
class ChartPoint:
    """The chart's lines at one bar: the same fields as the bias engine's overlay point."""

    minute_ts: int  # the bar's start
    ema_fast: float | None
    ema_slow: float | None
    vwap: float | None
    supertrend: float | None
    supertrend_dir: int


def aggregate(candles: Sequence[Candle], bar_ms: int) -> list[Candle]:
    """Group candles (oldest first) into bars of `bar_ms`: open of the first, close of the
    last, high and low over all, volumes summed. Sides are summed where every candle has
    them; a bar is synthetic only if every candle in it was."""
    out: list[Candle] = []
    group: list[Candle] = []

    def close() -> None:
        first, last = group[0], group[-1]
        sided = all(g.buy_volume is not None and g.sell_volume is not None for g in group)
        out.append(
            Candle(
                first.key,
                first.minute_ts // bar_ms * bar_ms,
                first.open,
                max(g.high for g in group),
                min(g.low for g in group),
                last.close,
                sum(g.volume for g in group),
                all(g.synthetic for g in group),
                ticks=sum(g.ticks for g in group),
                buy_volume=sum(g.buy_volume or 0 for g in group) if sided else None,
                sell_volume=sum(g.sell_volume or 0 for g in group) if sided else None,
            )
        )

    for cd in candles:
        if group and cd.minute_ts // bar_ms != group[0].minute_ts // bar_ms:
            close()
            group = []
        group.append(cd)
    if group:
        close()
    return out


def overlay_series(
    price: Sequence[Candle], volume: Sequence[Candle], trend: Trend
) -> list[ChartPoint]:
    """One point per price bar. EMAs and the supertrend over the price bars, periods
    counted in bars; VWAP from the volume bars (an index's future, or the metal itself),
    the latest one at or before each price bar."""
    closes = [b.close for b in price]
    fast = ema(closes, trend.ema_fast)
    slow = ema(closes, trend.ema_slow)
    if len(price) >= trend.supertrend_period + 1:
        line, direction = supertrend(price, trend.supertrend_period, trend.supertrend_mult)
    else:
        line, direction = [None] * len(price), [0] * len(price)
    vw = vwap_series(volume)
    out: list[ChartPoint] = []
    j = -1
    for i, b in enumerate(price):
        while j + 1 < len(volume) and volume[j + 1].minute_ts <= b.minute_ts:
            j += 1
        out.append(
            ChartPoint(
                b.minute_ts,
                fast[i],
                slow[i],
                vw[j] if j >= 0 else None,
                line[i],
                direction[i],
            )
        )
    return out

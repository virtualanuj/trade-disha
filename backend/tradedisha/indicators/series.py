"""Series maths shared by indicators and the chart overlays."""

from __future__ import annotations

from collections.abc import Sequence

from tradedisha.market.candles import Candle


def ema(values: Sequence[float], period: int) -> list[float | None]:
    """EMA seeded with the SMA of the first `period` values; None until seeded."""
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def true_ranges(candles: Sequence[Candle]) -> list[float]:
    out: list[float] = []
    for i, c in enumerate(candles):
        if i == 0:
            out.append(c.high - c.low)
        else:
            pc = candles[i - 1].close
            out.append(max(c.high - c.low, abs(c.high - pc), abs(c.low - pc)))
    return out


def atr(candles: Sequence[Candle], period: int) -> list[float | None]:
    """Wilder's ATR."""
    tr = true_ranges(candles)
    out: list[float | None] = [None] * len(tr)
    if len(tr) < period:
        return out
    prev = sum(tr[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(tr)):
        prev = (prev * (period - 1) + tr[i]) / period
        out[i] = prev
    return out


def supertrend(
    candles: Sequence[Candle], period: int, mult: float
) -> tuple[list[float | None], list[int]]:
    """Returns (line, direction) per bar; direction +1 when price is above the line."""
    n = len(candles)
    line: list[float | None] = [None] * n
    direction: list[int] = [0] * n
    a = atr(candles, period)
    upper_f: float | None = None
    lower_f: float | None = None
    for i in range(n):
        if a[i] is None:
            continue
        c = candles[i]
        hl2 = (c.high + c.low) / 2
        upper = hl2 + mult * a[i]  # type: ignore[operator]
        lower = hl2 - mult * a[i]  # type: ignore[operator]
        prev_close = candles[i - 1].close if i > 0 else c.close
        if upper_f is None or lower_f is None:
            upper_f, lower_f = upper, lower
            direction[i] = 1 if c.close > upper_f else -1
        else:
            upper_f = upper if (upper < upper_f or prev_close > upper_f) else upper_f
            lower_f = lower if (lower > lower_f or prev_close < lower_f) else lower_f
            prev_dir = direction[i - 1]
            if prev_dir == 1:
                direction[i] = -1 if c.close < lower_f else 1
            elif prev_dir == -1:
                direction[i] = 1 if c.close > upper_f else -1
            else:
                direction[i] = 1 if c.close > upper_f else -1
        line[i] = lower_f if direction[i] == 1 else upper_f
    return line, direction


def bars_since_flip(direction: Sequence[int]) -> int:
    """Number of bars the latest direction has persisted (1 = flipped on the last bar)."""
    if not direction:
        return 0
    last = direction[-1]
    n = 0
    for d in reversed(direction):
        if d != last:
            break
        n += 1
    return n


def roc_pct(now: float | None, then: float | None) -> float | None:
    if now is None or then is None or then == 0:
        return None
    return (now - then) / then * 100

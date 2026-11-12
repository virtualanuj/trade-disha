"""Price-trend group: EMA crossover, position vs VWAP, supertrend. Spec §8.1."""

from __future__ import annotations

import math
from collections.abc import Sequence

from tradedisha.indicators import IndicatorResult, clamp, warming
from tradedisha.indicators.series import bars_since_flip, ema, supertrend
from tradedisha.market.candles import Candle
from tradedisha.parameters.model import Trend


def ema_cross(spot: Sequence[Candle], p: Trend) -> IndicatorResult:
    closes = [c.close for c in spot]
    if len(closes) < p.ema_slow:
        return warming("ema_cross", "trend", p.ema_slow, len(closes))
    fast = ema(closes, p.ema_fast)[-1]
    slow = ema(closes, p.ema_slow)[-1]
    assert fast is not None
    assert slow is not None
    sep_pct = (fast - slow) / slow * 100
    score = math.tanh(p.ema_k * sep_pct)
    rel = "above" if sep_pct > 0 else "below" if sep_pct < 0 else "at"
    return IndicatorResult(
        "ema_cross",
        "trend",
        score,
        f"EMA{p.ema_fast} {rel} EMA{p.ema_slow} by {abs(sep_pct):.2f}%",
        value={"ema_fast": fast, "ema_slow": slow, "sep_pct": sep_pct},
    )


def vwap_position(fut_close: float | None, vwap: float | None, p: Trend) -> IndicatorResult:
    if fut_close is None or vwap is None or vwap == 0:
        return warming("vwap_position", "trend", 1, 0)
    dev_pct = (fut_close - vwap) / vwap * 100
    score = clamp(dev_pct / p.vwap_full_pct)
    rel = "above" if dev_pct > 0 else "below" if dev_pct < 0 else "at"
    return IndicatorResult(
        "vwap_position",
        "trend",
        score,
        f"futures {rel} VWAP by {abs(dev_pct):.2f}%",
        value={"close": fut_close, "vwap": vwap, "dev_pct": dev_pct},
    )


def supertrend_vote(spot: Sequence[Candle], p: Trend) -> IndicatorResult:
    need = p.supertrend_period + 1
    if len(spot) < need:
        return warming("supertrend", "trend", need, len(spot))
    line, direction = supertrend(spot, p.supertrend_period, p.supertrend_mult)
    d = direction[-1]
    bars = bars_since_flip(direction)
    ramp = min(1.0, bars / p.supertrend_ramp_bars)
    score = d * ramp
    side = "above" if d > 0 else "below"
    return IndicatorResult(
        "supertrend",
        "trend",
        score,
        f"price {side} supertrend for {bars} bar{'s' if bars != 1 else ''}",
        value={"line": line[-1] or 0.0, "direction": float(d), "bars": float(bars)},
    )

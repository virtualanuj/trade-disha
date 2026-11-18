"""Macro group: the dollar, the rupee, crude oil and gold. Spec §8.6.

Each instrument scores its own move over `macro.window_minutes` of 1-minute closes,
`sign * clamp(change% / full%)`. For the indices a rising dollar, a weakening rupee, rising
crude and rising gold (risk-off) are bearish; silver is shown but never scored. For bullion
a rising dollar is bearish and a weakening rupee bullish (MCX price = world price * USD/INR).

There is no dollar index on Upstox, so it is rebuilt from NSE's currency futures: the
dollar against the euro, yen and pound (the real DXY's three biggest weights, 83 % of it)
through their rupee rates. Only its % change is used, so its level does not matter.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from tradedisha.indicators import IndicatorResult, clamp, warming
from tradedisha.parameters.model import Macro

# The real DXY's weights for the currencies NSE trades against the rupee.
DXY_EUR, DXY_JPY, DXY_GBP = 0.576, 0.136, 0.119
_DXY_TOTAL = DXY_EUR + DXY_JPY + DXY_GBP


@dataclass(frozen=True)
class MacroSeries:
    """One instrument's 1-minute closes up to the minute evaluated, oldest first."""

    closes: tuple[float, ...]
    fresh: bool  # its last tick is recent enough to count


def dollar_index_proxy(usdinr: float, eurinr: float, gbpinr: float, jpyinr: float) -> float:
    """The dollar against the euro, yen and pound, from rupee rates. JPYINR is per 100 yen."""
    eurusd = eurinr / usdinr
    gbpusd = gbpinr / usdinr
    usdjpy = usdinr / (jpyinr / 100)
    return float(
        eurusd ** (-DXY_EUR / _DXY_TOTAL)
        * usdjpy ** (DXY_JPY / _DXY_TOTAL)
        * gbpusd ** (-DXY_GBP / _DXY_TOTAL)
    )


def align_closes(series: Sequence[Sequence[tuple[int, float]]]) -> list[tuple[float, ...]]:
    """Per-minute closes of several instruments side by side, from the first minute all have.

    Each input is (minute_ts, close) in time order. A minute one of them did not trade
    carries its last close forward.
    """
    if not series or any(not s for s in series):
        return []
    start = max(s[0][0] for s in series)
    minutes = sorted({m for s in series for m, _ in s if m >= start})
    by_minute = [dict(s) for s in series]
    last = [
        next(c for m, c in reversed(s) if m <= start) for s in series
    ]  # the close in force at `start`
    out: list[tuple[float, ...]] = []
    for m in minutes:
        last = [d.get(m, prev) for d, prev in zip(by_minute, last, strict=True)]
        out.append(tuple(last))
    return out


def move_pct(closes: Sequence[float], window: int) -> float | None:
    """% change of the last close against the close `window` minutes before it."""
    if len(closes) < window + 1:
        return None
    base = closes[-1 - window]
    if base <= 0:
        return None
    return (closes[-1] - base) / base * 100


def macro_move(
    name: str,
    label: str,
    series: MacroSeries | None,
    *,
    sign: float,
    full_pct: float,
    window: int,
    scored: bool = True,
) -> IndicatorResult:
    """`sign * clamp(move / full_pct)`; warming without data, history or a live price."""
    if series is None or not series.closes:
        return IndicatorResult(name, "macro", 0.0, f"{label}: no price", "warming")
    if not series.fresh:
        return IndicatorResult(name, "macro", 0.0, f"{label}: price not live", "warming")
    chg = move_pct(series.closes, window)
    if chg is None:
        return warming(name, "macro", window + 1, len(series.closes))
    note = f"{label} {chg:+.2f}% in {window} min"
    value = {"change_pct": chg, "window": float(window)}
    if not scored:
        return IndicatorResult(name, "macro", 0.0, f"{note} (shown, not scored)", "info", value)
    return IndicatorResult(name, "macro", sign * clamp(chg / full_pct), note, value=value)


def index_macro_indicators(view: Mapping[str, MacroSeries], p: Macro) -> list[IndicatorResult]:
    """For NIFTY and BANK NIFTY: everything rising is bearish; silver is shown only."""
    w = p.window_minutes
    return [
        macro_move(
            "dollar_index",
            "Dollar",
            view.get("dollar"),
            sign=-1,
            full_pct=p.dollar_full_pct,
            window=w,
        ),
        macro_move(
            "usd_inr", "USD/INR", view.get("usdinr"), sign=-1, full_pct=p.usdinr_full_pct, window=w
        ),
        macro_move(
            "crude", "Crude", view.get("crude"), sign=-1, full_pct=p.crude_full_pct, window=w
        ),
        macro_move("gold", "Gold", view.get("gold"), sign=-1, full_pct=p.gold_full_pct, window=w),
        macro_move(
            "silver", "Silver", view.get("silver"), sign=-1, full_pct=1.0, window=w, scored=False
        ),
    ]


def bullion_macro_indicators(view: Mapping[str, MacroSeries], p: Macro) -> list[IndicatorResult]:
    """For GOLD and SILVER: a rising dollar is bearish, a weakening rupee bullish."""
    w = p.window_minutes
    return [
        macro_move(
            "dollar_index",
            "Dollar",
            view.get("dollar"),
            sign=-1,
            full_pct=p.dollar_full_pct,
            window=w,
        ),
        macro_move(
            "usd_inr", "USD/INR", view.get("usdinr"), sign=1, full_pct=p.usdinr_full_pct, window=w
        ),
    ]

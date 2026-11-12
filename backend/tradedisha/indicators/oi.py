"""Open-interest group: PCR, ATM build-up balance, max-pain drift. Spec §8.2."""

from __future__ import annotations

from tradedisha.indicators import IndicatorResult, clamp, warming
from tradedisha.market.chain import ChainState
from tradedisha.parameters.model import OI

BULLISH_CE = {"long_unwinding", "short_covering"}  # calls being closed out -> less resistance
BULLISH_PE = {"long_buildup", "short_buildup"}  # puts being written/bought as support
BEARISH_CE = {"long_buildup", "short_buildup"}
BEARISH_PE = {"long_unwinding", "short_covering"}


def pcr_vote(chain: ChainState, p: OI) -> IndicatorResult:
    pcr = chain.pcr(p.pcr_strike_range)
    if pcr is None:
        return warming("pcr", "oi", 1, 0)
    score = clamp((pcr - p.pcr_centre) / p.pcr_full_dev)
    lean = "bullish" if score > 0 else "bearish" if score < 0 else "neutral"
    return IndicatorResult("pcr", "oi", score, f"PCR {pcr:.2f} ({lean})", value={"pcr": pcr})


def oi_change_atm(chain: ChainState, p: OI) -> IndicatorResult:
    rows = chain.strikes_within(p.oi_change_strike_range)
    bull = 0
    bear = 0
    classified = 0
    for r in rows:
        for leg, bull_set, bear_set in (
            (r.ce, BULLISH_CE, BEARISH_CE),
            (r.pe, BULLISH_PE, BEARISH_PE),
        ):
            d = abs(leg.oi_delta_min)
            if leg.buildup == "none" or d == 0:
                continue
            classified += 1
            if leg.buildup in bull_set:
                bull += d
            elif leg.buildup in bear_set:
                bear += d
    if classified == 0:
        return warming("oi_change_atm", "oi", 1, 0)
    total = bull + bear
    score = (bull - bear) / total if total else 0.0
    return IndicatorResult(
        "oi_change_atm",
        "oi",
        score,
        f"ATM±{p.oi_change_strike_range} OI flow: bullish {bull:,} vs bearish {bear:,}",
        value={"bull_oi": float(bull), "bear_oi": float(bear)},
    )


def max_pain_drift(chain: ChainState, p: OI) -> IndicatorResult:
    hist = list(chain.history)
    need = p.maxpain_drift_minutes + 1
    if len(hist) < need:
        return warming("max_pain_drift", "oi", need, len(hist))
    now = hist[-1].max_pain
    then = hist[-need].max_pain
    if now is None or then is None:
        return warming("max_pain_drift", "oi", need, 0)
    steps = (now - then) / chain.step
    score = clamp(steps / p.maxpain_full_steps)
    direction = "up" if steps > 0 else "down" if steps < 0 else "flat"
    return IndicatorResult(
        "max_pain_drift",
        "oi",
        score,
        f"max pain {direction} {abs(steps):.0f} step{'s' if abs(steps) != 1 else ''}"
        f" in {p.maxpain_drift_minutes}m",
        value={"now": now, "then": then, "steps": steps},
    )

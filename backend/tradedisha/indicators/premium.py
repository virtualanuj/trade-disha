"""Premium-behaviour group: CE vs PE momentum, IV change, premium confirmation. Spec §8.3.

All three read the chain's per-minute history of ATM leg values.
"""

from __future__ import annotations

from tradedisha.indicators import IndicatorResult, clamp, warming
from tradedisha.indicators.series import roc_pct
from tradedisha.market.chain import ChainState
from tradedisha.parameters.model import Premium


def premium_momentum(chain: ChainState, p: Premium) -> IndicatorResult:
    hist = list(chain.history)
    need = p.premium_roc_minutes + 1
    if len(hist) < need:
        return warming("premium_momentum", "premium", need, len(hist))
    now, then = hist[-1], hist[-need]
    roc_ce = roc_pct(now.atm_ce_ltp, then.atm_ce_ltp)
    roc_pe = roc_pct(now.atm_pe_ltp, then.atm_pe_ltp)
    if roc_ce is None or roc_pe is None:
        return warming("premium_momentum", "premium", need, 0)
    spread = roc_ce - roc_pe
    score = clamp(spread / p.premium_roc_full_spread)
    return IndicatorResult(
        "premium_momentum",
        "premium",
        score,
        f"ATM CE {roc_ce:+.1f}% vs PE {roc_pe:+.1f}% over {p.premium_roc_minutes}m",
        value={"roc_ce": roc_ce, "roc_pe": roc_pe, "spread": spread},
    )


def iv_change(chain: ChainState, p: Premium) -> IndicatorResult:
    hist = list(chain.history)
    need = p.iv_change_minutes + 1
    if len(hist) < need:
        return warming("iv_change", "premium", need, len(hist))
    now, then = hist[-1], hist[-need]
    if now.atm_iv is None or then.atm_iv is None or now.spot is None or then.spot is None:
        return warming("iv_change", "premium", need, 0)
    d_iv = now.atm_iv - then.atm_iv
    d_spot = now.spot - then.spot
    sign = 1.0 if d_spot > 0 else -1.0 if d_spot < 0 else 0.0
    score = sign * clamp(d_iv / p.iv_full_change, 0.0, 1.0)
    iv_dir = "rising" if d_iv > 0 else "falling" if d_iv < 0 else "flat"
    spot_dir = "up" if d_spot > 0 else "down" if d_spot < 0 else "flat"
    return IndicatorResult(
        "iv_change",
        "premium",
        score,
        f"IV {iv_dir} {abs(d_iv):.1f}pts with spot {spot_dir} over {p.iv_change_minutes}m",
        value={"d_iv": d_iv, "d_spot": d_spot},
    )


def premium_confirmation(chain: ChainState, p: Premium) -> IndicatorResult:
    hist = list(chain.history)
    need = p.confirmation_minutes + 1
    if len(hist) < need:
        return warming("premium_confirmation", "premium", need, len(hist))
    now, then = hist[-1], hist[-need]
    if now.spot is None or then.spot is None:
        return warming("premium_confirmation", "premium", need, 0)
    d_spot = now.spot - then.spot
    roc_ce = roc_pct(now.atm_ce_ltp, then.atm_ce_ltp)
    roc_pe = roc_pct(now.atm_pe_ltp, then.atm_pe_ltp)
    if roc_ce is None or roc_pe is None:
        return warming("premium_confirmation", "premium", need, 0)
    if d_spot == 0:
        return IndicatorResult(
            "premium_confirmation", "premium", 0.0, "spot flat; nothing to confirm", value={}
        )
    if d_spot > 0:
        agrees = roc_ce > 0 and roc_ce >= -roc_pe
        score = clamp(roc_ce / 10) if agrees else p.divergence_score
        note = "calls confirm the up-move" if agrees else "divergence: spot up but calls lag"
    else:
        agrees = roc_pe > 0 and roc_pe >= -roc_ce
        score = -clamp(roc_pe / 10) if agrees else -p.divergence_score
        note = "puts confirm the down-move" if agrees else "divergence: spot down but puts lag"
    return IndicatorResult(
        "premium_confirmation",
        "premium",
        score,
        note,
        value={"d_spot": d_spot, "roc_ce": roc_ce, "roc_pe": roc_pe},
    )

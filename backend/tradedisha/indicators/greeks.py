"""Black-Scholes helpers used when the feed does not supply Greeks. Spec §7.3."""

from __future__ import annotations

import math

SECONDS_PER_YEAR = 365.0 * 24 * 3600


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_delta(
    spot: float, strike: float, t_years: float, iv_pct: float, rate: float, *, call: bool
) -> float:
    """Delta of a European option; `iv_pct` is annualised volatility in percent."""
    if spot <= 0 or strike <= 0:
        return 0.0
    if t_years <= 0 or iv_pct <= 0:
        intrinsic = spot > strike if call else spot < strike
        return (1.0 if call else -1.0) if intrinsic else 0.0
    sigma = iv_pct / 100.0
    d1 = (math.log(spot / strike) + (rate + 0.5 * sigma * sigma) * t_years) / (
        sigma * math.sqrt(t_years)
    )
    return norm_cdf(d1) if call else norm_cdf(d1) - 1.0


def years_between_ms(now_ms: int, expiry_ms: int) -> float:
    return max(0.0, (expiry_ms - now_ms) / 1000.0 / SECONDS_PER_YEAR)

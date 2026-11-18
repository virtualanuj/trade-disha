"""Combine indicator results into one bias. Spec §8.4."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from tradedisha.indicators import Group, IndicatorResult
from tradedisha.parameters.model import ParameterSet

Label = Literal["Bullish", "Neutral", "Bearish"]
GROUPS: tuple[Group, ...] = ("trend", "oi", "premium", "macro")


def bullion_weights(p: ParameterSet) -> dict[Group, float]:
    """Bullion has no option chain: trend, and the dollar's share (spec §9a)."""
    m = p.bullion.macro_weight
    return {"trend": 1.0 - m, "oi": 0.0, "premium": 0.0, "macro": m}


@dataclass(frozen=True)
class Contribution:
    result: IndicatorResult
    weight: float  # effective weight of this indicator in the bias
    contribution: float  # score x weight (0 when quality != ok)


@dataclass(frozen=True)
class Bias:
    bias: float
    label: Label
    strength: int
    group_scores: dict[Group, float]
    group_weights: dict[Group, float]
    contributions: list[Contribution] = field(default_factory=list)
    is_expiry_day: bool = False


def effective_group_weights(p: ParameterSet, is_expiry_day: bool) -> dict[Group, float]:
    """The index groups' weights: macro takes its share, the others keep their proportions.

    On expiry day part of OI's weight is cut and spread over the other groups.
    """
    rest = 1.0 - p.weights.macro
    w: dict[Group, float] = {
        "trend": p.weights.trend * rest,
        "oi": p.weights.oi * rest,
        "premium": p.weights.premium * rest,
        "macro": p.weights.macro,
    }
    if not is_expiry_day:
        return w
    cut = w["oi"] * (1 - p.weights.expiry_oi_weight_factor)
    w["oi"] -= cut
    return _spread(w, cut, ("trend", "premium", "macro"))


def _spread(w: dict[Group, float], amount: float, to: tuple[Group, ...]) -> dict[Group, float]:
    """Add `amount` to the groups `to`, in proportion to their weights."""
    total = sum(w[g] for g in to)
    if total > 0:
        for g in to:
            w[g] += amount * w[g] / total
    return w


def _return_idle_macro(
    w: dict[Group, float], by_group: dict[Group, list[IndicatorResult]]
) -> dict[Group, float]:
    """No live macro price (market shut, no data): its share goes back to the others."""
    if w["macro"] <= 0 or any(r.quality == "ok" for r in by_group["macro"]):
        return w
    idle = w["macro"]
    w["macro"] = 0.0
    return _spread(w, idle, tuple(g for g in GROUPS if g != "macro" and w[g] > 0))


def aggregate(
    results: list[IndicatorResult],
    p: ParameterSet,
    *,
    is_expiry_day: bool,
    weights: dict[Group, float] | None = None,
    neutral_band: float | None = None,
) -> Bias:
    """Weighted group means. `weights` and `neutral_band` override the index settings."""
    weights = dict(weights) if weights is not None else effective_group_weights(p, is_expiry_day)
    by_group: dict[Group, list[IndicatorResult]] = {g: [] for g in GROUPS}
    for r in results:
        by_group[r.group].append(r)
    weights = _return_idle_macro(weights, by_group)

    group_scores: dict[Group, float] = {}
    contributions: list[Contribution] = []
    for g in GROUPS:
        members = by_group[g]
        ok = [r for r in members if r.quality == "ok"]
        group_scores[g] = sum(r.score for r in ok) / len(ok) if ok else 0.0
        per = weights[g] / len(ok) if ok else 0.0
        for r in members:
            w = per if r.quality == "ok" else 0.0
            contributions.append(Contribution(r, w, r.score * w))

    bias = sum(weights[g] * group_scores[g] for g in GROUPS)
    bias = max(-1.0, min(1.0, bias))
    band = p.bias.neutral_band if neutral_band is None else neutral_band
    label: Label = "Bullish" if bias >= band else "Bearish" if bias <= -band else "Neutral"
    return Bias(
        bias=bias,
        label=label,
        strength=round(abs(bias) * 100),
        group_scores=group_scores,
        group_weights=weights,
        contributions=contributions,
        is_expiry_day=is_expiry_day,
    )

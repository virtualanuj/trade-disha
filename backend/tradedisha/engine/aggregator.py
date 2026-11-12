"""Combine indicator results into one bias. Spec §8.4."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from tradedisha.indicators import Group, IndicatorResult
from tradedisha.parameters.model import ParameterSet

Label = Literal["Bullish", "Neutral", "Bearish"]
GROUPS: tuple[Group, ...] = ("trend", "oi", "premium")


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
    w: dict[Group, float] = {
        "trend": p.weights.trend,
        "oi": p.weights.oi,
        "premium": p.weights.premium,
    }
    if not is_expiry_day:
        return w
    cut = w["oi"] * (1 - p.weights.expiry_oi_weight_factor)
    w["oi"] -= cut
    others = w["trend"] + w["premium"]
    if others > 0:
        w["trend"] += cut * w["trend"] / others
        w["premium"] += cut * w["premium"] / others
    return w


def aggregate(results: list[IndicatorResult], p: ParameterSet, *, is_expiry_day: bool) -> Bias:
    weights = effective_group_weights(p, is_expiry_day)
    by_group: dict[Group, list[IndicatorResult]] = {g: [] for g in GROUPS}
    for r in results:
        by_group[r.group].append(r)

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
    band = p.bias.neutral_band
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

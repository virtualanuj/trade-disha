"""Combine indicator results into one bias. Spec §8.4."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from tradedisha.indicators import Group, IndicatorResult
from tradedisha.parameters.model import ParameterSet

Label = Literal["Bullish", "Neutral", "Bearish"]
GROUPS: tuple[Group, ...] = ("trend", "oi", "premium", "flow", "macro")
# Groups whose share goes back to the others while none of their readings is live.
INDEX_IDLE: tuple[Group, ...] = ("macro",)
BULLION_IDLE: tuple[Group, ...] = ("oi", "flow", "macro")


def bullion_weights(p: ParameterSet) -> dict[Group, float]:
    """Bullion has no option chain (spec §9a): trend has what the future's OI build-up,
    order flow and other markets leave."""
    b = p.bullion
    return {
        "trend": 1.0 - b.oi_weight - b.flow_weight - b.macro_weight,
        "oi": b.oi_weight,
        "premium": 0.0,
        "flow": b.flow_weight,
        "macro": b.macro_weight,
    }


@dataclass(frozen=True)
class Contribution:
    result: IndicatorResult
    weight: float  # effective weight of this indicator in the bias
    contribution: float  # score x weight (0 when quality != ok or switched off)
    enabled: bool = True  # False: switched off in the Evidence panel (Milestone E15)


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
        "flow": 0.0,  # the index reads order flow at the trigger, not in the bias
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


def _return_idle(
    w: dict[Group, float],
    by_group: dict[Group, list[IndicatorResult]],
    groups: tuple[Group, ...],
    off: frozenset[str],
) -> dict[Group, float]:
    """A group in `groups` with no live reading (market shut, warming, no data), or any
    group whose every factor is switched off, gives its share back to the others, in
    proportion to theirs."""

    def live(g: Group) -> bool:
        return any(r.quality == "ok" and r.name not in off for r in by_group[g])

    def all_off(g: Group) -> bool:
        return bool(by_group[g]) and all(r.name in off for r in by_group[g])

    idle = [g for g in GROUPS if w[g] > 0 and ((g in groups and not live(g)) or all_off(g))]
    if not idle:
        return w
    amount = sum(w[g] for g in idle)
    for g in idle:
        w[g] = 0.0
    return _spread(w, amount, tuple(g for g in GROUPS if g not in idle and w[g] > 0))


def aggregate(
    results: list[IndicatorResult],
    p: ParameterSet,
    *,
    is_expiry_day: bool,
    weights: dict[Group, float] | None = None,
    neutral_band: float | None = None,
    idle_groups: tuple[Group, ...] = INDEX_IDLE,
    off: frozenset[str] = frozenset(),
) -> Bias:
    """Weighted group means. `weights`, `neutral_band` and `idle_groups` override the index
    settings. Factors named in `off` are shown but carry no weight (Milestone E15)."""
    weights = dict(weights) if weights is not None else effective_group_weights(p, is_expiry_day)
    by_group: dict[Group, list[IndicatorResult]] = {g: [] for g in GROUPS}
    for r in results:
        by_group[r.group].append(r)
    weights = _return_idle(weights, by_group, idle_groups, off)

    group_scores: dict[Group, float] = {}
    contributions: list[Contribution] = []
    for g in GROUPS:
        members = by_group[g]
        ok = [r for r in members if r.quality == "ok" and r.name not in off]
        group_scores[g] = sum(r.score for r in ok) / len(ok) if ok else 0.0
        per = weights[g] / len(ok) if ok else 0.0
        for r in members:
            on = r.name not in off
            w = per if r.quality == "ok" and on else 0.0
            contributions.append(Contribution(r, w, r.score * w, on))

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

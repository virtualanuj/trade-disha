"""Pure indicator functions. Each returns an IndicatorResult; none touch I/O or time."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Group = Literal["trend", "oi", "premium"]
Quality = Literal["ok", "warming", "partial"]


@dataclass(frozen=True)
class IndicatorResult:
    name: str
    group: Group
    score: float  # in [-1, +1]; + bullish, - bearish
    note: str
    quality: Quality = "ok"
    value: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "score", max(-1.0, min(1.0, float(self.score))))


def clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def warming(name: str, group: Group, need: int, have: int) -> IndicatorResult:
    return IndicatorResult(
        name,
        group,
        0.0,
        f"warming up ({have}/{need} bars)",
        "warming",
        {"need": need, "have": have},
    )

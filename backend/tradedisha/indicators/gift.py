"""GIFT Nifty's overnight move as an opening-gap vote for NIFTY. Spec §8.6.

GIFT Nifty (NSE IX) trades while NSE is shut, so at 09:15 it says how far NIFTY moved
overnight. During NSE hours it is only a delayed copy of the NIFTY future, so the vote
fades out over `macro.gift_fade_minutes` after the open and is then shown, not scored.

The move is measured on GIFT's own prices, from its last close before the previous NSE
close (15:30) to its last close before today's open, so its premium over spot cancels.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from tradedisha.indicators import IndicatorResult, clamp
from tradedisha.parameters.model import Macro

NAME = "gift_nifty"
REF_WINDOW_MS = 30 * 60_000  # the reference must be within 30 minutes of the NSE close


@dataclass(frozen=True)
class GiftSnapshot:
    """GIFT Nifty at the previous NSE close and just before today's open."""

    day: date  # the NSE trading day it is for
    ref_ts: int
    ref_close: float
    preopen_ts: int
    preopen_price: float

    @property
    def move_pct(self) -> float:
        return (self.preopen_price / self.ref_close - 1) * 100


def _last_before(closes: Sequence[tuple[int, float]], before_ms: int) -> tuple[int, float] | None:
    best: tuple[int, float] | None = None
    for ts, c in closes:
        if ts < before_ms and (best is None or ts > best[0]):
            best = (ts, c)
    return best


def snapshot_from(
    prev_closes: Sequence[tuple[int, float]],
    today_closes: Sequence[tuple[int, float]],
    *,
    day: date,
    prev_close_ms: int,
    open_ms: int,
) -> GiftSnapshot | None:
    """From (minute_ts, close) rows of the previous NSE day and of today; None if either
    price is missing (no candle near the close, or none between the close and the open)."""
    ref = _last_before(prev_closes, prev_close_ms)
    if ref is None or ref[0] < prev_close_ms - REF_WINDOW_MS or ref[1] <= 0:
        return None
    pre = _last_before(today_closes, open_ms)
    if pre is None or pre[0] <= ref[0]:
        return None
    return GiftSnapshot(day, ref[0], ref[1], pre[0], pre[1])


def gift_gap(snap: GiftSnapshot | None, minutes_since_open: float, p: Macro) -> IndicatorResult:
    """`dir * clamp(move / full) * (1 - minutes / fade)`; `info` outside (0, fade)."""
    if snap is None:
        return IndicatorResult(NAME, "macro", 0.0, "GIFT Nifty: no overnight reading", "warming")
    move = snap.move_pct
    value = {"move_pct": move, "ref": snap.ref_close, "preopen": snap.preopen_price}
    note = f"GIFT Nifty {move:+.2f}% overnight"
    left = 1 - minutes_since_open / p.gift_fade_minutes
    if minutes_since_open <= 0 or left <= 0:
        return IndicatorResult(NAME, "macro", 0.0, f"{note} (faded, not scored)", "info", value)
    sign = 1.0 if p.gift_direction == "follow" else -1.0
    value["fade"] = left
    score = sign * clamp(move / p.gift_full_pct) * left
    return IndicatorResult(
        NAME, "macro", score, f"{note}, {p.gift_direction}, {left:.0%} weight left", value=value
    )

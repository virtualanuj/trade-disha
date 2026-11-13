"""Index day statistics for the details view."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tradedisha.api.deps import State
from tradedisha.app_state import AppState

router = APIRouter()


class IndexStatsOut(BaseModel):
    index: str
    day_open: float | None
    day_high: float | None
    day_low: float | None
    range_pos: float | None
    prev_close: float | None
    change: float | None
    change_pct: float | None
    high_52w: float | None
    low_52w: float | None
    fut_premium: float | None
    vix: float | None
    vix_change_pct: float | None
    updated_ts: int | None


def all_stats(state: AppState) -> list[IndexStatsOut]:
    session = state.session
    return [IndexStatsOut(**asdict(session.index_stats(i))) for i in session.resolved]


@router.get("/stats/{index}", response_model=IndexStatsOut)
def stats(index: str, state: State) -> IndexStatsOut:
    key = index.upper()
    if key not in state.session.resolved:
        raise HTTPException(status_code=404, detail=f"unknown index {index}")
    return IndexStatsOut(**asdict(state.session.index_stats(key)))

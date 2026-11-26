"""Index day statistics for the details view, and the rates strip's market-wide quotes."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tradedisha.api.deps import State
from tradedisha.app_state import AppState
from tradedisha.market.stats import market_quotes

router = APIRouter()


class SectorOut(BaseModel):
    """A sector index on the index's panel (Milestone E11). Display only."""

    name: str
    label: str
    ltp: float | None
    prev_close: float | None
    change: float | None
    change_pct: float | None


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
    sectors: list[SectorOut]


class QuoteOut(BaseModel):
    """A market-wide rate on the rates strip, such as SENSEX (Milestone E22)."""

    name: str
    ltp: float | None
    prev_close: float | None
    change: float | None
    change_pct: float | None
    updated_ts: int | None


def all_quotes(state: AppState) -> list[QuoteOut]:
    p = state.session.prices
    return [QuoteOut(**asdict(q)) for q in market_quotes(p.ltp, p.close_prev, p.ts)]


@router.get("/quotes", response_model=list[QuoteOut])
async def quotes(state: State) -> list[QuoteOut]:
    return all_quotes(state)


def all_stats(state: AppState) -> list[IndexStatsOut]:
    session = state.session
    return [IndexStatsOut(**asdict(session.index_stats(i))) for i in session.resolved]


@router.get("/stats/{index}", response_model=IndexStatsOut)
async def stats(index: str, state: State) -> IndexStatsOut:
    key = index.upper()
    if key not in state.session.resolved:
        raise HTTPException(status_code=404, detail=f"unknown index {index}")
    return IndexStatsOut(**asdict(state.session.index_stats(key)))

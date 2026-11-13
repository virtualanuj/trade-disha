"""The Data panel: how much is stored, and deleting raw ticks up to a chosen date."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from tradedisha.api.deps import State
from tradedisha.clock import epoch_ms_now

router = APIRouter()


class UsageOut(BaseModel):
    db_bytes: int
    tick_rows: int
    tick_days: int
    oldest: date | None
    newest: date | None
    prune_rows: int
    prune_days: int
    prune_bytes_estimate: int


class PruneRequest(BaseModel):
    until_date: date


class PruneOut(BaseModel):
    until_date: date
    rows_deleted: int
    bytes_freed: int


@router.get("/data/usage", response_model=UsageOut)
def usage(state: State, until_date: date | None = None) -> UsageOut:
    return UsageOut(**asdict(state.session.tick_store.usage(until_date)))


@router.post("/data/prune-ticks", response_model=PruneOut)
async def prune_ticks(body: PruneRequest, state: State) -> PruneOut:
    session = state.session
    session.tick_store.flush()
    result = await session.tick_store.prune(body.until_date)
    session.feed_log.write(
        epoch_ms_now(),
        "ticks_pruned",
        f"until={body.until_date.isoformat()} rows={result.rows_deleted}",
    )
    return PruneOut(until_date=body.until_date, **asdict(result))

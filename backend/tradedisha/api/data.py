"""The Data panel: how much is stored, and deleting raw ticks up to a chosen date."""

from __future__ import annotations

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
    """Index and bullion ticks together: both are raw ticks the trader may delete."""
    nse = state.session.tick_store.usage(until_date)
    mcx = state.session.bullion_tick_store.usage(until_date)
    days = [d for d in (nse.oldest, nse.newest, mcx.oldest, mcx.newest) if d is not None]
    return UsageOut(
        db_bytes=nse.db_bytes,
        tick_rows=nse.tick_rows + mcx.tick_rows,
        tick_days=max(nse.tick_days, mcx.tick_days),
        oldest=min(days) if days else None,
        newest=max(days) if days else None,
        prune_rows=nse.prune_rows + mcx.prune_rows,
        prune_days=max(nse.prune_days, mcx.prune_days),
        prune_bytes_estimate=nse.prune_bytes_estimate + mcx.prune_bytes_estimate,
    )


@router.post("/data/prune-ticks", response_model=PruneOut)
async def prune_ticks(body: PruneRequest, state: State) -> PruneOut:
    session = state.session
    rows = freed = 0
    for store in (session.tick_store, session.bullion_tick_store):
        store.flush()
        result = await store.prune(body.until_date)
        rows += result.rows_deleted
        freed += result.bytes_freed
    session.feed_log.write(
        epoch_ms_now(),
        "ticks_pruned",
        f"until={body.until_date.isoformat()} rows={rows}",
    )
    return PruneOut(until_date=body.until_date, rows_deleted=rows, bytes_freed=freed)

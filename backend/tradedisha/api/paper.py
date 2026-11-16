"""Paper trades and the journal. The only mutations in the app besides config reload."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from tradedisha.api.deps import State
from tradedisha.app_state import AppState
from tradedisha.engine.paper import (
    METALS,
    JournalStats,
    PaperError,
    PaperTrade,
    PaperTradeManager,
    PaperTradeStore,
    journal_stats,
)
from tradedisha.engine.signals import SignalStore
from tradedisha.store.ticks import day_bounds_ms

router = APIRouter()


class PaperTradeOut(BaseModel):
    id: str
    signal_id: str
    index: str
    instrument_key: str
    trading_symbol: str
    direction: str
    strike: float
    expiry: str
    lots: int
    qty: int
    signal_entry: float
    entry_price: float
    entry_ts: int
    slippage: float
    target_price: float
    stop_price: float
    cost: float
    status: str
    exit_price: float | None
    exit_ts: int | None
    exit_reason: str | None
    exit_fill_quality: str | None
    exit_price_age_ms: int | None
    gross: float | None
    net: float | None
    warning: str | None
    # live view of an open trade
    ltp: float | None = None
    ltp_ts: int | None = None
    live_gross: float | None = None
    live_net: float | None = None


class JournalStatsOut(BaseModel):
    scope: str
    trades: int
    hits: int
    hit_rate: float | None
    avg_win: float | None
    avg_loss: float | None
    net_total: float
    gross_total: float
    avg_duration_s: float | None
    by_reason: dict[str, int]
    non_live_fills: int


class JournalOut(BaseModel):
    stats: list[JournalStatsOut]
    open_trades: int


class OpenRequest(BaseModel):
    signal_id: str


def trade_out(state: AppState, t: PaperTrade) -> PaperTradeOut:
    out = PaperTradeOut(**asdict(t))
    if t.is_open:
        prices = state.session.prices
        ltp = prices.ltp.get(t.instrument_key)
        if ltp is not None:
            out.ltp = ltp
            out.ltp_ts = prices.ts.get(t.instrument_key)
            out.live_gross, out.live_net = t.pnl_at(ltp)
    return out


def _managers(state: AppState) -> list[PaperTradeManager]:
    """The index manager, and the bullion one when bullion is loaded."""
    desk = state.session.bullion_desk
    mgrs = [state.session.paper, desk.paper if desk else None]
    return [m for m in mgrs if m is not None]


def open_trades(state: AppState) -> list[PaperTradeOut]:
    return [trade_out(state, t) for m in _managers(state) for t in m.open_trades.values()]


def today_trades(state: AppState) -> list[PaperTradeOut]:
    """Everything still open plus everything entered today, newest first."""
    mgrs = _managers(state)
    if not mgrs:
        return []
    start, end = day_bounds_ms(state.clock.today())
    seen = {t.id: t for t in mgrs[0].store.read(start_ms=start, end_ms=end)}
    for m in mgrs:
        seen.update(m.open_trades)
    ordered = sorted(seen.values(), key=lambda t: t.entry_ts, reverse=True)
    return [trade_out(state, t) for t in ordered]


def _manager(state: AppState, index: str | None) -> PaperTradeManager:
    """The manager for a market: bullion trades go to the bullion desk."""
    desk = state.session.bullion_desk
    if index in METALS:
        if desk is None:
            raise HTTPException(status_code=409, detail="bullion is not loaded")
        return desk.paper
    mgr = state.session.paper
    if mgr is None:
        raise HTTPException(status_code=409, detail="the feed has not started yet")
    return mgr


def _fail(exc: PaperError) -> HTTPException:
    return HTTPException(status_code=404 if exc.not_found else 409, detail=exc.reason)


def _range(start: date | None, end: date | None) -> tuple[int | None, int | None]:
    lo = day_bounds_ms(start)[0] if start else None
    hi = day_bounds_ms(end)[1] if end else None
    return lo, hi


def _read(
    state: AppState, start: date | None, end: date | None, index: str | None, status: str | None
) -> list[PaperTrade]:
    lo, hi = _range(start, end)
    store = PaperTradeStore(state.conn)
    return store.read(start_ms=lo, end_ms=hi, index=index.upper() if index else None, status=status)


@router.post("/paper-trades", response_model=PaperTradeOut, status_code=201)
def open_trade(body: OpenRequest, state: State) -> PaperTradeOut:
    try:
        known = SignalStore(state.conn).get(body.signal_id)
        index = known.index if known else None
        return trade_out(state, _manager(state, index).open(body.signal_id))
    except PaperError as exc:
        raise _fail(exc) from exc


@router.post("/paper-trades/{trade_id}/close", response_model=PaperTradeOut)
def close_trade(trade_id: str, state: State) -> PaperTradeOut:
    try:
        known = PaperTradeStore(state.conn).get(trade_id)
        index = known.index if known else None
        return trade_out(state, _manager(state, index).close_manual(trade_id))
    except PaperError as exc:
        raise _fail(exc) from exc


@router.get("/paper-trades", response_model=list[PaperTradeOut])
def list_trades(
    state: State,
    index: str | None = None,
    status: str | None = None,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
) -> list[PaperTradeOut]:
    return [trade_out(state, t) for t in _read(state, start, end, index, status)]


@router.get("/journal/stats", response_model=JournalOut)
def stats(
    state: State,
    index: str | None = None,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
) -> JournalOut:
    trades = _read(state, start, end, index, None)
    return JournalOut(
        stats=[JournalStatsOut(**asdict(s)) for s in journal_stats(trades)],
        open_trades=sum(1 for t in trades if t.is_open),
    )


__all__ = ["JournalStats", "open_trades", "router", "today_trades", "trade_out"]

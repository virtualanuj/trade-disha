"""Paper trades and the journal. The only mutations in the app besides config reload.

A trade is opened from an active signal, or by hand from a ticket (E23); the target and
stop of any open trade can be changed."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from tradedisha.api.deps import State
from tradedisha.api.signals import SignalOut, signal_out
from tradedisha.app_state import AppState
from tradedisha.engine.bank import StatementKind
from tradedisha.engine.paper import (
    METALS,
    JournalStats,
    LevelChange,
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
    blocked: float  # held in the paper bank while open (E17)
    banked: bool
    levels_edited: bool  # target or stop changed after it opened (E23)
    manual: bool = False  # opened by hand, with no signal (E23)
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


class LedgerEntryOut(BaseModel):
    id: int
    ts: int
    kind: str  # OPEN, DEPOSIT, WITHDRAW
    amount: float
    opening_balance: float
    config_version: int | None


class BankOut(BaseModel):
    """The paper bank (spec §10.5): money held, blocked by open trades, and free."""

    opening_balance: float
    opened_ts: int
    deposited: float
    withdrawn: float
    realised: float
    balance: float
    blocked: float
    available: float
    open_trades: int
    ledger: list[LedgerEntryOut]


class StatementRowOut(BaseModel):
    ts: int
    kind: StatementKind
    held: float  # change in what is blocked
    cash: float  # change in the balance
    balance: float
    blocked: float
    available: float
    trade_id: str | None
    index: str | None
    direction: str | None
    strike: float | None
    trading_symbol: str | None


class BankStatementOut(BaseModel):
    """Every cash move in the paper bank, oldest first, with the figures after it (§10.5)."""

    rows: list[StatementRowOut]


def bank_out(state: AppState) -> BankOut:
    return BankOut.model_validate(asdict(state.session.bank.summary()))


class LevelChangeOut(BaseModel):
    ts: int
    target: float
    stop: float
    ltp: float  # the price when they were set
    source: str  # entry, edit


class PaperTradeDetailOut(BaseModel):
    """One trade, the signal it was taken from (none when opened by hand) and every set of
    levels it has had, for the Trades page (E19, E23)."""

    trade: PaperTradeOut
    signal: SignalOut | None
    levels: list[LevelChangeOut]


class OpenRequest(BaseModel):
    signal_id: str


ManualDirection = Literal["BUY_CE", "BUY_PE", "BUY_FUT", "SELL_FUT"]


class TicketOut(BaseModel):
    """What a trade opened by hand would be, now (E23). Nothing is opened."""

    index: str
    direction: str
    instrument_key: str
    trading_symbol: str
    strike: float
    expiry: str
    lots: int
    qty: int
    ltp: float | None
    ltp_ts: int | None
    target: float | None  # the signal rule's, at the current price
    stop: float | None
    cost: float | None
    blocked: float | None  # what the paper bank would hold
    available: float | None  # free money in the paper bank
    refusal: str | None  # why an open would be refused now


class ManualOpenRequest(BaseModel):
    """Open by hand: an index option (strike required) or a metal's future (no strike).
    A level left out is the signal rule's at the fill."""

    index: str
    direction: ManualDirection
    strike: float | None = None
    quoted: float | None = Field(None, gt=0)  # the price the ticket showed
    target: float | None = None
    stop: float | None = None
    contract: str | None = None  # a metal's mini, GOLDM or SILVERM (E28); None: the full one
    lots: int | None = None  # None: the contract's default; else 1 to 100


class LevelsRequest(BaseModel):
    target: float
    stop: float


def trade_out(state: AppState, t: PaperTrade) -> PaperTradeOut:
    out = PaperTradeOut(**asdict(t), manual=t.is_manual)
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
async def open_trade(body: OpenRequest, state: State) -> PaperTradeOut:
    try:
        known = SignalStore(state.conn).get(body.signal_id)
        index = known.index if known else None
        return trade_out(state, _manager(state, index).open(body.signal_id))
    except PaperError as exc:
        raise _fail(exc) from exc


@router.get("/paper-trades/ticket", response_model=TicketOut)
async def ticket(
    state: State,
    index: str,
    direction: ManualDirection,
    strike: float | None = None,
    contract: str | None = None,
    lots: int | None = None,
) -> TicketOut:
    try:
        quote = _manager(state, index.upper()).quote_manual(
            index.upper(),
            direction,
            strike,
            contract=contract.upper() if contract else None,
            lots=lots,
        )
    except PaperError as exc:
        raise _fail(exc) from exc
    return TicketOut(**asdict(quote))


@router.post("/paper-trades/manual", response_model=PaperTradeOut, status_code=201)
async def open_manual(body: ManualOpenRequest, state: State) -> PaperTradeOut:
    index = body.index.upper()
    try:
        trade = _manager(state, index).open_manual(
            index,
            body.direction,
            body.strike,
            quoted=body.quoted,
            target=body.target,
            stop=body.stop,
            contract=body.contract.upper() if body.contract else None,
            lots=body.lots,
        )
    except PaperError as exc:
        raise _fail(exc) from exc
    return trade_out(state, trade)


@router.patch("/paper-trades/{trade_id}/levels", response_model=PaperTradeOut)
async def set_levels(trade_id: str, body: LevelsRequest, state: State) -> PaperTradeOut:
    try:
        known = PaperTradeStore(state.conn).get(trade_id)
        if known is None:
            raise PaperError("unknown paper trade", not_found=True)
        mgr = _manager(state, known.index)
        return trade_out(state, mgr.set_levels(trade_id, target=body.target, stop=body.stop))
    except PaperError as exc:
        raise _fail(exc) from exc


@router.post("/paper-trades/{trade_id}/close", response_model=PaperTradeOut)
async def close_trade(trade_id: str, state: State) -> PaperTradeOut:
    try:
        known = PaperTradeStore(state.conn).get(trade_id)
        index = known.index if known else None
        return trade_out(state, _manager(state, index).close_manual(trade_id))
    except PaperError as exc:
        raise _fail(exc) from exc


@router.get("/paper-trades", response_model=list[PaperTradeOut])
async def list_trades(
    state: State,
    index: str | None = None,
    status: str | None = None,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
) -> list[PaperTradeOut]:
    return [trade_out(state, t) for t in _read(state, start, end, index, status)]


@router.get("/paper-trades/{trade_id}", response_model=PaperTradeDetailOut)
async def get_trade(trade_id: str, state: State) -> PaperTradeDetailOut:
    """An open trade comes from its manager (live P&L), a closed one from the store."""
    live = next(
        (m.open_trades[trade_id] for m in _managers(state) if trade_id in m.open_trades), None
    )
    store = PaperTradeStore(state.conn)
    t = live or store.get(trade_id)
    if t is None:
        raise HTTPException(status_code=404, detail="unknown trade")
    # one signals table serves index and bullion, and is there before the feed starts
    s = None if t.is_manual else SignalStore(state.conn).get(t.signal_id)
    return PaperTradeDetailOut(
        trade=trade_out(state, t),
        signal=signal_out(state, s) if s is not None else None,
        levels=[_level_out(c) for c in store.levels(t.id)],
    )


def _level_out(c: LevelChange) -> LevelChangeOut:
    return LevelChangeOut(ts=c.ts, target=c.target, stop=c.stop, ltp=c.ltp, source=c.source)


@router.get("/bank", response_model=BankOut)
async def bank(state: State) -> BankOut:
    return bank_out(state)


@router.get("/bank/statement", response_model=BankStatementOut)
async def bank_statement(
    state: State,
    index: str | None = None,
    kind: Annotated[list[StatementKind] | None, Query()] = None,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
) -> BankStatementOut:
    lo, hi = _range(start, end)
    rows = state.session.bank.statement(
        start_ms=lo, end_ms=hi, kinds=kind, index=index.upper() if index else None
    )
    return BankStatementOut(rows=[StatementRowOut.model_validate(asdict(r)) for r in rows])


@router.get("/journal/stats", response_model=JournalOut)
async def stats(
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


__all__ = ["JournalStats", "bank_out", "open_trades", "router", "today_trades", "trade_out"]

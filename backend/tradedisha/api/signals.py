"""Signals: active per index, history, and why the last minute did or did not fire."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from tradedisha.api.deps import State
from tradedisha.app_state import AppState
from tradedisha.engine.outcomes import Outcome, OutcomeStore, scorecard
from tradedisha.engine.paper import METALS
from tradedisha.engine.signals import Gate, Signal
from tradedisha.market.flow import FlowReading
from tradedisha.store.ticks import day_bounds_ms

router = APIRouter()


class OutcomeOut(BaseModel):
    """What the option did after the signal fired (spec §9.5)."""

    result: str  # open | target | stop | neither
    result_ts: int | None
    end_ts: int
    best_price: float
    best_ts: int
    best_pct: float  # over the signal's entry price
    worst_price: float
    worst_ts: int
    worst_pct: float
    px_1m: float | None
    px_5m: float | None
    px_15m: float | None
    spot_pre_move: float | None
    spot_best_move: float | None
    late_share: float | None
    final: bool


class ScoreRowOut(BaseModel):
    rule: str
    shadow: bool
    scope: str
    signals: int
    scored: int
    target_pct: float | None
    stop_pct: float | None
    neither_pct: float | None
    avg_best_pct: float | None
    avg_worst_pct: float | None
    avg_late_share: float | None


class LiveLevelsOut(BaseModel):
    """An active signal's entry, target and stop at the current price (spec §9.2)."""

    ltp: float
    target: float
    stop: float


class SignalOut(BaseModel):
    id: str
    index: str
    minute_ts: int
    ts_fired: int
    direction: str
    instrument_key: str
    trading_symbol: str
    strike: float
    expiry: str
    lot_size: int
    entry_price: float
    target_price: float
    stop_price: float
    target_basis: str
    target_points: float | None
    stop_points: float | None
    delta_used: float | None
    bias: float
    strength: int
    breakdown: dict[str, object]
    expires_at: int
    status: str
    status_ts: int
    entry_ask: float | None
    spread_pct: float | None
    entry_mode: str
    shadow: bool
    flow_score: float | None
    config_version: int | None
    outcome: OutcomeOut | None
    live: LiveLevelsOut | None = None  # while active; a paper trade takes these at its fill


class FlowOut(BaseModel):
    """Order-flow score for an index and its three parts, each -1 (selling) to +1 (buying)."""

    index: str
    ts: int
    score: float | None
    fut_book: float | None
    fut_trades: float | None
    options: float | None
    live: bool  # whether signals are firing on it, or it is only being recorded (shadow)


class GateOut(BaseModel):
    index: str
    minute_ts: int
    fired: bool
    reason: str | None


def outcome_out(s: Signal, o: Outcome) -> OutcomeOut:
    def pct(price: float) -> float:
        return round((price / s.entry_price - 1) * 100, 2)

    return OutcomeOut(
        result=o.result,
        result_ts=o.result_ts,
        end_ts=o.end_ts,
        best_price=o.best_price,
        best_ts=o.best_ts,
        best_pct=pct(o.best_price),
        worst_price=o.worst_price,
        worst_ts=o.worst_ts,
        worst_pct=pct(o.worst_price),
        px_1m=o.px_1m,
        px_5m=o.px_5m,
        px_15m=o.px_15m,
        spot_pre_move=o.spot_pre_move,
        spot_best_move=o.spot_best_move,
        late_share=None if o.late_share is None else round(o.late_share, 2),
        final=o.final,
    )


def signal_out(state: AppState, s: Signal) -> SignalOut:
    tracker = state.session.outcomes
    # before the feed starts there is no tracker, but past outcomes are stored
    o = tracker.get(s.id) if tracker is not None else OutcomeStore(state.conn).get(s.id)
    fields = asdict(s)
    return SignalOut(
        **{k: v for k, v in fields.items() if k != "breakdown_json"},
        breakdown=json.loads(s.breakdown_json),
        outcome=outcome_out(s, o) if o is not None else None,
        live=live_out(state, s),
    )


def live_out(state: AppState, s: Signal) -> LiveLevelsOut | None:
    """Live levels for a signal still waiting for the trader; None once it has ended."""
    if not s.is_active:
        return None
    desk = state.session.bullion_desk
    if s.index in METALS:
        live = desk.signals.live(s) if desk else None
    else:
        eng = state.session.signals
        live = eng.live(s) if eng else None
    return LiveLevelsOut(**asdict(live)) if live else None


def gate_out(g: Gate) -> GateOut:
    return GateOut(index=g.index, minute_ts=g.minute_ts, fired=g.fired, reason=g.reason)


def flow_out(state: AppState, r: FlowReading) -> FlowOut:
    return FlowOut(**asdict(r), live=state.params.params.signal.entry_mode == "trigger")


def flow_readings(state: AppState) -> list[FlowOut]:
    tracker = state.session.flow
    return [flow_out(state, r) for r in tracker.latest.values()] if tracker else []


def active_signals(state: AppState) -> list[SignalOut]:
    """Index and bullion signals that can still be paper-traded."""
    eng, desk = state.session.signals, state.session.bullion_desk
    out = list(eng.active.values()) if eng else []
    out += list(desk.signals.active.values()) if desk else []
    return [signal_out(state, s) for s in out]


def gates(state: AppState) -> list[GateOut]:
    eng, desk = state.session.signals, state.session.bullion_desk
    out = list(eng.gates.values()) if eng else []
    out += list(desk.signals.gates.values()) if desk else []
    return [gate_out(g) for g in out]


def today_signals(state: AppState, index: str | None = None) -> list[SignalOut]:
    eng = state.session.signals
    if eng is None:
        return []
    start, end = day_bounds_ms(state.clock.today())
    return [signal_out(state, s) for s in eng.store.read(start, end, index)]


@router.get("/signals", response_model=list[SignalOut])
async def list_signals(
    state: State, index: str | None = None, status: str | None = None, day: date | None = None
) -> list[SignalOut]:
    eng = state.session.signals
    if eng is None:
        return []
    start, end = day_bounds_ms(day or state.clock.today())
    out = [
        signal_out(state, s) for s in eng.store.read(start, end, index.upper() if index else None)
    ]
    return [s for s in out if status is None or s.status == status]


@router.get("/signals/active", response_model=list[SignalOut])
async def list_active(state: State) -> list[SignalOut]:
    return active_signals(state)


@router.get("/signals/gates", response_model=list[GateOut])
async def list_gates(state: State) -> list[GateOut]:
    return gates(state)


@router.get("/signals/scorecard", response_model=list[ScoreRowOut])
async def get_scorecard(
    state: State,
    index: str | None = None,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
) -> list[ScoreRowOut]:
    """How the signals of a date range turned out; today when no range is given."""
    eng, tracker = state.session.signals, state.session.outcomes
    today = state.clock.today()
    first, last = start or end or today, end or start or today
    if last < first:
        raise HTTPException(status_code=422, detail="'to' is before 'from'")
    if eng is None or tracker is None:
        return []
    tracker.flush()
    signals = [  # the yardstick scores NSE spot moves: bullion is not scored
        s
        for s in eng.store.read(
            day_bounds_ms(first)[0], day_bounds_ms(last)[1], index.upper() if index else None
        )
        if s.index not in METALS
    ]
    return [
        ScoreRowOut(**asdict(r)) for r in scorecard(signals, tracker.store.for_signals(signals))
    ]


@router.get("/flow", response_model=list[FlowOut])
async def list_flow(state: State) -> list[FlowOut]:
    return flow_readings(state)


@router.get("/signals/{signal_id}", response_model=SignalOut)
async def get_signal(signal_id: str, state: State) -> SignalOut:
    eng = state.session.signals
    s = eng.store.get(signal_id) if eng else None
    if s is None:
        raise HTTPException(status_code=404, detail="unknown signal")
    return signal_out(state, s)

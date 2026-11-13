"""Signals: active per index, history, and why the last minute did or did not fire."""

from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tradedisha.api.deps import State
from tradedisha.app_state import AppState
from tradedisha.engine.signals import Gate, Signal
from tradedisha.store.ticks import day_bounds_ms

router = APIRouter()


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


class GateOut(BaseModel):
    index: str
    minute_ts: int
    fired: bool
    reason: str | None


def signal_out(s: Signal) -> SignalOut:
    return SignalOut(
        id=s.id,
        index=s.index,
        minute_ts=s.minute_ts,
        ts_fired=s.ts_fired,
        direction=s.direction,
        instrument_key=s.instrument_key,
        trading_symbol=s.trading_symbol,
        strike=s.strike,
        expiry=s.expiry,
        lot_size=s.lot_size,
        entry_price=s.entry_price,
        target_price=s.target_price,
        stop_price=s.stop_price,
        target_basis=s.target_basis,
        target_points=s.target_points,
        stop_points=s.stop_points,
        delta_used=s.delta_used,
        bias=s.bias,
        strength=s.strength,
        breakdown=json.loads(s.breakdown_json),
        expires_at=s.expires_at,
        status=s.status,
        status_ts=s.status_ts,
    )


def gate_out(g: Gate) -> GateOut:
    return GateOut(index=g.index, minute_ts=g.minute_ts, fired=g.fired, reason=g.reason)


def active_signals(state: AppState) -> list[SignalOut]:
    eng = state.session.signals
    return [signal_out(s) for s in eng.active.values()] if eng else []


def gates(state: AppState) -> list[GateOut]:
    eng = state.session.signals
    return [gate_out(g) for g in eng.gates.values()] if eng else []


def today_signals(state: AppState, index: str | None = None) -> list[SignalOut]:
    eng = state.session.signals
    if eng is None:
        return []
    start, end = day_bounds_ms(state.clock.today())
    return [signal_out(s) for s in eng.store.read(start, end, index)]


@router.get("/signals", response_model=list[SignalOut])
def list_signals(
    state: State, index: str | None = None, status: str | None = None, day: date | None = None
) -> list[SignalOut]:
    eng = state.session.signals
    if eng is None:
        return []
    start, end = day_bounds_ms(day or state.clock.today())
    out = [signal_out(s) for s in eng.store.read(start, end, index.upper() if index else None)]
    return [s for s in out if status is None or s.status == status]


@router.get("/signals/active", response_model=list[SignalOut])
def list_active(state: State) -> list[SignalOut]:
    return active_signals(state)


@router.get("/signals/gates", response_model=list[GateOut])
def list_gates(state: State) -> list[GateOut]:
    return gates(state)


@router.get("/signals/{signal_id}", response_model=SignalOut)
def get_signal(signal_id: str, state: State) -> SignalOut:
    eng = state.session.signals
    s = eng.store.get(signal_id) if eng else None
    if s is None:
        raise HTTPException(status_code=404, detail="unknown signal")
    return signal_out(s)

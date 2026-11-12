"""Candles with overlays, bias with evidence, and the tunable parameters."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tradedisha.api.deps import State
from tradedisha.app_state import AppState
from tradedisha.clock import epoch_ms_now
from tradedisha.engine.bias_engine import BiasComputed, OverlayPoint
from tradedisha.events import ParametersChanged
from tradedisha.market.candles import Candle
from tradedisha.parameters import ParameterValidationError
from tradedisha.parameters.model import ParameterSet
from tradedisha.store.ticks import day_bounds_ms

router = APIRouter()


# -- schemas -------------------------------------------------------------------


class CandleOut(BaseModel):
    t: int
    o: float
    h: float
    l: float  # noqa: E741
    c: float
    v: int
    synthetic: bool


class OverlayOut(BaseModel):
    t: int
    ema_fast: float | None
    ema_slow: float | None
    vwap: float | None
    supertrend: float | None
    supertrend_dir: int


class CandlesResponse(BaseModel):
    index: str
    spot_key: str
    candles: list[CandleOut]
    overlays: list[OverlayOut]


class IndicatorOut(BaseModel):
    name: str
    group: str
    score: float
    note: str
    quality: str
    value: dict[str, float]
    weight: float
    contribution: float


class BiasOut(BaseModel):
    index: str
    minute_ts: int
    bias: float
    label: str
    strength: int
    is_expiry_day: bool
    group_scores: dict[str, float]
    group_weights: dict[str, float]
    indicators: list[IndicatorOut]


class BiasPoint(BaseModel):
    t: int
    bias: float
    label: str
    strength: int


class ParametersOut(BaseModel):
    loaded_at: int
    path: str
    params: ParameterSet


class ReloadError(BaseModel):
    field: str
    message: str


# -- converters ------------------------------------------------------------------


def candle_out(c: Candle) -> CandleOut:
    return CandleOut(
        t=c.minute_ts, o=c.open, h=c.high, l=c.low, c=c.close, v=c.volume, synthetic=c.synthetic
    )


def overlay_out(o: OverlayPoint) -> OverlayOut:
    return OverlayOut(
        t=o.minute_ts,
        ema_fast=o.ema_fast,
        ema_slow=o.ema_slow,
        vwap=o.vwap,
        supertrend=o.supertrend,
        supertrend_dir=o.supertrend_dir,
    )


def bias_out(b: BiasComputed) -> BiasOut:
    return BiasOut(
        index=b.index,
        minute_ts=b.minute_ts,
        bias=b.bias.bias,
        label=b.bias.label,
        strength=b.bias.strength,
        is_expiry_day=b.bias.is_expiry_day,
        group_scores=dict(b.bias.group_scores),
        group_weights=dict(b.bias.group_weights),
        indicators=[
            IndicatorOut(**asdict(c.result), weight=c.weight, contribution=c.contribution)
            for c in b.bias.contributions
        ],
    )


def candles_response(state: AppState, index: str, minutes: int) -> CandlesResponse:
    r = state.session.resolved[index]
    candles = state.session.candles.closed(r.spot.instrument_key)[-minutes:]
    engine = state.session.bias
    overlays = engine.overlays.get(index, [])[-minutes:] if engine else []
    return CandlesResponse(
        index=index,
        spot_key=r.spot.instrument_key,
        candles=[candle_out(c) for c in candles],
        overlays=[overlay_out(o) for o in overlays],
    )


def parameters_out(state: AppState) -> ParametersOut:
    cur = state.params.current
    return ParametersOut(loaded_at=cur.loaded_at, path=str(cur.path), params=cur.params)


def _index(state: AppState, index: str) -> str:
    key = index.upper()
    if key not in state.session.resolved:
        raise HTTPException(status_code=404, detail=f"unknown index {index}")
    return key


# -- routes -----------------------------------------------------------------------


@router.get("/candles/{index}", response_model=CandlesResponse)
def candles(index: str, state: State, minutes: int = 375) -> CandlesResponse:
    return candles_response(state, _index(state, index), max(1, min(minutes, 400)))


@router.get("/bias/{index}", response_model=BiasOut | None)
def bias(index: str, state: State) -> BiasOut | None:
    key = _index(state, index)
    engine = state.session.bias
    latest = engine.latest.get(key) if engine else None
    return bias_out(latest) if latest else None


@router.get("/bias/{index}/history", response_model=list[BiasPoint])
def bias_history(index: str, state: State, day: date | None = None) -> list[BiasPoint]:
    key = _index(state, index)
    engine = state.session.bias
    if engine is None:
        return []
    start, end = day_bounds_ms(day or state.clock.today())
    return [
        BiasPoint(t=r["minute_ts"], bias=r["bias"], label=r["label"], strength=r["strength"])
        for r in engine.history(key, start, end)
    ]


@router.get("/parameters", response_model=ParametersOut)
def parameters(state: State) -> ParametersOut:
    return parameters_out(state)


@router.post(
    "/parameters/reload",
    response_model=ParametersOut,
    responses={422: {"model": list[ReloadError]}},
)
async def reload_parameters(state: State) -> ParametersOut:
    try:
        loaded = state.params.reload()
    except ParameterValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors) from e
    next_minute = (epoch_ms_now() // 60_000 + 1) * 60_000
    await state.events.publish(ParametersChanged(loaded.loaded_at, next_minute))
    return parameters_out(state)

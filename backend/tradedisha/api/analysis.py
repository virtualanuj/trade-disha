"""Candles with overlays, bias with evidence, and the tunable parameters."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tradedisha.api.deps import State
from tradedisha.app_state import AppState
from tradedisha.engine.bias_engine import BiasComputed, OverlayPoint
from tradedisha.events import ParametersChanged
from tradedisha.market.candles import Candle
from tradedisha.parameters import ParameterValidationError
from tradedisha.parameters.model import ParameterSet
from tradedisha.parameters.schema import describe
from tradedisha.store.config_versions import ConfigVersion
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
    # Buyer- and seller-initiated volume (Milestone E8); None where the candle has no side
    # information: an index, or a minute backfilled from the candle API.
    bv: int | None = None
    sv: int | None = None


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
    fut_candles: list[CandleOut] = []  # the near-month future's, for net volume


class IndicatorOut(BaseModel):
    name: str
    group: str
    score: float
    note: str
    quality: str
    value: dict[str, float]
    weight: float
    contribution: float
    enabled: bool = True  # False: switched off in the Evidence panel (E15); absent before


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
    version: int
    tag: str
    created_ts: int
    params: ParameterSet


class ParameterFieldOut(BaseModel):
    path: str
    group: str
    key: str
    kind: str
    help: str
    ge: float | None
    gt: float | None
    le: float | None
    lt: float | None
    choices: list[str] | None


class ParametersIn(BaseModel):
    tag: str
    params: dict[str, Any]


class RevertIn(BaseModel):
    tag: str | None = None


class ConfigVersionOut(BaseModel):
    version: int
    tag: str
    created_ts: int
    source: str
    reverted_from: int | None
    active: bool


class ConfigVersionDetail(ConfigVersionOut):
    params: dict[str, Any]  # as stored; an old version may not match today's fields


class ReloadError(BaseModel):
    field: str
    message: str


# -- converters ------------------------------------------------------------------


def candle_out(c: Candle) -> CandleOut:
    return CandleOut(
        t=c.minute_ts,
        o=c.open,
        h=c.high,
        l=c.low,
        c=c.close,
        v=c.volume,
        synthetic=c.synthetic,
        bv=c.buy_volume,
        sv=c.sell_volume,
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
            IndicatorOut(
                **asdict(c.result),
                weight=c.weight,
                contribution=c.contribution,
                enabled=c.enabled,
            )
            for c in b.bias.contributions
        ],
    )


def candles_response(state: AppState, index: str, minutes: int) -> CandlesResponse:
    r = state.session.resolved[index]
    candles = state.session.candles.closed(r.spot.instrument_key)[-minutes:]
    fut = state.session.candles.closed(r.future.instrument_key)[-minutes:]
    engine = state.session.bias
    overlays = engine.overlays.get(index, [])[-minutes:] if engine else []
    return CandlesResponse(
        index=index,
        spot_key=r.spot.instrument_key,
        candles=[candle_out(c) for c in candles],
        overlays=[overlay_out(o) for o in overlays],
        fut_candles=[candle_out(c) for c in fut],
    )


def parameters_out(state: AppState) -> ParametersOut:
    cur = state.params.current
    return ParametersOut(
        version=cur.version, tag=cur.tag, created_ts=cur.created_ts, params=cur.params
    )


def _version_out(state: AppState, v: ConfigVersion) -> ConfigVersionOut:
    return ConfigVersionOut(
        version=v.version,
        tag=v.tag,
        created_ts=v.created_ts,
        source=v.source,
        reverted_from=v.reverted_from,
        active=v.version == state.params.current.version,
    )


async def _announce(state: AppState) -> ParametersOut:
    """Tell the screens; engines read the new set themselves at the next minute close
    of the market clock (in replay, the recorded day's)."""
    next_minute = (state.clock.now_ms() // 60_000 + 1) * 60_000
    await state.events.publish(ParametersChanged(state.params.current.version, next_minute))
    return parameters_out(state)


def _index(state: AppState, index: str) -> str:
    key = index.upper()
    if key not in state.session.resolved:
        raise HTTPException(status_code=404, detail=f"unknown index {index}")
    return key


# -- routes -----------------------------------------------------------------------


@router.get("/candles/{index}", response_model=CandlesResponse)
async def candles(index: str, state: State, minutes: int = 375) -> CandlesResponse:
    return candles_response(state, _index(state, index), max(1, min(minutes, 400)))


@router.get("/bias/{index}", response_model=BiasOut | None)
async def bias(index: str, state: State) -> BiasOut | None:
    key = _index(state, index)
    engine = state.session.bias
    latest = engine.latest.get(key) if engine else None
    return bias_out(latest) if latest else None


@router.get("/bias/{index}/history", response_model=list[BiasPoint])
async def bias_history(index: str, state: State, day: date | None = None) -> list[BiasPoint]:
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
async def parameters(state: State) -> ParametersOut:
    return parameters_out(state)


@router.get("/parameters/schema", response_model=list[ParameterFieldOut])
async def parameters_schema(state: State) -> list[ParameterFieldOut]:
    return [ParameterFieldOut(**asdict(f)) for f in describe(state.params.params)]


@router.put(
    "/parameters",
    response_model=ParametersOut,
    responses={422: {"model": list[ReloadError]}},
)
async def save_parameters(body: ParametersIn, state: State) -> ParametersOut:
    """Save edited values as a new version; it applies from the next minute close."""
    try:
        state.params.save_values(body.params, body.tag)
    except ParameterValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors) from e
    return await _announce(state)


@router.get("/parameters/versions", response_model=list[ConfigVersionOut])
async def parameter_versions(state: State) -> list[ConfigVersionOut]:
    return [_version_out(state, v) for v in state.params.versions()]


@router.get("/parameters/versions/{version}", response_model=ConfigVersionDetail)
async def parameter_version(version: int, state: State) -> ConfigVersionDetail:
    v = state.params.get(version)
    if v is None:
        raise HTTPException(status_code=404, detail=f"there is no config version {version}")
    return ConfigVersionDetail(
        **_version_out(state, v).model_dump(), params=json.loads(v.params_json)
    )


@router.post(
    "/parameters/versions/{version}/revert",
    response_model=ParametersOut,
    responses={422: {"model": list[ReloadError]}},
)
async def revert_parameters(version: int, body: RevertIn, state: State) -> ParametersOut:
    """Put an old version's values back in force, as a new version."""
    try:
        state.params.revert(version, body.tag)
    except ParameterValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors) from e
    return await _announce(state)


# -- factor switches (Milestone E16) ------------------------------------------------


class FactorIn(BaseModel):
    enabled: bool


@router.put(
    "/parameters/factors/{scope}/{name}",
    response_model=ParametersOut,
    responses={422: {"model": list[ReloadError]}},
)
async def set_factor(scope: str, name: str, body: FactorIn, state: State) -> ParametersOut:
    """Switch one factor of an index's or metal's bias on or off: a new version, tagged
    `Factor NIFTY.pcr: off`, from the next minute close. No version when already so."""
    before = state.params.current.version
    try:
        after = state.params.set_factor(scope, name, enabled=body.enabled).version
    except ParameterValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors) from e
    return await _announce(state) if after != before else parameters_out(state)

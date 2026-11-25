"""BULLION tab: gold and silver MCX futures, display only. Spec §6.6."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tradedisha.api.analysis import CandleOut, OverlayOut, candle_out
from tradedisha.api.deps import State
from tradedisha.app_state import AppState
from tradedisha.indicators.series import vwap_series
from tradedisha.market.candles import Candle

router = APIRouter()


class BullionMetalOut(BaseModel):
    metal: str
    trading_symbol: str
    expiry: date | None
    lot_size: int
    ltp: float | None
    prev_close: float | None
    change: float | None
    change_pct: float | None
    day_open: float | None
    day_high: float | None
    day_low: float | None
    range_pos: float | None
    atp: float | None
    volume: int | None
    oi: int | None
    bid: float | None
    ask: float | None
    bid_qty: int | None
    ask_qty: int | None
    spread: float | None
    tbq: int | None
    tsq: int | None
    buy_sell_ratio: float | None
    range_high: float | None
    range_low: float | None
    lower_circuit: float | None
    upper_circuit: float | None
    next_symbol: str | None
    next_expiry: date | None
    next_ltp: float | None
    calendar_spread: float | None
    calendar_spread_pct: float | None
    updated_ts: int | None


class BullionOut(BaseModel):
    metals: list[BullionMetalOut]
    ratio: float | None


class BullionCandlesOut(BaseModel):
    metal: str
    candles: list[CandleOut]
    overlays: list[OverlayOut]


def bullion_out(state: AppState) -> BullionOut:
    tracker = state.session.bullion
    if tracker is None:
        return BullionOut(metals=[], ratio=None)
    snap = tracker.snapshot()
    return BullionOut(metals=[BullionMetalOut(**asdict(m)) for m in snap.metals], ratio=snap.ratio)


def vwap_overlays(candles: list[Candle]) -> list[OverlayOut]:
    return [
        OverlayOut(
            t=c.minute_ts, ema_fast=None, ema_slow=None, vwap=v, supertrend=None, supertrend_dir=0
        )
        for c, v in zip(candles, vwap_series(candles), strict=True)
    ]


def bullion_candles(state: AppState, metal: str, minutes: int) -> BullionCandlesOut:
    """The near contract's closed candles with a VWAP line from the first one of the day."""
    tracker = state.session.bullion
    day = tracker.closed_candles(metal) if tracker else []
    overlays = vwap_overlays(day)[-minutes:]
    return BullionCandlesOut(
        metal=metal, candles=[candle_out(c) for c in day[-minutes:]], overlays=overlays
    )


def all_bullion_candles(state: AppState, minutes: int) -> list[BullionCandlesOut]:
    tracker = state.session.bullion
    return [bullion_candles(state, m, minutes) for m in (tracker.contracts if tracker else {})]


@router.get("/bullion", response_model=BullionOut)
async def bullion(state: State) -> BullionOut:
    """Gold and silver snapshot; no metals without the live feed."""
    return bullion_out(state)


@router.get("/bullion/{metal}/candles", response_model=BullionCandlesOut)
async def candles(metal: str, state: State, minutes: int = 900) -> BullionCandlesOut:
    tracker = state.session.bullion
    key = metal.upper()
    if tracker is None or key not in tracker.contracts:
        raise HTTPException(status_code=404, detail=f"no bullion contract for {metal}")
    return bullion_candles(state, key, minutes)

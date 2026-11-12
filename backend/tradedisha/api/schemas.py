"""Response models shared by REST and WebSocket."""

from __future__ import annotations

from pydantic import BaseModel


class FeedHealthOut(BaseModel):
    state: str
    last_tick_ts: int | None
    tick_age_ms: int | None
    reconnects: int
    subscribed: int
    provider: str


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    milestone: int
    market_status: str
    now_ms: int
    auth: str
    feed: FeedHealthOut
    replay_day: str | None


class InstrumentOut(BaseModel):
    instrument_key: str
    trading_symbol: str
    instrument_type: str
    expiry: str | None
    strike: float | None
    lot_size: int


class StrikePairOut(BaseModel):
    strike: float
    ce: InstrumentOut
    pe: InstrumentOut


class ResolvedIndexOut(BaseModel):
    index: str
    spot: InstrumentOut
    future: InstrumentOut
    options_expiry: str
    is_expiry_day: bool
    strike_step: float
    atm: float
    lot_size: int
    strikes: list[StrikePairOut]


class HopOut(BaseModel):
    hop: str
    n: int
    p50: float
    p95: float
    p99: float
    max: float


class MetricsResponse(BaseModel):
    last_1m: list[HopOut]
    last_15m: list[HopOut]


class ClientLatencyIn(BaseModel):
    """Per-minute summary posted by the browser."""

    out_to_recv_ms: list[float]
    recv_to_paint_ms: list[float]


class IndexPrices(BaseModel):
    index: str
    spot_ltp: float | None
    spot_ts: int | None
    fut_ltp: float | None
    fut_ts: int | None


class LegOut(BaseModel):
    ltp: float | None
    chg_pct: float | None
    oi: int | None
    oi_chg_open: int | None
    oi_chg_min: int | None
    iv: float | None
    buildup: str


class ChainRowOut(BaseModel):
    strike: float
    ce: LegOut
    pe: LegOut


class ChainOut(BaseModel):
    index: str
    expiry: str
    step: float
    atm: float
    spot: float | None
    pcr: float | None
    max_pain: float | None
    total_ce_oi: int
    total_pe_oi: int
    oi_baseline: str
    max_abs_oi_chg: int
    updated_ts: int | None
    rows: list[ChainRowOut]

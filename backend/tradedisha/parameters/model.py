"""Everything that shapes a recommendation, validated. Spec §3.2.

Units: percentages are percent (30 means 30 %), times are IST "HH:MM", durations are
minutes unless the name says seconds, and prices are rupees.
"""

from __future__ import annotations

from datetime import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Weights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trend: float = Field(0.40, ge=0, le=1)
    oi: float = Field(0.35, ge=0, le=1)
    premium: float = Field(0.25, ge=0, le=1)
    expiry_oi_weight_factor: float = Field(0.5, ge=0, le=1)

    @model_validator(mode="after")
    def _sum_to_one(self) -> Weights:
        total = self.trend + self.oi + self.premium
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"trend + oi + premium must equal 1.0, got {total:.4f}")
        return self


class Bias(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_threshold: float = Field(0.50, gt=0, le=1)
    setup_threshold: float = Field(0.35, gt=0, le=1)  # trigger mode: |bias| that sets up a signal
    neutral_band: float = Field(0.20, ge=0, lt=1)
    rearm_hysteresis: float = Field(0.0, ge=0, lt=1)

    @model_validator(mode="after")
    def _band_below_threshold(self) -> Bias:
        if self.neutral_band >= self.entry_threshold:
            raise ValueError("neutral_band must be below entry_threshold")
        if not self.neutral_band < self.setup_threshold <= self.entry_threshold:
            raise ValueError(
                "setup_threshold must be above neutral_band and no higher than entry_threshold"
            )
        return self


class Trend(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ema_fast: int = Field(9, ge=2, le=200)
    ema_slow: int = Field(21, ge=3, le=400)
    ema_k: float = Field(8.0, gt=0)
    vwap_full_pct: float = Field(0.3, gt=0)
    supertrend_period: int = Field(10, ge=2, le=100)
    supertrend_mult: float = Field(3.0, gt=0)
    supertrend_ramp_bars: int = Field(3, ge=1)

    @model_validator(mode="after")
    def _fast_below_slow(self) -> Trend:
        if self.ema_fast >= self.ema_slow:
            raise ValueError("ema_fast must be smaller than ema_slow")
        return self


class OI(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pcr_strike_range: int = Field(5, ge=0, le=20)
    pcr_centre: float = Field(1.0, gt=0)
    pcr_full_dev: float = Field(0.5, gt=0)
    oi_change_strike_range: int = Field(2, ge=0, le=20)
    maxpain_drift_minutes: int = Field(15, ge=1, le=60)
    maxpain_full_steps: float = Field(2.0, gt=0)


class Premium(BaseModel):
    model_config = ConfigDict(extra="forbid")
    premium_roc_minutes: int = Field(5, ge=1, le=60)
    premium_roc_full_spread: float = Field(20.0, gt=0)
    iv_change_minutes: int = Field(15, ge=1, le=60)
    iv_full_change: float = Field(2.0, gt=0)
    confirmation_minutes: int = Field(5, ge=1, le=60)
    divergence_score: float = Field(-0.5, ge=-1, le=0)


class Flow(BaseModel):
    """Order-flow score and the trigger that reads it. Spec §8.5, §9.6."""

    model_config = ConfigDict(extra="forbid")
    window_seconds: float = Field(15.0, gt=0, le=300)
    trigger_score: float = Field(0.25, gt=0, le=1)
    hold_seconds: float = Field(5.0, ge=0, le=120)
    w_fut_book: float = Field(0.4, ge=0, le=1)
    w_fut_trades: float = Field(0.3, ge=0, le=1)
    w_options: float = Field(0.3, ge=0, le=1)

    @model_validator(mode="after")
    def _sum_to_one(self) -> Flow:
        total = self.w_fut_book + self.w_fut_trades + self.w_options
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"w_fut_book + w_fut_trades + w_options must equal 1.0, got {total:.4f}"
            )
        return self


class ExpiryPoints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: float = Field(gt=0)
    stop: float = Field(gt=0)


class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signal_ttl_seconds: int = Field(300, ge=30, le=3600)
    target_pct: float = Field(30.0, gt=0)
    stop_pct: float = Field(-15.0, lt=0, gt=-100)
    expiry_points: dict[str, ExpiryPoints] = Field(
        default_factory=lambda: {
            "NIFTY": ExpiryPoints(target=40, stop=20),
            "BANKNIFTY": ExpiryPoints(target=100, stop=50),
        }
    )
    outcome_horizon_minutes: int = Field(30, ge=1, le=375)
    entry_mode: Literal["minute_close", "trigger"] = "minute_close"
    max_spread_pct: float = Field(1.0, gt=0, le=100)  # trigger mode: widest bid-ask spread allowed
    last_signal_time: time = time(15, 0)
    last_signal_time_expiry: time = time(13, 0)

    @field_validator("last_signal_time", "last_signal_time_expiry", mode="before")
    @classmethod
    def _parse_time(cls, v: object) -> object:
        if isinstance(v, str):
            h, m = v.split(":")
            return time(int(h), int(m))
        return v


class Chain(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strike_window: int = Field(10, ge=1, le=40)
    recenter_strikes: int = Field(2, ge=1, le=10)


class Paper(BaseModel):
    model_config = ConfigDict(extra="forbid")
    square_off_time: time = time(15, 15)
    cost_per_trade: float = Field(60.0, ge=0)
    lots: int = Field(1, ge=1, le=100)

    @field_validator("square_off_time", mode="before")
    @classmethod
    def _parse_time(cls, v: object) -> object:
        if isinstance(v, str):
            h, m = v.split(":")
            return time(int(h), int(m))
        return v


class ParameterSet(BaseModel):
    """The whole tunable configuration. Unknown keys are rejected so typos surface."""

    model_config = ConfigDict(extra="forbid")
    weights: Weights = Field(default_factory=Weights)
    bias: Bias = Field(default_factory=Bias)
    trend: Trend = Field(default_factory=Trend)
    oi: OI = Field(default_factory=OI)
    premium: Premium = Field(default_factory=Premium)
    flow: Flow = Field(default_factory=Flow)
    signal: Signal = Field(default_factory=Signal)
    chain: Chain = Field(default_factory=Chain)
    paper: Paper = Field(default_factory=Paper)

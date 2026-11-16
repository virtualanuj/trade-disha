"""Everything that shapes a recommendation, validated. Spec §3.2.

Units: percentages are percent (30 means 30 %), times are IST "HH:MM", durations are
minutes unless the name says seconds, and prices are rupees.
"""

from __future__ import annotations

from datetime import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _time(v: object) -> object:
    """ "15:00" as typed, or "15:00:00" as stored; anything else is left to the validator."""
    if isinstance(v, str):
        try:
            return time.fromisoformat(v.strip())
        except ValueError:
            return v
    return v


class Weights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trend: float = Field(
        0.40,
        ge=0,
        le=1,
        description=(
            "Share of the bias carried by the price-trend group. The three shares must sum to 1."
        ),
    )
    oi: float = Field(
        0.35, ge=0, le=1, description="Share of the bias carried by the open-interest group."
    )
    premium: float = Field(
        0.25, ge=0, le=1, description="Share of the bias carried by the premium-behaviour group."
    )
    expiry_oi_weight_factor: float = Field(
        0.5,
        ge=0,
        le=1,
        description=(
            "On expiry day the OI share is multiplied by this; the rest goes to the other "
            "two groups."
        ),
    )

    @model_validator(mode="after")
    def _sum_to_one(self) -> Weights:
        total = self.trend + self.oi + self.premium
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"trend + oi + premium must equal 1.0, got {total:.4f}")
        return self


class Bias(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_threshold: float = Field(
        0.50,
        gt=0,
        le=1,
        description="|bias| at which a signal fires at a minute close (entry mode minute_close).",
    )
    setup_threshold: float = Field(
        0.35,
        gt=0,
        le=1,
        description=(
            "|bias| that sets a direction up, waiting for order flow (entry mode trigger). "
            "Above the neutral band, no higher than the entry threshold."
        ),
    )
    neutral_band: float = Field(
        0.20,
        ge=0,
        lt=1,
        description="|bias| below this is labelled Neutral, and an active signal is reversed.",
    )
    rearm_hysteresis: float = Field(
        0.0,
        ge=0,
        lt=1,
        description=(
            "0 = off. Above 0, |bias| must dip below threshold minus this before the same "
            "direction can fire again."
        ),
    )

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
    ema_fast: int = Field(
        9,
        ge=2,
        le=200,
        description="Minutes in the fast EMA of spot closes. Must be smaller than the slow EMA.",
    )
    ema_slow: int = Field(21, ge=3, le=400, description="Minutes in the slow EMA of spot closes.")
    ema_k: float = Field(
        8.0,
        gt=0,
        description=(
            "Steepness of the EMA-separation score (tanh of this times the separation in % "
            "of the slow EMA)."
        ),
    )
    vwap_full_pct: float = Field(
        0.3, gt=0, description="Distance of futures from VWAP, in %, that counts as full strength."
    )
    supertrend_period: int = Field(
        10, ge=2, le=100, description="ATR period of the supertrend line, in minutes."
    )
    supertrend_mult: float = Field(
        3.0, gt=0, description="ATR multiple the supertrend line trails the price by."
    )
    supertrend_ramp_bars: int = Field(
        3, ge=1, description="Bars after a supertrend flip until its vote is at full strength."
    )

    @model_validator(mode="after")
    def _fast_below_slow(self) -> Trend:
        if self.ema_fast >= self.ema_slow:
            raise ValueError("ema_fast must be smaller than ema_slow")
        return self


class OI(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pcr_strike_range: int = Field(
        5, ge=0, le=20, description="Strikes each side of ATM used for the put-call ratio."
    )
    pcr_centre: float = Field(1.0, gt=0, description="Put-call ratio considered neutral.")
    pcr_full_dev: float = Field(
        0.5,
        gt=0,
        description="Distance of the put-call ratio from the centre that counts as full strength.",
    )
    oi_change_strike_range: int = Field(
        2, ge=0, le=20, description="Strikes each side of ATM used for the OI build-up vote."
    )
    maxpain_drift_minutes: int = Field(
        15, ge=1, le=60, description="Minutes over which the max-pain drift is measured."
    )
    maxpain_full_steps: float = Field(
        2.0, gt=0, description="Max-pain drift, in strike steps, that counts as full strength."
    )


class Premium(BaseModel):
    model_config = ConfigDict(extra="forbid")
    premium_roc_minutes: int = Field(
        5,
        ge=1,
        le=60,
        description="Minutes over which the ATM call and put rate of change is compared.",
    )
    premium_roc_full_spread: float = Field(
        20.0,
        gt=0,
        description=(
            "Call minus put rate-of-change spread, in percentage points, for full strength."
        ),
    )
    iv_change_minutes: int = Field(
        15, ge=1, le=60, description="Minutes over which the change in ATM IV is measured."
    )
    iv_full_change: float = Field(
        2.0, gt=0, description="Rise in IV, in percentage points, that counts as full strength."
    )
    confirmation_minutes: int = Field(
        5, ge=1, le=60, description="Minutes of spot move that the premiums are asked to confirm."
    )
    divergence_score: float = Field(
        -0.5,
        ge=-1,
        le=0,
        description="Vote, against the move, when premiums disagree with the spot move (-1 to 0).",
    )


class Flow(BaseModel):
    """Order-flow score and the trigger that reads it. Spec §8.5, §9.6."""

    model_config = ConfigDict(extra="forbid")
    window_seconds: float = Field(
        15.0,
        gt=0,
        le=300,
        description="Seconds over which book imbalance and signed trades are smoothed.",
    )
    trigger_score: float = Field(
        0.25,
        gt=0,
        le=1,
        description="Order-flow score, in the setup's direction, needed to fire a trigger signal.",
    )
    hold_seconds: float = Field(
        5.0,
        ge=0,
        le=120,
        description="Seconds the order-flow score must stay there before the signal fires.",
    )
    w_fut_book: float = Field(
        0.4,
        ge=0,
        le=1,
        description=(
            "Share of the flow score from the futures order book. The three shares must sum to 1."
        ),
    )
    w_fut_trades: float = Field(
        0.3, ge=0, le=1, description="Share of the flow score from signed futures trades."
    )
    w_options: float = Field(
        0.3,
        ge=0,
        le=1,
        description="Share of the flow score from ATM call flow minus ATM put flow.",
    )

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
    target: float = Field(
        gt=0,
        description=(
            "Expiry day: index points in the signal's favour at which the target sits "
            "(converted with delta)."
        ),
    )
    stop: float = Field(
        gt=0,
        description=(
            "Expiry day: index points against the signal at which the stop sits (converted "
            "with delta)."
        ),
    )


class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signal_ttl_seconds: int = Field(
        300, ge=30, le=3600, description="Seconds an untraded signal stays active before it lapses."
    )
    target_pct: float = Field(
        30.0, gt=0, description="Target, as % above the entry price (not used on expiry day)."
    )
    stop_pct: float = Field(
        -15.0,
        lt=0,
        gt=-100,
        description="Stop, as % below the entry price, written negative (not used on expiry day).",
    )
    expiry_points: dict[str, ExpiryPoints] = Field(
        description="Expiry-day target and stop per index, in index points.",
        default_factory=lambda: {
            "NIFTY": ExpiryPoints(target=40, stop=20),
            "BANKNIFTY": ExpiryPoints(target=100, stop=50),
        },
    )
    outcome_horizon_minutes: int = Field(
        30, ge=1, le=375, description="Minutes each signal's option is followed to score it."
    )
    entry_mode: Literal["minute_close", "trigger"] = Field(
        "minute_close",
        description=(
            "The live entry rule: minute_close fires at a minute close on the entry "
            "threshold; trigger sets up, then waits for order flow. The other rule runs in "
            "shadow."
        ),
    )
    max_spread_pct: float = Field(
        1.0,
        gt=0,
        le=100,
        description=(
            "Trigger mode: widest bid-ask spread, as % of the mid price, at which a signal "
            "may fire."
        ),
    )
    last_signal_time: time = Field(
        time(15, 0), description="No signal fires at or after this time (IST, HH:MM)."
    )
    last_signal_time_expiry: time = Field(
        time(13, 0), description="The same cut-off on expiry day (IST, HH:MM)."
    )

    @field_validator("last_signal_time", "last_signal_time_expiry", mode="before")
    @classmethod
    def _parse_time(cls, v: object) -> object:
        return _time(v)


class Chain(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strike_window: int = Field(
        10, ge=1, le=40, description="Strikes each side of ATM kept in the option chain."
    )
    recenter_strikes: int = Field(
        2,
        ge=1,
        le=10,
        description="Strikes spot must move from the chain's centre before the chain re-centres.",
    )


class Paper(BaseModel):
    model_config = ConfigDict(extra="forbid")
    square_off_time: time = Field(
        time(15, 15), description="Open paper trades are closed at this time (IST, HH:MM)."
    )
    cost_per_trade: float = Field(60.0, ge=0, description="Rupees charged per round trip, per lot.")
    lots: int = Field(1, ge=1, le=100, description="Lots bought per paper trade.")

    @field_validator("square_off_time", mode="before")
    @classmethod
    def _parse_time(cls, v: object) -> object:
        return _time(v)


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

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
            "On expiry day the OI share is multiplied by this; the rest goes to the other groups."
        ),
    )
    macro: float = Field(
        0.10,
        ge=0,
        le=0.5,
        description=(
            "Share of the bias carried by the macro group (dollar, USD/INR, crude, gold). "
            "Trend, OI and premium keep their proportions within the rest. When no macro "
            "price is live (for example the currency market after 17:00) its share goes back "
            "to the other groups."
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


class Macro(BaseModel):
    """Macro evidence (spec §8.6): each instrument's move over a window of 1-minute closes."""

    model_config = ConfigDict(extra="forbid")
    window_minutes: int = Field(
        30, ge=1, le=240, description="Minutes over which each macro instrument's move is measured."
    )
    max_age_seconds: int = Field(
        180,
        ge=30,
        le=1800,
        description=(
            "A macro price older than this is not live (its market is shut or silent) and "
            "carries no weight."
        ),
    )
    dollar_full_pct: float = Field(
        0.15,
        gt=0,
        le=10,
        description="Dollar-index proxy move (%) over the window that counts as full strength.",
    )
    usdinr_full_pct: float = Field(
        0.10,
        gt=0,
        le=10,
        description="USD/INR move (%) over the window that counts as full strength.",
    )
    crude_full_pct: float = Field(
        0.80,
        gt=0,
        le=20,
        description="Crude oil move (%) over the window that counts as full strength.",
    )
    gold_full_pct: float = Field(
        0.40, gt=0, le=10, description="Gold move (%) over the window that counts as full strength."
    )
    gift_full_pct: float = Field(
        0.50,
        gt=0,
        le=10,
        description=(
            "NIFTY only: GIFT Nifty's overnight move (%), from its price at the previous NSE "
            "close to its last before 09:15, that counts as full strength."
        ),
    )
    gift_fade_minutes: int = Field(
        30,
        ge=1,
        le=375,
        description=(
            "Minutes after the open over which the GIFT Nifty gap vote fades to nothing; "
            "after that it is shown, not scored."
        ),
    )
    gift_direction: Literal["follow", "fade"] = Field(
        "follow",
        description=(
            "follow: a gap up is bullish (the gap carries on); fade: a gap up is bearish "
            "(the gap fills)."
        ),
    )


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


class Bank(BaseModel):
    """The paper bank that funds paper trades (Milestone E17). Spec §10.5."""

    model_config = ConfigDict(extra="forbid")
    opening_balance: float = Field(
        2_500_000.0,
        gt=0,
        le=10_000_000_000,
        description=(
            "Rupees put into the paper bank. A paper trade opens only if the bank can block "
            "its money (an option's premium, a future's margin, plus cost). Raising this "
            "deposits the difference, lowering it withdraws it; P&L made so far is kept."
        ),
    )


class Bullion(BaseModel):
    """MCX GOLD and SILVER near-month futures, long or short. Spec §9a.

    Evidence: trend, the future's open-interest build-up, order flow, and other markets
    (the dollar, the other metal), each with a share of the bias.
    """

    model_config = ConfigDict(extra="forbid")
    signals: Literal["on", "off"] = Field(
        "on", description="Bullion signals on or off. Off keeps the tab display only."
    )
    entry_threshold: float = Field(
        0.60,
        gt=0,
        le=1,
        description=(
            "|bias| at which a bullion signal fires. Bullion has no option chain, so its "
            "bias rests mostly on trend and moves further than the index bias."
        ),
    )
    neutral_band: float = Field(
        0.20,
        ge=0,
        lt=1,
        description="Bullion |bias| below this is Neutral, and an active bullion signal reverses.",
    )
    rearm_hysteresis: float = Field(
        0.0,
        ge=0,
        lt=1,
        description=(
            "0 = off. Above 0, bullion |bias| must dip below the threshold minus this before "
            "the same direction can fire again."
        ),
    )
    signal_ttl_seconds: int = Field(
        300, ge=30, le=3600, description="Seconds an untraded bullion signal stays active."
    )
    eval_offset_seconds: int = Field(
        20,
        ge=0,
        le=50,
        description=(
            "Seconds after each minute close at which bullion bias and signals are worked "
            "out, so they never run at the same instant as the index engines."
        ),
    )
    first_signal_time: time = Field(
        time(9, 15), description="No bullion signal fires before this time (IST, HH:MM)."
    )
    last_signal_time: time = Field(
        time(22, 45), description="No bullion signal fires at or after this time (IST, HH:MM)."
    )
    square_off_time: time = Field(
        time(23, 0), description="Open bullion paper trades are closed at this time (IST, HH:MM)."
    )
    target_pct: float = Field(
        0.40,
        gt=0,
        le=10,
        description="Target, as % of the future's price in the signal's favour.",
    )
    stop_pct: float = Field(
        0.20,
        gt=0,
        le=10,
        description="Stop, as % of the future's price against the signal.",
    )
    gold_contract: Literal["GOLD", "GOLDM"] = Field(
        "GOLD",
        description=(
            "The future a GOLD signal's paper trade opens: GOLD (1 kg, ₹100 a point) or "
            "GOLDM (100 g, ₹10 a point). The signal itself always reads GOLD."
        ),
    )
    silver_contract: Literal["SILVER", "SILVERM"] = Field(
        "SILVER",
        description=(
            "The future a SILVER signal's paper trade opens: SILVER (30 kg, ₹30 a point) "
            "or SILVERM (5 kg, ₹5 a point). The signal itself always reads SILVER."
        ),
    )
    gold_lots: int = Field(1, ge=1, le=100, description="Default lots of a GOLD paper trade.")
    goldm_lots: int = Field(1, ge=1, le=100, description="Default lots of a GOLDM paper trade.")
    silver_lots: int = Field(1, ge=1, le=100, description="Default lots of a SILVER paper trade.")
    silverm_lots: int = Field(1, ge=1, le=100, description="Default lots of a SILVERM paper trade.")
    event_pause_before_minutes: int = Field(
        15,
        ge=0,
        le=120,
        description=(
            "Minutes before each US data release in config/us-events.txt (CPI, payrolls, "
            "Fed) from which no bullion signal fires. 0 with the after value 0 = no pause."
        ),
    )
    event_pause_after_minutes: int = Field(
        15,
        ge=0,
        le=120,
        description="Minutes after each US data release for which bullion signals stay paused.",
    )
    event_end_waiting: Literal["on", "off"] = Field(
        "off",
        description=(
            "On: a bullion signal still waiting when a US-release pause starts is ended "
            "(lapsed), so it is not traded into the release."
        ),
    )
    event_block_trades: Literal["on", "off"] = Field(
        "off",
        description=(
            "On: opening a bullion paper trade by hand is refused during a US-release pause. "
            "Open trades are never touched."
        ),
    )
    macro_weight: float = Field(
        0.10,
        ge=0,
        le=0.5,
        description=(
            "Share of the bullion bias carried by other markets: the dollar (dollar-index "
            "proxy and USD/INR) and the other metal's trend. Trend has what the OI, flow and "
            "macro shares leave; a share with no live reading goes to the other groups."
        ),
    )
    oi_weight: float = Field(
        0.15,
        ge=0,
        le=0.5,
        description=(
            "Share of the bullion bias carried by the future's open-interest build-up. Goes "
            "to the other groups while it warms up."
        ),
    )
    flow_weight: float = Field(
        0.15,
        ge=0,
        le=0.5,
        description=(
            "Share of the bullion bias carried by order flow: net traded volume and the "
            "order book's lean. Goes to the other groups while it warms up."
        ),
    )
    oi_window_minutes: int = Field(
        15,
        ge=2,
        le=120,
        description="Minutes over which the future's price and open-interest changes are read.",
    )
    oi_full_pct: float = Field(
        0.50,
        gt=0,
        le=10,
        description="Open-interest change (%) over the window that counts as full strength.",
    )
    oi_price_flat_pct: float = Field(
        0.02,
        ge=0,
        le=2,
        description="A price move (%) over the window smaller than this is flat: no build-up.",
    )
    oi_unwind_factor: float = Field(
        0.5,
        ge=0,
        le=1,
        description=(
            "Falling open interest (short covering, long unwinding) is weaker evidence than "
            "new positions; its score is scaled by this."
        ),
    )
    flow_window_minutes: int = Field(
        15,
        ge=1,
        le=120,
        description=(
            "Minutes of signed traded volume (buys at the ask less sells at the bid) behind "
            "the net-volume vote."
        ),
    )
    flow_trades_full: float = Field(
        0.50,
        gt=0,
        le=1,
        description="Net volume as a share of all traded volume that counts as full strength.",
    )
    flow_book_minutes: int = Field(
        30,
        ge=5,
        le=240,
        description=(
            "Minutes over which the order book's usual lean is averaged; the book vote reads "
            "the lean now against that average."
        ),
    )
    flow_book_full: float = Field(
        0.20,
        gt=0,
        le=2,
        description="Book lean above its average (on a -1..+1 scale) that counts as full strength.",
    )
    cost_fixed_per_lot: float = Field(
        60.0, ge=0, description="Rupees per round trip per lot: brokerage and fixed fees."
    )
    cost_pct_of_value: float = Field(
        0.012,
        ge=0,
        le=1,
        description=(
            "Charges that scale with value (CTT, exchange, stamp duty, GST), as % of the "
            "round-trip turnover. A GOLD lot is worth over a crore, so a flat fee alone "
            "understates them."
        ),
    )
    gold_margin_pct: float = Field(
        10.0,
        gt=0,
        le=100,
        description=(
            "Margin a GOLD paper trade blocks in the paper bank, as % of the contract's "
            "value (price x quantity). The round-trip cost is blocked on top."
        ),
    )
    silver_margin_pct: float = Field(
        12.0,
        gt=0,
        le=100,
        description=(
            "Margin a SILVER paper trade blocks in the paper bank, as % of the contract's "
            "value (price x quantity). The round-trip cost is blocked on top."
        ),
    )

    def margin_pct(self, metal: str) -> float:
        return self.gold_margin_pct if metal == "GOLD" else self.silver_margin_pct

    def contract_for(self, metal: str) -> str:
        """The contract a metal's signal trade opens: the full future or its mini."""
        return self.gold_contract if metal == "GOLD" else self.silver_contract

    def lots_for(self, contract: str) -> int:
        """Default lots for a contract (GOLD, GOLDM, SILVER, SILVERM)."""
        return {
            "GOLD": self.gold_lots,
            "GOLDM": self.goldm_lots,
            "SILVER": self.silver_lots,
            "SILVERM": self.silverm_lots,
        }.get(contract, 1)

    @model_validator(mode="before")
    @classmethod
    def _legacy_lots(cls, data: object) -> object:
        """A version saved before E28 has one `lots` for every bullion trade: it becomes
        each contract's default, so that version still loads."""
        if isinstance(data, dict) and "lots" in data:
            data = dict(data)
            lots = data.pop("lots")
            for name in ("gold_lots", "goldm_lots", "silver_lots", "silverm_lots"):
                data.setdefault(name, lots)
        return data

    @field_validator("first_signal_time", "last_signal_time", "square_off_time", mode="before")
    @classmethod
    def _parse_time(cls, v: object) -> object:
        return _time(v)

    @model_validator(mode="after")
    def _consistent(self) -> Bullion:
        if self.neutral_band >= self.entry_threshold:
            raise ValueError("bullion neutral_band must be below entry_threshold")
        if not self.first_signal_time < self.last_signal_time <= self.square_off_time:
            raise ValueError("bullion times must run first signal < last signal <= square-off")
        if self.oi_weight + self.flow_weight + self.macro_weight >= 1:
            raise ValueError("bullion oi, flow and macro weights must leave trend a share")
        return self


class News(BaseModel):
    """The Headlines panel (spec §6.7). Display only: nothing here shapes a signal."""

    model_config = ConfigDict(extra="forbid")
    poll_seconds: int = Field(
        180,
        ge=30,
        le=3600,
        description=(
            "Seconds between asks to Upstox for headlines while logged in. Unlike the signal "
            "parameters, a change applies as soon as it is saved."
        ),
    )


# -- factor switches (Milestone E16) ---------------------------------------------------

OnOff = Literal["on", "off"]


def _switch(label: str) -> OnOff:
    return Field("on", description=f"{label}: off leaves it out of the bias.")


class IndexFactors(BaseModel):
    """Each factor of an index's bias, on or off. Changed only by a switch in Config."""

    model_config = ConfigDict(extra="forbid")
    ema_cross: OnOff = _switch("EMA crossover (trend)")
    vwap_position: OnOff = _switch("Futures vs VWAP (trend)")
    supertrend: OnOff = _switch("Supertrend (trend)")
    pcr: OnOff = _switch("Put-call ratio (open interest)")
    oi_change_atm: OnOff = _switch("ATM OI build-up (open interest)")
    max_pain_drift: OnOff = _switch("Max-pain drift (open interest)")
    premium_momentum: OnOff = _switch("CE vs PE momentum (premium)")
    iv_change: OnOff = _switch("IV change (premium)")
    premium_confirmation: OnOff = _switch("Premium confirmation (premium)")
    dollar_index: OnOff = _switch("Dollar index proxy (macro)")
    usd_inr: OnOff = _switch("USD/INR (macro)")
    crude: OnOff = _switch("Crude oil (macro)")
    gold: OnOff = _switch("Gold (macro)")
    silver: OnOff = _switch("Silver (macro, shown only)")


class NiftyFactors(IndexFactors):
    gift_nifty: OnOff = _switch("GIFT Nifty gap (macro)")


class BullionFactors(BaseModel):
    """Each factor of a metal's bias, on or off. Changed only by a switch in Config."""

    model_config = ConfigDict(extra="forbid")
    ema_cross: OnOff = _switch("EMA crossover (trend)")
    vwap_position: OnOff = _switch("Futures vs VWAP (trend)")
    supertrend: OnOff = _switch("Supertrend (trend)")
    futures_oi: OnOff = _switch("Futures OI build-up (open interest)")
    net_volume: OnOff = _switch("Net traded volume (order flow)")
    book_imbalance: OnOff = _switch("Order-book lean (order flow)")
    dollar_index: OnOff = _switch("Dollar index proxy (macro)")
    usd_inr: OnOff = _switch("USD/INR (macro)")
    peer_metal: OnOff = _switch("Other metal's trend (macro)")


# scope as the engines name it -> the field of `Factors` holding its switches
FACTOR_SCOPES: dict[str, str] = {
    "NIFTY": "nifty",
    "BANKNIFTY": "banknifty",
    "GOLD": "gold",
    "SILVER": "silver",
}


class Factors(BaseModel):
    """Factor switches per index and metal (spec §8.4). Each flip in Config is a version."""

    model_config = ConfigDict(extra="forbid")
    nifty: NiftyFactors = Field(default_factory=NiftyFactors)
    banknifty: IndexFactors = Field(default_factory=IndexFactors)
    gold: BullionFactors = Field(default_factory=BullionFactors)
    silver: BullionFactors = Field(default_factory=BullionFactors)

    def scope_model(self, scope: str) -> BaseModel | None:
        field = FACTOR_SCOPES.get(scope)
        if field is None:
            return None
        m: BaseModel = getattr(self, field)
        return m

    def off_for(self, scope: str) -> frozenset[str]:
        """The factors switched off for an index or metal; none for an unknown scope."""
        m = self.scope_model(scope)
        if m is None:
            return frozenset()
        return frozenset(k for k, v in m.model_dump().items() if v == "off")


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
    bank: Bank = Field(default_factory=Bank)
    bullion: Bullion = Field(default_factory=Bullion)
    news: News = Field(default_factory=News)
    macro: Macro = Field(default_factory=Macro)
    factors: Factors = Field(default_factory=Factors)

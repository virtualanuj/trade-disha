"""Bullion signals: buy or sell an MCX near-month future (GOLD, GOLDM, SILVER or SILVERM,
each a market of its own, E29). Spec §9a.

The minute-close rule only: when a metal's trend bias reaches `bullion.entry_threshold`,
a long (`BUY_FUT`) or short (`SELL_FUT`) signal fires at the future's latest price, with
target and stop a percentage of that price either side. One active signal per metal; it
lapses after its TTL, reverses when the bias flips sign or falls inside the neutral band,
or ends when it is paper-traded. Gates: signals switched on, MCX open and inside the
bullion signal hours, no US data release near (E18), and bullion prices live. The index
engines and NSE hours play no part, and nothing here sends an order: paper only.

Rows go to the shared `signals` table: `index` is the metal, `strike` 0, `expiry` the
future's expiry, and `lot_size` the rupees per point per lot (`qty_multiplier`).
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from collections.abc import Callable, Sequence
from dataclasses import replace

from tradedisha.clock import MarketClock, ms_to_ist
from tradedisha.engine.bias_engine import BiasComputed, breakdown_json
from tradedisha.engine.signals import (
    FUTURE_DIRECTIONS,
    Direction,
    Gate,
    LiveLevels,
    ManualContract,
    NoFireReason,
    Signal,
    SignalStore,
    Status,
    rescale_levels,
    round_levels,
)
from tradedisha.market.bullion import BullionTracker
from tradedisha.market.us_events import UsEvent, event_in_window
from tradedisha.parameters.model import ParameterSet

log = logging.getLogger(__name__)


def future_levels(direction: Direction, entry: float, p: ParameterSet) -> tuple[float, float]:
    """Target and stop for a future entered at `entry`: a percentage of the price in the
    trade's favour and against it, in whole rupees. Signals and paper trades opened by hand
    use this rule."""
    side = -1 if direction == "SELL_FUT" else 1
    target = entry * (1 + side * p.bullion.target_pct / 100)
    stop = entry * (1 - side * p.bullion.stop_pct / 100)
    return round_levels(direction, entry, target, stop)


class BullionSignalEngine:
    def __init__(  # noqa: PLR0913 -- injected collaborators
        self,
        *,
        tracker: BullionTracker,
        clock: MarketClock,
        params: Callable[[], ParameterSet],
        conn: sqlite3.Connection,
        feed_live: Callable[[], bool],
        enforce_hours: bool,
        on_signal: Callable[[Signal], None] | None = None,
        config_version: Callable[[], int | None] | None = None,
        events: Sequence[UsEvent] = (),
    ) -> None:
        self._tracker = tracker
        self._events = events
        self._clock = clock
        self._params = params
        self.store = SignalStore(conn)
        self._feed_live = feed_live
        self._enforce_hours = enforce_hours
        self._on_signal = on_signal
        self._config_version = config_version
        self.active: dict[str, Signal] = {}
        self.gates: dict[str, Gate] = {}
        self._rearm_block: dict[str, Direction] = {}

    # -- inputs ----------------------------------------------------------------

    def on_bias(self, b: BiasComputed, now: int) -> None:
        """A metal's minute, evaluated at `now` (the minute close plus the offset)."""
        p = self._params()
        metal = b.index
        bias = b.bias.bias
        threshold = p.bullion.entry_threshold
        self._expire_lapsed(now)
        self._end_waiting_for_event(now, p)

        current = self.active.get(metal)
        if current is not None and self._reversed(current, bias, p):
            self._end(current, "reversed", now)
            current = None

        hysteresis = p.bullion.rearm_hysteresis
        if self._rearm_block.get(metal) and hysteresis > 0:
            if abs(bias) < threshold - hysteresis:
                self._rearm_block.pop(metal, None)
        else:
            self._rearm_block.pop(metal, None)

        reason = self._gate(metal, bias, p, now, current)
        fired = None if reason is not None else self._fire(metal, b, p, now)
        if reason is None and fired is None:
            reason = "no_price"
        self.gates[metal] = Gate(metal, b.minute_ts, fired is not None, reason)

    def tick(self, now_ms: int) -> None:
        self._expire_lapsed(now_ms)
        self._end_waiting_for_event(now_ms, self._params())

    def live(self, s: Signal) -> LiveLevels | None:
        """The future's price now, and target and stop worked out from it."""
        tick = self._tracker.ltp(s.index) if s.index in self._tracker.contracts else None
        if tick is None:
            return None
        target, stop = self.levels_at(s, tick.ltp)
        return LiveLevels(tick.ltp, target, stop)

    def levels_at(self, s: Signal, price: float) -> tuple[float, float]:
        return rescale_levels(s, price, None)

    def manual_contract(
        self, index: str, direction: Direction, strike: float | None, contract: str | None = None
    ) -> ManualContract | None:
        """A market's near-month future to paper-trade by hand; None if there is no such
        market, or `contract` names another one (a mini is its own market, E29). `strike`
        plays no part."""
        inst = self._tracker.instrument(index, contract)
        if inst is None or direction not in FUTURE_DIRECTIONS:
            return None
        return ManualContract(
            index=index,
            direction=direction,
            instrument_key=inst.instrument_key,
            trading_symbol=inst.trading_symbol,
            strike=0.0,
            expiry=inst.expiry.isoformat() if inst.expiry else "",
            lot_size=round(inst.qty_multiplier),
            is_expiry_day=False,
            product=inst.name,
        )

    def trade_contract(self, s: Signal) -> ManualContract | None:
        """What a signal trade opens: the signal's own contract (E29); None if it is not
        loaded."""
        return self.manual_contract(s.index, s.direction, None)

    def default_levels(self, c: ManualContract, price: float) -> tuple[float, float]:
        """The signal rule's target and stop for `c` entered at `price`."""
        return future_levels(c.direction, price, self._params())

    def mark_traded(self, signal_id: str, now_ms: int) -> Signal | None:
        for s in list(self.active.values()):
            if s.id == signal_id:
                return self._end(s, "traded", now_ms)
        return None

    # -- rules -----------------------------------------------------------------

    @staticmethod
    def _direction(bias: float) -> Direction:
        return "BUY_FUT" if bias > 0 else "SELL_FUT"

    def _reversed(self, s: Signal, bias: float, p: ParameterSet) -> bool:
        if abs(bias) < p.bullion.neutral_band:
            return True
        return self._direction(bias) != s.direction

    def paused_by(self, now: int, p: ParameterSet) -> UsEvent | None:
        """The US data release whose pause window holds `now`, if any (E18)."""
        b = p.bullion
        return event_in_window(
            self._events, now, b.event_pause_before_minutes, b.event_pause_after_minutes
        )

    def trade_block(self, now: int, p: ParameterSet) -> str | None:
        """Why a paper trade may not be opened now, when `event_block_trades` is on."""
        if p.bullion.event_block_trades == "off":
            return None
        event = self.paused_by(now, p)
        if event is None:
            return None
        return f"paused around US data: {event.label} {ms_to_ist(event.ts_ms):%H:%M}"

    def within_hours(self, now: int, p: ParameterSet) -> bool:
        if not self._enforce_hours:
            return True
        t = ms_to_ist(now).time()
        b = p.bullion
        return self._clock.status() == "live" and b.first_signal_time <= t < b.last_signal_time

    def _gate(
        self, metal: str, bias: float, p: ParameterSet, now: int, current: Signal | None
    ) -> NoFireReason | None:
        """The first reason not to fire, in the order the trader would want to hear it."""
        rearm = self._rearm_block.get(metal) == self._direction(bias)
        checks: list[tuple[bool, NoFireReason]] = [
            (p.bullion.signals == "off", "disabled"),
            (abs(bias) < p.bullion.entry_threshold, "below_threshold"),
            (current is not None, "active_exists"),
            (rearm and p.bullion.rearm_hysteresis > 0, "rearm"),
            (not self.within_hours(now, p), "outside_hours"),
            (self.paused_by(now, p) is not None, "event_pause"),
            (not self._feed_live(), "feed_down"),
        ]
        return next((reason for failed, reason in checks if failed), None)

    def _fire(self, metal: str, b: BiasComputed, p: ParameterSet, now: int) -> Signal | None:
        tick = self._tracker.ltp(metal)
        if tick is None:
            return None
        near = self._tracker.contracts[metal].near
        direction = self._direction(b.bias.bias)
        entry = tick.ltp
        target, stop = future_levels(direction, entry, p)
        spread = (
            round((tick.ask - tick.bid) / ((tick.ask + tick.bid) / 2) * 100, 4)
            if tick.ask and tick.bid
            else None
        )
        s = Signal(
            id=uuid.uuid4().hex[:12],
            index=metal,
            minute_ts=b.minute_ts,
            ts_fired=now,
            direction=direction,
            instrument_key=near.instrument_key,
            trading_symbol=near.trading_symbol,
            strike=0.0,
            expiry=near.expiry.isoformat() if near.expiry else "",
            lot_size=round(near.qty_multiplier),
            entry_price=entry,
            target_price=target,
            stop_price=stop,
            target_basis="pct",
            target_points=None,
            stop_points=None,
            delta_used=None,
            bias=b.bias.bias,
            strength=b.bias.strength,
            breakdown_json=breakdown_json(b.bias),
            expires_at=now + p.bullion.signal_ttl_seconds * 1000,
            status="active",
            status_ts=now,
            entry_ask=tick.ask if direction == "BUY_FUT" else tick.bid,
            spread_pct=spread,
            config_version=self._config_version() if self._config_version else None,
        )
        self.active[metal] = s
        self.store.upsert(s)
        log.info(
            "bullion signal %s %s %s @ %.2f target %.2f stop %.2f",
            s.id,
            metal,
            direction,
            entry,
            target,
            stop,
        )
        if self._on_signal:
            self._on_signal(s)
        return s

    def _expire_lapsed(self, now: int) -> None:
        for s in list(self.active.values()):
            if now >= s.expires_at:
                self._end(s, "lapsed", now)

    def _end_waiting_for_event(self, now: int, p: ParameterSet) -> None:
        if self.active and p.bullion.event_end_waiting == "on" and self.paused_by(now, p):
            for s in list(self.active.values()):
                self._end(s, "lapsed", now)

    def _end(self, s: Signal, status: Status, now: int) -> Signal:
        ended = replace(s, status=status, status_ts=now)
        if self.active.get(s.index) is s:
            self.active.pop(s.index, None)
        self._rearm_block[s.index] = s.direction
        self.store.upsert(ended)
        if self._on_signal:
            self._on_signal(ended)
        return ended

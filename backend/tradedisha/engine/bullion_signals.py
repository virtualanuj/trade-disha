"""Bullion signals: buy or sell the MCX GOLD/SILVER near-month future. Spec §9a.

The minute-close rule only: when a metal's trend bias reaches `bullion.entry_threshold`,
a long (`BUY_FUT`) or short (`SELL_FUT`) signal fires at the future's latest price, with
target and stop a percentage of that price either side. One active signal per metal; it
lapses after its TTL, reverses when the bias flips sign or falls inside the neutral band,
or ends when it is paper-traded. Gates: signals switched on, MCX open and inside the
bullion signal hours, and bullion prices live. The index engines and NSE hours play no
part, and nothing here sends an order: paper only.

Rows go to the shared `signals` table: `index` is the metal, `strike` 0, `expiry` the
future's expiry, and `lot_size` the rupees per point per lot (`qty_multiplier`).
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import replace

from tradedisha.clock import MarketClock, ms_to_ist
from tradedisha.engine.bias_engine import BiasComputed, breakdown_json
from tradedisha.engine.signals import Direction, Gate, NoFireReason, Signal, SignalStore, Status
from tradedisha.market.bullion import BullionTracker
from tradedisha.parameters.model import ParameterSet

log = logging.getLogger(__name__)


class BullionSignalEngine:
    def __init__(
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
    ) -> None:
        self._tracker = tracker
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
            (not self._feed_live(), "feed_down"),
        ]
        return next((reason for failed, reason in checks if failed), None)

    def _fire(self, metal: str, b: BiasComputed, p: ParameterSet, now: int) -> Signal | None:
        tick = self._tracker.ltp(metal)
        if tick is None:
            return None
        near = self._tracker.contracts[metal].near
        direction = self._direction(b.bias.bias)
        side = 1 if direction == "BUY_FUT" else -1
        entry = tick.ltp
        target = round(entry * (1 + side * p.bullion.target_pct / 100), 2)
        stop = round(entry * (1 - side * p.bullion.stop_pct / 100), 2)
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

    def _end(self, s: Signal, status: Status, now: int) -> Signal:
        ended = replace(s, status=status, status_ts=now)
        if self.active.get(s.index) is s:
            self.active.pop(s.index, None)
        self._rearm_block[s.index] = s.direction
        self.store.upsert(ended)
        if self._on_signal:
            self._on_signal(ended)
        return ended

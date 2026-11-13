"""Signal lifecycle. Spec §9.

A signal fires at a minute close when |bias| >= entry_threshold, no signal is active on
that index, the clock is within signal hours, and the feed is live. Open paper trades
never gate it. It ends when it lapses (TTL untraded), reverses (bias sign flips or falls
inside the neutral band), or is traded. A fresh one fires at the next qualifying minute.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, time
from typing import Literal

from tradedisha.clock import IST, MarketClock, ist_to_ms, ms_to_ist
from tradedisha.engine.aggregator import Bias
from tradedisha.engine.bias_engine import BiasComputed, breakdown_json
from tradedisha.indicators.greeks import bs_delta, years_between_ms
from tradedisha.instruments.models import ResolvedIndex
from tradedisha.market.chain import ChainState, LegState
from tradedisha.parameters.model import ParameterSet

log = logging.getLogger(__name__)

Direction = Literal["BUY_CE", "BUY_PE"]
Status = Literal["active", "traded", "lapsed", "reversed"]
NoFireReason = Literal[
    "below_threshold", "active_exists", "outside_hours", "feed_down", "no_price", "rearm"
]


@dataclass(frozen=True)
class Signal:
    id: str
    index: str
    minute_ts: int
    ts_fired: int
    direction: Direction
    instrument_key: str
    trading_symbol: str
    strike: float
    expiry: str
    lot_size: int
    entry_price: float
    target_price: float
    stop_price: float
    target_basis: Literal["pct", "points"]
    target_points: float | None
    stop_points: float | None
    delta_used: float | None
    bias: float
    strength: int
    breakdown_json: str
    expires_at: int
    status: Status
    status_ts: int

    @property
    def is_active(self) -> bool:
        return self.status == "active"


@dataclass(frozen=True)
class Gate:
    """Why the last evaluation did or did not fire; shown on the signal card."""

    index: str
    minute_ts: int
    fired: bool
    reason: NoFireReason | None


class SignalStore:
    COLS = (
        "id, idx, minute_ts, ts_fired, direction, instrument_key, trading_symbol, strike,"
        " expiry, lot_size, entry_price, target_price, stop_price, target_basis, target_points,"
        " stop_points, delta_used, bias, strength, breakdown_json, expires_at, status, status_ts"
    )

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, s: Signal) -> None:
        with self._conn:
            self._conn.execute(
                f"INSERT OR REPLACE INTO signals ({self.COLS}) VALUES ({','.join('?' * 23)})",
                (
                    s.id,
                    s.index,
                    s.minute_ts,
                    s.ts_fired,
                    s.direction,
                    s.instrument_key,
                    s.trading_symbol,
                    s.strike,
                    s.expiry,
                    s.lot_size,
                    s.entry_price,
                    s.target_price,
                    s.stop_price,
                    s.target_basis,
                    s.target_points,
                    s.stop_points,
                    s.delta_used,
                    s.bias,
                    s.strength,
                    s.breakdown_json,
                    s.expires_at,
                    s.status,
                    s.status_ts,
                ),
            )

    def read(self, start_ms: int, end_ms: int, index: str | None = None) -> list[Signal]:
        sql = f"SELECT {self.COLS} FROM signals WHERE ts_fired >= ? AND ts_fired < ?"
        args: list[object] = [start_ms, end_ms]
        if index:
            sql += " AND idx = ?"
            args.append(index)
        sql += " ORDER BY ts_fired DESC"
        return [self._row(r) for r in self._conn.execute(sql, args)]

    def get(self, signal_id: str) -> Signal | None:
        r = self._conn.execute(
            f"SELECT {self.COLS} FROM signals WHERE id = ?", (signal_id,)
        ).fetchone()
        return self._row(r) if r else None

    @staticmethod
    def _row(r: sqlite3.Row) -> Signal:
        return Signal(
            id=r["id"],
            index=r["idx"],
            minute_ts=r["minute_ts"],
            ts_fired=r["ts_fired"],
            direction=r["direction"],
            instrument_key=r["instrument_key"],
            trading_symbol=r["trading_symbol"],
            strike=r["strike"],
            expiry=r["expiry"],
            lot_size=r["lot_size"],
            entry_price=r["entry_price"],
            target_price=r["target_price"],
            stop_price=r["stop_price"],
            target_basis=r["target_basis"],
            target_points=r["target_points"],
            stop_points=r["stop_points"],
            delta_used=r["delta_used"],
            bias=r["bias"],
            strength=r["strength"],
            breakdown_json=r["breakdown_json"],
            expires_at=r["expires_at"],
            status=r["status"],
            status_ts=r["status_ts"],
        )


def expiry_close_ms(expiry_iso: str, market_close: time) -> int:
    y, m, d = (int(x) for x in expiry_iso.split("-"))
    return ist_to_ms(datetime(y, m, d, market_close.hour, market_close.minute, tzinfo=IST))


class SignalEngine:
    def __init__(  # noqa: PLR0913 -- injected collaborators and market rules
        self,
        *,
        clock: MarketClock,
        params: Callable[[], ParameterSet],
        resolved: dict[str, ResolvedIndex],
        chains: dict[str, ChainState],
        conn: sqlite3.Connection,
        feed_live: Callable[[], bool],
        enforce_hours: bool,
        market_open: time,
        market_close: time,
        risk_free_rate: float,
        on_signal: Callable[[Signal], None] | None = None,
    ) -> None:
        self._clock = clock
        self._params = params
        self._resolved = resolved
        self._chains = chains
        self.store = SignalStore(conn)
        self._feed_live = feed_live
        self._enforce_hours = enforce_hours
        self._open = market_open
        self._close = market_close
        self._rate = risk_free_rate
        self._on_signal = on_signal
        self.active: dict[str, Signal] = {}
        self.gates: dict[str, Gate] = {}
        self._rearm_block: dict[str, Direction] = {}  # index -> direction needing re-arm

    # -- inputs ----------------------------------------------------------------

    def on_bias(self, b: BiasComputed) -> None:
        """Called at every minute close for an index."""
        p = self._params()
        index = b.index
        bias = b.bias
        now = b.minute_ts + 60_000  # the close instant of the evaluated minute
        self._expire_lapsed(now)

        current = self.active.get(index)
        if current is not None and self._reversed(current, bias, p):
            self._end(current, "reversed", now)
            current = None

        if self._rearm_block.get(index) and p.bias.rearm_hysteresis > 0:
            if abs(bias.bias) < p.bias.entry_threshold - p.bias.rearm_hysteresis:
                self._rearm_block.pop(index, None)
        else:
            self._rearm_block.pop(index, None)

        reason = self._gate(index, bias, p, now, current)
        if reason is not None:
            self.gates[index] = Gate(index, b.minute_ts, False, reason)
            return
        fired = self._fire(index, b, p, now)
        self.gates[index] = Gate(
            index, b.minute_ts, fired is not None, None if fired else "no_price"
        )

    def tick(self, now_ms: int) -> None:
        """Time-based housekeeping between minute closes (lapse)."""
        self._expire_lapsed(now_ms)

    def mark_traded(self, signal_id: str, now_ms: int) -> Signal | None:
        for index, s in list(self.active.items()):
            if s.id == signal_id:
                ended = self._end(s, "traded", now_ms)
                self.active.pop(index, None)
                return ended
        return None

    # -- rules -----------------------------------------------------------------

    def _reversed(self, s: Signal, bias: Bias, p: ParameterSet) -> bool:
        if abs(bias.bias) < p.bias.neutral_band:
            return True
        want_pos = s.direction == "BUY_CE"
        return (bias.bias > 0) != want_pos

    def within_hours(self, now_ms: int, is_expiry_day: bool, p: ParameterSet) -> bool:
        if not self._enforce_hours:
            return True
        t = self._clock.now().time() if now_ms == 0 else _ist_time(now_ms)
        last = p.signal.last_signal_time_expiry if is_expiry_day else p.signal.last_signal_time
        return self._open <= t < last and self._clock.is_trading_day()

    def _gate(
        self, index: str, bias: Bias, p: ParameterSet, now: int, current: Signal | None
    ) -> NoFireReason | None:
        if abs(bias.bias) < p.bias.entry_threshold:
            return "below_threshold"
        if current is not None:
            return "active_exists"
        direction: Direction = "BUY_CE" if bias.bias > 0 else "BUY_PE"
        if self._rearm_block.get(index) == direction and p.bias.rearm_hysteresis > 0:
            return "rearm"
        if not self.within_hours(now, self._resolved[index].is_expiry_day, p):
            return "outside_hours"
        if not self._feed_live():
            return "feed_down"
        return None

    def _fire(self, index: str, b: BiasComputed, p: ParameterSet, now: int) -> Signal | None:
        r = self._resolved[index]
        chain = self._chains[index]
        row = chain.rows.get(chain.atm)
        if row is None:
            return None
        direction: Direction = "BUY_CE" if b.bias.bias > 0 else "BUY_PE"
        leg: LegState = row.ce if direction == "BUY_CE" else row.pe
        pair = next((pp for pp in r.strikes if pp.strike == row.strike), None)
        if leg.ltp is None or pair is None:
            return None
        inst = pair.ce if direction == "BUY_CE" else pair.pe
        entry = leg.ltp

        basis: Literal["pct", "points"]
        if r.is_expiry_day:
            pts = p.signal.expiry_points.get(index)
            if pts is None:
                basis, target, stop, tp, sp, delta = self._pct(entry, p)
            else:
                delta = leg.delta
                if delta is None:
                    spot = chain.spot or row.strike
                    t_years = years_between_ms(
                        now, expiry_close_ms(r.options_expiry.isoformat(), self._close)
                    )
                    delta = bs_delta(
                        spot,
                        row.strike,
                        t_years,
                        leg.iv or 15.0,
                        self._rate,
                        call=direction == "BUY_CE",
                    )
                d = abs(delta)
                basis = "points"
                target = round(entry + d * pts.target, 2)
                stop = round(max(0.05, entry - d * pts.stop), 2)
                tp, sp = pts.target, pts.stop
        else:
            basis, target, stop, tp, sp, delta = self._pct(entry, p)

        s = Signal(
            id=uuid.uuid4().hex[:12],
            index=index,
            minute_ts=b.minute_ts,
            ts_fired=now,
            direction=direction,
            instrument_key=inst.instrument_key,
            trading_symbol=inst.trading_symbol,
            strike=row.strike,
            expiry=r.options_expiry.isoformat(),
            lot_size=r.lot_size,
            entry_price=entry,
            target_price=target,
            stop_price=stop,
            target_basis=basis,
            target_points=tp,
            stop_points=sp,
            delta_used=delta,
            bias=b.bias.bias,
            strength=b.bias.strength,
            breakdown_json=breakdown_json(b.bias),
            expires_at=now + p.signal.signal_ttl_seconds * 1000,
            status="active",
            status_ts=now,
        )
        self.active[index] = s
        self.store.upsert(s)
        log.info(
            "signal %s %s %s @ %.2f target %.2f stop %.2f",
            s.id,
            index,
            direction,
            entry,
            target,
            stop,
        )
        if self._on_signal:
            self._on_signal(s)
        return s

    @staticmethod
    def _pct(
        entry: float, p: ParameterSet
    ) -> tuple[Literal["pct"], float, float, None, None, None]:
        target = round(entry * (1 + p.signal.target_pct / 100), 2)
        stop = round(max(0.05, entry * (1 + p.signal.stop_pct / 100)), 2)
        return "pct", target, stop, None, None, None

    def _expire_lapsed(self, now: int) -> None:
        for index, s in list(self.active.items()):
            if now >= s.expires_at:
                self._end(s, "lapsed", now)
                self.active.pop(index, None)

    def _end(self, s: Signal, status: Status, now: int) -> Signal:
        ended = replace(s, status=status, status_ts=now)
        if self.active.get(s.index) is s:
            self.active.pop(s.index, None)
        self._rearm_block[s.index] = s.direction
        self.store.upsert(ended)
        if self._on_signal:
            self._on_signal(ended)
        return ended


def _ist_time(ms: int) -> time:
    return ms_to_ist(ms).time()

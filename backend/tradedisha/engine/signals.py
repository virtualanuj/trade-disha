"""Signal lifecycle. Spec §9.

Two entry rules (`signal.entry_mode`):

- `minute_close`: a signal fires at a minute close when |bias| >= entry_threshold.
- `trigger`: a minute close with |bias| >= setup_threshold only sets a direction up; the
  signal fires inside the minute once the order-flow score has agreed for `hold_seconds`
  and the option's bid-ask spread is tight enough, at the ask.

Either way no signal may be active on that index, the clock must be within signal hours
and the feed live. Open paper trades never gate it. A signal ends when it lapses (TTL
untraded), reverses (bias sign flips or falls inside the neutral band), or is traded.

An engine built with `shadow=True` runs whichever rule is not the live one, so the two can
be compared on the same days; its signals are stored and marked, never offered for trading.
"""

from __future__ import annotations

import logging
import math
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import astuple, dataclass, fields, replace
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

# Index options are bought; a bullion future (spec §9a) is bought or sold.
Direction = Literal["BUY_CE", "BUY_PE", "BUY_FUT", "SELL_FUT"]
Status = Literal["active", "traded", "lapsed", "reversed"]
EntryMode = Literal["minute_close", "trigger"]
NoFireReason = Literal[
    "below_threshold",
    "active_exists",
    "outside_hours",
    "feed_down",
    "no_price",
    "rearm",
    "no_setup",
    "flow_not_confirmed",
    "spread_wide",
    "disabled",
    "event_pause",
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
    entry_ask: float | None = None  # best ask when it fired: what a buyer would have paid
    spread_pct: float | None = None  # bid-ask spread then, as % of the mid price
    entry_mode: EntryMode = "minute_close"  # the rule that fired it
    shadow: bool = False  # fired by the rule that is not live: scored, never offered
    flow_score: float | None = None  # order-flow score when a trigger signal fired
    config_version: int | None = None  # the parameters in force when it fired

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


# (basis, target, stop, target points, stop points, delta used)
Levels = tuple[Literal["pct", "points"], float, float, float | None, float | None, float | None]

OPTION_DIRECTIONS: frozenset[str] = frozenset({"BUY_CE", "BUY_PE"})
FUTURE_DIRECTIONS: frozenset[str] = frozenset({"BUY_FUT", "SELL_FUT"})


@dataclass(frozen=True)
class ManualContract:
    """What a paper trade opened by hand is in: an option in the chain window, or a
    metal's near-month future (strike 0, `lot_size` the rupees per point per lot)."""

    index: str
    direction: Direction
    instrument_key: str
    trading_symbol: str
    strike: float
    expiry: str
    lot_size: int
    is_expiry_day: bool
    product: str = ""  # what it is a contract of: the index, or GOLD / GOLDM / SILVER / SILVERM


@dataclass(frozen=True)
class LiveLevels:
    """Where an active signal's entry, target and stop are now (spec §9.2)."""

    ltp: float
    target: float
    stop: float


STOP_FLOOR = 0.05  # an option's stop never goes below the smallest premium


def round_rupee(value: float) -> float:
    """The nearest whole rupee, half a rupee up (E24)."""
    return float(math.floor(value + 0.5))


def round_levels(
    direction: Direction, entry: float, target: float, stop: float
) -> tuple[float, float]:
    """Target and stop in whole rupees (E24). A level the rounding puts on or past `entry`
    moves out to the next whole rupee beyond it, so nothing opens on its own target or
    stop; a long stop never goes below `STOP_FLOOR`. Mirrored for a short future."""
    t, st = round_rupee(target), round_rupee(stop)
    if direction == "SELL_FUT":
        if t >= entry:
            t = float(math.ceil(entry) - 1)
        if st <= entry:
            st = float(math.floor(entry) + 1)
        return t, st
    if t <= entry:
        t = float(math.floor(entry) + 1)
    if st >= entry:
        st = float(math.ceil(entry) - 1)
    return t, max(STOP_FLOOR, st)


def rescale_levels(s: Signal, price: float, delta: float | None) -> tuple[float, float]:
    """(target, stop) for `s` entered at `price`, by the rule it fired under.

    A percentage signal keeps its target/entry and stop/entry ratios, so a config change
    after it fired does not move it. An expiry-day signal re-applies its index points through
    `delta` (the option's current one; the delta it fired with if none is known).
    """
    if s.target_basis == "points" and s.target_points is not None and s.stop_points is not None:
        d = abs(delta if delta is not None else (s.delta_used or 0.0))
        target = price + d * s.target_points
        stop = price - d * s.stop_points
    elif s.entry_price > 0:
        target = price * s.target_price / s.entry_price
        stop = price * s.stop_price / s.entry_price
    else:
        return s.target_price, s.stop_price
    return round_levels(s.direction, price, target, stop)


_COLS = [f.name for f in fields(Signal)]
_DB_COLS = ", ".join("idx" if c == "index" else c for c in _COLS)


class SignalStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, s: Signal) -> None:
        with self._conn:
            self._conn.execute(
                f"INSERT OR REPLACE INTO signals ({_DB_COLS})"
                f" VALUES ({','.join('?' * len(_COLS))})",
                astuple(s),
            )

    def read(self, start_ms: int, end_ms: int, index: str | None = None) -> list[Signal]:
        sql = f"SELECT {_DB_COLS} FROM signals WHERE ts_fired >= ? AND ts_fired < ?"
        args: list[object] = [start_ms, end_ms]
        if index:
            sql += " AND idx = ?"
            args.append(index)
        sql += " ORDER BY ts_fired DESC"
        return [self._row(r) for r in self._conn.execute(sql, args)]

    def get(self, signal_id: str) -> Signal | None:
        r = self._conn.execute(
            f"SELECT {_DB_COLS} FROM signals WHERE id = ?", (signal_id,)
        ).fetchone()
        return self._row(r) if r else None

    @staticmethod
    def _row(r: sqlite3.Row) -> Signal:
        values = {c: r["idx" if c == "index" else c] for c in _COLS}
        return Signal(**{**values, "shadow": bool(values["shadow"])})


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
        shadow: bool = False,
        config_version: Callable[[], int | None] | None = None,
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
        self.shadow = shadow
        self._config_version = config_version
        self._setup: dict[str, BiasComputed] = {}  # trigger mode: the bias that set a side up
        self._agree_since: dict[str, int] = {}  # trigger mode: when the flow began agreeing

    def mode(self, p: ParameterSet) -> EntryMode:
        live = p.signal.entry_mode
        if not self.shadow:
            return live
        return "trigger" if live == "minute_close" else "minute_close"

    # -- inputs ----------------------------------------------------------------

    def on_bias(self, b: BiasComputed) -> None:
        """Called at every minute close for an index."""
        index = b.index
        if index not in self._resolved:
            return  # bullion bias shares the listener list; the bullion desk handles it
        p = self._params()
        bias = b.bias
        now = b.minute_ts + 60_000  # the close instant of the evaluated minute
        trigger = self.mode(p) == "trigger"
        threshold = p.bias.setup_threshold if trigger else p.bias.entry_threshold
        self._expire_lapsed(now)

        current = self.active.get(index)
        if current is not None and self._reversed(current, bias, p):
            self._end(current, "reversed", now)
            current = None

        if self._rearm_block.get(index) and p.bias.rearm_hysteresis > 0:
            if abs(bias.bias) < threshold - p.bias.rearm_hysteresis:
                self._rearm_block.pop(index, None)
        else:
            self._rearm_block.pop(index, None)

        if trigger:
            self._set_up(b, p, current)
            return
        self._setup.pop(index, None)
        reason = self._gate(index, bias, p, now, current)
        if reason is not None:
            self.gates[index] = Gate(index, b.minute_ts, False, reason)
            return
        fired = self._fire(index, b, p, now)
        self.gates[index] = Gate(
            index, b.minute_ts, fired is not None, None if fired else "no_price"
        )

    def on_flow(self, index: str, now: int, score: float | None) -> None:
        """Trigger mode: called about once a second with the index's order-flow score."""
        p = self._params()
        if self.mode(p) != "trigger":
            return
        self._expire_lapsed(now)
        setup = self._setup.get(index)
        if setup is None or index in self.active:
            self._agree_since.pop(index, None)
            return  # the gate from the last minute close already says why
        sign = 1.0 if setup.bias.bias > 0 else -1.0
        if score is None or sign * score < p.flow.trigger_score:
            self._agree_since.pop(index, None)
            self.gates[index] = Gate(index, setup.minute_ts, False, "flow_not_confirmed")
            return
        since = self._agree_since.setdefault(index, now)
        reason: NoFireReason | None = None
        if now - since < p.flow.hold_seconds * 1000:
            reason = "flow_not_confirmed"
        else:
            reason = self._common_gate(index, setup.bias, p, now) or self._quote_gate(setup, p)
        if reason is not None:
            self.gates[index] = Gate(index, setup.minute_ts, False, reason)
            return
        fired = self._fire(index, setup, p, now, at_ask=True, flow_score=score)
        self._agree_since.pop(index, None)
        self.gates[index] = Gate(
            index, setup.minute_ts, fired is not None, None if fired else "no_price"
        )

    def tick(self, now_ms: int) -> None:
        """Time-based housekeeping between minute closes (lapse)."""
        self._expire_lapsed(now_ms)

    def live(self, s: Signal) -> LiveLevels | None:
        """The signal's option price now, and target and stop worked out from it."""
        leg = self._leg(s)
        if leg is None or leg.ltp is None:
            return None
        target, stop = self.levels_at(s, leg.ltp)
        return LiveLevels(leg.ltp, target, stop)

    def levels_at(self, s: Signal, price: float) -> tuple[float, float]:
        """Target and stop if `s` were entered at `price` now (a paper trade's fill)."""
        delta = self._live_delta(s) if s.target_basis == "points" else None
        return rescale_levels(s, price, delta)

    def _leg(self, s: Signal) -> LegState | None:
        chain = self._chains.get(s.index)
        row = chain.rows.get(s.strike) if chain else None
        if row is None:
            return None
        return row.ce if s.direction == "BUY_CE" else row.pe

    def _live_delta(self, s: Signal) -> float | None:
        """The option's delta now: from the feed, else Black-Scholes as when it fired."""
        return self._delta(s.index, s.strike, s.direction, self._clock.now_ms())

    def _delta(self, index: str, strike: float, direction: Direction, now: int) -> float | None:
        """An option's delta: from the feed, else Black-Scholes at `now`."""
        chain = self._chains.get(index)
        row = chain.rows.get(strike) if chain else None
        if chain is None or row is None:
            return None
        leg = row.ce if direction == "BUY_CE" else row.pe
        if leg.delta is not None:
            return leg.delta
        r = self._resolved[index]
        t_years = years_between_ms(now, expiry_close_ms(r.options_expiry.isoformat(), self._close))
        return bs_delta(
            chain.spot or strike,
            strike,
            t_years,
            leg.iv or 15.0,
            self._rate,
            call=direction == "BUY_CE",
        )

    def levels_for(
        self,
        index: str,
        strike: float,
        direction: Direction,
        entry: float,
        now: int,
        p: ParameterSet,
    ) -> Levels:
        """Target and stop for an option bought at `entry`: a percentage of it, or on
        expiry day the index's points through the option's delta. Signals and paper trades
        opened by hand both use this rule."""
        pts = p.signal.expiry_points.get(index) if self._resolved[index].is_expiry_day else None
        if pts is None:
            return self._pct(entry, p)
        delta = self._delta(index, strike, direction, now)
        d = abs(delta or 0.0)
        target, stop = round_levels(direction, entry, entry + d * pts.target, entry - d * pts.stop)
        return "points", target, stop, pts.target, pts.stop, delta

    # -- paper trades opened by hand (E23) --------------------------------------

    def manual_contract(
        self, index: str, direction: Direction, strike: float | None, contract: str | None = None
    ) -> ManualContract | None:
        """An option in the chain window to paper-trade by hand; None if there is none.
        `contract` is for a metal's mini and plays no part here."""
        del contract
        r = self._resolved.get(index)
        chain = self._chains.get(index)
        if r is None or chain is None or strike is None or direction not in OPTION_DIRECTIONS:
            return None
        pair = next((pp for pp in r.strikes if pp.strike == strike), None)
        if pair is None or strike not in chain.rows:
            return None
        inst = pair.ce if direction == "BUY_CE" else pair.pe
        return ManualContract(
            index=index,
            direction=direction,
            instrument_key=inst.instrument_key,
            trading_symbol=inst.trading_symbol,
            strike=strike,
            expiry=r.options_expiry.isoformat(),
            lot_size=r.lot_size,
            is_expiry_day=r.is_expiry_day,
            product=index,
        )

    def trade_contract(self, s: Signal) -> ManualContract | None:
        """What a signal's paper trade opens: the signal's own option."""
        return ManualContract(
            index=s.index,
            direction=s.direction,
            instrument_key=s.instrument_key,
            trading_symbol=s.trading_symbol,
            strike=s.strike,
            expiry=s.expiry,
            lot_size=s.lot_size,
            is_expiry_day=False,
            product=s.index,
        )

    def default_levels(self, c: ManualContract, price: float) -> tuple[float, float]:
        """The signal rule's target and stop for `c` bought at `price` now."""
        _, target, stop, *_ = self.levels_for(
            c.index, c.strike, c.direction, price, self._clock.now_ms(), self._params()
        )
        return target, stop

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

    def _set_up(self, b: BiasComputed, p: ParameterSet, current: Signal | None) -> None:
        """Trigger mode at a minute close: remember or drop the side the bias favours."""
        index = b.index
        if abs(b.bias.bias) < p.bias.setup_threshold:
            self._setup.pop(index, None)
            self._agree_since.pop(index, None)
            reason: NoFireReason = "no_setup"
        else:
            previous = self._setup.get(index)
            if previous is not None and (previous.bias.bias > 0) != (b.bias.bias > 0):
                self._agree_since.pop(index, None)  # the side changed: the flow must agree anew
            self._setup[index] = b
            reason = "active_exists" if current is not None else "flow_not_confirmed"
        self.gates[index] = Gate(index, b.minute_ts, False, reason)

    def _gate(
        self, index: str, bias: Bias, p: ParameterSet, now: int, current: Signal | None
    ) -> NoFireReason | None:
        if abs(bias.bias) < p.bias.entry_threshold:
            return "below_threshold"
        if current is not None:
            return "active_exists"
        return self._common_gate(index, bias, p, now)

    def _common_gate(
        self, index: str, bias: Bias, p: ParameterSet, now: int
    ) -> NoFireReason | None:
        """The gates both entry rules share: re-arm, signal hours, a live feed."""
        direction: Direction = "BUY_CE" if bias.bias > 0 else "BUY_PE"
        if self._rearm_block.get(index) == direction and p.bias.rearm_hysteresis > 0:
            return "rearm"
        if not self.within_hours(now, self._resolved[index].is_expiry_day, p):
            return "outside_hours"
        if not self._feed_live():
            return "feed_down"
        return None

    def _quote_gate(self, setup: BiasComputed, p: ParameterSet) -> NoFireReason | None:
        """A trigger signal buys at the ask, so it needs a two-sided, tight quote."""
        chain = self._chains[setup.index]
        row = chain.rows.get(chain.atm)
        if row is None:
            return "no_price"
        leg = row.ce if setup.bias.bias > 0 else row.pe
        spread = leg.spread_pct
        return "spread_wide" if spread is None or spread > p.signal.max_spread_pct else None

    def _fire(
        self,
        index: str,
        b: BiasComputed,
        p: ParameterSet,
        now: int,
        *,
        at_ask: bool = False,
        flow_score: float | None = None,
    ) -> Signal | None:
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
        entry = leg.ask if at_ask and leg.ask is not None else leg.ltp

        basis, target, stop, tp, sp, delta = self.levels_for(
            index, row.strike, direction, entry, now, p
        )
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
            entry_ask=leg.ask,
            spread_pct=leg.spread_pct,
            entry_mode="trigger" if at_ask else "minute_close",
            shadow=self.shadow,
            flow_score=flow_score,
            config_version=self._config_version() if self._config_version else None,
        )
        self.active[index] = s
        self.store.upsert(s)
        log.info(
            "%ssignal %s %s %s @ %.2f target %.2f stop %.2f",
            "shadow " if self.shadow else "",
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
    def _pct(entry: float, p: ParameterSet) -> Levels:
        # an option is always bought, so the long rounding applies to a call and a put
        target, stop = round_levels(
            "BUY_CE",
            entry,
            entry * (1 + p.signal.target_pct / 100),
            entry * (1 + p.signal.stop_pct / 100),
        )
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

"""Paper trades: opened only by the trader, tracked tick by tick to an exit. Spec §10.

A trade opens at the price prevailing when the trader clicks (not the signal's entry
price) and closes at target, stop, the square-off time, or by hand. Nothing here places a
real order, and nothing here opens a trade on its own.

The trader can also open a trade by hand, with no signal (E23): any option in the chain
window, or a metal's near-month future either way. Its `signal_id` is `MANUAL_SIGNAL_ID`.
It takes the signal rule's target and stop at the fill, or levels the trader typed, and is
held to the same gates plus the signal cut-off. The target and stop of any open trade can
be changed; every set of levels a trade has had is kept in `paper_trade_levels`.

Index options are always bought. A bullion future (spec §9a) is bought or sold, so P&L and
the target/stop checks take the trade's side. Each manager runs one market's rules (its
clock, square-off, lots, cost) and owns only that market's trades, so the index manager and
the bullion manager share the `paper_trades` table without touching each other's rows.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from collections.abc import Callable, Iterable
from dataclasses import asdict, astuple, dataclass, fields, replace
from datetime import datetime, time
from typing import TYPE_CHECKING, Literal, Protocol

from tradedisha.clock import IST, MarketClock, ist_to_ms, ms_to_ist
from tradedisha.engine.bias_engine import BiasComputed
from tradedisha.engine.signals import (
    Direction,
    ManualContract,
    Signal,
    SignalStore,
    round_rupee,
)
from tradedisha.feed.bus import StampedTick
from tradedisha.parameters.model import ParameterSet

if TYPE_CHECKING:
    from tradedisha.engine.bank import PaperBank

log = logging.getLogger(__name__)

TradeStatus = Literal["open", "closed"]
ExitReason = Literal["TARGET", "STOP", "SQUARE_OFF", "MANUAL"]
FillQuality = Literal["live", "after_gap", "stale"]
Warning = Literal["bias_reversed"]

LevelSource = Literal["entry", "edit"]

METALS: frozenset[str] = frozenset({"GOLD", "SILVER"})  # bullion trades, by `index`

# The `signal_id` of every trade opened by hand. Signal ids are twelve hex digits, so no
# signal can ever have this one.
MANUAL_SIGNAL_ID = "manual"


class SignalSource(Protocol):
    """What a manager needs from a signal engine (index or bullion)."""

    active: dict[str, Signal]
    store: SignalStore

    def mark_traded(self, signal_id: str, now_ms: int) -> Signal | None: ...
    def levels_at(self, s: Signal, price: float) -> tuple[float, float]: ...
    def manual_contract(
        self, index: str, direction: Direction, strike: float | None
    ) -> ManualContract | None: ...
    def default_levels(self, c: ManualContract, price: float) -> tuple[float, float]: ...


@dataclass(frozen=True)
class PaperRules:
    """One market's paper-trading rules."""

    owns: Callable[[str], bool]  # which `index` values this manager trades
    square_off: Callable[[ParameterSet], time]
    lots: Callable[[ParameterSet], int]
    # round-trip cost for the whole trade, fixed at entry: (params, entry price, qty, lots)
    cost: Callable[[ParameterSet, float, int, int], float]
    # money the paper bank blocks while the trade is open: (params, index, entry, qty, cost)
    block: Callable[[ParameterSet, str, float, int, float], float]
    # why no trade may be opened now, if anything: (now, params) -> reason (E18)
    entry_block: Callable[[int, ParameterSet], str | None] | None = None
    # the last time a trade may be opened by hand: (params, is expiry day) -> the signal
    # cut-off (E23). Signal trades are not held to it.
    last_entry: Callable[[ParameterSet, bool], time] | None = None


def index_rules() -> PaperRules:
    """NIFTY / BANK NIFTY options: the `paper` section, a flat fee per lot."""
    return PaperRules(
        owns=lambda index: index not in METALS,
        square_off=lambda p: p.paper.square_off_time,
        lots=lambda p: p.paper.lots,
        cost=lambda p, _entry, _qty, lots: p.paper.cost_per_trade * lots,
        block=lambda _p, _index, entry, qty, cost: entry * qty + cost,  # the premium paid
        last_entry=lambda p, expiry_day: (
            p.signal.last_signal_time_expiry if expiry_day else p.signal.last_signal_time
        ),
    )


def bullion_rules(
    entry_block: Callable[[int, ParameterSet], str | None] | None = None,
) -> PaperRules:
    """MCX GOLD / SILVER futures: the `bullion` section; cost has a part that scales with
    value, because a GOLD lot is worth over a crore. `entry_block` refuses an entry during
    a US data-release pause (E18)."""

    def cost(p: ParameterSet, entry: float, qty: int, lots: int) -> float:
        b = p.bullion
        return b.cost_fixed_per_lot * lots + b.cost_pct_of_value / 100 * entry * qty * 2

    return PaperRules(
        owns=lambda index: index in METALS,
        square_off=lambda p: p.bullion.square_off_time,
        lots=lambda p: p.bullion.lots,
        cost=cost,
        block=lambda p, metal, entry, qty, cost: (
            p.bullion.margin_pct(metal) / 100 * entry * qty + cost
        ),
        entry_block=entry_block,
        last_entry=lambda p, _expiry_day: p.bullion.last_signal_time,
    )


class PaperError(Exception):
    """The request cannot be honoured right now; `reason` is shown to the trader."""

    def __init__(self, reason: str, *, not_found: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.not_found = not_found


@dataclass(frozen=True)
class PaperTrade:
    id: str
    signal_id: str
    index: str
    instrument_key: str
    trading_symbol: str
    direction: Direction
    strike: float
    expiry: str
    lots: int
    qty: int
    signal_entry: float  # the signal's entry price; by hand, the price the ticket showed
    entry_price: float
    entry_ts: int
    slippage: float  # fill minus `signal_entry`
    target_price: float
    stop_price: float
    cost: float  # round-trip cost for the whole trade, fixed at entry
    status: TradeStatus = "open"
    exit_price: float | None = None
    exit_ts: int | None = None
    exit_reason: ExitReason | None = None
    exit_fill_quality: FillQuality | None = None
    exit_price_age_ms: int | None = None
    gross: float | None = None
    net: float | None = None
    warning: Warning | None = None
    blocked: float = 0.0  # held in the paper bank while open (E17)
    banked: bool = False  # funded by the paper bank, so its P&L settles there
    levels_edited: bool = False  # target or stop changed after it opened (E23)

    @property
    def is_open(self) -> bool:
        return self.status == "open"

    @property
    def is_manual(self) -> bool:
        """Opened by hand, with no signal (E23)."""
        return self.signal_id == MANUAL_SIGNAL_ID

    @property
    def side(self) -> int:
        """+1 for a bought option or future, -1 for a sold (short) future."""
        return -1 if self.direction == "SELL_FUT" else 1

    def pnl_at(self, price: float) -> tuple[float, float]:
        """(gross, net) if the trade were closed at `price`."""
        gross = round(self.side * (price - self.entry_price) * self.qty, 2)
        return gross, round(gross - self.cost, 2)

    def hit_target(self, price: float) -> bool:
        return self.side * (price - self.target_price) >= 0

    def hit_stop(self, price: float) -> bool:
        return self.side * (price - self.stop_price) <= 0


_COLS = [f.name for f in fields(PaperTrade)]
_DB_COLS = ["idx" if c == "index" else c for c in _COLS]


@dataclass(frozen=True)
class LevelChange:
    """One set of levels a trade has had: at entry, then after each edit."""

    trade_id: str
    ts: int
    target: float
    stop: float
    ltp: float  # the price when they were set
    source: LevelSource


def check_levels(direction: Direction, price: float, target: float, stop: float) -> str | None:
    """Why `target` and `stop` cannot stand at `price`, if they cannot: the target must be
    on the trade's side of the price and the stop on the other (mirrored for a short)."""
    if target <= 0 or stop <= 0:
        return "target and stop must be above zero"
    short = direction == "SELL_FUT"
    side = -1 if short else 1
    if side * (target - price) <= 0:
        where = "below" if short else "above"
        return f"the target {target:g} must be {where} the price {price:g}"
    if side * (price - stop) <= 0:
        where = "above" if short else "below"
        return f"the stop {stop:g} must be {where} the price {price:g}"
    return None


class PaperTradeStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, t: PaperTrade) -> None:
        row = asdict(t)
        with self._conn:
            self._conn.execute(
                f"INSERT OR REPLACE INTO paper_trades ({', '.join(_DB_COLS)})"
                f" VALUES ({','.join('?' * len(_COLS))})",
                [row[c] for c in _COLS],
            )

    def get(self, trade_id: str) -> PaperTrade | None:
        r = self._conn.execute("SELECT * FROM paper_trades WHERE id = ?", (trade_id,)).fetchone()
        return self._row(r) if r else None

    def read(
        self,
        *,
        start_ms: int | None = None,
        end_ms: int | None = None,
        index: str | None = None,
        status: str | None = None,
    ) -> list[PaperTrade]:
        """Trades by entry time, newest first."""
        where: list[str] = []
        args: list[object] = []
        for clause, value in (
            ("entry_ts >= ?", start_ms),
            ("entry_ts < ?", end_ms),
            ("idx = ?", index),
            ("status = ?", status),
        ):
            if value is not None:
                where.append(clause)
                args.append(value)
        sql = "SELECT * FROM paper_trades"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY entry_ts DESC"
        return [self._row(r) for r in self._conn.execute(sql, args)]

    def add_levels(self, change: LevelChange) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO paper_trade_levels (trade_id, ts, target, stop, ltp, source)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                astuple(change),
            )

    def levels(self, trade_id: str) -> list[LevelChange]:
        """Every set of levels the trade has had, oldest first."""
        rows = self._conn.execute(
            "SELECT trade_id, ts, target, stop, ltp, source FROM paper_trade_levels"
            " WHERE trade_id = ? ORDER BY id",
            (trade_id,),
        )
        return [LevelChange(*r) for r in rows]

    @staticmethod
    def _row(r: sqlite3.Row) -> PaperTrade:
        row = {c: r[d] for c, d in zip(_COLS, _DB_COLS, strict=True)}
        row["banked"] = bool(row["banked"])
        row["levels_edited"] = bool(row["levels_edited"])
        return PaperTrade(**row)


@dataclass(frozen=True)
class Price:
    ltp: float
    ts: int


@dataclass(frozen=True)
class ManualQuote:
    """What the ticket shows before a trade is opened by hand. Nothing is opened. The
    price-dependent fields are None until the instrument has a price, and `refusal` says
    why the trade would be refused now, if it would be."""

    index: str
    direction: Direction
    instrument_key: str
    trading_symbol: str
    strike: float
    expiry: str
    lots: int
    qty: int
    available: float | None  # free money in the paper bank
    ltp: float | None = None
    ltp_ts: int | None = None
    target: float | None = None
    stop: float | None = None
    cost: float | None = None
    blocked: float | None = None
    refusal: str | None = None


class PaperTradeManager:
    def __init__(  # noqa: PLR0913 -- injected collaborators
        self,
        *,
        clock: MarketClock,
        params: Callable[[], ParameterSet],
        conn: sqlite3.Connection,
        signals: SignalSource,
        price: Callable[[str], Price | None],
        feed_live: Callable[[], bool],
        enforce_hours: bool,
        last_recorded: Callable[[str, int], Price | None] | None = None,
        on_trade: Callable[[PaperTrade], None] | None = None,
        rules: PaperRules | None = None,
        bank: PaperBank | None = None,
    ) -> None:
        self._clock = clock
        self._params = params
        self.store = PaperTradeStore(conn)
        self._signals = signals
        self._price = price
        self._feed_live = feed_live
        self._enforce_hours = enforce_hours
        self._last_recorded = last_recorded
        self._on_trade = on_trade
        self.rules = rules or index_rules()
        self.bank = bank
        self.open_trades: dict[str, PaperTrade] = {}
        self._gap: set[str] = set()  # open trades that lived through a feed outage
        self._restore()

    # -- trader actions --------------------------------------------------------

    def open(self, signal_id: str) -> PaperTrade:
        """Open a trade from an active signal at the current price."""
        if signal_id == MANUAL_SIGNAL_ID:
            raise PaperError("not a signal: use the manual ticket to open a trade by hand")
        now = self._clock.now_ms()
        signal = next((s for s in self._signals.active.values() if s.id == signal_id), None)
        if signal is None:
            known = self._signals.store.get(signal_id)
            if known is None:
                raise PaperError("unknown signal", not_found=True)
            if known.shadow:
                raise PaperError("this is a shadow signal, recorded for comparison only")
            raise PaperError(f"signal is no longer active ({known.status})")
        p = self._params()
        refusal = self._entry_gate(now, p, cutoff=None)
        if refusal:
            raise PaperError(refusal)
        price = self._price(signal.instrument_key)
        if price is None:
            raise PaperError("no price for this instrument yet")

        lots = self.rules.lots(p)
        qty = signal.lot_size * lots
        # The live levels at the fill: what the signal panel showed when the trader clicked.
        target, stop = self._signals.levels_at(signal, price.ltp)
        cost = round(self.rules.cost(p, price.ltp, qty, lots), 2)
        blocked = round(self.rules.block(p, signal.index, price.ltp, qty, cost), 2)
        if self.bank:
            self.bank.reserve(blocked)
        trade = PaperTrade(
            id=uuid.uuid4().hex[:12],
            signal_id=signal.id,
            index=signal.index,
            instrument_key=signal.instrument_key,
            trading_symbol=signal.trading_symbol,
            direction=signal.direction,
            strike=signal.strike,
            expiry=signal.expiry,
            lots=lots,
            qty=qty,
            signal_entry=signal.entry_price,
            entry_price=price.ltp,
            entry_ts=now,
            slippage=round(price.ltp - signal.entry_price, 2),
            target_price=target,
            stop_price=stop,
            cost=cost,
            blocked=blocked if self.bank else 0.0,
            banked=self.bank is not None,
        )
        self._signals.mark_traded(signal.id, now)
        self._opened(trade)
        return trade

    def quote_manual(self, index: str, direction: Direction, strike: float | None) -> ManualQuote:
        """The ticket for a trade opened by hand: the contract, its price, the signal
        rule's target and stop there, the money it would take, and any refusal."""
        c = self._contract(index, direction, strike)
        p = self._params()
        lots = self.rules.lots(p)
        qty = c.lot_size * lots
        available = self.bank.summary().available if self.bank else None
        head = ManualQuote(
            index=c.index,
            direction=c.direction,
            instrument_key=c.instrument_key,
            trading_symbol=c.trading_symbol,
            strike=c.strike,
            expiry=c.expiry,
            lots=lots,
            qty=qty,
            available=available,
        )
        refusal = self._entry_gate(self._clock.now_ms(), p, cutoff=self._cutoff(c, p))
        price = self._price(c.instrument_key)
        if price is None:
            return replace(head, refusal=refusal or "no price for this instrument yet")
        target, stop = self._signals.default_levels(c, price.ltp)
        cost = round(self.rules.cost(p, price.ltp, qty, lots), 2)
        blocked = round(self.rules.block(p, c.index, price.ltp, qty, cost), 2)
        refusal = refusal or check_levels(c.direction, price.ltp, target, stop)
        if refusal is None and self.bank:
            try:
                self.bank.reserve(blocked)  # only checks: nothing is held until the open
            except PaperError as exc:
                refusal = exc.reason
        return replace(
            head,
            ltp=price.ltp,
            ltp_ts=price.ts,
            target=target,
            stop=stop,
            cost=cost,
            blocked=blocked,
            refusal=refusal,
        )

    def open_manual(
        self,
        index: str,
        direction: Direction,
        strike: float | None,
        *,
        quoted: float | None = None,
        target: float | None = None,
        stop: float | None = None,
    ) -> PaperTrade:
        """Open a trade by hand, with no signal, at the current price (E23).

        A level left out is the signal rule's at the fill; a typed one is kept, rounded to
        the nearest rupee like every level (E24). Both must stand at the fill
        (`check_levels`). `quoted` is the price the ticket
        showed: the trade records how far the fill was from it.
        """
        c = self._contract(index, direction, strike)
        now = self._clock.now_ms()
        p = self._params()
        refusal = self._entry_gate(now, p, cutoff=self._cutoff(c, p))
        if refusal:
            raise PaperError(refusal)
        price = self._price(c.instrument_key)
        if price is None:
            raise PaperError("no price for this instrument yet")
        fill = price.ltp
        if target is None or stop is None:
            default_target, default_stop = self._signals.default_levels(c, fill)
            target = default_target if target is None else round_rupee(target)
            stop = default_stop if stop is None else round_rupee(stop)
        else:
            target, stop = round_rupee(target), round_rupee(stop)
        bad = check_levels(c.direction, fill, target, stop)
        if bad:
            raise PaperError(bad)
        lots = self.rules.lots(p)
        qty = c.lot_size * lots
        cost = round(self.rules.cost(p, fill, qty, lots), 2)
        blocked = round(self.rules.block(p, c.index, fill, qty, cost), 2)
        if self.bank:
            self.bank.reserve(blocked)
        shown = fill if quoted is None else quoted
        trade = PaperTrade(
            id=uuid.uuid4().hex[:12],
            signal_id=MANUAL_SIGNAL_ID,
            index=c.index,
            instrument_key=c.instrument_key,
            trading_symbol=c.trading_symbol,
            direction=c.direction,
            strike=c.strike,
            expiry=c.expiry,
            lots=lots,
            qty=qty,
            signal_entry=shown,
            entry_price=fill,
            entry_ts=now,
            slippage=round(fill - shown, 2),
            target_price=target,
            stop_price=stop,
            cost=cost,
            blocked=blocked if self.bank else 0.0,
            banked=self.bank is not None,
        )
        self._opened(trade)
        return trade

    def set_levels(self, trade_id: str, *, target: float, stop: float) -> PaperTrade:
        """Change an open trade's target and stop (E23), rounded to the nearest rupee (E24).
        They must stand at the current price, so a live feed is needed. The next tick is
        checked against them."""
        trade = self.open_trades.get(trade_id)
        if trade is None:
            if self.store.get(trade_id) is None:
                raise PaperError("unknown paper trade", not_found=True)
            raise PaperError("paper trade is already closed")
        if not self._feed_live():
            raise PaperError("feed is not live, so there is no price to check the levels at")
        price = self._price(trade.instrument_key)
        if price is None:
            raise PaperError("no price for this instrument yet")
        target, stop = round_rupee(target), round_rupee(stop)
        bad = check_levels(trade.direction, price.ltp, target, stop)
        if bad:
            raise PaperError(bad)
        now = self._clock.now_ms()
        edited = replace(trade, target_price=target, stop_price=stop, levels_edited=True)
        self.open_trades[trade.id] = edited
        self.store.add_levels(LevelChange(trade.id, now, target, stop, price.ltp, "edit"))
        self._save(edited)
        log.info("paper trade %s levels now target %.2f stop %.2f", trade.id, target, stop)
        return edited

    def close_manual(self, trade_id: str) -> PaperTrade:
        trade = self.open_trades.get(trade_id)
        if trade is None:
            if self.store.get(trade_id) is None:
                raise PaperError("unknown paper trade", not_found=True)
            raise PaperError("paper trade is already closed")
        if not self._feed_live():
            raise PaperError("feed is not live, so there is no price to close at")
        price = self._price(trade.instrument_key)
        if price is None:
            raise PaperError("no price for this instrument yet")
        return self._close(trade, price.ltp, self._clock.now_ms(), "MANUAL", "live", None)

    # -- market inputs ---------------------------------------------------------

    def on_tick(self, st: StampedTick) -> None:
        """Target and stop are checked on every tick of an open trade's option."""
        if not self.open_trades:
            return
        t = st.tick
        for trade in [x for x in self.open_trades.values() if x.instrument_key == t.key]:
            quality: FillQuality = "after_gap" if trade.id in self._gap else "live"
            self._gap.discard(trade.id)  # only the first tick after an outage is "after gap"
            if trade.hit_target(t.ltp):
                self._close(trade, t.ltp, t.ts, "TARGET", quality, None)
            elif trade.hit_stop(t.ltp):
                self._close(trade, t.ltp, t.ts, "STOP", quality, None)

    def on_bias(self, b: BiasComputed) -> None:
        """Flag open trades the current view opposes; clear the flag when it no longer does."""
        opposing = {
            "Bearish": {"BUY_CE", "BUY_FUT"},
            "Bullish": {"BUY_PE", "SELL_FUT"},
        }.get(b.bias.label, set())
        for trade in [x for x in self.open_trades.values() if x.index == b.index]:
            warning: Warning | None = "bias_reversed" if trade.direction in opposing else None
            if warning != trade.warning:
                updated = replace(trade, warning=warning)
                self.open_trades[trade.id] = updated
                self._save(updated)

    def mark_gap(self) -> None:
        """The feed was silent for a while: the next tick of each open trade is `after_gap`."""
        self._gap.update(self.open_trades)

    def tick(self, now_ms: int) -> None:
        """Housekeeping twice a second: note feed outages, and square off on time."""
        if not self.open_trades:
            return
        live = self._feed_live()
        if not live:
            self._gap.update(self.open_trades)
        if not self._enforce_hours:
            return
        if ms_to_ist(now_ms).time() < self.rules.square_off(self._params()):
            return
        for trade in list(self.open_trades.values()):
            price = self._price(trade.instrument_key)
            if price is None:  # restarted and never saw a tick: nothing better than entry
                self._close(trade, trade.entry_price, now_ms, "SQUARE_OFF", "stale", None)
            elif live and trade.id not in self._gap:
                self._close(trade, price.ltp, now_ms, "SQUARE_OFF", "live", None)
            else:
                age = max(0, now_ms - price.ts)
                self._close(trade, price.ltp, now_ms, "SQUARE_OFF", "stale", age)

    # -- internals -------------------------------------------------------------

    def _entry_gate(self, now: int, p: ParameterSet, *, cutoff: time | None) -> str | None:
        """Why no trade may be opened now, if anything. `cutoff` is the signal cut-off a
        trade opened by hand is held to."""
        if self._enforce_hours:
            if self._clock.status() != "live":
                return "market is not open"
            t = ms_to_ist(now).time()
            if t >= self.rules.square_off(p):
                return "past the square-off time"
            if cutoff is not None and t >= cutoff:
                return f"no new trades after {cutoff:%H:%M}"
        blocked_by = self.rules.entry_block(now, p) if self.rules.entry_block else None
        if blocked_by:
            return blocked_by
        if not self._feed_live():
            return "feed is not live, so there is no price to trade at"
        return None

    def _cutoff(self, c: ManualContract, p: ParameterSet) -> time | None:
        return self.rules.last_entry(p, c.is_expiry_day) if self.rules.last_entry else None

    def _contract(self, index: str, direction: Direction, strike: float | None) -> ManualContract:
        c = self._signals.manual_contract(index, direction, strike)
        if c is None or not self.rules.owns(c.index):
            raise PaperError("no such contract to trade here", not_found=True)
        return c

    def _opened(self, trade: PaperTrade) -> None:
        self.open_trades[trade.id] = trade
        t = trade
        self.store.add_levels(
            LevelChange(t.id, t.entry_ts, t.target_price, t.stop_price, t.entry_price, "entry")
        )
        self._save(trade)
        log.info(
            "paper trade %s opened%s %s @ %.2f",
            trade.id,
            " by hand" if trade.is_manual else "",
            trade.trading_symbol,
            trade.entry_price,
        )

    def _restore(self) -> None:
        """Pick up trades left open by a restart. The app was away, so that is a gap."""
        today = self._clock.today()
        for trade in self.store.read(status="open"):
            if not self.rules.owns(trade.index):
                continue  # another market's manager restores it
            entry_day = ms_to_ist(trade.entry_ts).date()
            if entry_day >= today:
                self.open_trades[trade.id] = trade
                self._gap.add(trade.id)
                continue
            # Left open on an earlier day: it should have been squared off then.
            sq = self.rules.square_off(self._params())
            sq_ms = ist_to_ms(datetime.combine(entry_day, sq, tzinfo=IST))
            last = self._last_recorded(trade.instrument_key, sq_ms) if self._last_recorded else None
            if last is None:
                self._close(trade, trade.entry_price, sq_ms, "SQUARE_OFF", "stale", None)
            else:
                age = max(0, sq_ms - last.ts)
                self._close(trade, last.ltp, sq_ms, "SQUARE_OFF", "stale", age)

    def _close(
        self,
        trade: PaperTrade,
        price: float,
        ts: int,
        reason: ExitReason,
        quality: FillQuality,
        age_ms: int | None,
    ) -> PaperTrade:
        gross, net = trade.pnl_at(price)
        closed = replace(
            trade,
            status="closed",
            exit_price=price,
            exit_ts=max(ts, trade.entry_ts),
            exit_reason=reason,
            exit_fill_quality=quality,
            exit_price_age_ms=age_ms,
            gross=gross,
            net=net,
            warning=None,
        )
        self.open_trades.pop(trade.id, None)
        self._gap.discard(trade.id)
        self._save(closed)
        log.info(
            "paper trade %s closed %s @ %.2f net %.2f (%s)", trade.id, reason, price, net, quality
        )
        return closed

    def _save(self, trade: PaperTrade) -> None:
        self.store.upsert(trade)
        if self._on_trade:
            self._on_trade(trade)


# -- journal ----------------------------------------------------------------------


@dataclass(frozen=True)
class JournalStats:
    scope: str  # "overall" (index options), an index, "bullion", a metal, or "manual"
    trades: int
    hits: int
    hit_rate: float | None  # share of closed trades with net > 0
    avg_win: float | None
    avg_loss: float | None
    net_total: float
    gross_total: float
    avg_duration_s: float | None
    by_reason: dict[str, int]
    non_live_fills: int


def _stats(scope: str, closed: list[PaperTrade]) -> JournalStats:
    nets = [t.net or 0.0 for t in closed]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n <= 0]
    durations = [(t.exit_ts or t.entry_ts) - t.entry_ts for t in closed]
    by_reason: dict[str, int] = {}
    for t in closed:
        key = t.exit_reason or "UNKNOWN"
        by_reason[key] = by_reason.get(key, 0) + 1
    n = len(closed)
    return JournalStats(
        scope=scope,
        trades=n,
        hits=len(wins),
        hit_rate=round(len(wins) / n, 4) if n else None,
        avg_win=round(sum(wins) / len(wins), 2) if wins else None,
        avg_loss=round(sum(losses) / len(losses), 2) if losses else None,
        net_total=round(sum(nets), 2),
        gross_total=round(sum(t.gross or 0.0 for t in closed), 2),
        avg_duration_s=round(sum(durations) / n / 1000, 1) if n else None,
        by_reason=by_reason,
        non_live_fills=sum(1 for t in closed if t.exit_fill_quality != "live"),
    )


def journal_stats(trades: Iterable[PaperTrade]) -> list[JournalStats]:
    """Overall (index options only) first, then one entry per index; then, when there are
    bullion trades, a `bullion` total and one entry per metal; last, when there are any,
    `manual`: every trade opened by hand, kept out of the others so they measure the
    signals alone (E23). Only closed trades count."""
    closed = [t for t in trades if not t.is_open]
    manual = [t for t in closed if t.is_manual]
    signalled = [t for t in closed if not t.is_manual]
    options = [t for t in signalled if t.index not in METALS]
    bullion = [t for t in signalled if t.index in METALS]
    out = [_stats("overall", options)]
    for index in sorted({t.index for t in options}):
        out.append(_stats(index, [t for t in options if t.index == index]))
    if bullion:
        out.append(_stats("bullion", bullion))
        for metal in sorted({t.index for t in bullion}):
            out.append(_stats(metal, [t for t in bullion if t.index == metal]))
    if manual:
        out.append(_stats("manual", manual))
    return out

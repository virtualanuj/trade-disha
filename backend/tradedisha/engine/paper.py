"""Paper trades: opened only by the trader, tracked tick by tick to an exit. Spec §10.

A trade opens at the price prevailing when the trader clicks (not the signal's entry
price) and closes at target, stop, the square-off time, or by hand. Nothing here places a
real order, and nothing here opens a trade on its own.

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
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, time
from typing import Literal, Protocol

from tradedisha.clock import IST, MarketClock, ist_to_ms, ms_to_ist
from tradedisha.engine.bias_engine import BiasComputed
from tradedisha.engine.signals import Direction, Signal, SignalStore
from tradedisha.feed.bus import StampedTick
from tradedisha.parameters.model import ParameterSet

log = logging.getLogger(__name__)

TradeStatus = Literal["open", "closed"]
ExitReason = Literal["TARGET", "STOP", "SQUARE_OFF", "MANUAL"]
FillQuality = Literal["live", "after_gap", "stale"]
Warning = Literal["bias_reversed"]

METALS: frozenset[str] = frozenset({"GOLD", "SILVER"})  # bullion trades, by `index`


class SignalSource(Protocol):
    """What a manager needs from a signal engine (index or bullion)."""

    active: dict[str, Signal]
    store: SignalStore

    def mark_traded(self, signal_id: str, now_ms: int) -> Signal | None: ...
    def levels_at(self, s: Signal, price: float) -> tuple[float, float]: ...


@dataclass(frozen=True)
class PaperRules:
    """One market's paper-trading rules."""

    owns: Callable[[str], bool]  # which `index` values this manager trades
    square_off: Callable[[ParameterSet], time]
    lots: Callable[[ParameterSet], int]
    # round-trip cost for the whole trade, fixed at entry: (params, entry price, qty, lots)
    cost: Callable[[ParameterSet, float, int, int], float]


def index_rules() -> PaperRules:
    """NIFTY / BANK NIFTY options: the `paper` section, a flat fee per lot."""
    return PaperRules(
        owns=lambda index: index not in METALS,
        square_off=lambda p: p.paper.square_off_time,
        lots=lambda p: p.paper.lots,
        cost=lambda p, _entry, _qty, lots: p.paper.cost_per_trade * lots,
    )


def bullion_rules() -> PaperRules:
    """MCX GOLD / SILVER futures: the `bullion` section; cost has a part that scales with
    value, because a GOLD lot is worth over a crore."""

    def cost(p: ParameterSet, entry: float, qty: int, lots: int) -> float:
        b = p.bullion
        return b.cost_fixed_per_lot * lots + b.cost_pct_of_value / 100 * entry * qty * 2

    return PaperRules(
        owns=lambda index: index in METALS,
        square_off=lambda p: p.bullion.square_off_time,
        lots=lambda p: p.bullion.lots,
        cost=cost,
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
    signal_entry: float
    entry_price: float
    entry_ts: int
    slippage: float  # fill minus the signal's entry price
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

    @property
    def is_open(self) -> bool:
        return self.status == "open"

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

    @staticmethod
    def _row(r: sqlite3.Row) -> PaperTrade:
        return PaperTrade(**{c: r[d] for c, d in zip(_COLS, _DB_COLS, strict=True)})


@dataclass(frozen=True)
class Price:
    ltp: float
    ts: int


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
        self.open_trades: dict[str, PaperTrade] = {}
        self._gap: set[str] = set()  # open trades that lived through a feed outage
        self._restore()

    # -- trader actions --------------------------------------------------------

    def open(self, signal_id: str) -> PaperTrade:
        """Open a trade from an active signal at the current price."""
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
        if self._enforce_hours:
            if self._clock.status() != "live":
                raise PaperError("market is not open")
            if ms_to_ist(now).time() >= self.rules.square_off(p):
                raise PaperError("past the square-off time")
        if not self._feed_live():
            raise PaperError("feed is not live, so there is no price to trade at")
        price = self._price(signal.instrument_key)
        if price is None:
            raise PaperError("no price for this instrument yet")

        lots = self.rules.lots(p)
        qty = signal.lot_size * lots
        # The live levels at the fill: what the signal panel showed when the trader clicked.
        target, stop = self._signals.levels_at(signal, price.ltp)
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
            cost=round(self.rules.cost(p, price.ltp, qty, lots), 2),
        )
        self._signals.mark_traded(signal.id, now)
        self.open_trades[trade.id] = trade
        self._save(trade)
        log.info("paper trade %s opened %s @ %.2f", trade.id, trade.trading_symbol, price.ltp)
        return trade

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
    scope: str  # "overall" (index options), an index, "bullion" or a metal
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
    bullion trades, a `bullion` total and one entry per metal. Only closed trades count."""
    closed = [t for t in trades if not t.is_open]
    options = [t for t in closed if t.index not in METALS]
    bullion = [t for t in closed if t.index in METALS]
    out = [_stats("overall", options)]
    for index in sorted({t.index for t in options}):
        out.append(_stats(index, [t for t in options if t.index == index]))
    if bullion:
        out.append(_stats("bullion", bullion))
        for metal in sorted({t.index for t in bullion}):
            out.append(_stats(metal, [t for t in bullion if t.index == metal]))
    return out

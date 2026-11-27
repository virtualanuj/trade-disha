"""The paper bank: the money behind paper trades (Milestone E17). Spec §10.5.

One account funds every market's paper trades (index options and bullion futures). A
trade blocks money when it opens (an option's premium, a future's margin, plus the
round-trip cost) and settles its net P&L when it closes. Nothing is ever deleted, and no
running balance is stored; it is worked out each time:

    balance   = opening balance + net of every closed trade the bank funded
    blocked   = what the open trades hold
    available = balance - blocked

The opening balance is a parameter. The first read records it as the opening deposit;
raising it later is a cash deposit of the difference, lowering it a withdrawal. Each move
is a row in `bank_ledger`, and P&L history keeps counting throughout. A withdrawal is not
capped by the free money, and a futures loss can be larger than the margin it blocked, so
available (or the balance) can go negative; no new trade opens until it is positive again.

The statement (E26) lists every cash move with the running figures after it: the ledger's
rows, and for each funded trade a BLOCK when it opened and a SETTLE when it closed.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from typing import Literal

from tradedisha.clock import epoch_ms_now
from tradedisha.engine.paper import PaperError, PaperTrade, PaperTradeStore
from tradedisha.parameters.model import ParameterSet

LedgerKind = Literal["OPEN", "DEPOSIT", "WITHDRAW"]
StatementKind = Literal["OPEN", "DEPOSIT", "WITHDRAW", "BLOCK", "SETTLE"]


@dataclass(frozen=True)
class LedgerEntry:
    id: int
    ts: int  # wall clock
    kind: LedgerKind
    amount: float  # always positive
    opening_balance: float  # the parameter after this entry
    config_version: int | None


@dataclass(frozen=True)
class BankSummary:
    opening_balance: float  # the parameter in force: cash put in, net of withdrawals
    opened_ts: int  # when the opening deposit was recorded
    deposited: float  # cash deposited after the opening
    withdrawn: float
    realised: float  # net of every closed trade the bank funded
    balance: float
    blocked: float
    available: float
    open_trades: int
    ledger: tuple[LedgerEntry, ...]


@dataclass(frozen=True)
class StatementRow:
    """One cash move and the bank's figures after it."""

    ts: int
    kind: StatementKind
    held: float  # change in what is blocked: + at BLOCK, - at SETTLE, else 0
    cash: float  # change in the balance: deposit +, withdrawal -, settled net +/-
    balance: float
    blocked: float
    available: float
    trade_id: str | None = None
    index: str | None = None
    direction: str | None = None
    strike: float | None = None
    trading_symbol: str | None = None


def build_statement(
    ledger: Iterable[LedgerEntry], trades: Iterable[PaperTrade]
) -> list[StatementRow]:
    """Every cash move, oldest first, with the running figures after each.

    Only trades the bank funded count. The opening deposit always comes first: ledger rows
    carry the wall clock and trades the market clock, which in a replay is another day.
    """
    events: list[tuple[int, int, int, LedgerEntry | PaperTrade, StatementKind]] = []
    for e in ledger:
        events.append((0 if e.kind == "OPEN" else 1, e.ts, len(events), e, e.kind))
    for t in trades:
        if not t.banked:
            continue
        events.append((1, t.entry_ts, len(events), t, "BLOCK"))
        if not t.is_open and t.exit_ts is not None:
            events.append((1, t.exit_ts, len(events), t, "SETTLE"))
    events.sort(key=lambda ev: ev[:3])

    rows: list[StatementRow] = []
    balance = blocked = 0.0
    for _, ts, _, source, kind in events:
        if isinstance(source, LedgerEntry):
            held, cash = 0.0, -source.amount if kind == "WITHDRAW" else source.amount
        elif kind == "BLOCK":
            held, cash = source.blocked, 0.0
        else:
            held, cash = -source.blocked, source.net or 0.0
        balance = round(balance + cash, 2)
        blocked = round(blocked + held, 2)
        trade = source if isinstance(source, PaperTrade) else None
        rows.append(
            StatementRow(
                ts=ts,
                kind=kind,
                held=round(held, 2),
                cash=round(cash, 2),
                balance=balance,
                blocked=blocked,
                available=round(balance - blocked, 2),
                trade_id=trade.id if trade else None,
                index=trade.index if trade else None,
                direction=trade.direction if trade else None,
                strike=trade.strike if trade else None,
                trading_symbol=trade.trading_symbol if trade else None,
            )
        )
    return rows


def rupees(amount: float) -> str:
    return f"₹{amount:,.0f}"


class PaperBank:
    def __init__(
        self,
        conn: sqlite3.Connection,
        params: Callable[[], ParameterSet],
        config_version: Callable[[], int | None] = lambda: None,
    ) -> None:
        self._conn = conn
        self._params = params
        self._config_version = config_version

    def ledger(self) -> list[LedgerEntry]:
        """Every cash move, oldest first, after recording any change of the opening balance."""
        self._sync()
        return self._entries()

    def summary(self) -> BankSummary:
        ledger = self.ledger()
        realised = float(
            self._conn.execute(
                "SELECT COALESCE(SUM(net), 0) FROM paper_trades"
                " WHERE status = 'closed' AND banked = 1"
            ).fetchone()[0]
        )
        blocked_sum, n_open = self._conn.execute(
            "SELECT COALESCE(SUM(blocked), 0), COUNT(*) FROM paper_trades WHERE status = 'open'"
        ).fetchone()
        opening = ledger[-1].opening_balance
        balance = round(opening + realised, 2)
        blocked = round(float(blocked_sum), 2)
        return BankSummary(
            opening_balance=opening,
            opened_ts=ledger[0].ts,
            deposited=round(sum(e.amount for e in ledger if e.kind == "DEPOSIT"), 2),
            withdrawn=round(sum(e.amount for e in ledger if e.kind == "WITHDRAW"), 2),
            realised=round(realised, 2),
            balance=balance,
            blocked=blocked,
            available=round(balance - blocked, 2),
            open_trades=int(n_open),
            ledger=tuple(ledger),
        )

    def statement(
        self,
        start_ms: int | None = None,
        end_ms: int | None = None,
        kinds: Collection[StatementKind] | None = None,
        index: str | None = None,
    ) -> list[StatementRow]:
        """The statement, narrowed after the running figures are worked out over the whole
        history. A market filter keeps trade rows only: cash moves belong to no market."""
        rows = build_statement(self.ledger(), PaperTradeStore(self._conn).read())
        return [
            r
            for r in rows
            if (start_ms is None or r.ts >= start_ms)
            and (end_ms is None or r.ts <= end_ms)
            and (not kinds or r.kind in kinds)
            and (index is None or r.index == index)
        ]

    def reserve(self, amount: float) -> None:
        """Refuse a trade the bank cannot fund: `amount` must fit in what is available."""
        s = self.summary()
        if amount > s.available:
            raise PaperError(
                f"not enough money in the paper bank: needs {rupees(amount)},"
                f" {rupees(s.available)} available"
            )

    # -- internals -------------------------------------------------------------------

    def _entries(self) -> list[LedgerEntry]:
        rows = self._conn.execute(
            "SELECT id, ts, kind, amount, opening_balance, config_version"
            " FROM bank_ledger ORDER BY id"
        ).fetchall()
        return [
            LedgerEntry(int(r[0]), int(r[1]), r[2], float(r[3]), float(r[4]), r[5]) for r in rows
        ]

    def _sync(self) -> None:
        """Record the opening deposit, or the deposit or withdrawal a changed balance means."""
        want = self._params().bank.opening_balance
        last = self._conn.execute(
            "SELECT opening_balance FROM bank_ledger ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if last is not None and float(last[0]) == want:
            return
        kind: LedgerKind
        if last is None:
            kind, amount = "OPEN", want
        else:
            diff = want - float(last[0])
            kind, amount = ("DEPOSIT", diff) if diff > 0 else ("WITHDRAW", -diff)
        with self._conn:
            self._conn.execute(
                "INSERT INTO bank_ledger (ts, kind, amount, opening_balance, config_version)"
                " VALUES (?, ?, ?, ?, ?)",
                (epoch_ms_now(), kind, round(amount, 2), want, self._config_version()),
            )

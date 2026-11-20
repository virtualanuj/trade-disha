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
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from tradedisha.clock import epoch_ms_now
from tradedisha.engine.paper import PaperError
from tradedisha.parameters.model import ParameterSet

LedgerKind = Literal["OPEN", "DEPOSIT", "WITHDRAW"]


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

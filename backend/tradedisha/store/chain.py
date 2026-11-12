"""Per-strike per-minute chain snapshots, for replay and tuning."""

from __future__ import annotations

import sqlite3

from tradedisha.market.chain import ChainSnapshotMinute, ChainState

INSERT = (
    "INSERT OR REPLACE INTO chain_minutes (idx, minute_ts, strike, ce_ltp, ce_oi, ce_oi_chg_open,"
    " ce_iv, ce_buildup, pe_ltp, pe_oi, pe_oi_chg_open, pe_iv, pe_buildup, atm, pcr, max_pain)"
    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)


class ChainMinuteStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def write(self, chain: ChainState, snap: ChainSnapshotMinute) -> int:
        rows = [
            (
                chain.index,
                snap.minute_ts,
                r.strike,
                r.ce.ltp,
                r.ce.oi,
                r.ce.oi_chg_open,
                r.ce.iv,
                r.ce.buildup,
                r.pe.ltp,
                r.pe.oi,
                r.pe.oi_chg_open,
                r.pe.iv,
                r.pe.buildup,
                snap.atm,
                snap.pcr,
                snap.max_pain,
            )
            for r in chain.rows.values()
        ]
        with self._conn:
            self._conn.executemany(INSERT, rows)
        return len(rows)

    def count(self, index: str | None = None) -> int:
        if index is None:
            return int(self._conn.execute("SELECT COUNT(*) FROM chain_minutes").fetchone()[0])
        return int(
            self._conn.execute(
                "SELECT COUNT(*) FROM chain_minutes WHERE idx = ?", (index,)
            ).fetchone()[0]
        )

"""GIFT Nifty snapshots, one per NSE trading day (spec §6.8)."""

from __future__ import annotations

import sqlite3
from datetime import date

from tradedisha.indicators.gift import GiftSnapshot


class GiftStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, day: date) -> GiftSnapshot | None:
        r = self._conn.execute(
            "SELECT ref_ts, ref_close, preopen_ts, preopen_price FROM gift_nifty WHERE day = ?",
            (day.isoformat(),),
        ).fetchone()
        return GiftSnapshot(day, int(r[0]), float(r[1]), int(r[2]), float(r[3])) if r else None

    def put(self, snap: GiftSnapshot, fetched_at: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO gift_nifty"
            " (day, ref_ts, ref_close, preopen_ts, preopen_price, fetched_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                snap.day.isoformat(),
                snap.ref_ts,
                snap.ref_close,
                snap.preopen_ts,
                snap.preopen_price,
                fetched_at,
            ),
        )

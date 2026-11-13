"""Batched tick persistence and date-ranged reads for replay."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

from tradedisha.clock import IST, ist_to_ms, ms_to_ist
from tradedisha.feed.provider import Tick

INSERT = (
    "INSERT INTO ticks (key, ts, ltp, volume, oi, bid, ask, iv, delta) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def _row(t: Tick) -> tuple[object, ...]:
    return (t.key, t.ts, t.ltp, t.volume, t.oi, t.bid, t.ask, t.iv, t.delta)


def _to_tick(r: sqlite3.Row) -> Tick:
    return Tick(
        key=r["key"],
        ts=r["ts"],
        ltp=r["ltp"],
        volume=r["volume"],
        oi=r["oi"],
        bid=r["bid"],
        ask=r["ask"],
        iv=r["iv"],
        delta=r["delta"],
    )


def day_bounds_ms(day: date) -> tuple[int, int]:
    """[start, end) epoch-ms of a calendar day in IST."""
    start = datetime.combine(day, datetime.min.time(), tzinfo=IST)
    return ist_to_ms(start), ist_to_ms(start + timedelta(days=1))


class TickStore:
    """Buffers ticks in memory and writes them in batches."""

    def __init__(self, conn: sqlite3.Connection, *, batch_size: int = 500) -> None:
        self._conn = conn
        self._batch_size = batch_size
        self._buffer: list[tuple[object, ...]] = []
        self.written = 0

    def add(self, tick: Tick) -> None:
        self._buffer.append(_row(tick))
        if len(self._buffer) >= self._batch_size:
            self.flush()

    def flush(self) -> int:
        if not self._buffer:
            return 0
        rows, self._buffer = self._buffer, []
        with self._conn:
            self._conn.executemany(INSERT, rows)
        self.written += len(rows)
        return len(rows)

    @property
    def pending(self) -> int:
        return len(self._buffer)

    def read_day(self, day: date, keys: list[str] | None = None) -> list[Tick]:
        """All ticks on an IST calendar day, ordered by timestamp."""
        start, end = day_bounds_ms(day)
        sql = "SELECT * FROM ticks WHERE ts >= ? AND ts < ?"
        params: list[object] = [start, end]
        if keys:
            sql += f" AND key IN ({','.join('?' * len(keys))})"
            params.extend(keys)
        sql += " ORDER BY ts, rowid"
        return [_to_tick(r) for r in self._conn.execute(sql, params)]

    def first_tick(self, day: date, key: str) -> Tick | None:
        """The earliest recorded tick of one instrument on an IST calendar day."""
        start, end = day_bounds_ms(day)
        row = self._conn.execute(
            "SELECT * FROM ticks WHERE key = ? AND ts >= ? AND ts < ? ORDER BY ts, rowid LIMIT 1",
            (key, start, end),
        ).fetchone()
        return _to_tick(row) if row is not None else None

    def last_tick_before(self, key: str, before_ms: int) -> Tick | None:
        """The latest recorded tick of one instrument at or before a moment."""
        row = self._conn.execute(
            "SELECT * FROM ticks WHERE key = ? AND ts <= ? ORDER BY ts DESC, rowid DESC LIMIT 1",
            (key, before_ms),
        ).fetchone()
        return _to_tick(row) if row is not None else None

    def recorded_days(self) -> list[date]:
        """Distinct IST dates that have ticks, newest first."""
        rows = self._conn.execute("SELECT MIN(ts) AS lo, MAX(ts) AS hi FROM ticks").fetchone()
        if rows["lo"] is None:
            return []
        day = ms_to_ist(rows["lo"]).date()
        last = ms_to_ist(rows["hi"]).date()
        out: list[date] = []
        while day <= last:
            s, e = day_bounds_ms(day)
            hit = self._conn.execute(
                "SELECT 1 FROM ticks WHERE ts >= ? AND ts < ? LIMIT 1", (s, e)
            ).fetchone()
            if hit:
                out.append(day)
            day += timedelta(days=1)
        return list(reversed(out))

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM ticks").fetchone()[0])


class FeedEventLog:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def write(self, ts: int, kind: str, detail: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO feed_events (ts, kind, detail) VALUES (?, ?, ?)", (ts, kind, detail)
            )

"""Batched tick persistence and date-ranged reads for replay."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
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


PRUNE_BATCH = 50_000


@dataclass(frozen=True)
class TickUsage:
    db_bytes: int
    tick_rows: int
    tick_days: int
    oldest: date | None
    newest: date | None
    prune_rows: int
    prune_days: int
    prune_bytes_estimate: int


@dataclass(frozen=True)
class PruneResult:
    rows_deleted: int
    bytes_freed: int


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

    # -- pruning (spec §10.4) --------------------------------------------------

    def db_bytes(self) -> int:
        pages = int(self._conn.execute("PRAGMA page_count").fetchone()[0])
        free = int(self._conn.execute("PRAGMA freelist_count").fetchone()[0])
        size = int(self._conn.execute("PRAGMA page_size").fetchone()[0])
        return (pages - free) * size

    def usage(self, until: date | None = None) -> TickUsage:
        """What is held, and what deleting ticks up to and including `until` would remove."""
        total = self.count()
        days = self.recorded_days()
        used = self.db_bytes()
        rows = 0
        prune_days = 0
        if until is not None:
            end = day_bounds_ms(until)[1]
            rows = int(
                self._conn.execute("SELECT COUNT(*) FROM ticks WHERE ts < ?", (end,)).fetchone()[0]
            )
            prune_days = sum(1 for d in days if d <= until)
        return TickUsage(
            db_bytes=used,
            tick_rows=total,
            tick_days=len(days),
            oldest=days[-1] if days else None,
            newest=days[0] if days else None,
            prune_rows=rows,
            prune_days=prune_days,
            # Ticks dominate the file, so their share of rows is a fair estimate of bytes.
            prune_bytes_estimate=int(used * rows / total) if total else 0,
        )

    async def prune(self, until: date, *, batch: int = PRUNE_BATCH) -> PruneResult:
        """Delete ticks up to and including `until`, in batches so live ticks keep flowing.

        Only `ticks` is touched; candles, chain history, bias, signals and trades stay.
        """
        end = day_bounds_ms(until)[1]
        before = self.db_bytes()
        deleted = 0
        while True:
            with self._conn:
                cur = self._conn.execute(
                    "DELETE FROM ticks WHERE rowid IN"
                    " (SELECT rowid FROM ticks WHERE ts < ? LIMIT ?)",
                    (end, batch),
                )
            deleted += cur.rowcount
            if cur.rowcount < batch:
                break
            await asyncio.sleep(0)  # let the feed pump and the websocket run
        self._conn.execute("PRAGMA incremental_vacuum").fetchall()
        self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        return PruneResult(rows_deleted=deleted, bytes_freed=max(0, before - self.db_bytes()))


class FeedEventLog:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def write(self, ts: int, kind: str, detail: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO feed_events (ts, kind, detail) VALUES (?, ?, ?)", (ts, kind, detail)
            )

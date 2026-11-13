"""1-minute OHLCV candles per instrument, built from ticks. Spec §7.1.

Minute boundaries are driven by exchange timestamps. A wall-clock fallback (`flush_stale`)
closes a candle when no tick arrives for a while. Minutes with no ticks produce a
carry-forward candle flagged synthetic so indicator windows stay aligned.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field

from tradedisha.feed.provider import Tick

MINUTE_MS = 60_000


@dataclass
class Candle:
    key: str
    minute_ts: int  # start of minute, epoch ms
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    synthetic: bool = False
    ticks: int = 0

    def update(self, ltp: float, dvol: int) -> None:
        self.high = max(self.high, ltp)
        self.low = min(self.low, ltp)
        self.close = ltp
        self.volume += dvol
        self.ticks += 1


@dataclass
class _Series:
    current: Candle | None = None
    closed: list[Candle] = field(default_factory=list)
    last_cum_volume: int | None = None
    pv_sum: float = 0.0  # sum of close x volume over closed candles, for VWAP
    v_sum: int = 0

    @property
    def vwap(self) -> float | None:
        return self.pv_sum / self.v_sum if self.v_sum else None


CandleListener = Callable[[Candle], None]


class CandleBuilder:
    def __init__(self, *, max_history: int = 400) -> None:
        self._series: dict[str, _Series] = {}
        self._listeners: list[CandleListener] = []
        self._max = max_history

    def on_close(self, fn: CandleListener) -> None:
        self._listeners.append(fn)

    # -- input ---------------------------------------------------------------

    def apply(self, t: Tick) -> list[Candle]:
        """Apply a tick; returns any candles closed as a result (usually 0 or 1)."""
        s = self._series.setdefault(t.key, _Series())
        minute = t.ts // MINUTE_MS * MINUTE_MS
        dvol = 0
        if t.volume is not None:
            if s.last_cum_volume is not None:
                dvol = max(0, t.volume - s.last_cum_volume)
            s.last_cum_volume = t.volume

        closed: list[Candle] = []
        cur = s.current
        if cur is None:
            s.current = Candle(t.key, minute, t.ltp, t.ltp, t.ltp, t.ltp, dvol, ticks=1)
            return closed
        if minute < cur.minute_ts:
            return closed  # late tick for an already-closed minute; ignore
        if minute > cur.minute_ts:
            closed.append(self._close(s, cur))
            # gap-fill minutes with no ticks
            m = cur.minute_ts + MINUTE_MS
            while m < minute:
                gap = Candle(
                    t.key, m, cur.close, cur.close, cur.close, cur.close, 0, synthetic=True
                )
                closed.append(self._close(s, gap))
                m += MINUTE_MS
            s.current = Candle(t.key, minute, t.ltp, t.ltp, t.ltp, t.ltp, dvol, ticks=1)
            return closed
        cur.update(t.ltp, dvol)
        return closed

    def flush_stale(self, now_ms: int, *, grace_ms: int = 2_000) -> list[Candle]:
        """Close any current candle whose minute ended more than `grace_ms` ago."""
        out: list[Candle] = []
        for s in self._series.values():
            cur = s.current
            if cur is not None and now_ms >= cur.minute_ts + MINUTE_MS + grace_ms:
                out.append(self._close(s, cur))
                s.current = None
        return out

    def _close(self, s: _Series, c: Candle) -> Candle:
        s.closed.append(c)
        if len(s.closed) > self._max:
            del s.closed[: len(s.closed) - self._max]
        if c.volume:
            s.pv_sum += c.close * c.volume
            s.v_sum += c.volume
        for fn in self._listeners:
            fn(c)
        return c

    # -- queries -------------------------------------------------------------

    def seed(self, key: str, candles: list[Candle]) -> None:
        """Pre-load closed candles (backfill); no listeners fire."""
        s = self._series.setdefault(key, _Series())
        for c in candles:
            s.closed.append(c)
            if c.volume:
                s.pv_sum += c.close * c.volume
                s.v_sum += c.volume

    def closed(self, key: str) -> list[Candle]:
        s = self._series.get(key)
        return list(s.closed) if s else []

    def current(self, key: str) -> Candle | None:
        s = self._series.get(key)
        return s.current if s else None

    def vwap(self, key: str) -> float | None:
        s = self._series.get(key)
        return s.vwap if s else None


class CandleStore:
    INSERT = (
        "INSERT OR REPLACE INTO candles_1m (key, minute_ts, o, h, l, c, v, synthetic)"
        " VALUES (?,?,?,?,?,?,?,?)"
    )

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def write(self, c: Candle) -> None:
        with self._conn:
            self._conn.execute(
                self.INSERT,
                (c.key, c.minute_ts, c.open, c.high, c.low, c.close, c.volume, int(c.synthetic)),
            )

    def write_many(self, candles: list[Candle]) -> None:
        """Backfilled candles, in one transaction."""
        with self._conn:
            self._conn.executemany(
                self.INSERT,
                [
                    (c.key, c.minute_ts, c.open, c.high, c.low, c.close, c.volume, int(c.synthetic))
                    for c in candles
                ],
            )

    def read(self, key: str, start_ms: int, end_ms: int) -> list[Candle]:
        rows = self._conn.execute(
            "SELECT * FROM candles_1m WHERE key = ? AND minute_ts >= ? AND minute_ts < ?"
            " ORDER BY minute_ts",
            (key, start_ms, end_ms),
        )
        return [
            Candle(
                r["key"],
                r["minute_ts"],
                r["o"],
                r["h"],
                r["l"],
                r["c"],
                r["v"],
                bool(r["synthetic"]),
            )
            for r in rows
        ]

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM candles_1m").fetchone()[0])

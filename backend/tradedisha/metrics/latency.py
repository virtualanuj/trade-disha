"""Per-hop latency samples with percentile summaries.

Hops (spec §14a): src_to_in (exchange ts → ingest), in_to_out (ingest → WS frame sent),
out_to_recv and recv_to_paint (reported by the browser), loop_lag (asyncio scheduling).
"""

from __future__ import annotations

import asyncio
import math
import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass

from tradedisha.clock import epoch_ms_now

HOPS = ("src_to_in", "in_to_out", "out_to_recv", "recv_to_paint", "loop_lag")


@dataclass(frozen=True)
class HopSummary:
    hop: str
    n: int
    p50: float
    p95: float
    p99: float
    max: float


def percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    idx = max(0, min(len(sorted_values) - 1, math.ceil(q * len(sorted_values)) - 1))
    return sorted_values[idx]


class LatencyTracker:
    """Keeps the last `window_ms` of samples per hop in memory."""

    def __init__(self, *, window_ms: int = 15 * 60_000, max_per_hop: int = 20_000) -> None:
        self._window = window_ms
        self._samples: dict[str, deque[tuple[int, float]]] = defaultdict(
            lambda: deque(maxlen=max_per_hop)
        )

    def record(self, hop: str, value_ms: float, *, at_ms: int | None = None) -> None:
        if value_ms < 0:
            return  # clock skew; ignore rather than pollute
        self._samples[hop].append((at_ms if at_ms is not None else epoch_ms_now(), value_ms))

    def _recent(self, hop: str, since_ms: int) -> list[float]:
        dq = self._samples.get(hop)
        if not dq:
            return []
        return sorted(v for ts, v in dq if ts >= since_ms)

    def summary(self, hop: str, *, last_ms: int | None = None) -> HopSummary:
        now = epoch_ms_now()
        values = self._recent(hop, now - (last_ms or self._window))
        return HopSummary(
            hop=hop,
            n=len(values),
            p50=percentile(values, 0.50),
            p95=percentile(values, 0.95),
            p99=percentile(values, 0.99),
            max=values[-1] if values else 0.0,
        )

    def summaries(self, *, last_ms: int | None = None) -> list[HopSummary]:
        return [self.summary(h, last_ms=last_ms) for h in HOPS]

    def persist_minute(self, conn: sqlite3.Connection, minute_ts: int) -> None:
        rows = [
            (minute_ts, s.hop, s.p50, s.p95, s.p99, s.n)
            for s in self.summaries(last_ms=60_000)
            if s.n
        ]
        if rows:
            with conn:
                conn.executemany(
                    "INSERT INTO latency_samples (ts, hop, p50, p95, p99, n) VALUES (?,?,?,?,?,?)",
                    rows,
                )


async def sample_loop_lag(tracker: LatencyTracker, *, every_ms: int = 100) -> None:
    """Measure how late the event loop wakes us; runs until cancelled."""
    loop = asyncio.get_running_loop()
    interval = every_ms / 1000
    while True:
        before = loop.time()
        await asyncio.sleep(interval)
        lag_ms = (loop.time() - before - interval) * 1000
        tracker.record("loop_lag", max(0.0, lag_ms))

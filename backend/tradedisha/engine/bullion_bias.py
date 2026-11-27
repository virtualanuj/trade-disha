"""Bullion bias on each MCX near-month future: GOLD, GOLDM, SILVER, SILVERM (E29). Spec §9a.

There is no option chain for bullion. The evidence is the trend group (EMA cross, VWAP
position, supertrend on the 1-minute candles), the future's open-interest build-up, order
flow (net traded volume, the book's lean) and other markets (the dollar, the other metal's
trend), each group with its `bullion.*_weight` share (Milestone E13). Each minute is worked out
`bullion.eval_offset_seconds` after it closes rather than at the close itself, so bullion
never competes with the index engines for the same instant: a close only queues the
minute, and `run_due` (called from the session's housekeeping, on the market clock) runs
what has come due. Replay therefore times it exactly as live did.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from tradedisha.engine.aggregator import BULLION_IDLE, aggregate, bullion_weights
from tradedisha.engine.bias_engine import BiasComputed, BiasStore, OverlayPoint, compute_overlays
from tradedisha.indicators import IndicatorResult
from tradedisha.indicators.futures import book_imbalance, futures_oi_buildup, net_volume
from tradedisha.indicators.macro import peer_metal
from tradedisha.indicators.series import vwap_series
from tradedisha.indicators.trend import ema_cross, supertrend_vote, vwap_position
from tradedisha.market.bullion import METALS, BullionTracker, family
from tradedisha.market.candles import MINUTE_MS, Candle
from tradedisha.parameters.model import ParameterSet

log = logging.getLogger(__name__)

OVERLAY_HISTORY = 900  # minutes: MCX runs 09:00 to 23:30


@dataclass(frozen=True)
class _Due:
    metal: str
    minute_ts: int
    due_ms: int


def run_bullion_indicators(candles: list[Candle], p: ParameterSet) -> list[IndicatorResult]:
    """The trend group on one metal's candles."""
    vwap = vwap_series(candles)[-1] if candles else None
    close = candles[-1].close if candles else None
    return [
        ema_cross(candles, p.trend),
        vwap_position(close, vwap, p.trend),
        supertrend_vote(candles, p.trend),
    ]


class BullionBiasEngine:
    def __init__(
        self,
        *,
        tracker: BullionTracker,
        params: Callable[[], ParameterSet],
        conn: sqlite3.Connection,
        on_bias: Callable[[BiasComputed], None] | None = None,
        macro: Callable[[int], list[IndicatorResult]] | None = None,
    ) -> None:
        self._tracker = tracker
        self._macro = macro  # the dollar for a minute (spec §8.6); none without currency data
        self._params = params
        self._store = BiasStore(conn)
        self._on_bias = on_bias
        self._queue: list[_Due] = []
        self.latest: dict[str, BiasComputed] = {}
        self.overlays: dict[str, list[OverlayPoint]] = {m: [] for m in tracker.contracts}

    def attach(self) -> None:
        """Queue each closed near-month candle of the tracker's own candle builder."""
        self._tracker.candles.on_close(self._on_candle_close)

    def _on_candle_close(self, c: Candle) -> None:
        metal = self._tracker.metal_of(c.key)
        if metal is not None:
            self.queue(metal, c.minute_ts)

    def queue(self, metal: str, minute_ts: int) -> None:
        """The offset in force now sets the due time, so a change applies from the next minute."""
        offset_ms = self._params().bullion.eval_offset_seconds * 1000
        self._queue.append(_Due(metal, minute_ts, minute_ts + MINUTE_MS + offset_ms))

    def run_due(self, now_ms: int) -> list[BiasComputed]:
        """Evaluate every queued minute whose time has come, oldest first."""
        due = [d for d in self._queue if d.due_ms <= now_ms]
        if not due:
            return []
        self._queue = [d for d in self._queue if d.due_ms > now_ms]
        out: list[BiasComputed] = []
        for d in sorted(due, key=lambda x: (x.minute_ts, x.metal)):
            try:
                out.append(self.evaluate(d.metal, d.minute_ts))
            except Exception:
                log.exception("bullion bias evaluation failed for %s", d.metal)
        return out

    def evaluate(self, metal: str, minute_ts: int) -> BiasComputed:
        p = self._params()
        candles = self._candles(metal, minute_ts)
        book = self._tracker.minute_book(metal, minute_ts)
        results = run_bullion_indicators(candles, p)
        results += [
            futures_oi_buildup(book, p.bullion),
            net_volume(candles, p.bullion),
            book_imbalance(book, p.bullion),
        ]
        if self._macro is not None:
            results += self._macro(minute_ts)
        for peer in self._peers(metal):
            peer_trend = run_bullion_indicators(self._candles(peer, minute_ts), p)
            results.append(peer_metal(peer, peer_trend))
        bias = aggregate(
            results,
            p,
            is_expiry_day=False,
            weights=bullion_weights(p),
            neutral_band=p.bullion.neutral_band,
            idle_groups=BULLION_IDLE,
            off=p.factors.off_for(metal),  # switched off in Config (E16)
        )
        vwap = vwap_series(candles)[-1] if candles else None
        overlay = compute_overlays(candles, vwap, p)
        out = BiasComputed(metal, minute_ts, bias, overlay)
        self.latest[metal] = out
        history = self.overlays.setdefault(metal, [])
        history.append(overlay)
        if len(history) > OVERLAY_HISTORY:
            del history[: len(history) - OVERLAY_HISTORY]
        self._store.write(metal, minute_ts, bias)
        if self._on_bias:
            self._on_bias(out)
        return out

    def _peers(self, name: str) -> list[str]:
        """The other metal's full future, for GOLD and GOLDM alike: it trades the most, and
        never the market's own metal (E29)."""
        own = family(name)
        return [m for m in self._tracker.contracts if m in METALS and m != own]

    def _candles(self, metal: str, upto_minute_ts: int) -> list[Candle]:
        """Closed near-month candles up to and including the minute being worked out."""
        key = self._tracker.near_key(metal)
        return [c for c in self._tracker.candles.closed(key) if c.minute_ts <= upto_minute_ts]

    def history(self, metal: str, start_ms: int, end_ms: int) -> list[sqlite3.Row]:
        return self._store.read_day(metal, start_ms, end_ms)

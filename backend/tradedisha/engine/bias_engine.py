"""Runs all indicators at each spot-candle close and publishes the bias. Spec §8.

Reads the active ParameterSet at the start of each evaluation, so a config reload takes
effect at the next minute close, never mid-computation.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass

from tradedisha.engine.aggregator import Bias, aggregate
from tradedisha.indicators import IndicatorResult
from tradedisha.indicators.oi import max_pain_drift, oi_change_atm, pcr_vote
from tradedisha.indicators.premium import iv_change, premium_confirmation, premium_momentum
from tradedisha.indicators.series import ema, supertrend
from tradedisha.indicators.trend import ema_cross, supertrend_vote, vwap_position
from tradedisha.instruments.models import ResolvedIndex
from tradedisha.market.candles import Candle, CandleBuilder
from tradedisha.market.chain import ChainState
from tradedisha.parameters.model import ParameterSet

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BiasComputed:
    index: str
    minute_ts: int
    bias: Bias
    overlays: OverlayPoint


@dataclass(frozen=True)
class OverlayPoint:
    minute_ts: int
    ema_fast: float | None
    ema_slow: float | None
    vwap: float | None
    supertrend: float | None
    supertrend_dir: int


def breakdown_json(b: Bias) -> str:
    return json.dumps(
        {
            "group_scores": b.group_scores,
            "group_weights": b.group_weights,
            "is_expiry_day": b.is_expiry_day,
            "indicators": [
                {**asdict(c.result), "weight": c.weight, "contribution": c.contribution}
                for c in b.contributions
            ],
        },
        separators=(",", ":"),
    )


class BiasStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def write(self, index: str, minute_ts: int, b: Bias) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO bias_minutes (idx, minute_ts, bias, label, strength,"
                " breakdown_json) VALUES (?,?,?,?,?,?)",
                (index, minute_ts, b.bias, b.label, b.strength, breakdown_json(b)),
            )

    def read_day(self, index: str, start_ms: int, end_ms: int) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT minute_ts, bias, label, strength FROM bias_minutes"
                " WHERE idx = ? AND minute_ts >= ? AND minute_ts < ? ORDER BY minute_ts",
                (index, start_ms, end_ms),
            )
        )


def compute_overlays(spot: list[Candle], fut_vwap: float | None, p: ParameterSet) -> OverlayPoint:
    closes = [c.close for c in spot]
    ef = ema(closes, p.trend.ema_fast)[-1] if closes else None
    es = ema(closes, p.trend.ema_slow)[-1] if closes else None
    st_line: float | None = None
    st_dir = 0
    if len(spot) >= p.trend.supertrend_period + 1:
        line, direction = supertrend(spot, p.trend.supertrend_period, p.trend.supertrend_mult)
        st_line, st_dir = line[-1], direction[-1]
    return OverlayPoint(spot[-1].minute_ts if spot else 0, ef, es, fut_vwap, st_line, st_dir)


def run_indicators(
    spot: list[Candle],
    fut: list[Candle],
    fut_vwap: float | None,
    chain: ChainState,
    p: ParameterSet,
) -> list[IndicatorResult]:
    fut_close = fut[-1].close if fut else None
    return [
        ema_cross(spot, p.trend),
        vwap_position(fut_close, fut_vwap, p.trend),
        supertrend_vote(spot, p.trend),
        pcr_vote(chain, p.oi),
        oi_change_atm(chain, p.oi),
        max_pain_drift(chain, p.oi),
        premium_momentum(chain, p.premium),
        iv_change(chain, p.premium),
        premium_confirmation(chain, p.premium),
    ]


class BiasEngine:
    def __init__(
        self,
        *,
        candles: CandleBuilder,
        chains: dict[str, ChainState],
        resolved: dict[str, ResolvedIndex],
        params: Callable[[], ParameterSet],
        conn: sqlite3.Connection,
        on_bias: Callable[[BiasComputed], None] | None = None,
    ) -> None:
        self._candles = candles
        self._chains = chains
        self._resolved = resolved
        self._params = params
        self._store = BiasStore(conn)
        self._on_bias = on_bias
        self.latest: dict[str, BiasComputed] = {}
        self.overlays: dict[str, list[OverlayPoint]] = {i: [] for i in resolved}
        self.evaluations = 0
        self._spot_keys = {r.spot.instrument_key: i for i, r in resolved.items()}
        candles.on_close(self._on_candle_close)

    def _on_candle_close(self, c: Candle) -> None:
        index = self._spot_keys.get(c.key)
        if index is None:
            return
        try:
            self.evaluate(index, c.minute_ts)
        except Exception:
            log.exception("bias evaluation failed for %s", index)

    def evaluate(self, index: str, minute_ts: int) -> BiasComputed:
        p = self._params()
        r = self._resolved[index]
        spot = self._candles.closed(r.spot.instrument_key)
        fut = self._candles.closed(r.future.instrument_key)
        fut_vwap = self._candles.vwap(r.future.instrument_key)
        chain = self._chains[index]
        results = run_indicators(spot, fut, fut_vwap, chain, p)
        bias = aggregate(results, p, is_expiry_day=r.is_expiry_day)
        overlay = compute_overlays(spot, fut_vwap, p)
        out = BiasComputed(index, minute_ts, bias, overlay)
        self.latest[index] = out
        self.overlays[index].append(overlay)
        if len(self.overlays[index]) > 400:
            del self.overlays[index][: len(self.overlays[index]) - 400]
        self._store.write(index, minute_ts, bias)
        self.evaluations += 1
        if self._on_bias:
            self._on_bias(out)
        return out

    def history(self, index: str, start_ms: int, end_ms: int) -> list[sqlite3.Row]:
        return self._store.read_day(index, start_ms, end_ms)

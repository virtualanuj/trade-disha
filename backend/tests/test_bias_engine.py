"""BiasEngine evaluates on spot-candle close and persists; params are read per evaluation."""

from datetime import date

import pytest

from tradedisha.engine.bias_engine import BiasComputed, BiasEngine, breakdown_json
from tradedisha.feed.provider import Tick
from tradedisha.indicators import IndicatorResult
from tradedisha.instruments.resolve import resolve_index
from tradedisha.instruments.synthetic_master import build_synthetic_master
from tradedisha.market.candles import CandleBuilder
from tradedisha.market.chain import ChainState
from tradedisha.parameters.model import ParameterSet
from tradedisha.store.db import connect

M = 60_000
TODAY = date(2026, 11, 12)


def test_engine_runs_on_spot_close_and_uses_latest_params() -> None:
    master = build_synthetic_master(TODAY)
    r = resolve_index(master, "NIFTY", TODAY, 25_000.0, strike_window=3)
    candles = CandleBuilder()
    chains = {"NIFTY": ChainState.from_resolved(r)}
    conn = connect(":memory:")
    params = ParameterSet()
    seen: list[BiasComputed] = []
    engine = BiasEngine(
        candles=candles,
        chains=chains,
        resolved={"NIFTY": r},
        params=lambda: params,
        conn=conn,
        on_bias=seen.append,
    )
    spot, fut = r.spot.instrument_key, r.future.instrument_key

    # 30 rising minutes of spot and futures
    for i in range(31):
        candles.apply(Tick(key=fut, ts=i * M, ltp=25_040.0 + i * 5, volume=1_000 * (i + 1)))
        candles.apply(Tick(key=spot, ts=i * M, ltp=25_000.0 + i * 5))

    assert engine.evaluations == 30
    last = seen[-1]
    assert last.index == "NIFTY"
    assert last.bias.label == "Bullish"
    names = {c.result.name for c in last.bias.contributions}
    assert len(names) == 9
    ok = {c.result.name for c in last.bias.contributions if c.result.quality == "ok"}
    assert {"ema_cross", "vwap_position", "supertrend"} <= ok  # trend group has data
    assert last.overlays.ema_fast is not None
    assert len(engine.overlays["NIFTY"]) == 30
    assert len(engine.history("NIFTY", 0, 100 * M)) == 30

    # a parameter change is picked up at the next evaluation
    params = ParameterSet.model_validate(
        {"bias": {"neutral_band": 0.99, "setup_threshold": 0.995, "entry_threshold": 0.995}}
    )
    candles.apply(Tick(key=spot, ts=31 * M, ltp=25_200.0))
    assert seen[-1].bias.label == "Neutral"


def test_macro_evidence_joins_the_bias_with_its_share() -> None:
    master = build_synthetic_master(TODAY)
    r = resolve_index(master, "NIFTY", TODAY, 25_000.0, strike_window=3)
    candles = CandleBuilder()
    asked: list[tuple[str, int]] = []

    def macro(index: str, minute_ts: int) -> list[IndicatorResult]:
        asked.append((index, minute_ts))
        return [IndicatorResult("crude", "macro", -1.0, "Crude +0.80% in 30 min")]

    seen: list[BiasComputed] = []
    BiasEngine(
        candles=candles,
        chains={"NIFTY": ChainState.from_resolved(r)},
        resolved={"NIFTY": r},
        params=ParameterSet,
        conn=connect(":memory:"),
        on_bias=seen.append,
        macro=macro,
    )
    spot = r.spot.instrument_key
    candles.apply(Tick(key=spot, ts=0, ltp=25_000.0))
    candles.apply(Tick(key=spot, ts=M, ltp=25_005.0))

    b = seen[-1].bias
    assert asked == [("NIFTY", 0)]  # asked for the index and minute being evaluated
    crude = next(c for c in b.contributions if c.result.name == "crude")
    assert crude.weight == pytest.approx(0.10)
    assert b.group_scores["macro"] == -1.0
    assert '"crude"' in breakdown_json(b)  # stored with the bias and with any signal

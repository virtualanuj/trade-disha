"""Indicator scores on synthetic series with known answers; bounds via Hypothesis."""

from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tradedisha.engine.aggregator import aggregate, effective_group_weights
from tradedisha.feed.provider import Tick
from tradedisha.indicators import IndicatorResult
from tradedisha.indicators.oi import max_pain_drift, oi_change_atm, pcr_vote
from tradedisha.indicators.premium import iv_change, premium_confirmation, premium_momentum
from tradedisha.indicators.series import bars_since_flip, ema, supertrend
from tradedisha.indicators.trend import ema_cross, supertrend_vote, vwap_position
from tradedisha.instruments.resolve import resolve_index
from tradedisha.instruments.synthetic_master import build_synthetic_master
from tradedisha.market.candles import Candle
from tradedisha.market.chain import ChainSnapshotMinute, ChainState
from tradedisha.parameters.model import ParameterSet

P = ParameterSet()
M = 60_000


def candles(closes: list[float], spread: float = 1.0) -> list[Candle]:
    return [Candle("S", i * M, c, c + spread, c - spread, c) for i, c in enumerate(closes)]


def _chain() -> ChainState:
    master = build_synthetic_master(date(2026, 11, 12))
    return ChainState.from_resolved(
        resolve_index(master, "NIFTY", date(2026, 11, 12), 25_000.0, strike_window=5)
    )


# -- series ----------------------------------------------------------------


def test_ema_seeds_with_sma_then_smooths() -> None:
    out = ema([1, 2, 3, 4, 5], 3)
    assert out[:2] == [None, None]
    assert out[2] == 2.0
    assert out[3] == 4 * 0.5 + 2.0 * 0.5
    assert out[4] is not None
    assert out[3] is not None
    assert out[4] > out[3]


def test_supertrend_direction_follows_trend() -> None:
    up = candles([100 + i * 2.0 for i in range(30)])
    _, d = supertrend(up, 10, 3.0)
    assert d[-1] == 1
    down = candles([200 - i * 2.0 for i in range(30)])
    _, d2 = supertrend(down, 10, 3.0)
    assert d2[-1] == -1
    assert bars_since_flip([1, 1, -1, -1, -1]) == 3
    assert bars_since_flip([]) == 0


# -- trend -----------------------------------------------------------------


def test_ema_cross_bullish_on_rising_series_and_warming_when_short() -> None:
    r = ema_cross(candles([100 + i for i in range(40)]), P.trend)
    assert r.quality == "ok"
    assert r.score > 0.5
    assert "above" in r.note
    w = ema_cross(candles([100.0] * 5), P.trend)
    assert w.quality == "warming"
    assert w.score == 0


def test_vwap_position_scales_and_clamps() -> None:
    assert vwap_position(100.3, 100.0, P.trend).score == pytest.approx(1.0)
    assert vwap_position(99.85, 100.0, P.trend).score == pytest.approx(-0.5)
    assert vwap_position(None, 100.0, P.trend).quality == "warming"


def test_supertrend_vote_ramps_after_flip() -> None:
    r = supertrend_vote(candles([100 + i * 2.0 for i in range(30)]), P.trend)
    assert r.score == 1.0
    series = candles([100 + i * 2.0 for i in range(25)] + [150, 120, 90])
    r2 = supertrend_vote(series, P.trend)
    assert r2.score < 0
    assert abs(r2.score) < 1.0  # fresh flip, still ramping


# -- oi --------------------------------------------------------------------


def _fill(c: ChainState, strike: float, side: str, oi: int, ltp: float, ts: int) -> None:
    leg = c.rows[strike].ce if side == "ce" else c.rows[strike].pe
    c.apply(Tick(key=leg.key, ts=ts, ltp=ltp, oi=oi))


def test_pcr_vote() -> None:
    c = _chain()
    _fill(c, 25_000, "ce", 1_000, 10, 1)
    _fill(c, 25_000, "pe", 1_500, 10, 1)
    r = pcr_vote(c, P.oi)
    assert r.score == 1.0  # PCR 1.5 -> (1.5-1)/0.5
    assert pcr_vote(_chain(), P.oi).quality == "warming"


def test_oi_change_atm_reads_buildups() -> None:
    c = _chain()
    # minute 1 baseline
    _fill(c, 25_000, "pe", 1_000, 10, 1)
    _fill(c, 25_000, "ce", 1_000, 10, 1)
    c.close_minute(0)
    # minute 2: PE long build-up (price up, OI up) = bullish; CE unchanged
    _fill(c, 25_000, "pe", 1_400, 12, M + 1)
    _fill(c, 25_000, "ce", 1_000, 10, M + 1)
    c.close_minute(M)
    r = oi_change_atm(c, P.oi)
    assert r.quality == "ok"
    assert r.score == 1.0


def test_max_pain_drift_uses_history() -> None:
    c = _chain()
    for i in range(17):
        c.history.append(ChainSnapshotMinute(i * M, 25_000, 1.0, 25_000 + (50 if i >= 10 else 0)))
    r = max_pain_drift(c, P.oi)
    assert r.quality == "ok"
    assert r.score == 0.5  # one step up over 15 minutes / full 2 steps
    assert max_pain_drift(_chain(), P.oi).quality == "warming"


# -- premium ---------------------------------------------------------------


def _hist(c: ChainState, n: int, ce: float, pe: float, iv: float, spot: float) -> None:
    c.history.append(ChainSnapshotMinute(n * M, 25_000, 1.0, 25_000, spot, ce, pe, iv))


def test_premium_momentum_and_confirmation() -> None:
    c = _chain()
    for i in range(6):
        _hist(c, i, ce=100 + i * 4, pe=100 - i * 2, iv=12, spot=25_000 + i * 10)
    m = premium_momentum(c, P.premium)
    assert m.quality == "ok"
    assert m.score > 0.5  # CE +20% vs PE -10% -> spread 30 -> clamped 1.0
    conf = premium_confirmation(c, P.premium)
    assert conf.score > 0
    assert "confirm" in conf.note

    div = _chain()
    for i in range(6):
        _hist(div, i, ce=100 - i, pe=100, iv=12, spot=25_000 + i * 10)
    d = premium_confirmation(div, P.premium)
    assert d.score == P.premium.divergence_score


def test_iv_change_sign_follows_spot() -> None:
    c = _chain()
    for i in range(16):
        _hist(c, i, ce=100, pe=100, iv=12 + i * 0.2, spot=25_000 - i * 5)
    r = iv_change(c, P.premium)
    assert r.score == -1.0  # IV +3 pts with spot falling -> fully bearish


# -- aggregation -------------------------------------------------------------


def test_aggregate_weights_groups_and_labels() -> None:
    results = [
        IndicatorResult("a", "trend", 1.0, ""),
        IndicatorResult("b", "trend", 0.0, "", "warming"),
        IndicatorResult("c", "oi", -1.0, ""),
        IndicatorResult("d", "premium", 0.5, ""),
    ]
    b = aggregate(results, P, is_expiry_day=False)
    assert b.group_scores == {"trend": 1.0, "oi": -1.0, "premium": 0.5}
    assert abs(b.bias - (0.40 * 1 + 0.35 * -1 + 0.25 * 0.5)) < 1e-9
    assert b.label == "Neutral"
    assert b.strength == 18
    trend_contribs = [c for c in b.contributions if c.result.group == "trend"]
    assert trend_contribs[0].weight == 0.40  # only one ok member carries the group weight
    assert trend_contribs[1].weight == 0.0


def test_expiry_day_halves_oi_weight_and_redistributes() -> None:
    w = effective_group_weights(P, True)
    assert abs(w["oi"] - 0.175) < 1e-9
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert w["trend"] > 0.40


@settings(max_examples=50)
@given(st.lists(st.floats(1, 1_000_000, allow_nan=False), min_size=25, max_size=60))
def test_trend_scores_are_bounded(closes: list[float]) -> None:
    cs = candles(closes)
    for r in (ema_cross(cs, P.trend), supertrend_vote(cs, P.trend)):
        assert -1.0 <= r.score <= 1.0

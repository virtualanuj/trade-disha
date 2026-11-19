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


@pytest.mark.parametrize(
    ("side", "d_ltp", "d_oi", "score", "meaning"),
    [
        ("ce", +2, +400, 1.0, "call long build-up: calls being bought"),
        ("ce", -2, +400, -1.0, "call short build-up: calls being written"),
        ("ce", +2, -400, 1.0, "call short covering: writers getting out"),
        ("ce", -2, -400, -1.0, "call long unwinding: buyers getting out"),
        ("pe", +2, +400, -1.0, "put long build-up: puts being bought"),
        ("pe", -2, +400, 1.0, "put short build-up: puts being written"),
        ("pe", +2, -400, -1.0, "put short covering: writers getting out"),
        ("pe", -2, -400, 1.0, "put long unwinding: buyers getting out"),
    ],
)
def test_oi_change_atm_takes_its_side_from_the_premium_move(
    side: str, d_ltp: float, d_oi: int, score: float, meaning: str
) -> None:
    c = _chain()
    other = "pe" if side == "ce" else "ce"
    _fill(c, 25_000, side, 1_000, 10, 1)
    _fill(c, 25_000, other, 1_000, 10, 1)
    c.close_minute(0)
    _fill(c, 25_000, side, 1_000 + d_oi, 10 + d_ltp, M + 1)
    _fill(c, 25_000, other, 1_000, 10, M + 1)  # unchanged: no vote
    c.close_minute(M)

    r = oi_change_atm(c, P.oi)

    assert r.quality == "ok", meaning
    assert r.score == score, meaning


def test_oi_change_atm_weighs_the_two_sides_by_oi_moved() -> None:
    c = _chain()
    _fill(c, 25_000, "ce", 1_000, 10, 1)
    _fill(c, 25_000, "pe", 1_000, 10, 1)
    c.close_minute(0)
    _fill(c, 25_000, "ce", 1_300, 12, M + 1)  # 300 of call buying: bullish
    _fill(c, 25_000, "pe", 1_100, 12, M + 1)  # 100 of put buying: bearish
    c.close_minute(M)

    r = oi_change_atm(c, P.oi)

    assert r.score == 0.5  # (300 - 100) / 400
    assert r.value == {"bull_oi": 300.0, "bear_oi": 100.0}
    assert oi_change_atm(_chain(), P.oi).quality == "warming"


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
    assert b.group_scores == {"trend": 1.0, "oi": -1.0, "premium": 0.5, "flow": 0.0, "macro": 0.0}
    assert abs(b.bias - (0.40 * 1 + 0.35 * -1 + 0.25 * 0.5)) < 1e-9
    assert b.label == "Neutral"
    assert b.strength == 18
    trend_contribs = [c for c in b.contributions if c.result.group == "trend"]
    assert trend_contribs[0].weight == 0.40  # only one ok member carries the group weight
    assert trend_contribs[1].weight == 0.0


def test_expiry_day_halves_oi_weight_and_redistributes() -> None:
    w = effective_group_weights(P, True)
    assert w["oi"] == pytest.approx(0.315 / 2)  # OI's share after macro's 10 %, halved
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["trend"] > 0.36
    assert w["macro"] > 0.10  # macro takes part of the cut too


# -- macro group (spec §8.6) ----------------------------------------------------


def _macro(score: float, name: str = "crude", quality: str = "ok") -> IndicatorResult:
    return IndicatorResult(name, "macro", score, "", quality)  # type: ignore[arg-type]


def test_macro_takes_its_share_and_the_others_keep_their_proportions() -> None:
    w = effective_group_weights(P, False)
    assert w == pytest.approx(
        {"trend": 0.36, "oi": 0.315, "premium": 0.225, "flow": 0.0, "macro": 0.10}
    )
    results = [IndicatorResult("a", "trend", 1.0, ""), _macro(-1.0), _macro(0.0, "gold")]
    b = aggregate(results, P, is_expiry_day=False)
    assert b.group_scores["macro"] == pytest.approx(-0.5)
    assert b.bias == pytest.approx(0.36 * 1.0 + 0.10 * -0.5)
    assert [c.weight for c in b.contributions if c.result.group == "macro"] == pytest.approx(
        [0.05, 0.05]
    )


@pytest.mark.parametrize(
    "macro",
    [[], [_macro(-1.0, quality="warming")], [_macro(0.0, "silver", quality="info")]],
)
def test_without_a_live_macro_price_the_bias_is_the_three_group_one(
    macro: list[IndicatorResult],
) -> None:
    results = [
        IndicatorResult("a", "trend", 1.0, ""),
        IndicatorResult("c", "oi", -1.0, ""),
        IndicatorResult("d", "premium", 0.5, ""),
        *macro,
    ]
    b = aggregate(results, P, is_expiry_day=False)
    assert b.group_weights == pytest.approx(
        {"trend": 0.40, "oi": 0.35, "premium": 0.25, "flow": 0.0, "macro": 0.0}
    )
    assert b.bias == pytest.approx(0.40 - 0.35 + 0.125)
    assert all(c.weight == 0 for c in b.contributions if c.result.group == "macro")


def test_an_info_reading_is_shown_with_no_weight_beside_scored_ones() -> None:
    results = [_macro(1.0), _macro(0.0, "silver", quality="info")]
    b = aggregate(results, P, is_expiry_day=False)
    weights = {c.result.name: c.weight for c in b.contributions}
    assert weights == pytest.approx({"crude": 0.10, "silver": 0.0})


# -- factor switches (Milestone E15) ---------------------------------------------

THREE = [
    IndicatorResult("a", "trend", 1.0, ""),
    IndicatorResult("b", "trend", -1.0, ""),
    IndicatorResult("c", "oi", -1.0, ""),
    IndicatorResult("d", "premium", 0.5, ""),
]


def test_a_factor_switched_off_is_shown_with_no_weight_and_its_group_shares_the_rest() -> None:
    b = aggregate(THREE, P, is_expiry_day=False, off=frozenset({"b"}))
    by = {c.result.name: c for c in b.contributions}
    assert (by["b"].enabled, by["b"].weight, by["b"].contribution) == (False, 0.0, 0.0)
    assert by["b"].result.score == -1.0  # still worked out and shown
    assert by["a"].enabled
    assert by["a"].weight == pytest.approx(0.40)
    assert b.group_scores["trend"] == 1.0
    assert b.bias == pytest.approx(0.40 - 0.35 + 0.125)


def test_a_group_with_every_factor_off_gives_its_share_back() -> None:
    b = aggregate(THREE, P, is_expiry_day=False, off=frozenset({"c"}))
    assert b.group_weights["oi"] == 0.0
    assert b.group_weights["trend"] == pytest.approx(0.40 / 0.65)
    assert b.group_weights["premium"] == pytest.approx(0.25 / 0.65)
    assert sum(b.group_weights.values()) == pytest.approx(1.0)
    assert b.group_scores["oi"] == 0.0


def test_switching_off_a_factor_that_carries_no_weight_changes_nothing() -> None:
    results = [*THREE, _macro(0.0, "silver", quality="info"), _macro(0.3, quality="warming")]
    on = aggregate(results, P, is_expiry_day=False)
    off = aggregate(results, P, is_expiry_day=False, off=frozenset({"silver", "crude"}))
    assert off.bias == on.bias
    assert off.group_weights == on.group_weights


def test_unknown_names_in_off_are_ignored_and_by_default_every_factor_is_on() -> None:
    b = aggregate(THREE, P, is_expiry_day=False, off=frozenset({"nope"}))
    assert all(c.enabled for c in b.contributions)
    assert b.bias == aggregate(THREE, P, is_expiry_day=False).bias


@settings(max_examples=50)
@given(
    st.lists(st.floats(-1, 1), min_size=6, max_size=6),
    st.sets(st.sampled_from(["t1", "t2", "o1", "p1", "p2", "m1"])),
    st.booleans(),
)
def test_with_any_factors_off_the_bias_stays_bounded_and_off_ones_weigh_nothing(
    scores: list[float], off: set[str], expiry: bool
) -> None:
    names = [("t1", "trend"), ("t2", "trend"), ("o1", "oi"), ("p1", "premium"), ("p2", "premium")]
    names.append(("m1", "macro"))
    results = [IndicatorResult(n, g, s, "") for (n, g), s in zip(names, scores, strict=True)]  # type: ignore[arg-type]
    b = aggregate(results, P, is_expiry_day=expiry, off=frozenset(off))
    assert -1.0 <= b.bias <= 1.0
    assert all(c.weight == 0 for c in b.contributions if c.result.name in off)
    total = sum(c.weight for c in b.contributions)
    assert total == pytest.approx(1.0 if len(off) < len(names) else 0.0)


@settings(max_examples=50)
@given(
    st.lists(st.floats(-1, 1), min_size=4, max_size=4),
    st.floats(0, 0.5),
    st.booleans(),
)
def test_bias_with_macro_stays_bounded(scores: list[float], macro: float, expiry: bool) -> None:
    p = ParameterSet.model_validate({"weights": {"macro": macro}})
    groups = ("trend", "oi", "premium", "macro")
    results = [IndicatorResult(g, g, s, "") for g, s in zip(groups, scores, strict=True)]  # type: ignore[arg-type]
    b = aggregate(results, p, is_expiry_day=expiry)
    assert -1.0 <= b.bias <= 1.0
    assert sum(b.group_weights.values()) == pytest.approx(1.0)


@settings(max_examples=50)
@given(st.lists(st.floats(1, 1_000_000, allow_nan=False), min_size=25, max_size=60))
def test_trend_scores_are_bounded(closes: list[float]) -> None:
    cs = candles(closes)
    for r in (ema_cross(cs, P.trend), supertrend_vote(cs, P.trend)):
        assert -1.0 <= r.score <= 1.0

"""Macro evidence (spec §8.6): the dollar-index proxy and moves over a window."""

from __future__ import annotations

import math

import pytest

from tradedisha.indicators.macro import (
    MacroSeries,
    align_closes,
    bullion_macro_indicators,
    dollar_index_proxy,
    index_macro_indicators,
    macro_move,
    move_pct,
)
from tradedisha.parameters.model import Macro

BASE = {"usdinr": 88.0, "eurinr": 102.0, "gbpinr": 116.0, "jpyinr": 57.0}


def _proxy(**over: float) -> float:
    return dollar_index_proxy(**{**BASE, **over})


def test_proxy_matches_the_formula() -> None:
    eurusd, gbpusd = 102.0 / 88.0, 116.0 / 88.0
    usdjpy = 88.0 / (57.0 / 100)  # JPYINR is quoted per 100 yen
    total = 0.576 + 0.136 + 0.119
    expected = eurusd ** (-0.576 / total) * usdjpy ** (0.136 / total) * gbpusd ** (-0.119 / total)
    assert math.isclose(_proxy(), expected, rel_tol=1e-12)


def test_proxy_rises_when_the_dollar_strengthens_against_each_currency() -> None:
    assert _proxy(eurinr=101.0) > _proxy()  # euro weaker against the rupee, so vs the dollar
    assert _proxy(gbpinr=115.0) > _proxy()
    assert _proxy(jpyinr=56.0) > _proxy()  # fewer rupees per 100 yen: yen weaker
    # the rupee alone moving leaves the dollar's value against the others unchanged
    moved = dollar_index_proxy(usdinr=90.0, eurinr=102 * 90 / 88, gbpinr=116 * 90 / 88,
                               jpyinr=57 * 90 / 88)  # fmt: skip
    assert math.isclose(moved, _proxy(), rel_tol=1e-12)


def test_align_closes_forward_fills_from_the_first_minute_all_have() -> None:
    a = [(1, 10.0), (2, 11.0), (3, 12.0), (4, 13.0)]
    b = [(2, 20.0), (4, 21.0)]
    assert align_closes([a, b]) == [(11.0, 20.0), (12.0, 20.0), (13.0, 21.0)]
    assert align_closes([a, []]) == []


def test_move_pct_over_the_window() -> None:
    assert move_pct([100.0, 101.0, 102.0], 2) == pytest.approx(2.0)
    assert move_pct([100.0, 101.0, 102.0], 1) == pytest.approx(100 / 101 * 1.0)
    assert move_pct([100.0], 1) is None
    assert move_pct([0.0, 1.0], 1) is None


def _series(*closes: float, fresh: bool = True) -> MacroSeries:
    return MacroSeries(tuple(closes), fresh)


def test_macro_move_scores_with_sign_and_clamps_at_full() -> None:
    up = _series(100.0, 100.4)
    r = macro_move("crude", "Crude", up, sign=-1.0, full_pct=0.8, window=1)
    assert (r.group, r.quality) == ("macro", "ok")
    assert r.score == pytest.approx(-0.5)
    assert r.note == "Crude +0.40% in 1 min"
    assert r.value["change_pct"] == pytest.approx(0.4)
    big = macro_move("crude", "Crude", _series(100.0, 105.0), sign=-1.0, full_pct=0.8, window=1)
    assert big.score == -1.0
    bull = macro_move("usd_inr", "USD/INR", up, sign=1.0, full_pct=0.8, window=1)
    assert bull.score == pytest.approx(0.5)


def test_macro_move_warms_without_data_history_or_a_fresh_price() -> None:
    none = macro_move("crude", "Crude", None, sign=-1.0, full_pct=1.0, window=2)
    short = macro_move("crude", "Crude", _series(1.0, 2.0), sign=-1.0, full_pct=1.0, window=2)
    stale = macro_move(
        "crude", "Crude", _series(1.0, 2.0, 3.0, fresh=False), sign=-1.0, full_pct=1.0, window=2
    )
    for r in (none, short, stale):
        assert (r.quality, r.score) == ("warming", 0.0)
    assert "no price" in none.note
    assert "warming up (2/3" in short.note
    assert "not live" in stale.note


def test_a_shown_only_move_is_info_with_no_score() -> None:
    r = macro_move(
        "silver", "Silver", _series(100.0, 101.0), sign=-1.0, full_pct=1.0, window=1, scored=False
    )
    assert (r.quality, r.score) == ("info", 0.0)
    assert r.note == "Silver +1.00% in 1 min (shown, not scored)"


VIEW = {
    "dollar": _series(100.0, 100.15),
    "usdinr": _series(88.0, 88.088),
    "crude": _series(70.0, 70.56),
    "gold": _series(1000.0, 1004.0),
    "silver": _series(100.0, 99.0),
}


def test_index_macro_signs_rising_dollar_rupee_crude_and_gold_are_bearish() -> None:
    p = Macro(window_minutes=1)
    out = {r.name: r for r in index_macro_indicators(VIEW, p)}
    assert list(out) == ["dollar_index", "usd_inr", "crude", "gold", "silver"]
    assert out["dollar_index"].score == pytest.approx(-1.0)  # +0.15% at full 0.15
    assert out["usd_inr"].score == pytest.approx(-1.0)  # +0.10% at full 0.10
    assert out["crude"].score == pytest.approx(-1.0)  # +0.80% at full 0.80
    assert out["gold"].score == pytest.approx(-1.0)  # +0.40% at full 0.40
    assert out["silver"].quality == "info"


def test_bullion_macro_dollar_bearish_rupee_weakness_bullish() -> None:
    out = {r.name: r for r in bullion_macro_indicators(VIEW, Macro(window_minutes=1))}
    assert list(out) == ["dollar_index", "usd_inr"]
    assert out["dollar_index"].score == pytest.approx(-1.0)
    assert out["usd_inr"].score == pytest.approx(1.0)


def test_missing_names_warm_rather_than_fail() -> None:
    out = index_macro_indicators({}, Macro())
    assert all(r.quality == "warming" for r in out if r.name != "silver")

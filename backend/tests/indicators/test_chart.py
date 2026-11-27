"""Chart bars and lines at other intervals (E27): pure maths over candle series."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tradedisha.engine.bias_engine import compute_overlays
from tradedisha.indicators.chart import aggregate, overlay_series
from tradedisha.market.candles import Candle
from tradedisha.parameters.model import ParameterSet

M = 60_000
T0 = 1_700_000_100_000 // (5 * M) * (5 * M)  # a 5-minute boundary


def c(
    i: int,
    o: float,
    h: float,
    lo: float,
    cl: float,
    v: int = 0,
    **kw: object,
) -> Candle:
    sides = {"buy_volume": kw.get("bv"), "sell_volume": kw.get("sv")}
    return Candle("K", T0 + i * M, o, h, lo, cl, v, bool(kw.get("synthetic")), **sides)  # type: ignore[arg-type]


# -- aggregate ----------------------------------------------------------------------------


def test_five_one_minute_candles_make_one_bar() -> None:
    ones = [
        c(0, 100, 101, 99, 100.5, 10, bv=6, sv=4),
        c(1, 100.5, 103, 100, 102, 20, bv=15, sv=5),
        c(2, 102, 102.5, 98, 99, 5, bv=1, sv=4),
        c(3, 99, 100, 97, 98, 0, bv=0, sv=0),
        c(4, 98, 99, 97.5, 98.5, 15, bv=5, sv=10),
        c(5, 98.5, 99, 98, 98.8, 3, bv=3, sv=0),  # starts the next bar
    ]
    first, second = aggregate(ones, 5 * M)
    assert (first.minute_ts, first.open, first.high, first.low, first.close) == (
        T0,
        100,
        103,
        97,
        98.5,
    )
    assert (first.volume, first.buy_volume, first.sell_volume) == (50, 27, 23)
    assert (second.minute_ts, second.open, second.close, second.volume) == (
        T0 + 5 * M,
        98.5,
        98.8,
        3,
    )


@pytest.mark.parametrize(
    ("flags", "synthetic"),
    [([True, True], True), ([True, False], False)],
)
def test_a_bar_is_synthetic_only_when_every_minute_was(flags: list[bool], synthetic: bool) -> None:
    (bar,) = aggregate([c(i, 1, 1, 1, 1, synthetic=f) for i, f in enumerate(flags)], 5 * M)
    assert bar.synthetic is synthetic


def test_no_sides_stays_unknown_and_empty_stays_empty() -> None:
    (bar,) = aggregate([c(0, 1, 1, 1, 1), c(1, 1, 2, 1, 2)], 5 * M)
    assert (bar.buy_volume, bar.sell_volume) == (None, None)
    assert aggregate([], 5 * M) == []


# -- overlay_series ---------------------------------------------------------------------------


def _walk(closes: list[float], step_ms: int = M) -> list[Candle]:
    return [Candle("K", T0 + i * step_ms, x, x + 1, x - 1, x, 10) for i, x in enumerate(closes)]


def test_one_point_per_bar_with_none_until_each_line_is_seeded() -> None:
    p = ParameterSet()
    price = _walk([100 + i for i in range(30)], 10_000)
    pts = overlay_series(price, price, p.trend)
    assert [x.minute_ts for x in pts] == [b.minute_ts for b in price]
    assert pts[0].ema_fast is None
    assert pts[p.trend.ema_fast - 1].ema_fast is not None
    assert pts[p.trend.ema_slow - 2].ema_slow is None
    assert pts[-1].supertrend is not None
    assert pts[-1].supertrend_dir == 1  # a steady climb


def test_vwap_is_taken_from_the_latest_volume_bar_at_or_before_each_price_bar() -> None:
    p = ParameterSet()
    price = _walk([100.0, 101.0, 102.0], 10_000)
    vol = [
        Candle("F", T0, 200.0, 200.0, 200.0, 200.0, 10),
        # no future bar at T0 + 10 s
        Candle("F", T0 + 20_000, 210.0, 210.0, 210.0, 210.0, 10),
    ]
    pts = overlay_series(price, vol, p.trend)
    assert [x.vwap for x in pts] == [200.0, 200.0, 205.0]


def test_no_volume_bars_means_no_vwap() -> None:
    pts = overlay_series(_walk([1.0, 2.0]), [], ParameterSet().trend)
    assert [x.vwap for x in pts] == [None, None]


@settings(max_examples=40, deadline=None)
@given(st.lists(st.floats(min_value=50, max_value=150), min_size=1, max_size=60))
def test_the_last_point_is_what_the_bias_engine_draws_on_the_same_minutes(
    closes: list[float],
) -> None:
    p = ParameterSet()
    spot = _walk(closes)
    last = overlay_series(spot, [], p.trend)[-1]
    want = compute_overlays(spot, None, p)
    assert (last.minute_ts, last.supertrend_dir) == (want.minute_ts, want.supertrend_dir)
    for got, exp in [
        (last.ema_fast, want.ema_fast),
        (last.ema_slow, want.ema_slow),
        (last.supertrend, want.supertrend),
    ]:
        assert got == pytest.approx(exp) if exp is not None else got is None

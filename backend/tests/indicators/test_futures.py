"""Bullion positioning and order flow (Milestone E13): futures OI, net volume, the book."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tradedisha.indicators import IndicatorResult
from tradedisha.indicators.futures import (
    MinuteBook,
    book_imbalance,
    futures_oi_buildup,
    net_volume,
)
from tradedisha.indicators.macro import peer_metal
from tradedisha.market.candles import Candle
from tradedisha.parameters.model import Bullion

M = 60_000
P = Bullion()  # oi window 15, full 0.50 %, flat 0.02 %, unwind 0.5; flow 15 min, book 30 min


def _book(
    minute: int,
    ltp: float,
    oi: int | None = 10_000,
    tbq: int | None = None,
    tsq: int | None = None,
    bid5: int | None = None,
    ask5: int | None = None,
) -> MinuteBook:
    return MinuteBook(minute * M, ltp, oi, tbq, tsq, bid5, ask5)


def _pair(price_pct: float, oi_pct: float, window: int = 15) -> list[MinuteBook]:
    """Two readings `window` minutes apart, with the given price and OI changes."""
    return [
        _book(0, 100_000.0, 10_000),
        _book(window, 100_000.0 * (1 + price_pct / 100), round(10_000 * (1 + oi_pct / 100))),
    ]


# -- futures OI build-up -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("price_pct", "oi_pct", "score", "kind"),
    [
        (0.20, 0.50, 1.0, "long build-up"),  # new longs behind a rise: full strength
        (-0.20, 0.50, -1.0, "short build-up"),
        (0.20, 0.25, 0.5, "long build-up"),  # half the full OI change
        (0.20, -0.50, 0.5, "short covering"),  # positions closing count half
        (-0.20, -0.50, -0.5, "long unwinding"),
        (0.20, 2.00, 1.0, "long build-up"),  # clamped
        (0.01, 0.50, 0.0, "price flat"),  # below oi_price_flat_pct
        (0.20, 0.00, 0.0, "OI unchanged"),
    ],
)
def test_futures_oi_reads_price_against_oi(
    price_pct: float, oi_pct: float, score: float, kind: str
) -> None:
    r = futures_oi_buildup(_pair(price_pct, oi_pct), P)
    assert r.quality == "ok"
    assert r.group == "oi"
    assert r.score == pytest.approx(score)
    assert r.note.startswith(kind)
    assert r.value["price_pct"] == pytest.approx(price_pct)
    assert r.value["oi_pct"] == pytest.approx(oi_pct, abs=0.01)


def test_futures_oi_compares_the_reading_in_force_a_window_back() -> None:
    # no reading at minute 5: the one from minute 3 is in force then
    book = [_book(3, 100.0, 1000), _book(12, 101.0, 2000), _book(20, 100.2, 1010)]
    r = futures_oi_buildup(book, Bullion(oi_window_minutes=15))
    assert r.value["oi_pct"] == pytest.approx(1.0)
    assert r.value["price_pct"] == pytest.approx(0.2)


def test_futures_oi_warms_without_a_window_of_readings() -> None:
    assert futures_oi_buildup([], P).quality == "warming"
    r = futures_oi_buildup([_book(0, 100.0), _book(10, 101.0)], P)
    assert r.quality == "warming"
    assert (r.value["need"], r.value["have"]) == (16, 11)


def test_futures_oi_does_not_compare_across_a_feed_gap() -> None:
    # nothing between minute 10 and minute 160: the reading in force 15 minutes back is
    # two and a half hours old, so the change is not a 15-minute one
    book = [_book(0, 100.0, 1000), _book(10, 100.0, 1000), _book(160, 99.0, 900)]
    r = futures_oi_buildup(book, P)
    assert r.quality == "warming"
    assert r.note == "no reading near 15 min back (feed gap)"
    # a reading up to 5 minutes older than the window still counts
    near = [_book(0, 100.0, 1000), _book(140, 100.0, 1000), _book(160, 100.2, 1010)]
    assert futures_oi_buildup(near, P).quality == "ok"


def test_futures_oi_skips_readings_without_oi() -> None:
    book = [_book(0, 100.0, None), _book(15, 101.0, None)]
    assert futures_oi_buildup(book, P).quality == "warming"


# -- net volume ----------------------------------------------------------------------------


def _candle(minute: int, buy: int | None, sell: int | None, *, synthetic: bool = False) -> Candle:
    vol = (buy or 0) + (sell or 0)
    return Candle(
        "K", minute * M, 100.0, 100.0, 100.0, 100.0, vol,
        synthetic=synthetic, buy_volume=buy, sell_volume=sell,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("buy", "sell", "score"),
    [
        (75, 25, 1.0),  # net +0.50 of traded volume: full strength
        (25, 75, -1.0),
        (60, 40, 0.4),  # net +0.20
        (50, 50, 0.0),
        (100, 0, 1.0),  # clamped
    ],
)
def test_net_volume_scores_buys_against_sells(buy: int, sell: int, score: float) -> None:
    candles = [_candle(i, buy, sell) for i in range(15)]
    r = net_volume(candles, P)
    assert r.quality == "ok"
    assert r.group == "flow"
    assert r.score == pytest.approx(score)


def test_net_volume_reads_only_the_window_and_counts_quiet_minutes() -> None:
    old = [_candle(i, 0, 1000) for i in range(10)]  # heavy selling, outside the window
    quiet = [_candle(10 + i, 0, 0, synthetic=True) for i in range(5)]
    recent = [_candle(15 + i, 70, 30) for i in range(10)]
    r = net_volume(old + quiet + recent, P)
    assert r.score == pytest.approx(0.8)  # 700 buy vs 300 sell
    assert r.value["minutes"] == 15


def test_net_volume_warms_on_backfilled_minutes_without_sides() -> None:
    backfill = [_candle(i, None, None) for i in range(10)]
    live = [_candle(10 + i, 60, 40) for i in range(5)]
    r = net_volume(backfill + live, P)
    assert r.quality == "warming"
    assert (r.value["need"], r.value["have"]) == (15, 5)


def test_net_volume_with_nothing_traded_is_neutral() -> None:
    r = net_volume([_candle(i, 0, 0, synthetic=True) for i in range(15)], P)
    assert (r.quality, r.score) == ("ok", 0.0)


# -- book imbalance ------------------------------------------------------------------------


def _leaning(n: int, tbq: int, tsq: int) -> list[MinuteBook]:
    return [_book(i, 100.0, tbq=tbq, tsq=tsq) for i in range(n)]


def test_book_imbalance_reads_the_lean_against_its_own_average() -> None:
    # a book that always leans to the sell side is not bearish by itself
    flat = _leaning(30, 4000, 6000)
    assert book_imbalance(flat, P).score == pytest.approx(0.0)
    # the lean easing (imbalance -0.2 -> +0.2) on the last minute is bullish
    eased = [*_leaning(29, 4000, 6000), _book(29, 100.0, tbq=6000, tsq=4000)]
    r = book_imbalance(eased, P)
    mean = (29 * -0.2 + 0.2) / 30
    assert r.score == pytest.approx(min(1.0, (0.2 - mean) / 0.20))
    assert r.group == "flow"
    assert r.value["imbalance"] == pytest.approx(0.2)


def test_book_imbalance_averages_total_and_five_level_quantities() -> None:
    rows = [_book(i, 100.0, tbq=5000, tsq=5000, bid5=500, ask5=500) for i in range(29)]
    rows.append(_book(29, 100.0, tbq=5000, tsq=5000, bid5=550, ask5=450))  # depth +0.1
    r = book_imbalance(rows, P)
    assert r.value["imbalance"] == pytest.approx(0.05)


def test_book_imbalance_warms_until_the_average_has_its_minutes() -> None:
    r = book_imbalance(_leaning(10, 5000, 5000), P)
    assert r.quality == "warming"
    assert (r.value["need"], r.value["have"]) == (30, 10)
    no_book = [_book(i, 100.0) for i in range(40)]
    assert book_imbalance(no_book, P).quality == "warming"


# -- the other metal -----------------------------------------------------------------------


def test_peer_metal_is_the_other_metals_trend() -> None:
    votes = [
        IndicatorResult("ema_cross", "trend", 0.6, ""),
        IndicatorResult("vwap_position", "trend", 0.3, ""),
        IndicatorResult("supertrend", "trend", 0.0, "", "warming"),  # left out
    ]
    r = peer_metal("SILVER", votes)
    assert (r.name, r.group, r.quality) == ("peer_metal", "macro", "ok")
    assert r.score == pytest.approx(0.45)
    assert "SILVER" in r.note
    assert peer_metal("GOLD", []).quality == "warming"
    assert peer_metal("GOLD", votes[2:]).quality == "warming"


# -- bounds --------------------------------------------------------------------------------


@settings(max_examples=60)
@given(
    st.lists(
        st.tuples(
            st.floats(1, 1e6, allow_nan=False),
            st.integers(0, 10**6),
            st.integers(0, 10**6),
            st.integers(0, 10**6),
        ),
        min_size=1,
        max_size=60,
    )
)
def test_positioning_and_flow_scores_stay_in_bounds(
    rows: list[tuple[float, int, int, int]],
) -> None:
    book = [_book(i, px, oi or None, tbq, tsq) for i, (px, oi, tbq, tsq) in enumerate(rows)]
    candles = [_candle(i, tbq, tsq) for i, (_, _, tbq, tsq) in enumerate(rows)]
    for r in (futures_oi_buildup(book, P), book_imbalance(book, P), net_volume(candles, P)):
        assert -1.0 <= r.score <= 1.0

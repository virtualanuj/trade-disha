"""GIFT Nifty's overnight move as an opening-gap vote for NIFTY (spec §8.6)."""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tradedisha.indicators.gift import GiftSnapshot, gift_gap, snapshot_from
from tradedisha.parameters.model import Macro

MIN = 60_000
DAY = date(2026, 11, 19)
PREV_CLOSE = 1_000_000 * MIN  # 15:30 on the previous NSE day, as epoch ms
OPEN = PREV_CLOSE + 1065 * MIN  # 09:15 the next day


def _snap(ref: float = 25000.0, preopen: float = 25125.0) -> GiftSnapshot:
    return GiftSnapshot(DAY, PREV_CLOSE - MIN, ref, OPEN - MIN, preopen)


# -- the snapshot -------------------------------------------------------------------


def test_snapshot_reads_the_last_close_before_each_cut_off() -> None:
    prev = [(PREV_CLOSE - 3 * MIN, 1.0), (PREV_CLOSE - MIN, 2.0), (PREV_CLOSE, 3.0)]
    today = [(OPEN - 2 * MIN, 4.0), (OPEN - MIN, 5.0), (OPEN, 6.0)]
    s = snapshot_from(prev, today, day=DAY, prev_close_ms=PREV_CLOSE, open_ms=OPEN)
    assert s == GiftSnapshot(DAY, PREV_CLOSE - MIN, 2.0, OPEN - MIN, 5.0)
    assert s.move_pct == pytest.approx(150.0)


def test_snapshot_skips_a_missing_minute_at_the_close() -> None:
    prev = [(PREV_CLOSE - 4 * MIN, 1.0)]  # 15:29 itself did not trade
    s = snapshot_from(prev, [(OPEN - MIN, 2.0)], day=DAY, prev_close_ms=PREV_CLOSE, open_ms=OPEN)
    assert s is not None
    assert (s.ref_ts, s.ref_close) == (PREV_CLOSE - 4 * MIN, 1.0)


@pytest.mark.parametrize(
    ("prev", "today"),
    [
        ([], [(OPEN - MIN, 2.0)]),  # no close on the previous day
        ([(PREV_CLOSE - 31 * MIN, 1.0)], [(OPEN - MIN, 2.0)]),  # nothing near the close
        ([(PREV_CLOSE - MIN, 1.0)], []),  # nothing overnight
        ([(PREV_CLOSE - MIN, 1.0)], [(OPEN, 2.0)]),  # only after the open
        ([(PREV_CLOSE - MIN, 1.0)], [(PREV_CLOSE - 2 * MIN, 2.0)]),  # not after the close
        ([(PREV_CLOSE - MIN, 0.0)], [(OPEN - MIN, 2.0)]),  # a zero reference
    ],
)
def test_no_snapshot_without_both_prices(
    prev: list[tuple[int, float]], today: list[tuple[int, float]]
) -> None:
    assert snapshot_from(prev, today, day=DAY, prev_close_ms=PREV_CLOSE, open_ms=OPEN) is None


# -- the vote -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("direction", "minutes", "quality", "score"),
    [
        ("follow", 1, "ok", 1.0 * (1 - 1 / 30)),  # +0.50 % at full 0.50, 29/30 left
        ("follow", 15, "ok", 0.5),
        ("fade", 15, "ok", -0.5),
        ("follow", 29, "ok", 1 / 30),
        ("follow", 30, "info", 0.0),  # faded out: shown, not scored
        ("follow", 200, "info", 0.0),
        ("follow", 0, "info", 0.0),  # before the first minute has closed
    ],
)
def test_gift_gap_follows_or_fades_and_decays(
    direction: str, minutes: float, quality: str, score: float
) -> None:
    p = Macro(gift_full_pct=0.5, gift_fade_minutes=30, gift_direction=direction)
    r = gift_gap(_snap(25000.0, 25125.0), minutes, p)
    assert (r.name, r.group, r.quality) == ("gift_nifty", "macro", quality)
    assert r.score == pytest.approx(score)
    assert r.value["move_pct"] == pytest.approx(0.5)
    assert "GIFT Nifty +0.50% overnight" in r.note


def test_gift_gap_clamps_and_signs_a_gap_down() -> None:
    r = gift_gap(_snap(25000.0, 24500.0), 1, Macro(gift_full_pct=0.5, gift_fade_minutes=30))
    assert r.score == pytest.approx(-1.0 * (1 - 1 / 30))


def test_gift_gap_warms_without_a_snapshot() -> None:
    r = gift_gap(None, 5, Macro())
    assert (r.name, r.quality, r.score) == ("gift_nifty", "warming", 0.0)
    assert "no overnight reading" in r.note


@given(
    ref=st.floats(1.0, 1e6),
    preopen=st.floats(1.0, 1e6),
    minutes=st.floats(-100, 1000),
    full=st.floats(0.01, 10),
    fade=st.integers(1, 375),
    direction=st.sampled_from(["follow", "fade"]),
)
def test_gift_gap_score_is_bounded(
    ref: float, preopen: float, minutes: float, full: float, fade: int, direction: str
) -> None:
    p = Macro(gift_full_pct=full, gift_fade_minutes=fade, gift_direction=direction)
    r = gift_gap(_snap(ref, preopen), minutes, p)
    assert -1.0 <= r.score <= 1.0
    if r.quality != "ok":
        assert r.score == 0.0

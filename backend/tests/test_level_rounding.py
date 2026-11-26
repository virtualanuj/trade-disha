"""Target and stop in whole rupees (enhancement 24): signals as fired and live, paper trades
at their fill (from a signal or by hand), the ticket's levels, and levels the trader types.

Half a rupee rounds up. A level the rounding puts on or past the entry moves out to the
next whole rupee beyond it, so a trade never opens on its own target or stop; an option's
stop never goes below the 0.05 floor.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.test_bullion_trading import GOLD_KEY, PaperHarness
from tests.test_bullion_trading import at as mcx_at
from tests.test_paper import Harness
from tradedisha.engine.bullion_signals import future_levels
from tradedisha.engine.paper import PaperError, check_levels
from tradedisha.engine.signals import Direction, rescale_levels, round_levels, round_rupee
from tradedisha.parameters.model import ParameterSet

EXPIRY = date(2026, 11, 17)


@pytest.mark.parametrize(
    ("value", "want"),
    [
        (86.28, 86.0),
        (131.95, 132.0),
        (127.5, 128.0),
        (2.5, 3.0),
        (0.49, 0.0),
        (134_459.6, 134_460.0),
    ],
)
def test_half_a_rupee_rounds_up(value: float, want: float) -> None:
    assert round_rupee(value) == want


@pytest.mark.parametrize(
    ("direction", "entry", "target", "stop", "want"),
    [
        ("BUY_CE", 101.5, 131.95, 86.28, (132.0, 86.0)),
        ("BUY_CE", 2.0, 2.6, 1.7, (3.0, 1.0)),  # the stop would round onto the entry
        ("BUY_CE", 2.3, 2.4, 1.96, (3.0, 2.0)),  # and here the target
        ("BUY_CE", 0.5, 0.65, 0.43, (1.0, 0.05)),  # below a rupee: the 0.05 floor
        ("BUY_FUT", 135_000.0, 135_540.0, 134_730.0, (135_540.0, 134_730.0)),
        ("SELL_FUT", 135_000.4, 134_460.4, 135_270.6, (134_460.0, 135_271.0)),
        ("SELL_FUT", 100.0, 99.7, 100.2, (99.0, 101.0)),  # both would round onto the entry
    ],
)
def test_levels_round_to_whole_rupees_either_side_of_the_entry(
    direction: Direction,
    entry: float,
    target: float,
    stop: float,
    want: tuple[float, float],
) -> None:
    assert round_levels(direction, entry, target, stop) == want


@given(
    entry=st.floats(min_value=0.1, max_value=500_000.0),
    up=st.floats(min_value=0.0, max_value=1_000.0),
    down=st.floats(min_value=0.0, max_value=1_000.0),
    direction=st.sampled_from(["BUY_CE", "BUY_PE", "BUY_FUT", "SELL_FUT"]),
)
def test_rounded_levels_are_whole_and_bracket_the_entry(
    entry: float, up: float, down: float, direction: Direction
) -> None:
    entry = round(entry, 2)
    if direction in {"BUY_FUT", "SELL_FUT"}:
        entry = max(entry, 1_000.0)  # a future is priced in thousands; an option can be paise
    short = direction == "SELL_FUT"
    target = entry - up if short else entry + up
    stop = entry + down if short else max(0.05, entry - down)
    t, s = round_levels(direction, entry, target, stop)
    assert t == int(t)
    assert s == int(s) or s == 0.05
    assert check_levels(direction, entry, t, s) is None


def test_a_signal_fires_with_whole_rupee_levels() -> None:
    h = Harness()
    s = h.fire(entry=100.35)  # +30 % = 130.455, -15 % = 85.2975
    assert (s.target_price, s.stop_price) == (130.0, 85.0)


def test_live_levels_and_a_trade_at_its_fill_are_whole_rupees() -> None:
    h = Harness()
    s = h.fire(entry=100.0)
    assert rescale_levels(s, 101.5, None) == (132.0, 86.0)  # 131.95, 86.275
    h.tick(s.instrument_key, 101.5)
    t = h.paper.open(s.id)
    assert (t.target_price, t.stop_price) == (132.0, 86.0)


def test_expiry_day_points_levels_are_whole_rupees() -> None:
    h = Harness(day=EXPIRY)
    s = h.fire(entry=100.0)
    assert s.target_basis == "points"
    assert s.target_price == int(s.target_price)
    assert s.stop_price == int(s.stop_price)
    h.tick(s.instrument_key, 103.3)
    t = h.paper.open(s.id)
    assert (t.target_price, t.stop_price) == (int(t.target_price), int(t.stop_price))


def test_the_ticket_and_a_trade_by_hand_are_whole_rupees() -> None:
    h = Harness()
    h.tick(h.ce, 81.0)
    q = h.paper.quote_manual("NIFTY", "BUY_CE", h.r.atm)
    assert (q.target, q.stop) == (105.0, 69.0)  # 105.3, 68.85
    t = h.paper.open_manual("NIFTY", "BUY_CE", h.r.atm)
    assert (t.target_price, t.stop_price) == (105.0, 69.0)


def test_typed_and_edited_levels_are_rounded_too() -> None:
    h = Harness()
    h.tick(h.ce, 100.0)
    t = h.paper.open_manual("NIFTY", "BUY_CE", h.r.atm, target=120.4, stop=90.6)
    assert (t.target_price, t.stop_price) == (120.0, 91.0)
    edited = h.paper.set_levels(t.id, target=140.5, stop=95.49)
    assert (edited.target_price, edited.stop_price) == (141.0, 95.0)
    assert h.paper.store.levels(t.id)[-1].target == 141.0


def test_a_typed_level_that_rounds_onto_the_price_is_refused() -> None:
    """Rounding the trader's own number never moves it past the price: it is refused."""
    h = Harness()
    h.tick(h.ce, 100.0)
    with pytest.raises(PaperError, match="target"):
        h.paper.open_manual("NIFTY", "BUY_CE", h.r.atm, target=100.4, stop=90.0)


def test_bullion_levels_are_whole_rupees() -> None:
    p = ParameterSet()
    assert future_levels("SELL_FUT", 135_000.4, p) == (134_460.0, 135_270.0)  # .398, .401


def test_a_gold_trade_by_hand_is_whole_rupees(tmp_path: Path) -> None:
    h = PaperHarness(tmp_path, now=mcx_at(20, 1, 20))
    h.quote(GOLD_KEY, 135_000.4)
    t = h.paper.open_manual("GOLD", "BUY_FUT", None)
    assert (t.target_price, t.stop_price) == (135_540.0, 134_730.0)

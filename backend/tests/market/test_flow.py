"""Order-flow measures: book imbalance, signed trades, and the combined score."""

from __future__ import annotations

from datetime import date

import pytest

from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.instruments.resolve import resolve_index
from tradedisha.instruments.synthetic_master import build_synthetic_master
from tradedisha.market.chain import ChainState
from tradedisha.market.flow import FlowReading, FlowTracker, KeyFlow
from tradedisha.parameters.model import ParameterSet

TODAY = date(2026, 11, 12)
T0 = 1_794_500_000_000
W = 15_000


def tick(ts: int, ltp: float = 100.0, **kw: float | None) -> Tick:
    return Tick(key="K", ts=ts, ltp=ltp, **kw)  # type: ignore[arg-type]


# -- one instrument ------------------------------------------------------------


def test_book_imbalance_averages_the_five_levels_and_the_total_quantities() -> None:
    k = KeyFlow()
    k.apply(tick(T0, bid_qty5=300, ask_qty5=100, tbq=500, tsq=500))

    assert k.book(T0, W) == pytest.approx(0.25)  # (0.5 from the levels + 0.0 from totals) / 2


def test_book_uses_whichever_pair_it_has_and_carries_unchanged_fields_forward() -> None:
    k = KeyFlow()
    k.apply(tick(T0, bid_qty5=300, ask_qty5=100))
    assert k.book(T0, W) == pytest.approx(0.5)

    k.apply(tick(T0 + 1000, bid_qty5=100))  # the ask side is unchanged at 100

    assert k.book(T0 + 1000, W) == pytest.approx(0.25)  # mean of 0.5 and 0.0


def test_book_is_unknown_not_zero_without_quantities_or_once_they_are_stale() -> None:
    k = KeyFlow()
    k.apply(tick(T0))
    assert k.book(T0, W) is None

    k.apply(tick(T0, bid_qty5=300, ask_qty5=100))

    assert k.book(T0 + W, W) == pytest.approx(0.5)
    assert k.book(T0 + W + 1, W) is None


def test_trades_are_signed_by_where_they_print_against_the_quote_before_them() -> None:
    k = KeyFlow()
    k.apply(tick(T0, 100.0, bid=99.0, ask=101.0, volume=1000))  # first volume: nothing traded yet
    k.apply(tick(T0 + 1, 101.0, volume=1100))  # at the ask: 100 bought
    k.apply(tick(T0 + 2, 99.0, volume=1150))  # at the bid: 50 sold
    k.apply(tick(T0 + 3, 100.0, volume=1250))  # inside the quote: 100, no side

    assert k.trades(T0 + 3, W) == pytest.approx((100 - 50) / 250)


def test_a_trade_is_judged_against_the_old_quote_not_the_one_arriving_with_it() -> None:
    k = KeyFlow()
    k.apply(tick(T0, 100.0, bid=99.0, ask=101.0, volume=1000))
    k.apply(tick(T0 + 1, 101.0, bid=101.0, ask=103.0, volume=1100))  # lifted the old ask

    assert k.trades(T0 + 1, W) == 1.0


def test_trades_are_unknown_without_a_quote_or_without_volume_in_the_window() -> None:
    k = KeyFlow()
    k.apply(tick(T0, 100.0, volume=1000))
    k.apply(tick(T0 + 1, 101.0, volume=1100))  # traded, but no quote to judge it by
    assert k.trades(T0 + 1, W) is None

    k.apply(tick(T0 + 2, 100.0, bid=99.0, ask=101.0))
    k.apply(tick(T0 + 3, 101.0, volume=1200))

    assert k.trades(T0 + 3, W) == 1.0
    assert k.trades(T0 + 3 + W + 1, W) is None


# -- one index -------------------------------------------------------------------


class Harness:
    def __init__(self) -> None:
        master = build_synthetic_master(TODAY)
        self.r = resolve_index(master, "NIFTY", TODAY, 25_000.0, strike_window=3)
        self.chain = ChainState.from_resolved(self.r)
        self.params = ParameterSet()
        self.heard: list[FlowReading] = []
        self.flow = FlowTracker(
            params=lambda: self.params,
            resolved={"NIFTY": self.r},
            chains={"NIFTY": self.chain},
            on_flow=self.heard.append,
        )
        self.fut = self.r.future.instrument_key
        row = self.chain.rows[self.chain.atm]
        self.ce, self.pe = row.ce.key, row.pe.key

    def send(self, key: str, ts: int, **kw: float) -> None:
        self.flow.on_tick(StampedTick(Tick(key=key, ts=ts, ltp=100.0, **kw), ts))  # type: ignore[arg-type]


def test_score_mixes_the_parts_it_has_by_their_weights() -> None:
    h = Harness()
    h.send(h.fut, T0, bid_qty5=300, ask_qty5=100)  # futures book +0.5
    h.send(h.ce, T0, bid_qty5=400, ask_qty5=100)  # calls bid: +0.6
    h.send(h.pe, T0, bid_qty5=200, ask_qty5=300)  # puts offered: -0.2

    r = h.flow.reading("NIFTY", T0)

    assert r.fut_book == pytest.approx(0.5)
    assert r.fut_trades is None
    assert r.options == pytest.approx(0.4)  # (0.6 - -0.2) / 2
    assert r.score == pytest.approx((0.4 * 0.5 + 0.3 * 0.4) / 0.7)  # no futures trades seen


def test_no_score_at_all_without_any_order_flow_data() -> None:
    h = Harness()
    h.send(h.fut, T0)

    r = h.flow.reading("NIFTY", T0)

    assert (r.score, r.fut_book, r.fut_trades, r.options) == (None, None, None, None)


def test_options_part_needs_both_the_call_and_the_put() -> None:
    h = Harness()
    h.send(h.ce, T0, bid_qty5=400, ask_qty5=100)

    assert h.flow.reading("NIFTY", T0).options is None


def test_the_option_legs_read_are_the_ones_at_the_money_now() -> None:
    h = Harness()
    h.send(h.ce, T0, bid_qty5=400, ask_qty5=100)
    h.send(h.pe, T0, bid_qty5=100, ask_qty5=400)
    assert h.flow.reading("NIFTY", T0).options == pytest.approx(0.6)

    h.chain.atm += h.chain.step  # the market moved a strike; nothing seen there yet

    assert h.flow.reading("NIFTY", T0).options is None


def test_listeners_hear_a_reading_at_most_once_a_second_by_tick_time() -> None:
    h = Harness()
    for ms in (0, 300, 999, 1000, 1500, 2100):
        h.send(h.fut, T0 + ms, bid_qty5=300, ask_qty5=100)
    h.send("NSE_FO|not-ours", T0 + 5000, bid_qty5=1, ask_qty5=1)

    assert [r.ts - T0 for r in h.heard] == [0, 1000, 2100]
    assert h.flow.latest["NIFTY"] is h.heard[-1]
    assert h.heard[0].index == "NIFTY"

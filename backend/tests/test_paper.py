"""Paper trades: entry, every exit path, costs, fill quality, and the journal numbers."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time

import pytest

from tradedisha.clock import IST, MarketClock, ist_to_ms
from tradedisha.engine.aggregator import Bias, Label
from tradedisha.engine.bias_engine import BiasComputed, OverlayPoint
from tradedisha.engine.paper import (
    ExitReason,
    FillQuality,
    PaperError,
    PaperTrade,
    PaperTradeManager,
    PaperTradeStore,
    Price,
    journal_stats,
)
from tradedisha.engine.signals import Signal, SignalEngine
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.instruments.resolve import resolve_index
from tradedisha.instruments.synthetic_master import build_synthetic_master
from tradedisha.market.chain import ChainState
from tradedisha.parameters.model import ParameterSet
from tradedisha.store.db import connect

TODAY = date(2026, 11, 12)  # a Thursday, not an expiry day
M = 60_000


def at(h: int, m: int, s: int = 0, day: date = TODAY) -> int:
    return ist_to_ms(datetime(day.year, day.month, day.day, h, m, s, tzinfo=IST))


def _bias(minute_ts: int, value: float) -> BiasComputed:
    label: Label = "Bullish" if value >= 0.2 else "Bearish" if value <= -0.2 else "Neutral"
    b = Bias(value, label, round(abs(value) * 100), {}, {}, [], False)
    return BiasComputed("NIFTY", minute_ts, b, OverlayPoint(minute_ts, None, None, None, None, 0))


class Harness:
    def __init__(self, *, enforce_hours: bool = True) -> None:
        master = build_synthetic_master(TODAY)
        self.r = resolve_index(master, "NIFTY", TODAY, 25_000.0, strike_window=3)
        self.chain = ChainState.from_resolved(self.r)
        self.params = ParameterSet()
        self.feed_live = True
        self.now = at(10, 0)
        self.prices: dict[str, Price] = {}
        self.conn = connect(":memory:")
        self.enforce_hours = enforce_hours
        self.updates: list[PaperTrade] = []
        self.signal_events: list[Signal] = []
        self.clock = MarketClock(
            market_open=time(9, 15),
            market_close=time(15, 30),
            pre_open_start=time(9, 0),
            source=lambda: datetime.fromtimestamp(self.now / 1000, tz=IST),
        )
        self.signals = SignalEngine(
            clock=self.clock,
            params=lambda: self.params,
            resolved={"NIFTY": self.r},
            chains={"NIFTY": self.chain},
            conn=self.conn,
            feed_live=lambda: self.feed_live,
            enforce_hours=enforce_hours,
            market_open=time(9, 15),
            market_close=time(15, 30),
            risk_free_rate=0.065,
            on_signal=self.signal_events.append,
        )
        self.paper = self.new_manager()
        atm = next(p for p in self.r.strikes if p.strike == self.r.atm)
        self.ce = atm.ce.instrument_key
        self.pe = atm.pe.instrument_key

    def new_manager(self) -> PaperTradeManager:
        return PaperTradeManager(
            clock=self.clock,
            params=lambda: self.params,
            conn=self.conn,
            signals=self.signals,
            price=self.prices.get,
            feed_live=lambda: self.feed_live,
            enforce_hours=self.enforce_hours,
            last_recorded=lambda key, before: self.prices.get(key),
            on_trade=self.updates.append,
        )

    def tick(self, key: str, ltp: float, ts: int | None = None) -> None:
        """A tick reaches the chain, the price cache and the paper manager, as in the app."""
        ts = self.now if ts is None else ts
        t = Tick(key=key, ts=ts, ltp=ltp)
        self.chain.apply(t)
        self.prices[key] = Price(ltp, ts)
        self.paper.on_tick(StampedTick(t, ts))

    def fire(self, value: float = 0.7, entry: float = 100.0) -> Signal:
        """Bias crosses the threshold at 10:00 with the ATM option at `entry`."""
        self.tick(self.ce if value > 0 else self.pe, entry)
        self.signals.on_bias(_bias(self.now - M, value))
        return self.signals.active["NIFTY"]

    def open(self, fill: float = 101.0) -> PaperTrade:
        """Signal at 100 (target 130, stop 85), trader clicks when the price is `fill`."""
        signal = self.fire()
        self.tick(signal.instrument_key, fill)
        return self.paper.open(signal.id)


# -- entry --------------------------------------------------------------------------


def test_opens_at_the_current_price_and_records_slippage() -> None:
    h = Harness()
    trade = h.open(fill=101.5)

    assert trade.status == "open"
    assert trade.entry_price == 101.5
    assert trade.signal_entry == 100.0
    assert trade.slippage == 1.5
    assert (trade.target_price, trade.stop_price) == (130.0, 85.0)  # copied from the signal
    assert trade.lots == 1
    assert trade.qty == h.r.lot_size
    assert trade.cost == 60.0
    assert h.paper.store.get(trade.id) == trade
    assert h.updates == [trade]


def test_opening_marks_the_signal_traded_so_a_fresh_one_can_fire() -> None:
    h = Harness()
    trade = h.open()

    assert "NIFTY" not in h.signals.active
    assert h.signal_events[-1].status == "traded"
    h.now += M
    h.signals.on_bias(_bias(h.now - M, 0.7))
    fresh = h.signals.active["NIFTY"]
    assert fresh.id != trade.signal_id  # open trades never gate a signal


def test_nothing_opens_without_a_click() -> None:
    h = Harness()
    h.fire()
    h.tick(h.ce, 140.0)
    h.paper.tick(h.now)
    assert h.paper.open_trades == {}
    assert h.paper.store.read() == []


def test_lots_and_cost_come_from_the_parameters() -> None:
    h = Harness()
    h.params = h.params.model_copy(
        update={"paper": h.params.paper.model_copy(update={"lots": 3, "cost_per_trade": 40.0})}
    )
    trade = h.open()
    assert trade.qty == 3 * h.r.lot_size
    assert trade.cost == 120.0


def test_refuses_when_the_signal_is_not_active() -> None:
    h = Harness()
    with pytest.raises(PaperError) as unknown:
        h.paper.open("nope")
    assert unknown.value.not_found

    trade = h.open()
    with pytest.raises(PaperError, match="no longer active \\(traded\\)"):
        h.paper.open(trade.signal_id)


def test_refuses_when_the_feed_is_down() -> None:
    h = Harness()
    signal = h.fire()
    h.feed_live = False
    with pytest.raises(PaperError, match="feed is not live"):
        h.paper.open(signal.id)
    assert "NIFTY" in h.signals.active  # the signal is untouched


def test_refuses_outside_market_hours_and_after_square_off() -> None:
    h = Harness()
    signal = h.fire()
    h.now = at(15, 20)
    with pytest.raises(PaperError, match="square-off"):
        h.paper.open(signal.id)
    h.now = at(16, 0)
    with pytest.raises(PaperError, match="market is not open"):
        h.paper.open(signal.id)


# -- exits --------------------------------------------------------------------------


def test_target_exit_fills_at_the_triggering_tick_net_of_cost() -> None:
    h = Harness()
    trade = h.open(fill=101.0)
    h.tick(h.ce, 120.0, at(10, 1))
    assert trade.id in h.paper.open_trades

    h.tick(h.ce, 131.0, at(10, 2))

    closed = h.paper.store.get(trade.id)
    assert closed is not None
    assert h.paper.open_trades == {}
    assert (closed.status, closed.exit_reason, closed.exit_fill_quality) == (
        "closed",
        "TARGET",
        "live",
    )
    assert closed.exit_price == 131.0
    assert closed.exit_ts == at(10, 2)
    assert closed.gross == 30.0 * h.r.lot_size
    assert closed.net == 30.0 * h.r.lot_size - 60.0
    assert h.updates[-1] == closed


def test_stop_exit() -> None:
    h = Harness()
    trade = h.open(fill=101.0)
    h.tick(h.ce, 84.5, at(10, 3))

    closed = h.paper.store.get(trade.id)
    assert closed is not None
    assert (closed.exit_reason, closed.exit_price) == ("STOP", 84.5)
    assert closed.net == pytest.approx(-16.5 * h.r.lot_size - 60.0)


def test_ticks_of_other_instruments_do_not_touch_the_trade() -> None:
    h = Harness()
    trade = h.open()
    h.tick(h.pe, 500.0)
    assert trade.id in h.paper.open_trades


def test_manual_close_at_current_price_needs_a_live_feed() -> None:
    h = Harness()
    trade = h.open(fill=101.0)
    h.tick(h.ce, 110.0)
    h.feed_live = False
    with pytest.raises(PaperError, match="feed is not live"):
        h.paper.close_manual(trade.id)

    h.feed_live = True
    h.now = at(10, 5)
    closed = h.paper.close_manual(trade.id)
    assert (closed.exit_reason, closed.exit_price, closed.exit_fill_quality) == (
        "MANUAL",
        110.0,
        "live",
    )
    assert closed.exit_ts == at(10, 5)
    with pytest.raises(PaperError, match="already closed"):
        h.paper.close_manual(trade.id)
    with pytest.raises(PaperError) as unknown:
        h.paper.close_manual("nope")
    assert unknown.value.not_found


def test_square_off_at_1515_with_a_live_feed() -> None:
    h = Harness()
    trade = h.open(fill=101.0)
    h.tick(h.ce, 105.0, at(15, 14, 58))
    h.paper.tick(at(15, 14, 59))
    assert trade.id in h.paper.open_trades

    h.paper.tick(at(15, 15))

    closed = h.paper.store.get(trade.id)
    assert closed is not None
    assert (closed.exit_reason, closed.exit_price, closed.exit_fill_quality) == (
        "SQUARE_OFF",
        105.0,
        "live",
    )
    assert closed.exit_price_age_ms is None


def test_square_off_time_is_tunable() -> None:
    h = Harness()
    h.params = h.params.model_copy(
        update={"paper": h.params.paper.model_copy(update={"square_off_time": time(14, 0)})}
    )
    trade = h.open()
    h.paper.tick(at(14, 0))
    assert trade.id not in h.paper.open_trades


def test_no_square_off_when_hours_are_not_enforced() -> None:
    h = Harness(enforce_hours=False)
    trade = h.open()
    h.paper.tick(at(15, 20))
    assert trade.id in h.paper.open_trades


# -- feed outages -------------------------------------------------------------------


def test_first_tick_after_an_outage_exits_marked_after_gap() -> None:
    h = Harness()
    trade = h.open(fill=101.0)
    h.feed_live = False
    h.paper.tick(at(10, 1))
    assert trade.id in h.paper.open_trades  # nothing is evaluated without prices

    h.feed_live = True
    h.tick(h.ce, 70.0, at(10, 9))  # gapped straight through the stop at 85

    closed = h.paper.store.get(trade.id)
    assert closed is not None
    assert (closed.exit_reason, closed.exit_price, closed.exit_fill_quality) == (
        "STOP",
        70.0,
        "after_gap",
    )


def test_only_the_first_tick_after_an_outage_counts_as_after_gap() -> None:
    h = Harness()
    trade = h.open(fill=101.0)
    h.feed_live = False
    h.paper.tick(at(10, 1))
    h.feed_live = True
    h.tick(h.ce, 100.0, at(10, 9))
    h.tick(h.ce, 131.0, at(10, 10))

    closed = h.paper.store.get(trade.id)
    assert closed is not None
    assert (closed.exit_reason, closed.exit_fill_quality) == ("TARGET", "live")


def test_square_off_with_the_feed_down_uses_the_last_price_marked_stale() -> None:
    h = Harness()
    trade = h.open(fill=101.0)
    h.tick(h.ce, 96.0, at(15, 10))
    h.feed_live = False

    h.paper.tick(at(15, 15))

    closed = h.paper.store.get(trade.id)
    assert closed is not None
    assert (closed.exit_reason, closed.exit_price, closed.exit_fill_quality) == (
        "SQUARE_OFF",
        96.0,
        "stale",
    )
    assert closed.exit_price_age_ms == 5 * M


def test_trades_left_open_survive_a_restart_as_a_gap() -> None:
    h = Harness()
    trade = h.open(fill=101.0)

    h.paper = h.new_manager()  # the app restarts the same day

    assert trade.id in h.paper.open_trades
    h.tick(h.ce, 140.0, at(10, 30))
    closed = h.paper.store.get(trade.id)
    assert closed is not None
    assert (closed.exit_reason, closed.exit_fill_quality) == ("TARGET", "after_gap")


def test_a_trade_left_open_overnight_is_squared_off_stale_on_the_next_start() -> None:
    h = Harness()
    trade = h.open(fill=101.0)
    h.tick(h.ce, 99.0, at(15, 0))
    h.now = at(9, 20, day=date(2026, 11, 13))

    h.paper = h.new_manager()

    closed = h.paper.store.get(trade.id)
    assert closed is not None
    assert h.paper.open_trades == {}
    assert (closed.exit_reason, closed.exit_price, closed.exit_fill_quality) == (
        "SQUARE_OFF",
        99.0,
        "stale",
    )
    assert closed.exit_ts == at(15, 15)
    assert closed.exit_price_age_ms == 15 * M


# -- bias warning -------------------------------------------------------------------


def test_bias_reversed_warning_sets_and_clears_without_closing() -> None:
    h = Harness()
    trade = h.open()  # a call
    h.paper.on_bias(_bias(at(10, 1), -0.4))
    assert h.paper.open_trades[trade.id].warning == "bias_reversed"
    assert h.updates[-1].warning == "bias_reversed"

    n = len(h.updates)
    h.paper.on_bias(_bias(at(10, 2), -0.5))
    assert len(h.updates) == n  # unchanged warning publishes nothing

    h.paper.on_bias(_bias(at(10, 3), 0.0))  # neutral no longer opposes
    assert h.paper.open_trades[trade.id].warning is None
    assert h.paper.open_trades[trade.id].status == "open"


# -- journal ------------------------------------------------------------------------


def _closed(
    net: float,
    *,
    index: str = "NIFTY",
    reason: ExitReason = "TARGET",
    quality: FillQuality = "live",
    minutes: int = 10,
    n: int = 0,
) -> PaperTrade:
    return PaperTrade(
        id=f"t{n}",
        signal_id="s",
        index=index,
        instrument_key="K",
        trading_symbol="SYM",
        direction="BUY_CE",
        strike=25_000,
        expiry="2026-11-17",
        lots=1,
        qty=65,
        signal_entry=100,
        entry_price=100,
        entry_ts=at(10, 0),
        slippage=0,
        target_price=130,
        stop_price=85,
        cost=60,
        status="closed",
        exit_price=110,
        exit_ts=at(10, minutes),
        exit_reason=reason,
        exit_fill_quality=quality,
        gross=net + 60,
        net=net,
    )


def test_journal_stats_overall_and_per_index() -> None:
    trades = [
        _closed(1000, n=1),
        _closed(-400, reason="STOP", minutes=20, n=2),
        _closed(0, reason="MANUAL", n=3),  # break-even after costs is not a hit
        _closed(600, index="BANKNIFTY", reason="SQUARE_OFF", quality="stale", n=4),
        replace(_closed(0, n=5), status="open", net=None, gross=None),
    ]

    overall, bank, nifty = journal_stats(trades)

    assert overall.scope == "overall"
    assert (overall.trades, overall.hits, overall.hit_rate) == (4, 2, 0.5)
    assert overall.avg_win == 800.0
    assert overall.avg_loss == -200.0
    assert overall.net_total == 1200.0
    assert overall.gross_total == 1440.0
    assert overall.avg_duration_s == 750.0
    assert overall.by_reason == {"TARGET": 1, "STOP": 1, "MANUAL": 1, "SQUARE_OFF": 1}
    assert overall.non_live_fills == 1
    assert (bank.scope, bank.trades, bank.hit_rate) == ("BANKNIFTY", 1, 1.0)
    assert (nifty.scope, nifty.trades, nifty.hits, nifty.net_total) == ("NIFTY", 3, 1, 600.0)


def test_journal_stats_with_no_trades() -> None:
    (overall,) = journal_stats([])
    assert (overall.trades, overall.hit_rate, overall.avg_win, overall.net_total) == (
        0,
        None,
        None,
        0.0,
    )


def test_store_filters_by_day_index_and_status() -> None:
    h = Harness()
    trade = h.open()
    store = PaperTradeStore(h.conn)
    assert store.read(index="NIFTY", status="open") == [trade]
    assert store.read(index="BANKNIFTY") == []
    assert store.read(status="closed") == []
    assert store.read(start_ms=at(0, 0), end_ms=at(23, 59)) == [trade]
    assert store.read(end_ms=at(9, 0)) == []

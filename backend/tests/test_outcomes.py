"""Scoring every signal: what the option did after it fired, whoever traded it or not."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

import pytest

from tradedisha.clock import IST, ist_to_ms
from tradedisha.engine.outcomes import Outcome, OutcomeTracker, scorecard
from tradedisha.engine.signals import Direction, Signal, SignalStore
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.parameters.model import ParameterSet
from tradedisha.store.db import connect

DAY = date(2026, 11, 12)
M = 60_000
OPT = "NSE_FO|1"
SPOT = "NSE_INDEX|Nifty 50"


def at(h: int, m: int, s: int = 0) -> int:
    return ist_to_ms(datetime(DAY.year, DAY.month, DAY.day, h, m, s, tzinfo=IST))


def make_signal(
    sid: str = "s1", *, fired: int | None = None, direction: Direction = "BUY_CE"
) -> Signal:
    ts = at(10, 0) if fired is None else fired
    return Signal(
        id=sid,
        index="NIFTY",
        minute_ts=ts - M,
        ts_fired=ts,
        direction=direction,
        instrument_key=OPT,
        trading_symbol="NIFTY 25000 CE",
        strike=25_000.0,
        expiry="2026-11-17",
        lot_size=75,
        entry_price=100.0,
        target_price=130.0,
        stop_price=85.0,
        target_basis="pct",
        target_points=None,
        stop_points=None,
        delta_used=None,
        bias=0.6,
        strength=60,
        breakdown_json="{}",
        expires_at=ts + 5 * M,
        status="active",
        status_ts=ts,
    )


class Harness:
    def __init__(self) -> None:
        self.conn = connect(":memory:")
        self.params = ParameterSet()
        self.spot_history: dict[int, float] = {}
        self.events: list[Outcome] = []
        self.tracker = self._tracker()

    def _tracker(self) -> OutcomeTracker:
        return OutcomeTracker(
            params=lambda: self.params,
            conn=self.conn,
            spot_keys={"NIFTY": SPOT},
            spot_before=lambda _index, ms: self.spot_history.get(ms),
            on_outcome=self.events.append,
        )

    def restart(self) -> None:
        self.tracker = self._tracker()

    def fire(self, s: Signal) -> Signal:
        SignalStore(self.conn).upsert(s)
        self.tracker.on_signal(s)
        return s

    def opt(self, ts: int, ltp: float) -> None:
        self.tracker.on_tick(StampedTick(Tick(key=OPT, ts=ts, ltp=ltp), ts))

    def spot(self, ts: int, ltp: float) -> None:
        self.tracker.on_tick(StampedTick(Tick(key=SPOT, ts=ts, ltp=ltp), ts))

    def get(self, sid: str = "s1") -> Outcome:
        o = self.tracker.get(sid)
        assert o is not None
        return o


def test_a_new_signal_is_open_until_something_happens() -> None:
    h = Harness()
    h.fire(make_signal())

    o = h.get()

    assert o.result == "open"
    assert o.final is False
    assert o.end_ts == at(10, 30)  # the default 30-minute horizon
    assert (o.best_price, o.worst_price) == (100.0, 100.0)


def test_target_first_is_recorded_and_later_prices_do_not_change_the_result() -> None:
    h = Harness()
    h.fire(make_signal())
    h.opt(at(10, 1), 110.0)
    h.opt(at(10, 3), 131.0)
    h.opt(at(10, 6), 80.0)  # through the stop, but the target came first

    o = h.get()

    assert (o.result, o.result_ts) == ("target", at(10, 3))
    assert (o.best_price, o.best_ts) == (131.0, at(10, 3))
    assert (o.worst_price, o.worst_ts) == (80.0, at(10, 6))
    assert o.final is False  # best and worst are still followed to the horizon


def test_stop_first() -> None:
    h = Harness()
    h.fire(make_signal())
    h.opt(at(10, 2), 84.0)
    h.opt(at(10, 4), 140.0)

    assert (h.get().result, h.get().result_ts) == ("stop", at(10, 2))


def test_neither_when_the_horizon_passes_untouched() -> None:
    h = Harness()
    h.fire(make_signal())
    h.opt(at(10, 10), 112.0)
    h.opt(at(10, 20), 93.0)

    h.tracker.tick(at(10, 30))
    h.opt(at(10, 31), 200.0)  # after the horizon: ignored

    o = h.get()
    assert (o.result, o.result_ts, o.final) == ("neither", at(10, 30), True)
    assert (o.best_price, o.worst_price) == (112.0, 93.0)


def test_a_tick_past_the_horizon_also_closes_the_books() -> None:
    """Replay has no timer running at market speed; tick times must be enough."""
    h = Harness()
    h.fire(make_signal())

    h.spot(at(10, 45), 25_000.0)

    assert h.get().final is True
    assert h.get().result == "neither"


def test_horizon_is_cut_at_square_off() -> None:
    h = Harness()
    h.fire(make_signal(fired=at(15, 5)))

    assert h.get().end_ts == at(15, 15)


def test_prices_one_five_and_fifteen_minutes_after_firing() -> None:
    h = Harness()
    h.fire(make_signal())
    h.opt(at(10, 0, 30), 104.0)
    h.opt(at(10, 2), 108.0)  # the 1-minute mark has passed: price then was 104
    h.opt(at(10, 4), 111.0)
    h.tracker.tick(at(10, 5))  # exactly at the 5-minute mark
    h.opt(at(10, 20), 99.0)

    o = h.get()

    assert (o.px_1m, o.px_5m, o.px_15m) == (104.0, 111.0, 111.0)


@pytest.mark.parametrize(
    ("direction", "pre", "best"), [("BUY_CE", 40.0, 30.0), ("BUY_PE", -40.0, 10.0)]
)
def test_spot_move_before_and_after_firing_in_the_signal_direction(
    direction: Direction, pre: float, best: float
) -> None:
    h = Harness()
    h.spot_history[at(9, 50)] = 24_960.0  # ten minutes before firing
    h.spot(at(9, 59, 59), 25_000.0)
    h.fire(make_signal(direction=direction))
    h.spot(at(10, 5), 25_030.0)
    h.spot(at(10, 9), 24_990.0)

    o = h.get()

    assert o.spot_at_fire == 25_000.0
    assert o.spot_pre_move == pre
    assert o.spot_best_move == best


def test_a_signal_that_is_traded_or_reversed_is_still_scored() -> None:
    h = Harness()
    s = h.fire(make_signal())
    h.tracker.on_signal(replace(s, status="reversed", status_ts=at(10, 1)))
    h.opt(at(10, 2), 135.0)

    assert h.get().result == "target"


def test_listeners_hear_the_start_the_result_and_the_close_but_not_every_tick() -> None:
    h = Harness()
    h.fire(make_signal())
    h.opt(at(10, 1), 105.0)
    h.opt(at(10, 2), 106.0)
    h.opt(at(10, 3), 131.0)
    h.tracker.tick(at(10, 30))

    assert [(o.result, o.final) for o in h.events] == [
        ("open", False),
        ("target", False),
        ("target", True),
    ]


def test_unfinished_outcomes_carry_on_after_a_restart() -> None:
    h = Harness()
    h.fire(make_signal())
    h.opt(at(10, 1), 120.0)
    h.tracker.flush()

    h.restart()
    h.opt(at(10, 2), 84.0)

    o = h.get()
    assert o.result == "stop"
    assert o.best_price == 120.0


def test_scorecard_counts_rates_moves_and_lateness() -> None:
    h = Harness()
    h.spot_history[at(9, 50)] = 24_970.0
    h.spot(at(9, 59), 25_000.0)
    h.fire(make_signal("a"))
    h.fire(make_signal("b"))
    h.fire(replace(make_signal("c"), index="BANKNIFTY"))
    h.spot(at(10, 5), 25_010.0)  # 30 points before firing, 10 after: three quarters late
    h.opt(at(10, 6), 130.0)  # all three watch the same option here
    h.tracker.tick(at(10, 30))
    signals = SignalStore(h.conn).read(at(9, 0), at(16, 0))

    rows = {r.scope: r for r in scorecard(signals, h.tracker.store.for_signals(signals))}

    assert set(rows) == {"all", "NIFTY", "BANKNIFTY"}
    nifty = rows["NIFTY"]
    assert (nifty.signals, nifty.scored) == (2, 2)
    assert (nifty.target_pct, nifty.stop_pct, nifty.neither_pct) == (100.0, 0.0, 0.0)
    assert nifty.avg_best_pct == 30.0
    assert nifty.avg_worst_pct == 0.0
    assert nifty.avg_late_share == 0.75
    assert rows["all"].signals == 3
    assert rows["BANKNIFTY"].avg_late_share is None  # no spot was seen for it
    assert {(r.rule, r.shadow) for r in rows.values()} == {("minute_close", False)}


def test_scorecard_keeps_each_rule_apart_with_the_live_one_first() -> None:
    h = Harness()
    h.fire(make_signal("live"))
    h.fire(replace(make_signal("sh1"), entry_mode="trigger", shadow=True))
    h.fire(replace(make_signal("sh2"), entry_mode="trigger", shadow=True))
    h.opt(at(10, 6), 130.0)
    signals = SignalStore(h.conn).read(at(9, 0), at(16, 0))

    rows = scorecard(signals, h.tracker.store.for_signals(signals))

    assert [(r.rule, r.shadow, r.scope, r.signals) for r in rows] == [
        ("minute_close", False, "all", 1),
        ("minute_close", False, "NIFTY", 1),
        ("trigger", True, "all", 2),
        ("trigger", True, "NIFTY", 2),
    ]


def test_scorecard_of_nothing_is_empty() -> None:
    assert scorecard([], {}) == []


def test_scorecard_leaves_open_signals_out_of_the_rates() -> None:
    h = Harness()
    h.fire(make_signal("a"))
    signals = SignalStore(h.conn).read(at(9, 0), at(16, 0))

    overall, _nifty = scorecard(signals, h.tracker.store.for_signals(signals))

    assert (overall.signals, overall.scored, overall.target_pct) == (1, 0, None)

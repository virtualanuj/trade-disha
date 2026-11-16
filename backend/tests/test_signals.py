"""Signal lifecycle: fire, lapse, reversal, hours, feed gate, expiry-day points, re-arm."""

from __future__ import annotations

from datetime import date, datetime, time

import pytest

from tradedisha.clock import IST, MarketClock, ist_to_ms
from tradedisha.engine.aggregator import Bias, Label
from tradedisha.engine.bias_engine import BiasComputed, OverlayPoint
from tradedisha.engine.signals import Signal, SignalEngine
from tradedisha.feed.provider import Tick
from tradedisha.indicators.greeks import bs_delta
from tradedisha.instruments.resolve import resolve_index
from tradedisha.instruments.synthetic_master import build_synthetic_master
from tradedisha.market.chain import ChainState
from tradedisha.parameters.model import ParameterSet
from tradedisha.store.db import connect

TODAY = date(2026, 11, 12)
EXPIRY = date(2026, 11, 17)
M = 60_000


def at(day: date, h: int, m: int) -> int:
    return ist_to_ms(datetime(day.year, day.month, day.day, h, m, tzinfo=IST))


def _bias(index: str, minute_ts: int, value: float) -> BiasComputed:
    label: Label = "Bullish" if value >= 0.2 else "Bearish" if value <= -0.2 else "Neutral"
    b = Bias(value, label, round(abs(value) * 100), {}, {}, [], False)
    return BiasComputed(index, minute_ts, b, OverlayPoint(minute_ts, None, None, None, None, 0))


class Harness:
    def __init__(
        self,
        day: date = TODAY,
        *,
        feed_live: bool = True,
        enforce_hours: bool = True,
        shadow: bool = False,
        entry_mode: str = "minute_close",
    ) -> None:
        master = build_synthetic_master(TODAY)
        self.r = resolve_index(master, "NIFTY", day, 25_000.0, strike_window=3)
        self.chain = ChainState.from_resolved(self.r)
        self.params = ParameterSet.model_validate({"signal": {"entry_mode": entry_mode}})
        self.feed_live = feed_live
        self.events: list[Signal] = []
        self.clock = MarketClock(
            market_open=time(9, 15),
            market_close=time(15, 30),
            pre_open_start=time(9, 0),
            source=lambda: datetime(day.year, day.month, day.day, 10, 0, tzinfo=IST),
        )
        self.engine = SignalEngine(
            clock=self.clock,
            params=lambda: self.params,
            resolved={"NIFTY": self.r},
            chains={"NIFTY": self.chain},
            conn=connect(":memory:"),
            feed_live=lambda: self.feed_live,
            enforce_hours=enforce_hours,
            market_open=time(9, 15),
            market_close=time(15, 30),
            risk_free_rate=0.065,
            on_signal=self.events.append,
            shadow=shadow,
        )
        self.price_atm(ce=150.0, pe=140.0)

    def price_atm(self, *, ce: float, pe: float, iv: float = 14.0) -> None:
        row = self.chain.rows[self.chain.atm]
        self.chain.set_spot(self.chain.atm)
        self.chain.apply(Tick(key=row.ce.key, ts=1, ltp=ce, oi=1000, iv=iv))
        self.chain.apply(Tick(key=row.pe.key, ts=1, ltp=pe, oi=1000, iv=iv))

    def minute(self, h: int, m: int, bias: float, day: date = TODAY) -> None:
        self.engine.on_bias(_bias("NIFTY", at(day, h, m) - M, bias))

    def quote(self, *, ce: tuple[float, float], pe: tuple[float, float]) -> None:
        row = self.chain.rows[self.chain.atm]
        self.chain.apply(Tick(key=row.ce.key, ts=2, ltp=150.0, bid=ce[0], ask=ce[1]))
        self.chain.apply(Tick(key=row.pe.key, ts=2, ltp=140.0, bid=pe[0], ask=pe[1]))

    def flow(self, h: int, m: int, s: int, score: float | None) -> None:
        self.engine.on_flow("NIFTY", at(TODAY, h, m) + s * 1000, score)

    def reason(self) -> str | None:
        return self.engine.gates["NIFTY"].reason


def test_fires_buy_ce_with_pct_target_and_stop() -> None:
    h = Harness()
    h.minute(10, 0, 0.62)
    s = h.engine.active["NIFTY"]
    assert s.direction == "BUY_CE"
    assert s.strike == 25_000
    assert s.trading_symbol.endswith("25000CE")
    assert (s.entry_price, s.target_price, s.stop_price) == (150.0, 195.0, 127.5)
    assert s.target_basis == "pct"
    assert s.expires_at == s.ts_fired + 300_000
    assert h.engine.store.get(s.id) is not None
    assert h.engine.gates["NIFTY"].fired is True


def test_below_threshold_and_active_exists_gates() -> None:
    h = Harness()
    h.minute(10, 0, 0.3)
    assert "NIFTY" not in h.engine.active
    assert h.reason() == "below_threshold"
    h.minute(10, 1, 0.7)
    first = h.engine.active["NIFTY"]
    h.minute(10, 2, 0.8)
    assert h.engine.active["NIFTY"] is first
    assert h.reason() == "active_exists"


def test_lapses_after_ttl_then_refires_if_still_strong() -> None:
    h = Harness()
    h.minute(10, 0, 0.7)
    first = h.engine.active["NIFTY"]
    h.engine.tick(first.expires_at - 1)
    assert h.engine.active["NIFTY"] is first
    h.engine.tick(first.expires_at)
    assert "NIFTY" not in h.engine.active
    assert h.events[-1].status == "lapsed"
    h.minute(10, 6, 0.7)
    second = h.engine.active["NIFTY"]
    assert second.id != first.id  # fresh signal at the next qualifying minute


def test_reversal_on_sign_flip_and_on_neutral() -> None:
    h = Harness()
    h.minute(10, 0, 0.7)
    h.minute(10, 1, -0.65)  # flips: ends the CE signal and fires a PE one in the same minute
    statuses = [e.status for e in h.events]
    assert statuses == ["active", "reversed", "active"]
    assert h.engine.active["NIFTY"].direction == "BUY_PE"
    h.minute(10, 2, 0.1)  # neutral band: reversed, nothing fires
    assert "NIFTY" not in h.engine.active
    assert h.events[-1].status == "reversed"


def test_outside_hours_and_feed_down() -> None:
    h = Harness()
    h.minute(15, 1, 0.9)  # after last_signal_time 15:00
    assert h.reason() == "outside_hours"
    h.minute(9, 14, 0.9)  # before open
    assert h.reason() == "outside_hours"
    h.feed_live = False
    h.minute(10, 0, 0.9)
    assert h.reason() == "feed_down"


def test_hours_not_enforced_for_dev_feeds() -> None:
    h = Harness(enforce_hours=False)
    h.minute(22, 0, 0.9)
    assert "NIFTY" in h.engine.active


def test_expiry_day_uses_points_via_delta_and_13_00_cutoff() -> None:
    h = Harness(day=EXPIRY)
    assert h.r.is_expiry_day
    h.minute(10, 0, 0.7, day=EXPIRY)
    s = h.engine.active["NIFTY"]
    assert s.target_basis == "points"
    assert (s.target_points, s.stop_points) == (40, 20)
    assert s.delta_used is not None
    assert 0.3 < s.delta_used < 0.7  # ATM call
    assert s.target_price == pytest.approx(150 + s.delta_used * 40, abs=0.011)
    assert s.stop_price == pytest.approx(150 - s.delta_used * 20, abs=0.011)
    h.engine.mark_traded(s.id, s.ts_fired + 1000)
    h.minute(13, 1, 0.9, day=EXPIRY)
    assert h.reason() == "outside_hours"


def test_rearm_hysteresis_when_enabled() -> None:
    h = Harness()
    h.params = ParameterSet.model_validate({"bias": {"rearm_hysteresis": 0.1}})
    h.minute(10, 0, 0.7)
    s = h.engine.active["NIFTY"]
    h.engine.mark_traded(s.id, s.ts_fired + 1000)
    h.minute(10, 1, 0.7)  # same direction, has not dipped below 0.4
    assert h.reason() == "rearm"
    h.minute(10, 2, 0.3)  # dips below threshold - h
    h.minute(10, 3, 0.7)
    assert "NIFTY" in h.engine.active


def test_traded_signal_frees_index_next_minute() -> None:
    h = Harness()
    h.minute(10, 0, 0.7)
    s = h.engine.active["NIFTY"]
    assert h.engine.mark_traded(s.id, s.ts_fired + 5000) is not None
    assert h.events[-1].status == "traded"
    h.minute(10, 1, 0.7)
    assert h.engine.active["NIFTY"].id != s.id


def test_params_reload_mid_session_changes_targets() -> None:
    h = Harness()
    h.minute(10, 0, 0.7)
    first = h.engine.active["NIFTY"]
    h.params = ParameterSet.model_validate({"signal": {"target_pct": 50, "stop_pct": -10}})
    h.engine.mark_traded(first.id, first.ts_fired + 1)
    h.minute(10, 1, 0.7)
    second = h.engine.active["NIFTY"]
    assert (second.target_price, second.stop_price) == (225.0, 135.0)


def test_bs_delta_sanity() -> None:
    assert 0.45 < bs_delta(25_000, 25_000, 5 / 365, 14, 0.065, call=True) < 0.6
    assert -0.6 < bs_delta(25_000, 25_000, 5 / 365, 14, 0.065, call=False) < -0.4
    assert bs_delta(25_100, 25_000, 0, 14, 0.065, call=True) == 1.0
    assert bs_delta(24_900, 25_000, 0, 14, 0.065, call=True) == 0.0


def test_signal_records_the_ask_and_spread_at_firing() -> None:
    h = Harness()
    row = h.chain.rows[h.chain.atm]
    h.chain.apply(Tick(key=row.ce.key, ts=2, ltp=150.0, bid=149.0, ask=152.0))

    h.minute(10, 0, 0.62)

    s = h.engine.active["NIFTY"]
    assert s.entry_price == 150.0  # still the last traded price in this entry mode
    assert s.entry_ask == 152.0
    assert s.spread_pct == pytest.approx(3 / 150.5 * 100)
    stored = h.engine.store.get(s.id)
    assert stored is not None
    assert (stored.entry_ask, stored.spread_pct) == (s.entry_ask, s.spread_pct)


def test_signal_without_a_quote_has_no_ask_or_spread() -> None:
    h = Harness()

    h.minute(10, 0, 0.62)

    s = h.engine.active["NIFTY"]
    assert (s.entry_ask, s.spread_pct) == (None, None)


# -- trigger mode: setup at minute close, then order flow (spec §9.6) -----------------


def trig(*, feed_live: bool = True) -> Harness:
    h = Harness(entry_mode="trigger", feed_live=feed_live)
    h.quote(ce=(149.9, 150.1), pe=(139.9, 140.1))
    return h


def test_trigger_waits_for_order_flow_then_fires_at_the_ask() -> None:
    h = trig()
    h.minute(10, 0, 0.40)  # a setup: below the 0.50 that the minute-close rule needs
    assert "NIFTY" not in h.engine.active
    assert h.reason() == "flow_not_confirmed"

    h.flow(10, 0, 10, 0.30)  # agrees, but has not held yet
    assert "NIFTY" not in h.engine.active
    h.flow(10, 0, 14, 0.32)
    assert "NIFTY" not in h.engine.active
    h.flow(10, 0, 15, 0.31)  # five seconds of agreement

    s = h.engine.active["NIFTY"]
    assert s.direction == "BUY_CE"
    assert s.ts_fired == at(TODAY, 10, 0) + 15_000
    assert s.minute_ts == at(TODAY, 10, 0) - M  # the minute whose bias set it up
    assert (s.entry_price, s.entry_ask) == (150.1, 150.1)
    assert s.target_price == round(150.1 * 1.30, 2)
    assert (s.entry_mode, s.shadow, s.flow_score) == ("trigger", False, 0.31)
    assert s.bias == 0.40
    assert h.engine.gates["NIFTY"].fired is True
    stored = h.engine.store.get(s.id)
    assert stored == s


def test_trigger_needs_a_setup() -> None:
    h = trig()
    h.minute(10, 0, 0.30)  # under the setup threshold
    assert h.reason() == "no_setup"

    h.flow(10, 0, 10, 0.9)
    h.flow(10, 0, 20, 0.9)

    assert "NIFTY" not in h.engine.active
    assert h.reason() == "no_setup"


def test_trigger_setup_ends_when_the_bias_fades() -> None:
    h = trig()
    h.minute(10, 0, 0.40)
    h.minute(10, 1, 0.25)

    h.flow(10, 1, 10, 0.9)
    h.flow(10, 1, 20, 0.9)

    assert "NIFTY" not in h.engine.active


@pytest.mark.parametrize("score", [0.2, -0.6, None])
def test_trigger_does_not_fire_on_weak_opposite_or_unknown_flow(score: float | None) -> None:
    h = trig()
    h.minute(10, 0, 0.40)

    h.flow(10, 0, 10, score)
    h.flow(10, 0, 20, score)

    assert "NIFTY" not in h.engine.active
    assert h.reason() == "flow_not_confirmed"


def test_trigger_hold_starts_again_if_the_flow_lets_go() -> None:
    h = trig()
    h.minute(10, 0, 0.40)

    h.flow(10, 0, 10, 0.3)
    h.flow(10, 0, 13, 0.1)  # lets go
    h.flow(10, 0, 14, 0.3)
    h.flow(10, 0, 16, 0.3)  # six seconds after the first, only two after the restart
    assert "NIFTY" not in h.engine.active

    h.flow(10, 0, 19, 0.3)
    assert "NIFTY" in h.engine.active


def test_trigger_bearish_setup_needs_selling_and_buys_the_put() -> None:
    h = trig()
    h.minute(10, 0, -0.45)

    h.flow(10, 0, 10, 0.5)
    h.flow(10, 0, 20, 0.5)
    assert "NIFTY" not in h.engine.active

    h.flow(10, 0, 21, -0.5)
    h.flow(10, 0, 26, -0.5)

    s = h.engine.active["NIFTY"]
    assert (s.direction, s.entry_price) == ("BUY_PE", 140.1)


def test_trigger_refuses_a_wide_or_missing_quote() -> None:
    h = trig()
    h.quote(ce=(148.0, 152.0), pe=(139.9, 140.1))  # 2.7 % wide against a 1 % limit
    h.minute(10, 0, 0.40)
    h.flow(10, 0, 10, 0.5)
    h.flow(10, 0, 20, 0.5)
    assert "NIFTY" not in h.engine.active
    assert h.reason() == "spread_wide"

    h.quote(ce=(149.9, 150.1), pe=(139.9, 140.1))
    h.flow(10, 0, 21, 0.5)  # the flow held all along; only the quote was in the way
    assert "NIFTY" in h.engine.active

    bare = Harness(entry_mode="trigger")  # no bid or ask seen at all
    bare.minute(10, 0, 0.40)
    bare.flow(10, 0, 10, 0.5)
    bare.flow(10, 0, 20, 0.5)
    assert bare.reason() == "spread_wide"


def test_trigger_respects_hours_and_the_feed() -> None:
    h = trig()
    h.minute(15, 0, 0.40)
    h.flow(15, 0, 10, 0.5)
    h.flow(15, 0, 20, 0.5)
    assert h.reason() == "outside_hours"

    down = trig(feed_live=False)
    down.minute(10, 0, 0.40)
    down.flow(10, 0, 10, 0.5)
    down.flow(10, 0, 20, 0.5)
    assert down.reason() == "feed_down"


def test_trigger_signal_lapses_reverses_and_blocks_a_second_one_as_before() -> None:
    h = trig()
    h.minute(10, 0, 0.40)
    h.flow(10, 0, 10, 0.5)
    h.flow(10, 0, 15, 0.5)
    first = h.engine.active["NIFTY"]

    h.flow(10, 0, 30, 0.5)
    assert h.engine.active["NIFTY"] is first
    h.minute(10, 1, 0.45)
    assert h.reason() == "active_exists"

    h.minute(10, 2, 0.1)  # into the neutral band
    assert h.events[-1].status == "reversed"
    assert h.reason() == "no_setup"


def test_minute_close_mode_ignores_order_flow() -> None:
    h = Harness()
    h.quote(ce=(149.9, 150.1), pe=(139.9, 140.1))
    h.minute(10, 0, 0.40)

    h.flow(10, 0, 10, 0.9)
    h.flow(10, 0, 20, 0.9)

    assert "NIFTY" not in h.engine.active
    assert h.reason() == "below_threshold"
    h.minute(10, 1, 0.6)
    s = h.engine.active["NIFTY"]
    assert (s.entry_mode, s.shadow, s.flow_score) == ("minute_close", False, None)


def test_shadow_engine_runs_the_rule_that_is_not_live_and_marks_its_signals() -> None:
    h = Harness(shadow=True)  # live rule is minute_close, so the shadow runs the trigger
    h.quote(ce=(149.9, 150.1), pe=(139.9, 140.1))
    h.minute(10, 0, 0.40)
    h.flow(10, 0, 10, 0.5)
    h.flow(10, 0, 15, 0.5)

    s = h.engine.active["NIFTY"]
    assert (s.entry_mode, s.shadow) == ("trigger", True)

    other = Harness(shadow=True, entry_mode="trigger")
    other.minute(10, 0, 0.6)
    s2 = other.engine.active["NIFTY"]
    assert (s2.entry_mode, s2.shadow) == ("minute_close", True)

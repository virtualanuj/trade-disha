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
        self, day: date = TODAY, *, feed_live: bool = True, enforce_hours: bool = True
    ) -> None:
        master = build_synthetic_master(TODAY)
        self.r = resolve_index(master, "NIFTY", day, 25_000.0, strike_window=3)
        self.chain = ChainState.from_resolved(self.r)
        self.params = ParameterSet()
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
        )
        self.price_atm(ce=150.0, pe=140.0)

    def price_atm(self, *, ce: float, pe: float, iv: float = 14.0) -> None:
        row = self.chain.rows[self.chain.atm]
        self.chain.set_spot(self.chain.atm)
        self.chain.apply(Tick(key=row.ce.key, ts=1, ltp=ce, oi=1000, iv=iv))
        self.chain.apply(Tick(key=row.pe.key, ts=1, ltp=pe, oi=1000, iv=iv))

    def minute(self, h: int, m: int, bias: float, day: date = TODAY) -> None:
        self.engine.on_bias(_bias("NIFTY", at(day, h, m) - M, bias))

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

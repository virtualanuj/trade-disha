"""Bullion signals and paper trades (Milestone E6): MCX GOLD/SILVER futures, long or short."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from tradedisha.app_state import AppState
from tradedisha.clock import IST, MarketClock, epoch_ms_now, ist_to_ms, ms_to_ist
from tradedisha.config import Settings
from tradedisha.engine.aggregator import BULLION_IDLE, Bias, Label, aggregate, bullion_weights
from tradedisha.engine.bias_engine import BiasComputed, OverlayPoint
from tradedisha.engine.bullion_bias import BullionBiasEngine
from tradedisha.engine.bullion_desk import BullionDesk
from tradedisha.engine.bullion_signals import BullionSignalEngine
from tradedisha.engine.paper import (
    PaperError,
    PaperTrade,
    PaperTradeManager,
    Price,
    bullion_rules,
    journal_stats,
)
from tradedisha.engine.signals import Signal
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.indicators import IndicatorResult
from tradedisha.instruments.models import Instrument
from tradedisha.main import create_app
from tradedisha.market.bullion import BullionContract, BullionTracker
from tradedisha.market.candles import Candle
from tradedisha.market.us_events import UsEvent
from tradedisha.parameters import ParameterService
from tradedisha.parameters.model import Bullion, ParameterSet
from tradedisha.parameters.schema import describe
from tradedisha.store.db import connect

# -- parameters ----------------------------------------------------------------------------


def test_bullion_parameters_have_mcx_session_defaults() -> None:
    b = ParameterSet().bullion
    assert b.signals == "on"
    assert (b.first_signal_time, b.last_signal_time, b.square_off_time) == (
        time(9, 15),
        time(22, 45),
        time(23, 0),
    )
    assert b.eval_offset_seconds == 20
    assert b.target_pct > b.stop_pct > 0


def test_a_stored_version_without_bullion_still_loads() -> None:
    stored = ParameterSet().model_dump(mode="json")
    del stored["bullion"]
    assert ParameterSet.model_validate(stored).bullion == Bullion()


@pytest.mark.parametrize(
    "change",
    [
        {"neutral_band": 0.7, "entry_threshold": 0.6},
        {"last_signal_time": "23:10"},  # after the square-off
        {"first_signal_time": "23:00", "last_signal_time": "22:45"},
        {"eval_offset_seconds": 55},
    ],
)
def test_bullion_parameters_reject_inconsistent_values(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Bullion.model_validate({**Bullion().model_dump(mode="json"), **change})


def test_bullion_fields_reach_the_editor() -> None:
    specs = {s.path: s for s in describe(ParameterSet())}
    assert specs["bullion.signals"].kind == "choice"
    assert specs["bullion.square_off_time"].kind == "time"
    assert specs["bullion.eval_offset_seconds"].kind == "integer"
    assert all(s.help for s in specs.values() if s.group == "bullion")


# -- aggregator ----------------------------------------------------------------------------


def _trend(score: float, name: str = "ema_cross") -> IndicatorResult:
    return IndicatorResult(name, "trend", score, "")


def test_trend_only_weights_let_a_full_trend_reach_the_ends() -> None:
    p = ParameterSet()
    results = [_trend(1.0), _trend(1.0, "vwap_position"), _trend(1.0, "supertrend")]
    assert aggregate(results, p, is_expiry_day=False).bias == pytest.approx(0.4)  # index weights
    b = aggregate(
        results,
        p,
        is_expiry_day=False,
        weights=bullion_weights(p),
        neutral_band=0.15,
        idle_groups=BULLION_IDLE,
    )
    assert b.bias == pytest.approx(1.0)  # no OI, flow or macro reading: trend carries it all
    assert b.label == "Bullish"
    assert b.group_weights == pytest.approx(
        {"trend": 1.0, "oi": 0.0, "premium": 0.0, "flow": 0.0, "macro": 0.0}
    )


def test_bullion_weights_share_the_bias_out() -> None:
    p = ParameterSet()
    assert bullion_weights(p) == pytest.approx(
        {"trend": 0.60, "oi": 0.15, "premium": 0.0, "flow": 0.15, "macro": 0.10}
    )


def test_a_warming_group_gives_its_share_to_the_live_ones() -> None:
    p = ParameterSet()
    results = [
        _trend(1.0),
        IndicatorResult("futures_oi", "oi", -1.0, ""),
        IndicatorResult("net_volume", "flow", 0.0, "", "warming"),
        IndicatorResult("dollar_index", "macro", 0.0, "", "warming"),
    ]
    b = aggregate(
        results, p, is_expiry_day=False, weights=bullion_weights(p), idle_groups=BULLION_IDLE
    )
    # flow's 0.15 and macro's 0.10 go to trend and OI in proportion (0.60 : 0.15)
    assert b.group_weights == pytest.approx(
        {"trend": 0.80, "oi": 0.20, "premium": 0.0, "flow": 0.0, "macro": 0.0}
    )
    assert b.bias == pytest.approx(0.80 - 0.20)


def test_bullion_weights_must_leave_trend_a_share() -> None:
    with pytest.raises(ValidationError, match="leave trend a share"):
        Bullion(oi_weight=0.5, flow_weight=0.4, macro_weight=0.1)


def test_the_neutral_band_override_sets_the_label() -> None:
    b = aggregate(
        [_trend(0.3)],
        ParameterSet(),
        is_expiry_day=False,
        weights=bullion_weights(ParameterSet()),
        neutral_band=0.35,
    )
    assert b.label == "Neutral"


@given(st.lists(st.floats(-1, 1), min_size=0, max_size=3))
def test_trend_only_bias_stays_in_bounds(scores: list[float]) -> None:
    b = aggregate(
        [_trend(s) for s in scores],
        ParameterSet(),
        is_expiry_day=False,
        weights=bullion_weights(ParameterSet()),
        neutral_band=0.2,
    )
    assert -1.0 <= b.bias <= 1.0
    assert 0 <= b.strength <= 100


# -- fixtures ----------------------------------------------------------------------------------

DAY = date(2026, 11, 16)  # a Monday
M = 60_000
GOLD_KEY = "MCX_FO|495213"
SILVER_KEY = "MCX_FO|495214"


def at(h: int, m: int, s: int = 0, day: date = DAY) -> int:
    return ist_to_ms(datetime(day.year, day.month, day.day, h, m, s, tzinfo=IST))


def _fut(metal: str, key: str, multiplier: float) -> Instrument:
    return Instrument(
        instrument_key=key,
        trading_symbol=f"{metal} FUT 04 DEC 26",
        exchange="MCX",
        segment="MCX_FO",
        name=metal,
        instrument_type="FUT",
        expiry=date(2026, 12, 4),
        strike=None,
        lot_size=1 if metal == "GOLD" else 30,
        tick_size=1.0,
        qty_multiplier=multiplier,
    )


def _tracker() -> BullionTracker:
    return BullionTracker(
        {
            "GOLD": BullionContract("GOLD", _fut("GOLD", GOLD_KEY, 100.0), None),
            "SILVER": BullionContract("SILVER", _fut("SILVER", SILVER_KEY, 30.0), None),
        }
    )


def _rising(key: str, start_ms: int, n: int, *, step: float = 20.0) -> list[Candle]:
    """n closed minutes from `start_ms`, climbing steadily, with volume."""
    out = []
    for i in range(n):
        px = 135_000.0 + i * step
        out.append(Candle(key, start_ms + i * M, px - 5, px + 10, px - 10, px, volume=100))
    return out


# -- bias engine and its offset -------------------------------------------------------------


class BiasHarness:
    def __init__(self, tmp_path: Path, offset: int = 20) -> None:
        self.conn = connect(tmp_path / "b.sqlite")
        p = ParameterSet()
        self.params = p.model_copy(
            update={"bullion": p.bullion.model_copy(update={"eval_offset_seconds": offset})}
        )
        self.tracker = _tracker()
        self.out: list[BiasComputed] = []
        self.engine = BullionBiasEngine(
            tracker=self.tracker,
            params=lambda: self.params,
            conn=self.conn,
            on_bias=self.out.append,
        )

    def seed(self, metal: str, key: str, n: int = 40, step: float = 20.0) -> int:
        candles = _rising(key, at(19, 0), n, step=step)
        self.tracker.seed(metal, candles)
        return candles[-1].minute_ts


def test_bullion_bias_adds_the_dollar_when_there_is_a_reading(tmp_path: Path) -> None:
    h = BiasHarness(tmp_path, offset=0)
    h.engine = BullionBiasEngine(
        tracker=h.tracker,
        params=lambda: h.params,
        conn=h.conn,
        macro=lambda _m: [IndicatorResult("dollar_index", "macro", -1.0, "Dollar +0.20%")],
    )
    b = h.engine.evaluate("GOLD", h.seed("GOLD", GOLD_KEY)).bias
    # OI and flow warming: their 0.30 goes to trend and macro in proportion (0.60 : 0.10)
    assert b.group_weights["macro"] == pytest.approx(0.10 / 0.70)
    assert b.group_weights["trend"] == pytest.approx(0.60 / 0.70)
    weighted = [c.result.name for c in b.contributions if c.weight > 0]
    assert weighted[-1] == "dollar_index"


def test_backfilled_bullion_bias_is_trend_only_and_stored_per_metal(tmp_path: Path) -> None:
    h = BiasHarness(tmp_path, offset=0)
    last = h.seed("GOLD", GOLD_KEY)  # backfilled candles: no OI, book or trade sides
    b = h.engine.evaluate("GOLD", last)
    assert b.index == "GOLD"
    assert [(c.result.name, c.result.quality) for c in b.bias.contributions] == [
        ("ema_cross", "ok"),
        ("vwap_position", "ok"),
        ("supertrend", "ok"),
        ("futures_oi", "warming"),
        ("net_volume", "warming"),
        ("book_imbalance", "warming"),
        ("peer_metal", "warming"),  # no SILVER candles
    ]
    assert b.bias.bias > 0.6  # a steady climb: every trend vote is bullish
    assert b.bias.group_weights == pytest.approx(
        {"trend": 1.0, "oi": 0.0, "premium": 0.0, "flow": 0.0, "macro": 0.0}
    )
    rows = h.conn.execute("SELECT idx, minute_ts FROM bias_minutes").fetchall()
    assert [(r["idx"], r["minute_ts"]) for r in rows] == [("GOLD", last)]


def _live_minutes(h: BiasHarness, key: str, n: int, *, base: float, ease_at: int) -> None:
    """n minutes of ticks: price and OI climbing, every trade at the ask, a book leaning to
    the sell side until minute `ease_at`, when it turns to the buy side."""
    for i in range(n):
        t, px = at(19, 0) + i * M, base + i * 20
        tbq, tsq = (6000, 4000) if i == ease_at else (4000, 6000)
        quoted = Tick(
            key,
            t + 1000,
            px,
            volume=20 * i,
            oi=10_000 + 20 * i,
            bid=px - 1,
            ask=px + 1,
            tbq=tbq,
            tsq=tsq,
        )
        h.tracker.on_tick(StampedTick(quoted, t))
        h.tracker.on_tick(StampedTick(Tick(key, t + 30_000, px + 1, volume=20 * i + 10), t))


def test_live_bullion_bias_reads_positioning_flow_and_the_other_metal(tmp_path: Path) -> None:
    h = BiasHarness(tmp_path, offset=0)
    _live_minutes(h, GOLD_KEY, 40, base=135_000.0, ease_at=38)
    _live_minutes(h, SILVER_KEY, 40, base=170_000.0, ease_at=38)
    b = h.engine.evaluate("GOLD", at(19, 38)).bias  # minute 39 is still open
    by = {c.result.name: c for c in b.contributions}
    assert list(by) == [
        "ema_cross", "vwap_position", "supertrend", "futures_oi",
        "net_volume", "book_imbalance", "peer_metal",
    ]  # fmt: skip
    assert {c.result.quality for c in b.contributions} == {"ok"}
    assert b.group_weights == pytest.approx(bullion_weights(h.params))  # every group live
    assert by["futures_oi"].result.note.startswith("long build-up")
    assert by["futures_oi"].result.score == pytest.approx(1.0)
    assert by["net_volume"].result.score == pytest.approx(1.0)  # every trade at the ask
    assert by["book_imbalance"].result.score == pytest.approx(1.0)  # the lean turned
    assert by["peer_metal"].result.note.startswith("SILVER trend +")
    assert b.bias > 0.8


def test_bullion_bias_warms_up_on_few_candles(tmp_path: Path) -> None:
    h = BiasHarness(tmp_path, offset=0)
    last = h.seed("SILVER", SILVER_KEY, n=3)
    b = h.engine.evaluate("SILVER", last)
    assert {c.result.quality for c in b.bias.contributions} >= {"warming"}
    assert abs(b.bias.bias) < 0.6


def test_a_candle_close_is_evaluated_only_after_the_offset(tmp_path: Path) -> None:
    h = BiasHarness(tmp_path, offset=20)
    last = h.seed("GOLD", GOLD_KEY)
    close = last + M  # the instant that minute closed
    h.engine.queue("GOLD", last)

    assert h.engine.run_due(close + 500) == []
    assert h.engine.run_due(close + 19_999) == []
    done = h.engine.run_due(close + 20_000)
    assert [(b.index, b.minute_ts) for b in done] == [("GOLD", last)]
    assert h.out == done
    assert h.engine.run_due(close + 25_000) == []  # each minute is evaluated once


def test_offset_zero_runs_on_the_next_pass_and_a_change_applies_next_minute(
    tmp_path: Path,
) -> None:
    h = BiasHarness(tmp_path, offset=0)
    last = h.seed("GOLD", GOLD_KEY)
    h.engine.queue("GOLD", last)
    assert len(h.engine.run_due(last + M)) == 1

    h.engine.queue("SILVER", last)  # queued under offset 0 ...
    h.params = h.params.model_copy(
        update={"bullion": h.params.bullion.model_copy(update={"eval_offset_seconds": 30})}
    )
    assert len(h.engine.run_due(last + M)) == 1  # ... so it keeps that due time
    h.engine.queue("GOLD", last + M)  # the next minute takes the new offset
    assert h.engine.run_due(last + 2 * M + 29_000) == []
    assert len(h.engine.run_due(last + 2 * M + 30_000)) == 1


def test_bullion_candle_closes_reach_the_queue(tmp_path: Path) -> None:
    h = BiasHarness(tmp_path, offset=0)
    h.engine.attach()  # listens to the tracker's own candle builder
    t0 = at(20, 0)
    h.tracker.on_tick(StampedTick(Tick(key=GOLD_KEY, ts=t0, ltp=135_000.0, volume=1), t0))
    h.tracker.on_tick(StampedTick(Tick(key=GOLD_KEY, ts=t0 + M, ltp=135_010.0, volume=2), t0))
    assert [(b.index, b.minute_ts) for b in h.engine.run_due(t0 + M)] == [("GOLD", t0)]


# -- signals -----------------------------------------------------------------------------------


def _b(metal: str, minute_ts: int, value: float) -> BiasComputed:
    label: Label = "Bullish" if value >= 0.2 else "Bearish" if value <= -0.2 else "Neutral"
    b = Bias(value, label, round(abs(value) * 100), {}, {}, [], False)
    return BiasComputed(metal, minute_ts, b, OverlayPoint(minute_ts, None, None, None, None, 0))


class SignalHarness:
    def __init__(
        self,
        tmp_path: Path,
        *,
        now: int,
        holidays: frozenset[date] = frozenset(),
        events: tuple[UsEvent, ...] = (),
    ) -> None:
        self.now = now
        self.live = True
        self.conn = connect(tmp_path / "s.sqlite")
        ParameterService(self.conn, Settings(_env_file=None).params_path).load()  # version 1
        self.params = ParameterSet()
        self.mcx = MarketClock(
            market_open=time(9, 0),
            market_close=time(23, 30),
            pre_open_start=time(9, 0),
            holidays=holidays,
            source=lambda: ms_to_ist(self.now),
        )
        self.tracker = _tracker()
        self.fired: list[Signal] = []
        self.engine = BullionSignalEngine(
            tracker=self.tracker,
            clock=self.mcx,
            params=lambda: self.params,
            conn=self.conn,
            feed_live=lambda: self.live,
            enforce_hours=True,
            on_signal=self.fired.append,
            config_version=lambda: 1,
            events=events,
        )

    def bullion(self, **update: object) -> None:
        self.params = self.params.model_copy(
            update={"bullion": self.params.bullion.model_copy(update=update)}
        )

    def price(self, key: str, ltp: float) -> None:
        self.tracker.on_tick(StampedTick(Tick(key=key, ts=self.now, ltp=ltp), self.now))

    def evaluate(self, metal: str, value: float, *, minute_ts: int | None = None) -> None:
        minute = minute_ts if minute_ts is not None else self.now - M - 20_000
        self.engine.on_bias(_b(metal, minute, value), self.now)


def test_a_bullish_gold_bias_fires_a_long_future(tmp_path: Path) -> None:
    h = SignalHarness(tmp_path, now=at(20, 1, 20))
    h.price(GOLD_KEY, 135_000.0)
    h.evaluate("GOLD", 0.7, minute_ts=at(20, 0))

    s = h.engine.active["GOLD"]
    assert (s.direction, s.instrument_key, s.trading_symbol) == (
        "BUY_FUT",
        GOLD_KEY,
        "GOLD FUT 04 DEC 26",
    )
    assert (s.minute_ts, s.ts_fired) == (at(20, 0), at(20, 1, 20))  # fired at evaluation time
    assert s.entry_price == 135_000.0
    assert (s.target_price, s.stop_price) == (135_540.0, 134_730.0)  # +0.40 %, -0.20 %
    assert (s.strike, s.expiry, s.lot_size) == (0.0, "2026-12-04", 100)  # ₹ per point per lot
    assert s.expires_at == at(20, 1, 20) + 300_000
    assert s.config_version == 1
    assert h.engine.gates["GOLD"].fired
    assert h.fired == [s]


def test_a_bearish_silver_bias_fires_a_short_with_target_below(tmp_path: Path) -> None:
    h = SignalHarness(tmp_path, now=at(20, 1, 20))
    h.price(SILVER_KEY, 170_000.0)
    h.evaluate("SILVER", -0.65)

    s = h.engine.active["SILVER"]
    assert s.direction == "SELL_FUT"
    assert (s.target_price, s.stop_price) == (169_320.0, 170_340.0)
    assert s.lot_size == 30


@pytest.mark.parametrize(
    ("now", "value", "live", "signals", "reason"),
    [
        (at(20, 1, 20), 0.55, True, "on", "below_threshold"),
        (at(9, 10), 0.8, True, "on", "outside_hours"),  # MCX open, before 09:15
        (at(22, 45), 0.8, True, "on", "outside_hours"),  # the last-signal cut-off
        (at(23, 40), 0.8, True, "on", "outside_hours"),  # MCX closed
        (at(12, 0, day=date(2026, 11, 14)), 0.8, True, "on", "outside_hours"),  # Saturday
        (at(20, 1, 20), 0.8, False, "on", "feed_down"),  # bullion prices stale
        (at(20, 1, 20), 0.8, True, "off", "disabled"),
    ],
)
def test_bullion_gates(
    tmp_path: Path, now: int, value: float, live: bool, signals: str, reason: str
) -> None:
    h = SignalHarness(tmp_path, now=now)
    h.live = live
    h.params = h.params.model_copy(
        update={"bullion": h.params.bullion.model_copy(update={"signals": signals})}
    )
    h.price(GOLD_KEY, 135_000.0)
    h.evaluate("GOLD", value)
    assert "GOLD" not in h.engine.active
    assert h.engine.gates["GOLD"].reason == reason


def test_no_price_yet_means_no_signal(tmp_path: Path) -> None:
    h = SignalHarness(tmp_path, now=at(20, 1, 20))
    h.evaluate("GOLD", 0.8)
    assert h.engine.gates["GOLD"].reason == "no_price"


def test_one_active_signal_per_metal_then_lapse_and_reversal(tmp_path: Path) -> None:
    h = SignalHarness(tmp_path, now=at(20, 1, 20))
    h.price(GOLD_KEY, 135_000.0)
    h.price(SILVER_KEY, 170_000.0)
    h.evaluate("GOLD", 0.7)
    h.now += M
    h.evaluate("SILVER", 0.7)  # the other metal is independent
    h.evaluate("GOLD", 0.8)
    assert set(h.engine.active) == {"GOLD", "SILVER"}
    assert h.engine.gates["GOLD"].reason == "active_exists"

    h.now = h.engine.active["GOLD"].expires_at  # GOLD's TTL is up; SILVER's is not
    h.engine.tick(h.now)
    assert set(h.engine.active) == {"SILVER"}
    assert h.fired[-1].status == "lapsed"
    assert h.fired[-1].index == "GOLD"

    h.evaluate("SILVER", 0.1)  # inside the neutral band: reversed
    assert "SILVER" not in h.engine.active
    ended = h.fired[-1]
    assert (ended.index, ended.status) == ("SILVER", "reversed")


def test_rearm_needs_a_dip_before_the_same_side_fires_again(tmp_path: Path) -> None:
    h = SignalHarness(tmp_path, now=at(20, 1, 20))
    h.params = h.params.model_copy(
        update={"bullion": h.params.bullion.model_copy(update={"rearm_hysteresis": 0.2})}
    )
    h.price(GOLD_KEY, 135_000.0)
    h.evaluate("GOLD", 0.7)
    h.engine.mark_traded(h.engine.active["GOLD"].id, h.now)
    h.now += M
    h.evaluate("GOLD", 0.7)
    assert h.engine.gates["GOLD"].reason == "rearm"
    h.now += M
    h.evaluate("GOLD", 0.3)  # below 0.6 - 0.2
    h.now += M
    h.evaluate("GOLD", 0.7)
    assert h.engine.active["GOLD"].direction == "BUY_FUT"


# -- the US data-release pause (E18) -----------------------------------------------------------

CPI = UsEvent(at(20, 0), "CPI")  # the window is 19:45 to 20:15 at the default 15 / 15


def test_event_pause_parameters_default_to_signals_only() -> None:
    b = ParameterSet().bullion
    assert (b.event_pause_before_minutes, b.event_pause_after_minutes) == (15, 15)
    assert (b.event_end_waiting, b.event_block_trades) == ("off", "off")
    specs = {s.path: s for s in describe(ParameterSet())}
    assert specs["bullion.event_end_waiting"].kind == "choice"
    assert specs["bullion.event_pause_before_minutes"].kind == "integer"


def test_a_stored_version_without_the_event_fields_loads_with_the_defaults() -> None:
    stored = ParameterSet().model_dump(mode="json")
    for name in (
        "event_pause_before_minutes",
        "event_pause_after_minutes",
        "event_end_waiting",
        "event_block_trades",
    ):
        del stored["bullion"][name]
    assert ParameterSet.model_validate(stored).bullion == Bullion()


@pytest.mark.parametrize(
    ("now", "before", "after", "reason"),
    [
        (at(19, 44, 59), 15, 15, None),  # fires: the window opens at 19:45
        (at(19, 45), 15, 15, "event_pause"),
        (at(20, 14, 59), 15, 15, "event_pause"),
        (at(20, 15), 15, 15, None),  # the window has closed
        (at(20, 0), 0, 0, None),  # both zero: no pause
        (at(20, 5), 0, 30, "event_pause"),
    ],
)
def test_a_us_release_pauses_bullion_signals(
    tmp_path: Path, now: int, before: int, after: int, reason: str | None
) -> None:
    h = SignalHarness(tmp_path, now=now, events=(CPI,))
    h.bullion(event_pause_before_minutes=before, event_pause_after_minutes=after)
    h.price(GOLD_KEY, 135_000.0)
    h.evaluate("GOLD", 0.8)
    assert h.engine.gates["GOLD"].reason == reason
    assert ("GOLD" in h.engine.active) is (reason is None)


def test_the_event_pause_sits_between_hours_and_the_feed(tmp_path: Path) -> None:
    late = UsEvent(at(22, 50), "Late release")
    h = SignalHarness(tmp_path, now=at(22, 46), events=(late,))
    h.price(GOLD_KEY, 135_000.0)
    h.evaluate("GOLD", 0.8)
    assert h.engine.gates["GOLD"].reason == "outside_hours"  # past 22:45, pause or not

    h = SignalHarness(tmp_path, now=at(20, 1), events=(CPI,))
    h.live = False
    h.evaluate("GOLD", 0.8)
    assert h.engine.gates["GOLD"].reason == "event_pause"  # named before the stale feed


@pytest.mark.parametrize(("end_waiting", "kept"), [("off", True), ("on", False)])
def test_a_waiting_signal_ends_at_the_window_only_when_switched_on(
    tmp_path: Path, end_waiting: str, kept: bool
) -> None:
    h = SignalHarness(tmp_path, now=at(19, 42), events=(CPI,))
    h.bullion(event_end_waiting=end_waiting)
    h.price(GOLD_KEY, 135_000.0)
    h.price(SILVER_KEY, 170_000.0)
    h.evaluate("GOLD", 0.8)
    h.evaluate("SILVER", -0.8)
    h.now = at(19, 44, 59)
    h.engine.tick(h.now)
    assert set(h.engine.active) == {"GOLD", "SILVER"}  # not yet

    h.now = at(19, 45)
    h.engine.tick(h.now)
    assert ("GOLD" in h.engine.active) is kept
    assert ("SILVER" in h.engine.active) is kept
    if not kept:
        assert {(s.index, s.status, s.status_ts) for s in h.fired[-2:]} == {
            ("GOLD", "lapsed", at(19, 45)),
            ("SILVER", "lapsed", at(19, 45)),
        }


def test_an_evaluation_in_the_window_also_ends_a_waiting_signal(tmp_path: Path) -> None:
    h = SignalHarness(tmp_path, now=at(19, 42), events=(CPI,))
    h.bullion(event_end_waiting="on")
    h.price(GOLD_KEY, 135_000.0)
    h.evaluate("GOLD", 0.8)
    h.now = at(19, 45, 20)
    h.evaluate("GOLD", 0.8)
    assert "GOLD" not in h.engine.active
    assert h.fired[-1].status == "lapsed"
    assert h.engine.gates["GOLD"].reason == "event_pause"  # and nothing new fires


# -- paper trades ------------------------------------------------------------------------------


class PaperHarness(SignalHarness):
    def __init__(self, tmp_path: Path, *, now: int, events: tuple[UsEvent, ...] = ()) -> None:
        super().__init__(tmp_path, now=now, events=events)
        self.trades: list[PaperTrade] = []
        self.prices: dict[str, Price] = {}
        self.paper = self._manager()

    def _manager(self) -> PaperTradeManager:
        return PaperTradeManager(
            clock=self.mcx,
            params=lambda: self.params,
            conn=self.conn,
            signals=self.engine,
            price=self.prices.get,
            feed_live=lambda: self.live,
            enforce_hours=True,
            on_trade=self.trades.append,
            rules=bullion_rules(entry_block=self.engine.trade_block),
        )

    def quote(self, key: str, ltp: float) -> None:
        self.prices[key] = Price(ltp, self.now)
        self.price(key, ltp)

    def tick(self, key: str, ltp: float) -> None:
        self.prices[key] = Price(ltp, self.now)
        self.paper.on_tick(StampedTick(Tick(key=key, ts=self.now, ltp=ltp), self.now))

    def short_silver(self) -> PaperTrade:
        self.quote(SILVER_KEY, 170_000.0)
        self.evaluate("SILVER", -0.7)
        return self.paper.open(self.engine.active["SILVER"].id)


def test_a_short_future_profits_when_the_price_falls(tmp_path: Path) -> None:
    h = PaperHarness(tmp_path, now=at(20, 1, 20))
    t = h.short_silver()
    assert (t.direction, t.qty, t.lots) == ("SELL_FUT", 30, 1)  # ₹30 per point per lot
    assert t.pnl_at(169_900.0)[0] == 3_000.0
    assert t.pnl_at(170_100.0)[0] == -3_000.0

    h.now += 5_000
    h.tick(SILVER_KEY, 169_800.0)  # moving its way, short of the target
    assert t.id in h.paper.open_trades
    h.tick(SILVER_KEY, 169_320.0)  # the target is below the entry for a short
    closed = h.trades[-1]
    assert (closed.exit_reason, closed.exit_price, closed.gross) == ("TARGET", 169_320.0, 20_400.0)


def test_a_short_future_stops_out_above_entry(tmp_path: Path) -> None:
    h = PaperHarness(tmp_path, now=at(20, 1, 20))
    h.short_silver()
    h.now += 5_000
    h.tick(SILVER_KEY, 170_340.0)
    assert (h.trades[-1].exit_reason, h.trades[-1].gross) == ("STOP", -10_200.0)


def test_gold_point_value_and_a_cost_that_scales_with_value(tmp_path: Path) -> None:
    h = PaperHarness(tmp_path, now=at(20, 1, 20))
    h.quote(GOLD_KEY, 135_000.0)
    h.evaluate("GOLD", 0.7)
    t = h.paper.open(h.engine.active["GOLD"].id)
    assert t.qty == 100
    # ₹60 fixed + 0.012 % of the round trip (135,000 x 100 x 2 = ₹2.7 Cr) = 60 + 3,240
    assert t.cost == 3_300.0
    h.now += 5_000
    h.tick(GOLD_KEY, 135_540.0)
    assert (h.trades[-1].exit_reason, h.trades[-1].gross, h.trades[-1].net) == (
        "TARGET",
        54_000.0,
        50_700.0,
    )


def test_bullion_trades_square_off_at_23_00_on_mcx_time(tmp_path: Path) -> None:
    h = PaperHarness(tmp_path, now=at(22, 40))
    t = h.short_silver()
    h.now = at(22, 59, 59)
    h.paper.tick(h.now)
    assert t.id in h.paper.open_trades  # NSE has been closed for hours; MCX has not
    h.now = at(23, 0)
    h.paper.tick(h.now)
    assert h.trades[-1].exit_reason == "SQUARE_OFF"


def test_no_bullion_entry_after_the_bullion_square_off(tmp_path: Path) -> None:
    h = PaperHarness(tmp_path, now=at(22, 44))
    h.quote(GOLD_KEY, 135_000.0)
    h.evaluate("GOLD", 0.7)
    h.now = at(23, 0)
    with pytest.raises(PaperError, match="square-off"):
        h.paper.open(h.engine.active["GOLD"].id)


def test_each_manager_restores_only_its_own_trades(tmp_path: Path) -> None:
    h = PaperHarness(tmp_path, now=at(14, 0))
    gold = h.short_silver()  # a bullion trade, open, from 14:00
    nse_like = replace(gold, id="nse1", index="NIFTY", direction="BUY_CE", signal_id="x")
    h.paper.store.upsert(nse_like)

    assert set(h._manager().open_trades) == {gold.id}  # a restart of the bullion manager
    nse = PaperTradeManager(
        clock=h.mcx,
        params=lambda: h.params,
        conn=h.conn,
        signals=h.engine,
        price=h.prices.get,
        feed_live=lambda: True,
        enforce_hours=True,
    )
    assert set(nse.open_trades) == {"nse1"}


def test_an_opposing_bullion_bias_flags_the_trade(tmp_path: Path) -> None:
    h = PaperHarness(tmp_path, now=at(20, 1, 20))
    t = h.short_silver()
    h.paper.on_bias(_b("SILVER", at(20, 2), 0.5))
    assert h.paper.open_trades[t.id].warning == "bias_reversed"
    h.paper.on_bias(_b("GOLD", at(20, 2), -0.5))  # the other metal: no effect
    h.paper.on_bias(_b("SILVER", at(20, 3), -0.5))
    assert h.paper.open_trades[t.id].warning is None


@pytest.mark.parametrize("block", ["off", "on"])
def test_opening_a_trade_in_the_window_is_refused_only_when_switched_on(
    tmp_path: Path, block: str
) -> None:
    h = PaperHarness(tmp_path, now=at(19, 40), events=(CPI,))
    h.bullion(event_block_trades=block, signal_ttl_seconds=3600)  # it waits to 20:40
    h.quote(GOLD_KEY, 135_000.0)
    h.evaluate("GOLD", 0.7)
    signal_id = h.engine.active["GOLD"].id
    h.now = at(19, 50)
    if block == "on":
        with pytest.raises(PaperError, match="paused around US data: CPI 20:00"):
            h.paper.open(signal_id)
        h.now = at(20, 15)  # the window has closed
    assert h.paper.open(signal_id).index == "GOLD"


def test_an_open_trade_runs_to_its_target_inside_the_window(tmp_path: Path) -> None:
    h = PaperHarness(tmp_path, now=at(19, 40), events=(CPI,))
    h.bullion(event_end_waiting="on", event_block_trades="on")
    t = h.short_silver()
    h.now = at(20, 0)
    h.paper.tick(h.now)
    h.tick(SILVER_KEY, 169_320.0)
    closed = h.trades[-1]
    assert (closed.id, closed.exit_reason) == (t.id, "TARGET")


# -- journal -----------------------------------------------------------------------------------


def _closed(index: str, net: float) -> PaperTrade:
    base = PaperTrade(
        id=f"{index}{net}",
        signal_id="s",
        index=index,
        instrument_key="k",
        trading_symbol="t",
        direction="BUY_FUT" if index in {"GOLD", "SILVER"} else "BUY_CE",
        strike=0.0,
        expiry="2026-12-04",
        lots=1,
        qty=1,
        signal_entry=1.0,
        entry_price=1.0,
        entry_ts=0,
        slippage=0.0,
        target_price=2.0,
        stop_price=0.5,
        cost=0.0,
    )
    return replace(base, status="closed", exit_ts=60_000, gross=net, net=net, exit_reason="TARGET")


def test_journal_keeps_bullion_out_of_overall() -> None:
    trades = [_closed("NIFTY", 500.0), _closed("GOLD", 9_000.0), _closed("SILVER", -2_000.0)]
    stats = {s.scope: s for s in journal_stats(trades)}
    assert list(stats) == ["overall", "NIFTY", "bullion", "GOLD", "SILVER"]
    assert (stats["overall"].trades, stats["overall"].net_total) == (1, 500.0)
    assert (stats["bullion"].trades, stats["bullion"].net_total) == (2, 7_000.0)


# -- through the API ---------------------------------------------------------------------------


def _desk(client: TestClient) -> tuple[AppState, BullionDesk]:
    td: AppState = client.app.state.td  # type: ignore[attr-defined]
    td.session.bullion_live = lambda: True  # type: ignore[method-assign]
    td.session.attach_bullion(_tracker())
    desk = td.session.bullion_desk
    assert desk is not None
    return td, desk


def test_a_bullion_signal_is_traded_and_closed_through_the_api(client: TestClient) -> None:
    td, desk = _desk(client)
    now = epoch_ms_now()
    assert client.portal is not None
    tick = Tick(key=GOLD_KEY, ts=now, ltp=135_000.0)
    client.portal.call(td.session.tick_bus.publish, StampedTick(tick, now))
    desk.signals.on_bias(_b("GOLD", now - M, 0.8), now)  # synthetic feed: hours not enforced

    active = {s["index"]: s for s in client.get("/api/signals/active").json()}
    assert active["GOLD"]["direction"] == "BUY_FUT"
    gates = {g["index"]: g for g in client.get("/api/signals/gates").json()}
    assert gates["GOLD"]["fired"] is True

    r = client.post("/api/paper-trades", json={"signal_id": active["GOLD"]["id"]})
    assert r.status_code == 201, r.text
    trade = r.json()
    assert (trade["direction"], trade["qty"], trade["index"]) == ("BUY_FUT", 100, "GOLD")
    assert trade["id"] in desk.paper.open_trades
    assert td.session.paper is not None
    assert trade["id"] not in td.session.paper.open_trades

    closed = client.post(f"/api/paper-trades/{trade['id']}/close")
    assert closed.status_code == 200, closed.text
    assert closed.json()["exit_reason"] == "MANUAL"

    scopes = [s["scope"] for s in client.get("/api/journal/stats").json()["stats"]]
    assert scopes[0] == "overall"
    assert scopes[-2:] == ["bullion", "GOLD"]
    assert all(r["index"] != "GOLD" for r in client.get("/api/signals/scorecard").json())


def test_bullion_ticks_and_candles_are_recorded_apart_from_nse(client: TestClient) -> None:
    td, _ = _desk(client)
    assert client.portal is not None
    t0 = epoch_ms_now() - epoch_ms_now() % M - 2 * M
    for ts, ltp in ((t0, 135_000.0), (t0 + M, 135_010.0)):  # the second closes a minute
        tick = Tick(key=GOLD_KEY, ts=ts, ltp=ltp, volume=1, day_open=134_000.0)
        client.portal.call(td.session.tick_bus.publish, StampedTick(tick, ts))
    client.portal.call(td.session.bullion_tick_store.flush)
    client.portal.call(td.session.tick_store.flush)

    recorded = td.session.bullion_tick_store.read_day(td.clock.today(), [GOLD_KEY])
    assert [(t.ltp, t.day_open) for t in recorded] == [
        (135_000.0, 134_000.0),
        (135_010.0, 134_000.0),
    ]
    assert td.session.tick_store.read_day(td.clock.today(), [GOLD_KEY]) == []
    stored = td.session.candle_store.read(GOLD_KEY, t0, t0 + M)
    assert [c.close for c in stored] == [135_000.0]

    before = client.get("/api/data/usage").json()["tick_rows"]
    assert before >= 2  # the Data panel counts bullion ticks too


def test_hello_carries_bullion_bias_and_signals(client: TestClient) -> None:
    td, desk = _desk(client)
    now = epoch_ms_now()
    assert client.portal is not None
    tick = Tick(key=GOLD_KEY, ts=now, ltp=135_000.0)
    client.portal.call(td.session.tick_bus.publish, StampedTick(tick, now))
    desk.signals.on_bias(_b("GOLD", now - M, 0.8), now)
    desk.bias.latest["GOLD"] = _b("GOLD", now - M, 0.8)

    with client.websocket_connect("/ws") as ws:
        hello = json.loads(ws.receive_text())["payload"]
    assert "GOLD" in {b["index"] for b in hello["bias"]}
    assert "GOLD" in {s["index"] for s in hello["signals_active"]}
    assert "GOLD" in {g["index"] for g in hello["gates"]}


def test_index_engines_ignore_bullion_bias(client: TestClient) -> None:
    td, desk = _desk(client)
    now = epoch_ms_now()
    tick = Tick(key=GOLD_KEY, ts=now, ltp=135_000.0)
    assert client.portal is not None
    client.portal.call(td.session.tick_bus.publish, StampedTick(tick, now))
    desk._on_bias(_b("GOLD", now - M, 0.9))  # reaches every bias listener, as live

    for engine in (td.session.signals, td.session.shadow_signals):
        assert engine is not None
        assert "GOLD" not in engine.gates
        assert "GOLD" not in engine.active
    gates = [g["index"] for g in client.get("/api/signals/gates").json()]
    assert gates.count("GOLD") == 1


def _events_client(settings: Settings, tmp_path: Path, text: str) -> TestClient:
    f = tmp_path / "us-events.txt"
    f.write_text(text)
    return TestClient(create_app(settings.model_copy(update={"us_events_file": f})))


def test_the_session_reads_the_us_events_file(settings: Settings, tmp_path: Path) -> None:
    now = epoch_ms_now()
    release = ms_to_ist(now).strftime("%Y-%m-%d %H:%M")
    with _events_client(settings, tmp_path, f"{release}  CPI\n") as client:
        td, desk = _desk(client)
        assert [e.label for e in td.session.us_events] == ["CPI"]
        assert client.portal is not None
        tick = Tick(key=GOLD_KEY, ts=now, ltp=135_000.0)
        client.portal.call(td.session.tick_bus.publish, StampedTick(tick, now))
        desk.signals.on_bias(_b("GOLD", now - M, 0.8), now)
        assert desk.signals.gates["GOLD"].reason == "event_pause"


def test_a_bad_us_events_file_leaves_bullion_running_without_a_pause(
    settings: Settings, tmp_path: Path
) -> None:
    with _events_client(settings, tmp_path, "tomorrow at seven: CPI\n") as client:
        td, desk = _desk(client)
        assert td.session.us_events == ()
        now = epoch_ms_now()
        assert client.portal is not None
        tick = Tick(key=GOLD_KEY, ts=now, ltp=135_000.0)
        client.portal.call(td.session.tick_bus.publish, StampedTick(tick, now))
        desk.signals.on_bias(_b("GOLD", now - M, 0.8), now)
        assert desk.signals.gates["GOLD"].fired

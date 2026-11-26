"""Live signal levels: while a signal waits, its entry, target and stop follow the price.

The fired levels stay on the signal (history, scoring). The live ones keep the rule the
signal fired under: percentage signals keep their target/entry and stop/entry ratios;
expiry-day signals re-apply their index points through the option's current delta. A paper
trade takes the live levels at its fill price.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_bullion_trading import (
    GOLD_KEY,
    SILVER_KEY,
    PaperHarness,
    SignalHarness,
    _b,
    _desk,
    at,
)
from tests.test_signals import EXPIRY, Harness
from tradedisha.clock import epoch_ms_now
from tradedisha.engine.paper import PaperTradeManager, Price
from tradedisha.engine.signals import rescale_levels, round_rupee
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick


def test_a_pct_signal_keeps_its_ratios_at_a_new_price() -> None:
    h = Harness()
    h.minute(10, 0, 0.62)
    s = h.engine.active["NIFTY"]  # 150 / 195 / 128: +30 %, -15 % in whole rupees
    assert rescale_levels(s, 160.0, None) == (208.0, 137.0)  # 160 x 128 / 150 = 136.53
    assert rescale_levels(s, 150.0, None) == (s.target_price, s.stop_price)


def test_a_stop_never_falls_below_five_paise() -> None:
    h = Harness()
    h.minute(10, 0, 0.62)
    assert rescale_levels(h.engine.active["NIFTY"], 0.04, None)[1] == 0.05


def test_an_expiry_day_signal_reapplies_its_points_through_live_delta() -> None:
    h = Harness(day=EXPIRY)
    h.minute(10, 0, 0.7, day=EXPIRY)
    s = h.engine.active["NIFTY"]
    assert rescale_levels(s, 170.0, 0.6) == (round(170 + 0.6 * 40, 2), round(170 - 0.6 * 20, 2))
    assert rescale_levels(s, 170.0, -0.6) == rescale_levels(s, 170.0, 0.6)  # a put's delta


def test_the_index_engine_reads_live_levels_from_the_chain() -> None:
    h = Harness()
    h.minute(10, 0, 0.62)
    s = h.engine.active["NIFTY"]
    row = h.chain.rows[h.chain.atm]
    h.chain.apply(Tick(key=row.ce.key, ts=5, ltp=160.0))

    live = h.engine.live(s)
    assert live is not None
    assert (live.ltp, live.target, live.stop) == (160.0, 208.0, 137.0)
    assert h.engine.levels_at(s, 140.0) == (182.0, 119.0)


def test_an_expiry_day_live_level_uses_the_chain_delta_when_upstox_sends_one() -> None:
    h = Harness(day=EXPIRY)
    h.minute(10, 0, 0.7, day=EXPIRY)
    s = h.engine.active["NIFTY"]
    row = h.chain.rows[h.chain.atm]
    h.chain.apply(Tick(key=row.ce.key, ts=5, ltp=170.0, delta=0.62))
    live = h.engine.live(s)
    assert live is not None
    assert (live.target, live.stop) == (round_rupee(170 + 0.62 * 40), round_rupee(170 - 0.62 * 20))


def test_no_live_levels_without_a_price() -> None:
    h = Harness()
    h.minute(10, 0, 0.62)
    s = h.engine.active["NIFTY"]
    assert h.engine.live(replace(s, strike=99_999.0)) is None  # no such row in the chain


def test_a_bullion_short_follows_the_future(tmp_path: Path) -> None:
    h = SignalHarness(tmp_path, now=at(20, 1, 20))
    h.price(SILVER_KEY, 170_000.0)
    h.evaluate("SILVER", -0.7)
    s = h.engine.active["SILVER"]  # 170,000 / 169,320 / 170,340
    h.price(SILVER_KEY, 169_000.0)
    live = h.engine.live(s)
    assert live is not None
    assert (live.ltp, live.target, live.stop) == (169_000.0, 168_324.0, 169_338.0)


def test_a_paper_trade_takes_the_live_levels_at_its_fill() -> None:
    h = Harness()
    h.minute(10, 0, 0.62)
    s = h.engine.active["NIFTY"]
    prices = {s.instrument_key: Price(160.0, 5)}
    paper = PaperTradeManager(
        clock=h.clock,
        params=lambda: h.params,
        conn=h.conn,
        signals=h.engine,
        price=prices.get,
        feed_live=lambda: True,
        enforce_hours=False,
    )
    t = paper.open(s.id)
    assert (t.entry_price, t.target_price, t.stop_price) == (160.0, 208.0, 137.0)
    assert t.signal_entry == 150.0  # the fired entry is kept for slippage
    assert t.slippage == pytest.approx(10.0)


def test_a_bullion_paper_trade_takes_the_live_levels_at_its_fill(tmp_path: Path) -> None:
    h = PaperHarness(tmp_path, now=at(20, 1, 20))
    h.quote(GOLD_KEY, 135_000.0)
    h.evaluate("GOLD", 0.7)
    h.quote(GOLD_KEY, 136_000.0)
    t = h.paper.open(h.engine.active["GOLD"].id)
    assert (t.entry_price, t.target_price, t.stop_price) == (136_000.0, 136_544.0, 135_728.0)


# -- to the browser ----------------------------------------------------------------------------


def test_active_signals_carry_live_levels_and_are_pushed_each_second(client: TestClient) -> None:
    td, desk = _desk(client)
    now = epoch_ms_now()
    assert client.portal is not None
    for ltp in (135_000.0, 136_000.0):  # fires at 135,000; the price moves on
        tick = Tick(key=GOLD_KEY, ts=now, ltp=ltp)
        client.portal.call(td.session.tick_bus.publish, StampedTick(tick, now))
        if ltp == 135_000.0:
            desk.signals.on_bias(_b("GOLD", now - 60_000, 0.8), now)

    (gold,) = [s for s in client.get("/api/signals/active").json() if s["index"] == "GOLD"]
    assert (gold["entry_price"], gold["target_price"]) == (135_000.0, 135_540.0)  # as fired
    assert gold["live"] == {"ltp": 136_000.0, "target": 136_544.0, "stop": 135_728.0}

    with client.websocket_connect("/ws") as ws:
        for _ in range(400):
            frame = json.loads(ws.receive_text())
            if frame["type"] == "signal_live":
                break
        else:
            pytest.fail("no signal_live frame")
    (pushed,) = [s for s in frame["payload"]["signals"] if s["index"] == "GOLD"]
    assert pushed["live"]["target"] == 136_544.0


def test_an_ended_signal_has_no_live_levels(client: TestClient) -> None:
    td, desk = _desk(client)
    now = epoch_ms_now()
    assert client.portal is not None
    tick = Tick(key=GOLD_KEY, ts=now, ltp=135_000.0)
    client.portal.call(td.session.tick_bus.publish, StampedTick(tick, now))
    desk.signals.on_bias(_b("GOLD", now - 60_000, 0.8), now)
    desk.signals.on_bias(_b("GOLD", now, 0.0), now + 1)  # reversed
    rows = [s for s in client.get("/api/signals").json() if s["index"] == "GOLD"]
    assert rows
    assert all(s["live"] is None for s in rows)

"""Paper trades opened by hand (enhancement 23, Milestone E20). Spec §10.1, §10.3.

Any option in the chain window, or a GOLD / SILVER future long or short, with the signal
formula's target and stop at the fill unless the trader typed their own. The same gates as a
signal trade plus the signal cut-off. Target and stop of any open trade can be changed, and
every change is recorded. In the journal these trades have their own scope.
"""

from __future__ import annotations

import string
import time as walltime
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st

from tests.test_bank import BankHarness
from tests.test_bullion_trading import CPI, GOLD_KEY, PaperHarness, _desk
from tests.test_bullion_trading import at as mcx_at
from tests.test_paper import Harness, at
from tests.test_scorecard_api import _fire
from tradedisha.clock import epoch_ms_now
from tradedisha.engine.bullion_signals import future_levels
from tradedisha.engine.paper import (
    MANUAL_SIGNAL_ID,
    PaperError,
    PaperTrade,
    check_levels,
    journal_stats,
)
from tradedisha.engine.signals import Direction
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.market.session import FeedSession
from tradedisha.parameters.model import ParameterSet

EXPIRY = date(2026, 11, 17)  # a NIFTY weekly expiry in the synthetic master


def _key(h: Harness, strike: float, direction: Direction) -> str:
    pair = next(p for p in h.r.strikes if p.strike == strike)
    return pair.ce.instrument_key if direction == "BUY_CE" else pair.pe.instrument_key


def test_the_manual_id_can_never_be_a_signal_id() -> None:
    # signal ids are uuid4().hex[:12]: twelve hex digits
    assert len(MANUAL_SIGNAL_ID) != 12 or set(MANUAL_SIGNAL_ID) - set(string.hexdigits)
    assert set(MANUAL_SIGNAL_ID) - set(string.hexdigits)


# -- index options -----------------------------------------------------------------------


def test_a_call_at_any_strike_quotes_then_opens_at_the_click_price() -> None:
    h = Harness()
    strike = h.r.atm + 50
    key = _key(h, strike, "BUY_CE")
    h.tick(key, 80.0)

    q = h.paper.quote_manual("NIFTY", "BUY_CE", strike)
    assert q.refusal is None
    assert (q.instrument_key, q.strike, q.ltp) == (key, strike, 80.0)
    assert q.trading_symbol.endswith(f"{strike:.0f}CE")
    assert (q.target, q.stop) == (104.0, 68.0)  # the signal's +30 % / -15 %
    assert (q.lots, q.qty, q.cost) == (1, h.r.lot_size, 60.0)
    assert q.blocked == 80.0 * h.r.lot_size + 60.0
    assert h.paper.open_trades == {}  # a quote never opens anything

    h.tick(key, 81.0)
    t = h.paper.open_manual("NIFTY", "BUY_CE", strike, quoted=80.0)

    assert t.is_manual
    assert t.signal_id == MANUAL_SIGNAL_ID
    assert (t.entry_price, t.signal_entry, t.slippage) == (81.0, 80.0, 1.0)
    assert (t.target_price, t.stop_price) == (105.0, 69.0)  # at the fill: 105.3, 68.85
    assert (t.direction, t.instrument_key, t.expiry) == (
        "BUY_CE",
        key,
        h.r.options_expiry.isoformat(),
    )
    assert h.paper.store.get(t.id) == t
    assert h.updates == [t]
    assert h.signal_events == []  # no signal was involved, none was marked traded
    (row,) = h.paper.store.levels(t.id)
    assert (row.source, row.target, row.stop, row.ltp) == ("entry", 105.0, 69.0, 81.0)


def test_without_a_quoted_price_there_is_no_slippage() -> None:
    h = Harness()
    h.tick(h.pe, 120.0)
    t = h.paper.open_manual("NIFTY", "BUY_PE", h.r.atm)
    assert (t.signal_entry, t.slippage) == (120.0, 0.0)


def test_typed_levels_are_kept_as_given() -> None:
    h = Harness()
    strike = h.r.atm - 50
    h.tick(_key(h, strike, "BUY_PE"), 90.0)
    t = h.paper.open_manual("NIFTY", "BUY_PE", strike, quoted=90.0, target=120.0, stop=70.0)
    assert (t.target_price, t.stop_price) == (120.0, 70.0)
    assert t.levels_edited is False  # typed on the ticket is not an edit


def test_one_typed_level_leaves_the_other_to_the_formula() -> None:
    h = Harness()
    h.tick(h.ce, 100.0)
    t = h.paper.open_manual("NIFTY", "BUY_CE", h.r.atm, target=150.0)
    assert (t.target_price, t.stop_price) == (150.0, 85.0)


@pytest.mark.parametrize(
    ("target", "stop", "message"),
    [
        (99.0, 80.0, "target"),  # the price is already past the target
        (130.0, 101.0, "stop"),  # and here past the stop
        (130.0, 0.0, "above zero"),
    ],
)
def test_typed_levels_the_fill_has_passed_are_refused(
    target: float, stop: float, message: str
) -> None:
    h = Harness()
    h.tick(h.ce, 100.0)
    with pytest.raises(PaperError, match=message):
        h.paper.open_manual("NIFTY", "BUY_CE", h.r.atm, target=target, stop=stop)
    assert h.paper.open_trades == {}
    assert h.updates == []


@pytest.mark.parametrize(
    ("hm", "feed_live", "reason"),
    [
        ((9, 0), True, "market is not open"),
        ((15, 0), True, "no new trades after 15:00"),
        ((15, 20), True, "past the square-off time"),
        ((14, 59), False, "feed is not live"),
        ((14, 59), True, None),
    ],
)
def test_manual_entry_gates(hm: tuple[int, int], feed_live: bool, reason: str | None) -> None:
    h = Harness()
    h.tick(h.ce, 100.0)
    h.now = at(*hm)
    h.feed_live = feed_live

    q = h.paper.quote_manual("NIFTY", "BUY_CE", h.r.atm)
    if reason is None:
        assert q.refusal is None
        assert h.paper.open_manual("NIFTY", "BUY_CE", h.r.atm).is_open
        return
    assert q.refusal is not None
    assert q.refusal.startswith(reason)
    with pytest.raises(PaperError, match=reason):
        h.paper.open_manual("NIFTY", "BUY_CE", h.r.atm)


def test_the_cut_off_does_not_apply_when_hours_are_not_enforced() -> None:
    h = Harness(enforce_hours=False)
    h.tick(h.ce, 100.0)
    h.now = at(15, 10)
    assert h.paper.open_manual("NIFTY", "BUY_CE", h.r.atm).is_open


def test_signal_trades_are_not_held_to_the_cut_off() -> None:
    """A signal fired before 15:00 may still be traded after it, as before."""
    h = Harness()
    signal = h.fire()
    h.now = at(15, 1)
    h.tick(signal.instrument_key, 101.0)
    assert h.paper.open(signal.id).is_open


def test_the_expiry_day_cut_off() -> None:
    h = Harness(day=EXPIRY)
    h.tick(h.ce, 100.0)
    h.now = at(13, 0, day=EXPIRY)
    assert h.paper.quote_manual("NIFTY", "BUY_CE", h.r.atm).refusal == "no new trades after 13:00"
    h.now = at(12, 59, day=EXPIRY)
    assert h.paper.open_manual("NIFTY", "BUY_CE", h.r.atm).is_open


@pytest.mark.parametrize("day", [date(2026, 11, 12), EXPIRY])
def test_default_levels_match_a_signal_on_the_same_option(day: date) -> None:
    """Percentage on a normal day, index points through the option's delta on expiry day."""
    h = Harness(day=day)
    signal = h.fire(entry=100.0)
    h.tick(signal.instrument_key, 104.0)
    want = h.signals.levels_at(signal, 104.0)

    q = h.paper.quote_manual("NIFTY", signal.direction, signal.strike)
    assert (q.target, q.stop) == want
    t = h.paper.open_manual("NIFTY", signal.direction, signal.strike)
    assert (t.target_price, t.stop_price) == want
    assert "NIFTY" in h.signals.active  # the signal is still on offer


@pytest.mark.parametrize(
    ("index", "direction", "strike"),
    [
        ("NIFTY", "BUY_CE", 99_000.0),  # not in the chain window
        ("NIFTY", "BUY_CE", None),
        ("NIFTY", "BUY_FUT", None),  # a future on an index
        ("BANKNIFTY", "BUY_CE", 25_000.0),  # not loaded here
        ("GOLD", "BUY_FUT", None),  # the index manager does not trade metals
    ],
)
def test_an_unknown_contract_is_not_found(
    index: str, direction: Direction, strike: float | None
) -> None:
    h = Harness()
    for call in (h.paper.quote_manual, h.paper.open_manual):
        with pytest.raises(PaperError) as e:
            call(index, direction, strike)
        assert e.value.not_found


def test_no_price_yet_is_a_refusal_on_the_ticket() -> None:
    h = Harness()
    q = h.paper.quote_manual("NIFTY", "BUY_CE", h.r.atm)
    assert q.refusal == "no price for this instrument yet"
    assert (q.ltp, q.target, q.stop, q.blocked) == (None, None, None, None)
    with pytest.raises(PaperError, match="no price"):
        h.paper.open_manual("NIFTY", "BUY_CE", h.r.atm)


def test_a_bank_shortfall_is_refused_and_shown_on_the_ticket() -> None:
    h = BankHarness(opening=5_000.0)
    h.tick(h.ce, 100.0)  # 100 x 65 + 60 is more than 5,000
    q = h.paper.quote_manual("NIFTY", "BUY_CE", h.r.atm)
    assert q.refusal is not None
    assert q.refusal.startswith("not enough money in the paper bank")
    assert q.available == 5_000.0
    with pytest.raises(PaperError, match="not enough money"):
        h.paper.open_manual("NIFTY", "BUY_CE", h.r.atm)

    h.set_opening(100_000.0)
    t = h.paper.open_manual("NIFTY", "BUY_CE", h.r.atm)
    assert (t.banked, t.blocked) == (True, 100.0 * h.r.lot_size + 60.0)


def test_a_price_too_low_for_a_stop_is_refused() -> None:
    """At five paise there is no stop below the price: the trader is told, nothing opens."""
    h = Harness()
    h.tick(h.ce, 0.05)
    assert h.paper.quote_manual("NIFTY", "BUY_CE", h.r.atm).refusal is not None
    with pytest.raises(PaperError, match="stop"):
        h.paper.open_manual("NIFTY", "BUY_CE", h.r.atm)


def test_a_manual_trade_runs_to_its_stop_and_closes_by_hand_like_any_other() -> None:
    h = Harness()
    h.tick(h.ce, 100.0)
    t = h.paper.open_manual("NIFTY", "BUY_CE", h.r.atm)
    h.tick(h.ce, 85.0)
    closed = h.updates[-1]
    assert (closed.id, closed.exit_reason, closed.exit_price) == (t.id, "STOP", 85.0)

    h.tick(h.pe, 50.0)
    t2 = h.paper.open_manual("NIFTY", "BUY_PE", h.r.atm)
    h.tick(h.pe, 55.0)
    assert h.paper.close_manual(t2.id).exit_reason == "MANUAL"


def test_a_manual_trade_survives_a_restart() -> None:
    h = Harness()
    h.tick(h.ce, 100.0)
    t = h.paper.open_manual("NIFTY", "BUY_CE", h.r.atm)
    restored = h.new_manager().open_trades[t.id]
    assert restored.is_manual


# -- editing levels ------------------------------------------------------------------------


def test_a_signal_trade_gets_new_levels_and_the_next_tick_uses_them() -> None:
    h = Harness()
    t = h.open(fill=101.0)  # target 131, stop 86
    h.now += 30_000
    edited = h.paper.set_levels(t.id, target=110.0, stop=95.0)

    assert (edited.target_price, edited.stop_price, edited.levels_edited) == (110.0, 95.0, True)
    assert h.paper.open_trades[t.id] == edited
    assert h.paper.store.get(t.id) == edited
    assert h.updates[-1] == edited
    entry, edit = h.paper.store.levels(t.id)
    assert (entry.source, entry.target, entry.stop) == ("entry", 131.0, 86.0)
    assert (edit.source, edit.target, edit.stop, edit.ltp, edit.ts) == (
        "edit",
        110.0,
        95.0,
        101.0,
        h.now,
    )

    h.tick(t.instrument_key, 110.0)
    closed = h.updates[-1]
    assert (closed.exit_reason, closed.exit_price, closed.levels_edited) == ("TARGET", 110.0, True)


def test_a_manual_trade_can_be_edited_too() -> None:
    h = Harness()
    h.tick(h.ce, 100.0)
    t = h.paper.open_manual("NIFTY", "BUY_CE", h.r.atm)
    h.paper.set_levels(t.id, target=140.0, stop=90.0)
    h.paper.set_levels(t.id, target=150.0, stop=92.0)
    assert [r.source for r in h.paper.store.levels(t.id)] == ["entry", "edit", "edit"]
    h.tick(h.ce, 92.0)
    assert h.updates[-1].exit_reason == "STOP"


@pytest.mark.parametrize(
    ("target", "stop", "message"),
    [(100.0, 90.0, "target"), (130.0, 101.0, "stop"), (130.0, -1.0, "above zero")],
)
def test_edited_levels_are_checked_against_the_current_price(
    target: float, stop: float, message: str
) -> None:
    h = Harness()
    t = h.open(fill=101.0)
    with pytest.raises(PaperError, match=message):
        h.paper.set_levels(t.id, target=target, stop=stop)
    assert h.paper.open_trades[t.id] == t
    assert len(h.paper.store.levels(t.id)) == 1


def test_levels_cannot_change_without_a_live_feed_or_on_a_closed_trade() -> None:
    h = Harness()
    t = h.open(fill=101.0)
    h.feed_live = False
    with pytest.raises(PaperError, match="feed is not live"):
        h.paper.set_levels(t.id, target=120.0, stop=90.0)
    h.feed_live = True
    h.paper.close_manual(t.id)
    with pytest.raises(PaperError, match="already closed"):
        h.paper.set_levels(t.id, target=120.0, stop=90.0)
    with pytest.raises(PaperError) as e:
        h.paper.set_levels("nope", target=120.0, stop=90.0)
    assert e.value.not_found


# -- level checks --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("direction", "price", "target", "stop", "ok"),
    [
        ("BUY_CE", 100.0, 120.0, 90.0, True),
        ("BUY_CE", 100.0, 100.0, 90.0, False),
        ("BUY_CE", 100.0, 120.0, 100.0, False),
        ("BUY_FUT", 1000.0, 1010.0, 990.0, True),
        ("SELL_FUT", 1000.0, 990.0, 1010.0, True),
        ("SELL_FUT", 1000.0, 1010.0, 990.0, False),
    ],
)
def test_check_levels(
    direction: Direction, price: float, target: float, stop: float, ok: bool
) -> None:
    assert (check_levels(direction, price, target, stop) is None) == ok


@given(
    fill=st.floats(min_value=1.0, max_value=5_000.0),
    target_pct=st.floats(min_value=1.0, max_value=200.0),
    stop_pct=st.floats(min_value=-99.0, max_value=-1.0),
)
def test_default_option_levels_bracket_the_fill(
    fill: float, target_pct: float, stop_pct: float
) -> None:
    h = _PCT_HARNESS
    h.params = ParameterSet.model_validate(
        {"signal": {"target_pct": target_pct, "stop_pct": stop_pct}}
    )
    c = h.signals.manual_contract("NIFTY", "BUY_CE", h.r.atm)
    assert c is not None
    target, stop = h.signals.default_levels(c, round(fill, 2))
    assert check_levels("BUY_CE", round(fill, 2), target, stop) is None


_PCT_HARNESS = Harness()


@given(
    fill=st.floats(min_value=1_000.0, max_value=500_000.0),
    target_pct=st.floats(min_value=0.01, max_value=10.0),
    stop_pct=st.floats(min_value=0.01, max_value=10.0),
    direction=st.sampled_from(["BUY_FUT", "SELL_FUT"]),
)
def test_default_future_levels_bracket_the_fill_on_either_side(
    fill: float, target_pct: float, stop_pct: float, direction: Direction
) -> None:
    p = ParameterSet.model_validate({"bullion": {"target_pct": target_pct, "stop_pct": stop_pct}})
    target, stop = future_levels(direction, round(fill, 2), p)
    assert check_levels(direction, round(fill, 2), target, stop) is None


# -- bullion ----------------------------------------------------------------------------------


def test_buy_and_sell_a_gold_future_by_hand(tmp_path: Path) -> None:
    h = PaperHarness(tmp_path, now=mcx_at(20, 1, 20))
    h.quote(GOLD_KEY, 135_000.0)

    q = h.paper.quote_manual("GOLD", "SELL_FUT", None)
    assert q.refusal is None
    assert (q.instrument_key, q.qty, q.target, q.stop) == (GOLD_KEY, 100, 134_460.0, 135_270.0)

    long = h.paper.open_manual("GOLD", "BUY_FUT", None)
    short = h.paper.open_manual("GOLD", "SELL_FUT", None, quoted=135_010.0)
    assert (long.target_price, long.stop_price) == (135_540.0, 134_730.0)
    assert (short.target_price, short.stop_price) == (134_460.0, 135_270.0)
    assert short.slippage == -10.0  # sold 10 below the ticket's price
    assert (short.strike, short.expiry, short.qty) == (0.0, "2026-12-04", 100)
    assert h.fired == []  # no bullion signal involved

    h.now += 5_000
    h.tick(GOLD_KEY, 135_270.0)  # the short's stop
    assert h.trades[-1].id == short.id
    assert h.trades[-1].exit_reason == "STOP"
    assert long.id in h.paper.open_trades


def test_bullion_cut_off_and_the_us_pause(tmp_path: Path) -> None:
    h = PaperHarness(tmp_path, now=mcx_at(22, 45), events=(CPI,))
    h.quote(GOLD_KEY, 135_000.0)
    assert h.paper.quote_manual("GOLD", "BUY_FUT", None).refusal == "no new trades after 22:45"

    h.now = mcx_at(19, 50)
    h.bullion(event_block_trades="on")
    with pytest.raises(PaperError, match="paused around US data: CPI 20:00"):
        h.paper.open_manual("GOLD", "BUY_FUT", None)


@pytest.mark.parametrize(
    ("index", "direction"), [("GOLD", "BUY_CE"), ("COPPER", "BUY_FUT"), ("NIFTY", "BUY_FUT")]
)
def test_a_metal_needs_a_future_direction(tmp_path: Path, index: str, direction: Direction) -> None:
    h = PaperHarness(tmp_path, now=mcx_at(20, 1, 20))
    with pytest.raises(PaperError) as e:
        h.paper.quote_manual(index, direction, None)
    assert e.value.not_found


# -- journal ----------------------------------------------------------------------------------


def _closed(index: str, net: float, *, manual: bool, n: int) -> PaperTrade:
    t = PaperTrade(
        id=f"t{n}",
        signal_id=MANUAL_SIGNAL_ID if manual else "abcdef012345",
        index=index,
        instrument_key="K",
        trading_symbol="SYM",
        direction="BUY_FUT" if index == "GOLD" else "BUY_CE",
        strike=0.0,
        expiry="2026-11-17",
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
    return replace(t, status="closed", exit_ts=60_000, gross=net, net=net, exit_reason="TARGET")


def test_manual_trades_have_their_own_scope_in_the_journal() -> None:
    trades = [
        _closed("NIFTY", 500.0, manual=False, n=1),
        _closed("NIFTY", -300.0, manual=True, n=2),
        _closed("GOLD", 9_000.0, manual=True, n=3),
        _closed("GOLD", 1_000.0, manual=False, n=4),
    ]
    stats = {s.scope: s for s in journal_stats(trades)}
    assert list(stats) == ["overall", "NIFTY", "bullion", "GOLD", "manual"]
    assert (stats["overall"].trades, stats["overall"].net_total) == (1, 500.0)
    assert (stats["NIFTY"].trades, stats["GOLD"].trades) == (1, 1)
    assert (stats["manual"].trades, stats["manual"].net_total) == (2, 8_700.0)


def test_no_manual_scope_without_manual_trades() -> None:
    scopes = [s.scope for s in journal_stats([_closed("NIFTY", 1.0, manual=False, n=1)])]
    assert scopes == ["overall", "NIFTY"]


# -- through the API ---------------------------------------------------------------------------


def _session(client: TestClient) -> FeedSession:
    return client.app.state.td.session  # type: ignore[attr-defined, no-any-return]


def _priced_strike(client: TestClient) -> float:
    """A strike off the ATM whose call the synthetic feed has priced."""
    chains = _session(client).chains
    assert chains is not None
    for _ in range(50):
        chain = chains.chains["NIFTY"]
        priced = [s for s, row in chain.rows.items() if row.ce.ltp and s != chain.atm]
        if priced:
            return priced[0]
        walltime.sleep(0.1)
    raise AssertionError("the synthetic feed never priced the chain")


def test_ticket_open_edit_and_close_by_hand_through_the_api(client: TestClient) -> None:
    strike = _priced_strike(client)
    q = client.get(f"/api/paper-trades/ticket?index=nifty&direction=BUY_CE&strike={strike}")
    assert q.status_code == 200, q.text
    ticket = q.json()
    assert ticket["refusal"] is None  # synthetic: hours are not enforced
    assert ticket["ltp"] > 0
    assert ticket["target"] > ticket["ltp"] > ticket["stop"]
    assert ticket["available"] is not None

    body = {"index": "NIFTY", "direction": "BUY_CE", "strike": strike, "quoted": ticket["ltp"]}
    r = client.post("/api/paper-trades/manual", json=body)
    assert r.status_code == 201, r.text
    trade = r.json()
    assert (trade["manual"], trade["signal_id"], trade["levels_edited"]) == (
        True,
        MANUAL_SIGNAL_ID,
        False,
    )
    assert trade["signal_entry"] == ticket["ltp"]

    ltp = trade["entry_price"]
    edit = {"target": float(round(ltp * 3)), "stop": float(round(ltp / 3))}
    e = client.patch(f"/api/paper-trades/{trade['id']}/levels", json=edit)
    assert e.status_code == 200, e.text
    assert (e.json()["target_price"], e.json()["levels_edited"]) == (edit["target"], True)

    bad = client.patch(
        f"/api/paper-trades/{trade['id']}/levels", json={"target": 0.1, "stop": 0.05}
    )
    assert bad.status_code == 409

    detail = client.get(f"/api/paper-trades/{trade['id']}").json()
    assert detail["signal"] is None
    assert [lv["source"] for lv in detail["levels"]] == ["entry", "edit"]

    closed = client.post(f"/api/paper-trades/{trade['id']}/close")
    assert closed.json()["exit_reason"] == "MANUAL"
    stats = {s["scope"]: s for s in client.get("/api/journal/stats").json()["stats"]}
    assert stats["manual"]["trades"] == 1
    assert stats["overall"]["trades"] == 0


def test_a_signal_trade_detail_lists_its_levels(client: TestClient) -> None:
    walltime.sleep(0.3)
    sid = _fire(_session(client))
    trade = client.post("/api/paper-trades", json={"signal_id": sid}).json()
    assert trade["manual"] is False
    detail = client.get(f"/api/paper-trades/{trade['id']}").json()
    assert detail["signal"]["id"] == sid
    assert [lv["source"] for lv in detail["levels"]] == ["entry"]


def test_the_manual_id_is_not_a_signal_to_trade(client: TestClient) -> None:
    r = client.post("/api/paper-trades", json={"signal_id": MANUAL_SIGNAL_ID})
    assert r.status_code == 409
    assert "manual" in r.json()["detail"]


@pytest.mark.parametrize(
    "query",
    [
        "index=NIFTY&direction=BUY_CE&strike=1",
        "index=NIFTY&direction=BUY_FUT",
        "index=GOLD&direction=BUY_FUT",  # bullion is not loaded on the synthetic feed
    ],
)
def test_an_unknown_ticket_is_404_or_409(client: TestClient, query: str) -> None:
    r = client.get(f"/api/paper-trades/ticket?{query}")
    assert r.status_code in {404, 409}, r.text


def test_an_unknown_trade_cannot_be_edited(client: TestClient) -> None:
    r = client.patch("/api/paper-trades/nope/levels", json={"target": 2.0, "stop": 1.0})
    assert r.status_code == 404


def test_a_gold_future_by_hand_through_the_api(client: TestClient) -> None:
    td, desk = _desk(client)
    now = epoch_ms_now()
    assert client.portal is not None
    tick = Tick(key=GOLD_KEY, ts=now, ltp=135_000.0)
    client.portal.call(td.session.tick_bus.publish, StampedTick(tick, now))

    q = client.get("/api/paper-trades/ticket?index=GOLD&direction=SELL_FUT").json()
    assert (q["ltp"], q["target"], q["stop"], q["refusal"]) == (
        135_000.0,
        134_460.0,
        135_270.0,
        None,
    )
    r = client.post("/api/paper-trades/manual", json={"index": "GOLD", "direction": "SELL_FUT"})
    assert r.status_code == 201, r.text
    assert r.json()["id"] in desk.paper.open_trades
    assert r.json()["manual"] is True

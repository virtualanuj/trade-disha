"""GOLDM and SILVERM as trading choices for each metal (E28): signal trades and tickets."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_bullion_trading import GOLD_KEY, SILVER_KEY, PaperHarness, _b, _fut, at
from tradedisha.app_state import AppState
from tradedisha.clock import epoch_ms_now
from tradedisha.engine.paper import PaperError
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.market.bullion import BullionContract, BullionTracker

GOLDM_KEY = "MCX_FO|575011"
SILVERM_KEY = "MCX_FO|483080"


def _tracker(*, minis: bool = True) -> BullionTracker:
    gold_mini = BullionContract("GOLDM", _fut("GOLDM", GOLDM_KEY, 10.0), None) if minis else None
    silver_mini = (
        BullionContract("SILVERM", _fut("SILVERM", SILVERM_KEY, 5.0), None) if minis else None
    )
    return BullionTracker(
        {
            "GOLD": BullionContract("GOLD", _fut("GOLD", GOLD_KEY, 100.0), None, mini=gold_mini),
            "SILVER": BullionContract(
                "SILVER", _fut("SILVER", SILVER_KEY, 30.0), None, mini=silver_mini
            ),
        }
    )


def _harness(tmp_path: Path, *, minis: bool = True) -> PaperHarness:
    return PaperHarness(tmp_path, now=at(20, 1, 20), tracker=_tracker(minis=minis))


def test_a_gold_signal_opens_the_chosen_mini_with_its_lots(tmp_path: Path) -> None:
    h = _harness(tmp_path)
    h.bullion(gold_contract="GOLDM", goldm_lots=3)
    h.quote(GOLD_KEY, 135_000.0)
    h.quote(GOLDM_KEY, 135_010.0)
    h.evaluate("GOLD", 0.7)
    signal = h.engine.active["GOLD"]
    assert signal.instrument_key == GOLD_KEY  # the signal reads the full contract

    t = h.paper.open(signal.id)
    assert (t.index, t.instrument_key, t.trading_symbol) == (
        "GOLD",
        GOLDM_KEY,
        "GOLDM FUT 04 DEC 26",
    )
    assert (t.lots, t.qty, t.entry_price) == (3, 30, 135_010.0)  # ₹10 a point a lot
    assert t.slippage == 10.0  # the mini's price against the signal's
    assert (t.target_price, t.stop_price) == (135_550.0, 134_740.0)  # the rule at the fill

    h.now += 5_000
    h.tick(GOLD_KEY, 135_600.0)  # the full contract passing the target does nothing
    assert t.id in h.paper.open_trades
    h.tick(GOLDM_KEY, 135_550.0)
    closed = h.trades[-1]
    assert (closed.exit_reason, closed.gross) == ("TARGET", 540.0 * 30)


def test_the_full_contracts_take_their_own_default_lots(tmp_path: Path) -> None:
    h = _harness(tmp_path)
    h.bullion(gold_lots=2, silver_lots=4)
    h.quote(GOLD_KEY, 135_000.0)
    h.evaluate("GOLD", 0.7)
    assert h.paper.open(h.engine.active["GOLD"].id).qty == 200
    silver = h.short_silver()
    assert (silver.instrument_key, silver.lots, silver.qty) == (SILVER_KEY, 4, 120)


def test_a_signal_for_a_mini_that_is_not_loaded_is_refused(tmp_path: Path) -> None:
    h = _harness(tmp_path, minis=False)
    h.bullion(silver_contract="SILVERM")
    h.quote(SILVER_KEY, 170_000.0)
    h.evaluate("SILVER", -0.7)
    with pytest.raises(PaperError, match="not loaded"):
        h.paper.open(h.engine.active["SILVER"].id)
    assert h.paper.open_trades == {}


def test_a_mini_by_hand_defaults_to_its_lots_and_the_ticket_can_change_them(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path)
    h.bullion(goldm_lots=3)
    h.quote(GOLDM_KEY, 135_000.0)
    q = h.paper.quote_manual("GOLD", "SELL_FUT", None, contract="GOLDM")
    assert (q.instrument_key, q.lots, q.qty, q.refusal) == (GOLDM_KEY, 3, 30, None)
    # the bank blocks GOLD's margin on the mini's value, plus cost
    assert q.cost is not None
    assert q.blocked == pytest.approx(0.10 * 135_000.0 * 30 + q.cost)

    q5 = h.paper.quote_manual("GOLD", "SELL_FUT", None, contract="GOLDM", lots=5)
    assert (q5.lots, q5.qty) == (5, 50)
    t = h.paper.open_manual("GOLD", "SELL_FUT", None, contract="GOLDM", lots=5)
    assert (t.index, t.instrument_key, t.lots, t.qty) == ("GOLD", GOLDM_KEY, 5, 50)
    assert t.is_manual


def test_the_full_contract_by_hand_is_unchanged(tmp_path: Path) -> None:
    h = _harness(tmp_path)
    h.quote(GOLD_KEY, 135_000.0)
    for contract in (None, "GOLD"):
        q = h.paper.quote_manual("GOLD", "BUY_FUT", None, contract=contract)
        assert (q.instrument_key, q.lots, q.qty) == (GOLD_KEY, 1, 100)


@pytest.mark.parametrize("lots", [0, 101])
def test_lots_outside_one_to_a_hundred_are_refused(tmp_path: Path, lots: int) -> None:
    h = _harness(tmp_path)
    h.quote(GOLDM_KEY, 135_000.0)
    q = h.paper.quote_manual("GOLD", "BUY_FUT", None, contract="GOLDM", lots=lots)
    assert q.refusal == "lots must be 1 to 100"
    with pytest.raises(PaperError, match="lots must be 1 to 100"):
        h.paper.open_manual("GOLD", "BUY_FUT", None, contract="GOLDM", lots=lots)


@pytest.mark.parametrize(("metal", "contract"), [("GOLD", "SILVERM"), ("SILVER", "GOLDM")])
def test_another_metals_contract_is_not_found(tmp_path: Path, metal: str, contract: str) -> None:
    h = _harness(tmp_path)
    with pytest.raises(PaperError) as e:
        h.paper.quote_manual(metal, "BUY_FUT", None, contract=contract)
    assert e.value.not_found


# -- through the API ---------------------------------------------------------------------


def _publish(client: TestClient, td: AppState, key: str, ltp: float) -> None:
    now = epoch_ms_now()
    assert client.portal is not None
    client.portal.call(
        td.session.tick_bus.publish, StampedTick(Tick(key=key, ts=now, ltp=ltp), now)
    )


def test_minis_through_the_api(client: TestClient) -> None:
    td: AppState = client.app.state.td  # type: ignore[attr-defined]
    td.session.bullion_live = lambda: True  # type: ignore[method-assign]
    td.session.attach_bullion(_tracker())
    desk = td.session.bullion_desk
    assert desk is not None
    cur = td.params.current.params
    bullion = cur.bullion.model_copy(update={"gold_contract": "GOLDM", "goldm_lots": 3})
    td.params.save(cur.model_copy(update={"bullion": bullion}), "minis")
    _publish(client, td, GOLD_KEY, 135_000.0)
    _publish(client, td, GOLDM_KEY, 135_010.0)

    gold = client.get("/api/bullion").json()["metals"][0]
    assert (gold["mini"]["metal"], gold["mini"]["ltp"], gold["mini"]["point_value"]) == (
        "GOLDM",
        135_010.0,
        10,
    )

    q = client.get("/api/paper-trades/ticket?index=GOLD&direction=BUY_FUT&contract=goldm&lots=2")
    assert q.status_code == 200, q.text
    assert (q.json()["instrument_key"], q.json()["lots"], q.json()["qty"]) == (GOLDM_KEY, 2, 20)
    body = {"index": "GOLD", "direction": "BUY_FUT", "contract": "GOLDM", "lots": 2}
    r = client.post("/api/paper-trades/manual", json=body)
    assert r.status_code == 201, r.text
    assert (r.json()["instrument_key"], r.json()["qty"]) == (GOLDM_KEY, 20)
    bad = client.post("/api/paper-trades/manual", json={**body, "lots": 0})
    assert bad.status_code == 409
    assert "lots" in bad.json()["detail"]

    now = epoch_ms_now()
    desk.signals.on_bias(_b("GOLD", now - 60_000, 0.8), now)
    active = {s["index"]: s for s in client.get("/api/signals/active").json()}
    assert active["GOLD"]["trade"] == {
        "contract": "GOLDM",
        "trading_symbol": "GOLDM FUT 04 DEC 26",
        "lots": 3,
        "qty": 30,
    }
    t = client.post("/api/paper-trades", json={"signal_id": active["GOLD"]["id"]})
    assert t.status_code == 201, t.text
    assert (t.json()["instrument_key"], t.json()["lots"], t.json()["index"]) == (
        GOLDM_KEY,
        3,
        "GOLD",
    )

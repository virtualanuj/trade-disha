"""GOLDM and SILVERM as markets of their own (E29): own candles, bias, signals and trades."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_bullion_trading import GOLD_KEY, SILVER_KEY, PaperHarness, _b, _fut, _rising, at
from tradedisha.app_state import AppState
from tradedisha.clock import epoch_ms_now
from tradedisha.engine.bias_engine import BiasComputed
from tradedisha.engine.bullion_bias import BullionBiasEngine
from tradedisha.engine.paper import METALS, PaperError
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.market.bullion import BullionContract, BullionTracker, family
from tradedisha.parameters.model import ParameterSet
from tradedisha.store.db import connect

GOLDM_KEY = "MCX_FO|575011"
SILVERM_KEY = "MCX_FO|483080"
M = 60_000


def _contracts(*, minis: bool = True) -> dict[str, BullionContract]:
    out = {"GOLD": BullionContract("GOLD", _fut("GOLD", GOLD_KEY, 100.0), None)}
    if minis:
        out["GOLDM"] = BullionContract("GOLDM", _fut("GOLDM", GOLDM_KEY, 10.0), None)
    out["SILVER"] = BullionContract("SILVER", _fut("SILVER", SILVER_KEY, 30.0), None)
    if minis:
        out["SILVERM"] = BullionContract("SILVERM", _fut("SILVERM", SILVERM_KEY, 5.0), None)
    return out


def _tracker(*, minis: bool = True) -> BullionTracker:
    return BullionTracker(_contracts(minis=minis))


def _harness(tmp_path: Path, *, minis: bool = True) -> PaperHarness:
    return PaperHarness(tmp_path, now=at(20, 1, 20), tracker=_tracker(minis=minis))


# -- the four markets ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "metal"),
    [("GOLD", "GOLD"), ("GOLDM", "GOLD"), ("SILVER", "SILVER"), ("SILVERM", "SILVER")],
)
def test_each_contract_belongs_to_its_metal(name: str, metal: str) -> None:
    assert family(name) == metal
    assert name in METALS


def test_a_mini_ticks_into_its_own_candles_book_and_card() -> None:
    t = _tracker()
    t0 = at(20, 1)
    for i, px in enumerate([135_000.0, 135_020.0, 135_010.0]):
        t.on_tick(StampedTick(Tick(key=GOLDM_KEY, ts=t0 + i * M, ltp=px, oi=900 + i), t0))
    assert [c.close for c in t.closed_candles("GOLDM")] == [135_000.0, 135_020.0]
    assert [b.oi for b in t.minute_book("GOLDM", t0 + M)] == [900, 901]
    assert t.closed_candles("GOLD") == []  # the full contract is its own market
    snap = {s.metal: s for s in t.snapshot().metals}
    assert list(snap) == ["GOLD", "GOLDM", "SILVER", "SILVERM"]
    assert (snap["GOLDM"].ltp, snap["GOLDM"].point_value) == (135_010.0, 10)
    assert snap["GOLD"].ltp is None


def test_a_mini_has_its_own_view_and_reads_the_other_metals_full_future(tmp_path: Path) -> None:
    t = _tracker()
    t0 = at(20, 1)
    t.seed("GOLDM", _rising(GOLDM_KEY, t0, 30))
    t.seed("SILVER", _rising(SILVER_KEY, t0, 30))
    seen: list[BiasComputed] = []
    engine = BullionBiasEngine(
        tracker=t, params=ParameterSet, conn=connect(tmp_path / "b.sqlite"), on_bias=seen.append
    )
    b = engine.evaluate("GOLDM", t0 + 29 * M)
    assert b.index == "GOLDM"
    assert b.bias.bias > 0  # GOLDM's own climb
    names = [c.result.name for c in b.bias.contributions]
    assert "peer_metal" in names
    peer = next(c.result for c in b.bias.contributions if c.result.name == "peer_metal")
    assert peer.note.startswith("SILVER trend")  # the full future, not SILVERM
    assert peer.score > 0


# -- signals and trades ----------------------------------------------------------------------


def test_a_gold_mini_signal_trades_the_mini_with_its_lots_at_golds_margin(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path)
    h.bullion(goldm_lots=3)
    h.quote(GOLDM_KEY, 135_010.0)
    h.evaluate("GOLDM", 0.7)
    s = h.engine.active["GOLDM"]
    assert (s.index, s.instrument_key, s.lot_size, s.entry_price) == (
        "GOLDM",
        GOLDM_KEY,
        10,
        135_010.0,
    )
    t = h.paper.open(s.id)
    assert (t.index, t.instrument_key, t.lots, t.qty) == ("GOLDM", GOLDM_KEY, 3, 30)
    assert t.slippage == 0.0
    h.now += 5_000
    h.tick(GOLD_KEY, 136_000.0)  # the full contract plays no part
    assert t.id in h.paper.open_trades
    h.tick(GOLDM_KEY, t.target_price)
    assert h.trades[-1].exit_reason == "TARGET"


def test_gold_and_its_mini_can_hold_opposite_signals(tmp_path: Path) -> None:
    h = _harness(tmp_path)
    h.quote(GOLD_KEY, 135_000.0)
    h.quote(GOLDM_KEY, 135_010.0)
    h.evaluate("GOLD", 0.7)
    h.evaluate("GOLDM", -0.7)
    assert h.engine.active["GOLD"].direction == "BUY_FUT"
    assert h.engine.active["GOLDM"].direction == "SELL_FUT"
    gold = h.paper.open(h.engine.active["GOLD"].id)
    mini = h.paper.open(h.engine.active["GOLDM"].id)
    assert (gold.instrument_key, mini.instrument_key) == (GOLD_KEY, GOLDM_KEY)


def test_without_its_mini_a_metal_has_no_mini_market(tmp_path: Path) -> None:
    h = _harness(tmp_path, minis=False)
    with pytest.raises(PaperError) as e:
        h.paper.quote_manual("GOLDM", "BUY_FUT", None)
    assert e.value.not_found


def test_a_mini_by_hand_defaults_to_its_lots_and_blocks_its_metals_margin(
    tmp_path: Path,
) -> None:
    h = _harness(tmp_path)
    h.bullion(goldm_lots=3)
    h.quote(GOLDM_KEY, 135_000.0)
    q = h.paper.quote_manual("GOLDM", "SELL_FUT", None)
    assert (q.instrument_key, q.lots, q.qty, q.refusal) == (GOLDM_KEY, 3, 30, None)
    assert q.cost is not None
    assert q.blocked == pytest.approx(0.10 * 135_000.0 * 30 + q.cost)  # GOLD's 10 %
    t = h.paper.open_manual("GOLDM", "SELL_FUT", None, lots=5)
    assert (t.index, t.instrument_key, t.lots, t.qty) == ("GOLDM", GOLDM_KEY, 5, 50)
    assert t.is_manual


@pytest.mark.parametrize(
    ("index", "contract", "found"),
    [
        ("GOLDM", None, True),
        ("GOLDM", "GOLDM", True),
        ("GOLD", None, True),
        ("GOLD", "GOLDM", False),  # a mini is its own market now
        ("SILVER", "GOLDM", False),
    ],
)
def test_the_contract_is_the_index(
    tmp_path: Path, index: str, contract: str | None, found: bool
) -> None:
    h = _harness(tmp_path)
    if found:
        assert h.paper.quote_manual(index, "BUY_FUT", None, contract=contract).index == index
    else:
        with pytest.raises(PaperError) as e:
            h.paper.quote_manual(index, "BUY_FUT", None, contract=contract)
        assert e.value.not_found


@pytest.mark.parametrize("lots", [0, 101])
def test_lots_outside_one_to_a_hundred_are_refused(tmp_path: Path, lots: int) -> None:
    h = _harness(tmp_path)
    h.quote(GOLDM_KEY, 135_000.0)
    q = h.paper.quote_manual("GOLDM", "BUY_FUT", None, lots=lots)
    assert q.refusal == "lots must be 1 to 100"


# -- parameters ------------------------------------------------------------------------------


def test_a_version_that_chose_a_contract_still_loads() -> None:
    stored = ParameterSet().model_dump(mode="json")
    stored["bullion"]["gold_contract"] = "GOLDM"
    stored["bullion"]["silver_contract"] = "SILVER"
    p = ParameterSet.model_validate(stored)
    assert "gold_contract" not in p.bullion.model_dump()


def test_the_minis_have_their_own_factor_switches() -> None:
    p = ParameterSet()
    off = p.factors.model_copy(
        update={"goldm": p.factors.goldm.model_copy(update={"net_volume": "off"})}
    )
    assert off.off_for("GOLDM") == frozenset({"net_volume"})
    assert off.off_for("GOLD") == frozenset()
    stored = ParameterSet().model_dump(mode="json")
    del stored["factors"]["goldm"], stored["factors"]["silverm"]
    assert ParameterSet.model_validate(stored).factors.off_for("SILVERM") == frozenset()


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
    td.params.save(
        cur.model_copy(update={"bullion": cur.bullion.model_copy(update={"goldm_lots": 3})}),
        "minis",
    )
    _publish(client, td, GOLDM_KEY, 135_010.0)

    metals = client.get("/api/bullion").json()["metals"]
    assert [m["metal"] for m in metals] == ["GOLD", "GOLDM", "SILVER", "SILVERM"]
    assert (metals[1]["ltp"], metals[1]["point_value"]) == (135_010.0, 10)

    q = client.get("/api/paper-trades/ticket?index=GOLDM&direction=BUY_FUT&lots=2")
    assert q.status_code == 200, q.text
    assert (q.json()["instrument_key"], q.json()["lots"], q.json()["qty"]) == (GOLDM_KEY, 2, 20)

    now = epoch_ms_now()
    desk.signals.on_bias(_b("GOLDM", now - 60_000, 0.8), now)
    active = {s["index"]: s for s in client.get("/api/signals/active").json()}
    assert active["GOLDM"]["trade"] == {
        "contract": "GOLDM",
        "trading_symbol": "GOLDM FUT 04 DEC 26",
        "lots": 3,
        "qty": 30,
    }
    t = client.post("/api/paper-trades", json={"signal_id": active["GOLDM"]["id"]})
    assert t.status_code == 201, t.text
    assert (t.json()["index"], t.json()["instrument_key"], t.json()["lots"]) == (
        "GOLDM",
        GOLDM_KEY,
        3,
    )
    assert client.get("/api/chart/GOLDM", params={"interval": "1m"}).status_code == 200

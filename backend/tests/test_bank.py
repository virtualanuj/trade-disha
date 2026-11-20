"""The paper bank (Milestone E17): money blocked at entry, P&L settled at exit. Spec §10.5."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.test_bullion_trading import GOLD_KEY, SILVER_KEY, PaperHarness, _b, _desk
from tests.test_bullion_trading import at as mcx_at
from tests.test_paper import Harness, at
from tradedisha.clock import epoch_ms_now
from tradedisha.engine.bank import PaperBank
from tradedisha.engine.paper import PaperError, PaperTrade, PaperTradeManager
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.parameters.model import ParameterSet
from tradedisha.parameters.schema import describe


def _with_opening(p: ParameterSet, amount: float) -> ParameterSet:
    return p.model_copy(update={"bank": p.bank.model_copy(update={"opening_balance": amount})})


class BankHarness(Harness):
    """The index harness with a bank behind its manager."""

    def __init__(self, opening: float = 100_000.0) -> None:
        self.opening = opening
        super().__init__()

    def new_manager(self) -> PaperTradeManager:
        self.params = _with_opening(self.params, self.opening)
        self.bank = PaperBank(self.conn, lambda: self.params)
        mgr = super().new_manager()
        mgr.bank = self.bank
        return mgr

    def set_opening(self, amount: float) -> None:
        self.params = _with_opening(self.params, amount)

    def close(self, trade: PaperTrade, price: float) -> PaperTrade:
        """Close by hand at `price`, unless the tick itself reached the target or stop."""
        self.tick(trade.instrument_key, price)
        if trade.id in self.paper.open_trades:
            return self.paper.close_manual(trade.id)
        closed = self.paper.store.get(trade.id)
        assert closed is not None
        return closed


# -- parameters -------------------------------------------------------------------------------


def test_opening_balance_and_margins_are_editable_parameters() -> None:
    p = ParameterSet()
    assert p.bank.opening_balance == 2_500_000
    assert (p.bullion.gold_margin_pct, p.bullion.silver_margin_pct) == (10.0, 12.0)
    specs = {s.path: s for s in describe(p)}
    for path in ("bank.opening_balance", "bullion.gold_margin_pct", "bullion.silver_margin_pct"):
        assert specs[path].kind == "number"
        assert specs[path].help


def test_a_stored_version_without_a_bank_still_loads() -> None:
    stored = ParameterSet().model_dump(mode="json")
    del stored["bank"]
    del stored["bullion"]["gold_margin_pct"]
    assert ParameterSet.model_validate(stored).bank.opening_balance == 2_500_000


# -- index options ------------------------------------------------------------------------------


def test_an_option_buy_blocks_premium_times_qty_plus_cost() -> None:
    h = BankHarness()
    trade = h.open(fill=101.0)
    want = 101.0 * h.r.lot_size + 60.0
    assert trade.blocked == want
    assert trade.banked
    s = h.bank.summary()
    assert (s.opening_balance, s.realised, s.balance) == (100_000.0, 0.0, 100_000.0)
    assert s.blocked == want
    assert s.available == 100_000.0 - want


def test_refused_when_the_bank_cannot_cover_the_block_and_the_signal_stays_active() -> None:
    h = BankHarness(opening=5_000.0)
    signal = h.fire()
    h.tick(signal.instrument_key, 101.0)
    with pytest.raises(PaperError, match="not enough money in the paper bank"):
        h.paper.open(signal.id)
    assert h.signals.active["NIFTY"].id == signal.id
    assert h.signals.active["NIFTY"].status == "active"
    assert h.paper.open_trades == {}
    assert h.bank.summary().blocked == 0.0


@pytest.mark.parametrize(
    ("exit_price", "net_per_unit"),
    [
        (125.0, 24.0),  # profit is deposited (the target is 131.30)
        (90.0, -11.0),  # loss is deducted (the stop is 85.85)
        (101.0, 0.0),  # flat: only the cost goes
    ],
)
def test_closing_releases_the_block_and_settles_net(exit_price: float, net_per_unit: float) -> None:
    h = BankHarness()
    trade = h.open(fill=101.0)
    h.now = at(10, 5)
    closed = h.close(trade, exit_price)
    net = net_per_unit * h.r.lot_size - 60.0
    assert closed.net == pytest.approx(net)
    s = h.bank.summary()
    assert s.blocked == 0.0
    assert s.realised == pytest.approx(net)
    assert s.balance == pytest.approx(100_000.0 + net)
    assert s.available == pytest.approx(100_000.0 + net)


def test_target_and_stop_exits_settle_too() -> None:
    h = BankHarness()
    trade = h.open(fill=101.0)
    h.tick(h.ce, 140.0, at(10, 2))  # target
    assert trade.id not in h.paper.open_trades
    assert h.bank.summary().realised == pytest.approx(39.0 * h.r.lot_size - 60.0)


# -- deposits and withdrawals ---------------------------------------------------------------


def test_the_first_read_records_the_opening_deposit() -> None:
    h = BankHarness()
    (entry,) = h.bank.ledger()
    assert (entry.kind, entry.amount, entry.opening_balance) == ("OPEN", 100_000.0, 100_000.0)
    assert h.bank.summary().opened_ts == entry.ts


@pytest.mark.parametrize(
    ("new_opening", "kind", "amount"),
    [
        (150_000.0, "DEPOSIT", 50_000.0),  # a bigger amount is cash deposited
        (60_000.0, "WITHDRAW", 40_000.0),  # a smaller one is cash withdrawn
    ],
)
def test_changing_the_opening_balance_deposits_or_withdraws_the_difference(
    new_opening: float, kind: str, amount: float
) -> None:
    h = BankHarness()
    first = h.open(fill=101.0)
    h.now = at(10, 5)
    closed = h.close(first, 120.0)
    h.now = at(10, 10)
    still_open = h.open(fill=101.0)
    before = h.bank.summary()

    h.set_opening(new_opening)
    s = h.bank.summary()
    entry = h.bank.ledger()[-1]
    assert (entry.kind, entry.amount, entry.opening_balance) == (kind, amount, new_opening)
    assert s.balance == pytest.approx(before.balance + new_opening - 100_000.0)
    assert s.realised == pytest.approx(closed.net or 0.0)  # P&L history is kept
    assert s.blocked == still_open.blocked  # open trades are untouched
    assert (s.deposited, s.withdrawn) == ((amount, 0.0) if kind == "DEPOSIT" else (0.0, amount))

    h.now = at(10, 15)
    later = h.close(h.paper.open_trades[still_open.id], 110.0)
    assert h.bank.summary().realised == pytest.approx((closed.net or 0.0) + (later.net or 0.0))


def test_saving_the_same_amount_moves_no_cash_and_a_revert_is_another_entry() -> None:
    h = BankHarness()
    h.set_opening(100_000.0)  # saved again unchanged
    assert [e.kind for e in h.bank.ledger()] == ["OPEN"]
    h.set_opening(150_000.0)
    h.bank.ledger()  # the app reads the bank on every save (the `bank` frame)
    h.set_opening(100_000.0)  # a revert
    assert [(e.kind, e.amount) for e in h.bank.ledger()] == [
        ("OPEN", 100_000.0),
        ("DEPOSIT", 50_000.0),
        ("WITHDRAW", 50_000.0),
    ]
    assert h.bank.summary().balance == 100_000.0


def test_withdrawing_more_than_is_free_leaves_nothing_to_trade_with() -> None:
    h = BankHarness()
    trade = h.open(fill=101.0)  # blocks about ₹7,600
    h.set_opening(5_000.0)  # withdraws ₹95,000 while the trade holds its block
    s = h.bank.summary()
    assert s.balance == 5_000.0
    assert s.available == pytest.approx(5_000.0 - trade.blocked)
    assert s.available < 0
    h.now = at(10, 5)
    signal = h.fire()
    h.tick(signal.instrument_key, 101.0)
    with pytest.raises(PaperError, match="not enough money"):
        h.paper.open(signal.id)


def test_trades_from_before_the_bank_never_count() -> None:
    h = Harness()  # no bank: a trade from before this milestone
    old = h.open(fill=101.0)
    h.now = at(10, 5)
    h.tick(old.instrument_key, 120.0)
    h.paper.close_manual(old.id)
    assert h.paper.store.get(old.id) is not None
    assert not h.paper.store.get(old.id).banked  # type: ignore[union-attr]
    bank = PaperBank(h.conn, lambda: h.params)
    s = bank.summary()
    assert (s.realised, s.blocked, s.balance) == (0.0, 0.0, 2_500_000.0)


# -- bullion futures -------------------------------------------------------------------------


def _bullion(tmp_path: Path, opening: float = 2_500_000.0) -> tuple[PaperHarness, PaperBank]:
    h = PaperHarness(tmp_path, now=mcx_at(20, 1, 20))
    h.params = _with_opening(h.params, opening)
    bank = PaperBank(h.conn, lambda: h.params)
    h.paper.bank = bank
    return h, bank


def test_a_gold_future_blocks_its_margin_plus_cost(tmp_path: Path) -> None:
    h, bank = _bullion(tmp_path)
    h.quote(GOLD_KEY, 135_000.0)
    h.evaluate("GOLD", 0.7)
    t = h.paper.open(h.engine.active["GOLD"].id)
    # 10 % of 135,000 x 100 = ₹13.5 lakh, plus the ₹3,300 round-trip cost
    assert t.blocked == 1_350_000.0 + 3_300.0
    assert bank.summary().available == 2_500_000.0 - 1_353_300.0


def test_a_silver_short_blocks_the_silver_margin(tmp_path: Path) -> None:
    h, bank = _bullion(tmp_path)
    t = h.short_silver()
    # 12 % of 170,000 x 30 = ₹6.12 lakh, plus cost
    assert t.blocked == pytest.approx(612_000.0 + t.cost)
    assert bank.summary().blocked == t.blocked


def test_a_futures_loss_beyond_its_margin_takes_the_balance_negative(tmp_path: Path) -> None:
    h, bank = _bullion(tmp_path, opening=700_000.0)
    h.params = h.params.model_copy(
        update={"bullion": h.params.bullion.model_copy(update={"stop_pct": 10.0})}
    )
    t = h.short_silver()  # blocks about ₹6.13 lakh
    h.now += 5_000
    h.tick(SILVER_KEY, 200_000.0)  # gaps through the stop: +30,000 against 30 kg, -₹9 lakh
    assert t.id not in h.paper.open_trades
    s = bank.summary()
    assert s.balance < 0
    assert s.available == s.balance
    h.now += 60_000
    h.quote(GOLD_KEY, 135_000.0)
    h.evaluate("GOLD", 0.7)
    with pytest.raises(PaperError, match="not enough money"):
        h.paper.open(h.engine.active["GOLD"].id)


def test_index_and_bullion_draw_on_one_account(tmp_path: Path) -> None:
    h, _bank = _bullion(tmp_path, opening=1_600_000.0)
    t = h.short_silver()  # about ₹6.13 lakh
    h.now += 60_000
    h.quote(GOLD_KEY, 135_000.0)
    h.evaluate("GOLD", 0.7)
    with pytest.raises(PaperError, match="not enough money"):
        h.paper.open(h.engine.active["GOLD"].id)  # ₹13.5 lakh more is not left
    h.tick(SILVER_KEY, 169_990.0)
    h.paper.close_manual(t.id)
    h.paper.open(h.engine.active["GOLD"].id)  # the silver money is back


# -- the books always balance ------------------------------------------------------------------


@settings(max_examples=30, deadline=None)
@given(
    st.lists(
        st.tuples(st.booleans(), st.floats(min_value=50.0, max_value=200.0)),
        min_size=1,
        max_size=12,
    )
)
def test_available_is_opening_plus_realised_minus_blocked(steps: list[tuple[bool, float]]) -> None:
    h = BankHarness(opening=50_000.0)
    minute = 0
    for opening, price in steps:
        minute += 2
        h.now = at(10, minute)
        if opening or not h.paper.open_trades:
            try:
                signal = h.fire(entry=price)
                h.tick(signal.instrument_key, price)
                h.paper.open(signal.id)
            except PaperError:
                pass
        else:
            trade = next(iter(h.paper.open_trades.values()))
            h.close(trade, price)
        trades = h.paper.store.read()
        realised = sum(t.net or 0.0 for t in trades if not t.is_open and t.banked)
        blocked = sum(t.blocked for t in trades if t.is_open)
        s = h.bank.summary()
        assert s.realised == pytest.approx(realised)
        assert s.blocked == pytest.approx(blocked)
        assert s.available == pytest.approx(50_000.0 + realised - blocked)
        assert s.blocked <= 50_000.0 + max(realised, 0.0) + 1e-6  # never blocked more than held


# -- API and socket ----------------------------------------------------------------------------


def _save_opening(client: TestClient, amount: float) -> None:
    values = client.get("/api/parameters").json()["params"]
    values["bank"]["opening_balance"] = amount
    r = client.put("/api/parameters", json={"tag": f"bank {amount}", "params": values})
    assert r.status_code == 200, r.text


def _gold_signal(client: TestClient) -> str:
    td, desk = _desk(client)
    now = epoch_ms_now()
    assert client.portal is not None
    tick = Tick(key=GOLD_KEY, ts=now, ltp=135_000.0)
    client.portal.call(td.session.tick_bus.publish, StampedTick(tick, now))
    desk.signals.on_bias(_b("GOLD", now - 60_000, 0.8), now)
    return str(client.get("/api/signals/active").json()[0]["id"])


def test_bank_endpoint_refuses_an_open_it_cannot_fund_and_edits_move_cash(
    client: TestClient,
) -> None:
    body = client.get("/api/bank").json()
    assert body["opening_balance"] == 2_500_000
    assert body["available"] == body["balance"] - body["blocked"]
    assert [e["kind"] for e in body["ledger"]] == ["OPEN"]

    _save_opening(client, 100_000.0)
    signal_id = _gold_signal(client)
    r = client.post("/api/paper-trades", json={"signal_id": signal_id})
    assert r.status_code == 409
    assert "not enough money in the paper bank" in r.json()["detail"]
    after = client.get("/api/bank").json()
    assert (after["opening_balance"], after["blocked"]) == (100_000.0, 0.0)
    assert (after["withdrawn"], after["ledger"][-1]["kind"]) == (2_400_000.0, "WITHDRAW")

    _save_opening(client, 2_500_000.0)
    r = client.post("/api/paper-trades", json={"signal_id": signal_id})
    assert r.status_code == 201, r.text
    trade = r.json()
    assert trade["blocked"] == 1_353_300.0
    final = client.get("/api/bank").json()
    assert final["blocked"] == 1_353_300.0
    assert [e["kind"] for e in final["ledger"]] == ["OPEN", "WITHDRAW", "DEPOSIT"]
    assert trade["banked"] is True


def test_hello_carries_the_bank_and_a_trade_pushes_it(client: TestClient) -> None:
    signal_id = _gold_signal(client)
    with client.websocket_connect("/ws") as ws:
        hello = json.loads(ws.receive_text())
        assert hello["payload"]["bank"]["opening_balance"] == 2_500_000
        assert hello["payload"]["bank"]["blocked"] == 0.0
        r = client.post("/api/paper-trades", json={"signal_id": signal_id})
        assert r.status_code == 201, r.text
        for _ in range(400):
            frame = json.loads(ws.receive_text())
            if frame["type"] == "bank":
                break
        else:
            raise AssertionError("no bank frame")
    assert frame["payload"]["blocked"] == 1_353_300.0
    assert frame["payload"]["open_trades"] == 1

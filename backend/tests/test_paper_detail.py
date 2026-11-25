"""One paper trade with the signal it came from (Milestone E19): the Trades page's detail."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from tests.test_bullion_trading import GOLD_KEY, M, _b, _desk
from tests.test_scorecard_api import _fire
from tradedisha.clock import epoch_ms_now
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.market.session import FeedSession


def _session(client: TestClient) -> FeedSession:
    return client.app.state.td.session  # type: ignore[attr-defined, no-any-return]


def _open_index_trade(client: TestClient) -> tuple[str, str]:
    """Fire a NIFTY signal and paper-trade it; returns (trade id, signal id)."""
    time.sleep(0.3)  # let the synthetic feed price the chain
    sid = _fire(_session(client))
    r = client.post("/api/paper-trades", json={"signal_id": sid})
    assert r.status_code == 201, r.text
    return str(r.json()["id"]), sid


def test_an_open_trade_comes_with_its_signal_and_live_pnl(client: TestClient) -> None:
    tid, sid = _open_index_trade(client)

    body = client.get(f"/api/paper-trades/{tid}").json()
    trade, signal = body["trade"], body["signal"]
    assert (trade["id"], trade["status"], trade["signal_id"]) == (tid, "open", sid)
    assert trade["ltp"] is not None
    assert trade["live_net"] is not None
    assert signal["id"] == sid
    assert signal["status"] == "traded"
    assert signal["config_version"] == 1
    assert set(signal["breakdown"]) >= {"group_scores", "group_weights", "indicators"}
    assert signal["outcome"]["result"] == "open"


def test_a_closed_trade_is_read_from_the_store(client: TestClient) -> None:
    tid, sid = _open_index_trade(client)
    closed = client.post(f"/api/paper-trades/{tid}/close")
    assert closed.status_code == 200, closed.text

    body = client.get(f"/api/paper-trades/{tid}").json()
    trade = body["trade"]
    assert (trade["status"], trade["exit_reason"]) == ("closed", "MANUAL")
    assert trade["net"] == closed.json()["net"]
    assert trade["ltp"] is None  # no live view once closed
    assert body["signal"]["id"] == sid


def test_an_unknown_trade_is_404(client: TestClient) -> None:
    r = client.get("/api/paper-trades/nope")
    assert r.status_code == 404
    assert r.json()["detail"] == "unknown trade"


def test_the_outcome_is_read_from_the_store_without_the_tracker(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before the feed starts there is no tracker; a past trade still shows its outcome."""
    tid, sid = _open_index_trade(client)
    monkeypatch.setattr(_session(client), "outcomes", None)

    signal = client.get(f"/api/paper-trades/{tid}").json()["signal"]
    assert signal["outcome"]["result"] == "open"
    assert client.get(f"/api/signals/{sid}").json()["outcome"]["result"] == "open"


def test_a_bullion_trade_resolves_through_the_same_endpoint(client: TestClient) -> None:
    td, desk = _desk(client)
    now = epoch_ms_now()
    assert client.portal is not None
    tick = Tick(key=GOLD_KEY, ts=now, ltp=135_000.0)
    client.portal.call(td.session.tick_bus.publish, StampedTick(tick, now))
    desk.signals.on_bias(_b("GOLD", now - M, 0.8), now)
    sid = str(client.get("/api/signals/active").json()[0]["id"])
    r = client.post("/api/paper-trades", json={"signal_id": sid})
    assert r.status_code == 201, r.text

    body = client.get(f"/api/paper-trades/{r.json()['id']}").json()
    assert (body["trade"]["index"], body["trade"]["direction"]) == ("GOLD", "BUY_FUT")
    assert (body["signal"]["id"], body["signal"]["index"]) == (sid, "GOLD")

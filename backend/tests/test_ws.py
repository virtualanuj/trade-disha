"""WebSocket contract: hello snapshot, then tick frames with latency stamps."""

import json
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tradedisha.engine.aggregator import Bias
from tradedisha.engine.bias_engine import BiasComputed, OverlayPoint
from tradedisha.market.news import Headline
from tradedisha.market.session import FeedSession


def test_hello_then_ticks(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        hello = json.loads(ws.receive_text())
        assert hello["type"] == "hello"
        assert hello["payload"]["health"]["feed"]["provider"] == "synthetic"
        assert [i["index"] for i in hello["payload"]["instruments"]] == ["NIFTY", "BANKNIFTY"]
        assert len(hello["payload"]["prices"]) == 2
        assert isinstance(hello["payload"]["flow"], list)

        seen: dict[str, dict[str, Any]] = {}
        for _ in range(40):
            frame = json.loads(ws.receive_text())
            if frame["type"] == "tick":
                seen[str(frame["payload"]["index"])] = frame
            if len(seen) == 2:
                break

        assert set(seen) == {"NIFTY", "BANKNIFTY"}
        nifty = seen["NIFTY"]
        assert nifty["t_in"] is not None
        assert nifty["t_out"] >= nifty["t_in"]
        prices = (nifty["payload"]["spot_ltp"], nifty["payload"]["fut_ltp"])
        assert any(p is not None for p in prices)  # whichever leg ticked first

        ws.send_text('{"type":"ping"}')
        for _ in range(40):
            frame = json.loads(ws.receive_text())
            if frame["type"] == "pong":
                break
        else:
            raise AssertionError("no pong")


def test_hello_carries_news_needing_login_on_synthetic(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        hello = json.loads(ws.receive_text())
    news = hello["payload"]["news"]
    assert (news["status"], news["error"], news["fetched_at"], news["items"]) == (
        "needs_login",
        None,
        None,
        [],
    )
    # the shipped stock list, so the page can colour each chip by its index
    assert news["stock_indices"]["SBIN"] == ["NIFTY", "BANKNIFTY"]
    assert news["stock_indices"]["ITC"] == ["NIFTY"]


def test_news_change_is_pushed(client: TestClient) -> None:
    td = client.app.state.td  # type: ignore[attr-defined]
    item = Headline("Market wrap", "Nifty up", "https://x/1", 1_700_000_000_000, ("SBIN", "ITC"))
    assert client.portal is not None
    with client.websocket_connect("/ws") as ws:
        ws.receive_text()  # hello
        client.portal.call(td.news._update, "ok", [item], None)
        for _ in range(400):
            frame = json.loads(ws.receive_text())
            if frame["type"] == "news":
                break
        else:
            raise AssertionError("no news frame")
    assert frame["payload"]["status"] == "ok"
    assert frame["payload"]["items"] == [
        {
            "heading": "Market wrap",
            "summary": "Nifty up",
            "link": "https://x/1",
            "published_ts": 1_700_000_000_000,
            "symbols": ["SBIN", "ITC"],
        }
    ]


def test_a_bias_frame_carries_the_gate_of_its_own_minute(client: TestClient) -> None:
    """The hub listens to the bias before the signal engines do; the frame's gates must still
    be the ones this minute's evaluation set, not the previous minute's."""
    time.sleep(0.3)  # let the synthetic feed price the chain
    session: FeedSession = client.app.state.td.session  # type: ignore[attr-defined]
    minute_ts = session.clock.now_ms() // 60_000 * 60_000 - 60_000
    bias = Bias(0.8, "Bullish", 80, {}, {}, [], False)
    computed = BiasComputed(
        "NIFTY", minute_ts, bias, OverlayPoint(minute_ts, None, None, None, None, 0)
    )
    with client.websocket_connect("/ws") as ws:
        ws.receive_text()  # hello
        assert client.portal is not None
        client.portal.call(session._on_bias, computed)  # every bias listener, on the loop
        for _ in range(400):
            frame = json.loads(ws.receive_text())
            p = frame["payload"]
            if frame["type"] == "bias" and p["bias"]["strength"] == 80:
                break
        else:
            raise AssertionError("no bias frame")
    gate = next(g for g in p["gates"] if g["index"] == "NIFTY")
    assert (gate["minute_ts"], gate["fired"]) == (minute_ts, True)


def test_every_frame_carries_the_market_clock(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In replay the market clock is the recorded day's; the page shows times from it."""
    replayed = 1_795_000_000_000  # some minute of an earlier day
    td = client.app.state.td  # type: ignore[attr-defined]
    monkeypatch.setattr(td.clock, "now_ms", lambda: replayed)
    with client.websocket_connect("/ws") as ws:
        hello = json.loads(ws.receive_text())
        tick = next(
            f for f in (json.loads(ws.receive_text()) for _ in range(40)) if f["type"] == "tick"
        )
    assert hello["t_mkt"] == replayed
    assert tick["t_mkt"] == replayed
    assert tick["ts"] != replayed  # `ts` stays the wall-clock send time

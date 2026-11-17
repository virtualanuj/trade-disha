"""WebSocket contract: hello snapshot, then tick frames with latency stamps."""

import json
from typing import Any

from fastapi.testclient import TestClient

from tradedisha.market.news import Headline


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

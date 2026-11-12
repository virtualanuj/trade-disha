"""WebSocket contract: hello snapshot, then tick frames with latency stamps."""

import json
from typing import Any

from fastapi.testclient import TestClient


def test_hello_then_ticks(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        hello = json.loads(ws.receive_text())
        assert hello["type"] == "hello"
        assert hello["payload"]["health"]["feed"]["provider"] == "synthetic"
        assert [i["index"] for i in hello["payload"]["instruments"]] == ["NIFTY", "BANKNIFTY"]
        assert len(hello["payload"]["prices"]) == 2

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

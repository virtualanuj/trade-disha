"""The config over the API: read, edit into a new version, history, revert."""

from typing import Any

import pytest
from fastapi.testclient import TestClient


def _values(client: TestClient) -> dict[str, Any]:
    params: dict[str, Any] = client.get("/api/parameters").json()["params"]
    return params


def test_parameters_start_at_version_one(client: TestClient) -> None:
    body = client.get("/api/parameters").json()
    assert (body["version"], body["tag"]) == (1, "initial")
    assert body["params"]["weights"]["trend"] == 0.4
    assert body["created_ts"] > 0


def test_schema_lists_every_field_with_help_and_limits(client: TestClient) -> None:
    fields = {f["path"]: f for f in client.get("/api/parameters/schema").json()}
    f = fields["bias.entry_threshold"]
    assert (f["group"], f["key"], f["kind"]) == ("bias", "entry_threshold", "number")
    assert (f["gt"], f["le"]) == (0, 1)
    assert f["help"]
    assert fields["signal.entry_mode"]["choices"] == ["minute_close", "trigger"]
    assert fields["signal.expiry_points.NIFTY.target"]["key"] == "expiry_points.NIFTY.target"


def test_saving_creates_a_version_and_takes_effect(client: TestClient) -> None:
    values = _values(client)
    values["weights"] = {**values["weights"], "trend": 0.5, "oi": 0.3, "premium": 0.2}
    r = client.put("/api/parameters", json={"tag": "more trend", "params": values})
    assert r.status_code == 200
    assert (r.json()["version"], r.json()["tag"]) == (2, "more trend")
    assert client.get("/api/parameters").json()["params"]["weights"]["trend"] == 0.5
    state = client.app.state.td  # type: ignore[attr-defined]
    assert state.params.params.weights.trend == 0.5
    assert state.session.config_version() == 2


def test_an_invalid_or_untagged_save_is_refused_and_nothing_changes(client: TestClient) -> None:
    values = _values(client)
    bad = {**values, "weights": {**values["weights"], "trend": 0.9}}
    r = client.put("/api/parameters", json={"tag": "broken", "params": bad})
    assert r.status_code == 422
    assert r.json()["detail"][0]["field"] == "weights"

    changed = {**values, "bias": {**values["bias"], "entry_threshold": 0.6}}
    r = client.put("/api/parameters", json={"tag": " ", "params": changed})
    assert r.status_code == 422
    assert r.json()["detail"][0]["field"] == "tag"

    r = client.put("/api/parameters", json={"tag": "same", "params": values})
    assert r.status_code == 422
    assert client.get("/api/parameters").json()["version"] == 1


def test_history_and_revert(client: TestClient) -> None:
    values = _values(client)
    values["bias"] = {**values["bias"], "entry_threshold": 0.6}
    client.put("/api/parameters", json={"tag": "higher bar", "params": values})

    history = client.get("/api/parameters/versions").json()
    assert [(v["version"], v["tag"], v["source"], v["active"]) for v in history] == [
        (2, "higher bar", "edit", True),
        (1, "initial", "seed", False),
    ]
    one = client.get("/api/parameters/versions/1").json()
    assert one["params"]["bias"]["entry_threshold"] == 0.5
    assert client.get("/api/parameters/versions/9").status_code == 404

    r = client.post("/api/parameters/versions/1/revert", json={})
    assert r.status_code == 200
    assert (r.json()["version"], r.json()["tag"]) == (3, "Revert to v1")
    assert r.json()["params"]["bias"]["entry_threshold"] == 0.5
    newest = client.get("/api/parameters/versions").json()[0]
    assert (newest["source"], newest["reverted_from"], newest["active"]) == ("revert", 1, True)

    r = client.post("/api/parameters/versions/2/revert", json={"tag": "back to 0.6"})
    assert r.json()["tag"] == "back to 0.6"
    assert client.post("/api/parameters/versions/9/revert", json={}).status_code == 422


def test_a_save_is_announced_on_the_websocket(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["payload"]["parameters"]["version"] == 1
        values = _values(client)
        values["bias"] = {**values["bias"], "entry_threshold": 0.6}
        client.put("/api/parameters", json={"tag": "higher bar", "params": values})
        for _ in range(500):
            frame = ws.receive_json()
            if frame["type"] == "parameters":
                break
        assert frame["type"] == "parameters"
        assert (frame["payload"]["version"], frame["payload"]["tag"]) == (2, "higher bar")
        assert frame["payload"]["effective_from_minute_ts"] % 60_000 == 0


def test_a_save_applies_from_the_market_clocks_next_minute(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parameters apply at the next minute close of the market clock (in replay, the
    recorded day's), so that is the minute announced."""
    replayed = 1_795_000_012_345
    td = client.app.state.td  # type: ignore[attr-defined]
    monkeypatch.setattr(td.clock, "now_ms", lambda: replayed)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        values = _values(client)
        values["bias"] = {**values["bias"], "entry_threshold": 0.6}
        client.put("/api/parameters", json={"tag": "higher bar", "params": values})
        for _ in range(500):
            frame = ws.receive_json()
            if frame["type"] == "parameters":
                break
    assert frame["payload"]["effective_from_minute_ts"] == (replayed // 60_000 + 1) * 60_000

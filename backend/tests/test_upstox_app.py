"""The app with the live feed selected but nobody logged in yet."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tradedisha.config import Settings
from tradedisha.main import create_app


@pytest.fixture
def live_client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        db_path=tmp_path / "live.sqlite",
        data_dir=tmp_path,
        feed_provider="upstox",
        upstox_api_key="the-key",
        upstox_api_secret="the-secret",
    )
    with TestClient(create_app(settings)) as c:
        yield c


def test_app_serves_and_asks_for_login(live_client: TestClient) -> None:
    body = live_client.get("/api/health").json()
    assert body["auth"] == "missing"
    assert body["feed"]["state"] == "disconnected"
    assert body["feed"]["provider"] == "upstox"

    assert live_client.get("/api/instruments").json() == []
    assert live_client.get("/api/signals").json() == []
    assert live_client.get("/api/chain/NIFTY").status_code == 404
    with live_client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
    assert hello["type"] == "hello"
    assert hello["payload"]["instruments"] == []


def test_login_redirects_to_upstox(live_client: TestClient) -> None:
    r = live_client.get("/api/auth/login", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://api.upstox.com/v2/login/authorization/dialog?")
    assert "client_id=the-key" in r.headers["location"]
    assert "the-secret" not in r.headers["location"]


def test_callback_rejects_a_login_this_app_did_not_start(live_client: TestClient) -> None:
    r = live_client.get("/api/auth/callback?code=x&state=forged", follow_redirects=False)
    assert r.status_code == 400
    assert live_client.get("/api/health").json()["auth"] == "missing"


def test_synthetic_feed_has_no_login(client: TestClient) -> None:
    assert client.get("/api/auth/login", follow_redirects=False).status_code == 400

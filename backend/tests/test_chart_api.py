"""The chart at other intervals over HTTP and the socket (E27)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from tradedisha.app_state import AppState
from tradedisha.clock import epoch_ms_now
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.indicators.chart import ChartPoint
from tradedisha.market.candles import Candle
from tradedisha.market.chart_bars import ChartBar


def _state(client: TestClient) -> AppState:
    return client.app.state.td  # type: ignore[attr-defined, no-any-return]


@pytest.mark.parametrize("interval", ["10s", "30s", "1m", "5m"])
def test_a_chart_at_each_interval(client: TestClient, interval: str) -> None:
    r = client.get("/api/chart/nifty", params={"interval": interval})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["name"], body["interval"]) == ("NIFTY", interval)
    assert len(body["overlays"]) == len(body["candles"])
    assert isinstance(body["vol_candles"], list)


def test_ten_second_bars_come_from_the_ticks(client: TestClient) -> None:
    td = _state(client)
    spot = td.session.resolved["NIFTY"].spot.instrument_key
    later = (epoch_ms_now() // 10_000 + 6) * 10_000  # ahead of the synthetic ticks
    assert client.portal is not None
    for dt, ltp in [(0, 25_000.0), (3_000, 25_010.0), (10_000, 25_005.0)]:
        tick = Tick(key=spot, ts=later + dt, ltp=ltp)
        client.portal.call(td.session.tick_bus.publish, StampedTick(tick, later + dt))
    bars = client.get("/api/chart/NIFTY", params={"interval": "10s"}).json()["candles"]
    mine = [b for b in bars if b["t"] == later]
    assert mine
    assert (mine[0]["o"], mine[0]["h"], mine[0]["c"]) == (25_000.0, 25_010.0, 25_010.0)


def test_unknown_chart_and_bad_interval(client: TestClient) -> None:
    assert client.get("/api/chart/NOPE").status_code == 404
    assert client.get("/api/chart/NIFTY", params={"interval": "2m"}).status_code == 422


def test_a_closed_bar_reaches_the_socket(client: TestClient) -> None:
    td = _state(client)
    now = epoch_ms_now()
    bar = ChartBar(
        "NIFTY",
        "10s",
        "price",
        Candle("K", now, 1.0, 2.0, 0.5, 1.5, 0),
        ChartPoint(now, 1.0, None, None, None, 0),
    )
    with client.websocket_connect("/ws") as ws:
        json.loads(ws.receive_text())  # hello
        assert client.portal is not None
        client.portal.call(td.session._on_chart_bar, bar)
        for _ in range(400):
            frame = json.loads(ws.receive_text())
            if frame["type"] == "chart_bar":
                break
        else:
            raise AssertionError("no chart_bar frame")
    p = frame["payload"]
    assert (p["name"], p["interval"], p["role"]) == ("NIFTY", "10s", "price")
    assert p["candle"]["h"] == 2.0
    assert p["overlay"]["ema_fast"] == 1.0

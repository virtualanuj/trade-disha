"""REST contracts for Milestone 1."""

import time

from fastapi.testclient import TestClient


def test_health_reports_feed_and_market(client: TestClient) -> None:
    body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["milestone"] == 1
    assert body["market_status"] in {"pre_open", "live", "closed", "holiday"}
    assert body["auth"] == "not_required"
    assert body["feed"]["provider"] == "synthetic"
    assert body["feed"]["state"] == "connected"
    assert body["feed"]["subscribed"] == 2 * (2 + 5 * 2)


def test_instruments_resolved_for_both_indices(client: TestClient) -> None:
    body = client.get("/api/instruments").json()

    assert [r["index"] for r in body] == ["NIFTY", "BANKNIFTY"]
    nifty = body[0]
    assert nifty["spot"]["instrument_key"] == "NSE_INDEX|Nifty 50"
    assert nifty["strike_step"] == 50
    assert len(nifty["strikes"]) == 5
    assert nifty["strikes"][2]["strike"] == nifty["atm"]


def test_metrics_accepts_client_samples(client: TestClient) -> None:
    r = client.post(
        "/api/metrics/client", json={"out_to_recv_ms": [3, 4, 5], "recv_to_paint_ms": [8]}
    )
    assert r.status_code == 204

    body = client.get("/api/metrics").json()
    by_hop = {h["hop"]: h for h in body["last_1m"]}
    assert by_hop["out_to_recv"]["n"] == 3
    assert by_hop["recv_to_paint"]["p50"] == 8


def test_ticks_are_recorded_to_sqlite(client: TestClient) -> None:
    time.sleep(0.7)  # housekeeping flushes every 0.5 s
    state = client.app.state.td  # type: ignore[attr-defined]
    assert state.session.tick_store.count() > 0

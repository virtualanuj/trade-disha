"""REST contracts for Milestone 1."""

import time
from pathlib import Path

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


def test_chain_endpoint_returns_window(client: TestClient) -> None:
    time.sleep(0.3)
    body = client.get("/api/chain/nifty").json()

    assert body["index"] == "NIFTY"
    assert body["step"] == 50
    assert len(body["rows"]) == 5
    assert body["rows"][2]["strike"] == body["atm"]
    assert body["total_ce_oi"] > 0
    assert body["pcr"] is not None
    assert body["max_pain"] in [r["strike"] for r in body["rows"]]
    assert client.get("/api/chain/FOO").status_code == 404


def test_parameters_endpoint_and_reload(client: TestClient, tmp_path: Path) -> None:
    body = client.get("/api/parameters").json()
    assert body["params"]["weights"]["trend"] == 0.4
    assert body["path"].endswith("params.toml")

    state = client.app.state.td  # type: ignore[attr-defined]
    bad = tmp_path / "bad.toml"
    bad.write_text("[weights]\ntrend = 0.9\noi = 0.9\npremium = 0.9\n")
    state.params.path = bad
    r = client.post("/api/parameters/reload")
    assert r.status_code == 422
    assert r.json()["detail"][0]["field"] == "weights"
    assert state.params.params.weights.trend == 0.4  # previous set kept

    good = tmp_path / "good.toml"
    good.write_text("[weights]\ntrend = 0.5\noi = 0.3\npremium = 0.2\n")
    state.params.path = good
    r = client.post("/api/parameters/reload")
    assert r.status_code == 200
    assert r.json()["params"]["weights"]["trend"] == 0.5


def test_candles_and_bias_endpoints_shape(client: TestClient) -> None:
    body = client.get("/api/candles/NIFTY?minutes=10").json()
    assert body["index"] == "NIFTY"
    assert body["spot_key"] == "NSE_INDEX|Nifty 50"
    assert isinstance(body["candles"], list)
    assert client.get("/api/bias/NIFTY").json() is None  # no minute closed yet
    assert client.get("/api/bias/NIFTY/history").json() == []
    assert client.get("/api/candles/FOO").status_code == 404


def test_signals_endpoints_shape(client: TestClient) -> None:
    assert client.get("/api/signals").json() == []
    assert client.get("/api/signals/active").json() == []
    assert client.get("/api/signals/gates").json() == []
    assert client.get("/api/signals/nope").status_code == 404


def test_paper_trade_endpoints_shape(client: TestClient) -> None:
    assert client.get("/api/paper-trades").json() == []
    journal = client.get("/api/journal/stats?from=2026-11-01&to=2026-11-30").json()
    assert journal["open_trades"] == 0
    assert journal["stats"][0]["scope"] == "overall"
    assert journal["stats"][0]["trades"] == 0
    assert client.post("/api/paper-trades", json={"signal_id": "nope"}).status_code == 404
    assert client.post("/api/paper-trades/nope/close").status_code == 404


def test_health_has_no_banner_once_the_synthetic_feed_is_ticking(client: TestClient) -> None:
    time.sleep(0.3)
    body = client.get("/api/health").json()
    assert body["feed_live"] is True
    assert body["banner"] is None
    assert body["serves_frontend"] is False


def test_data_usage_and_prune(client: TestClient) -> None:
    time.sleep(0.7)
    usage = client.get("/api/data/usage?until_date=2099-01-01").json()
    assert usage["tick_rows"] > 0
    assert usage["prune_rows"] == usage["tick_rows"]
    assert usage["tick_days"] == 1

    assert client.get("/api/data/usage").json()["prune_rows"] == 0
    old = client.post("/api/data/prune-ticks", json={"until_date": "2000-01-01"}).json()
    assert old["rows_deleted"] == 0

    done = client.post("/api/data/prune-ticks", json={"until_date": "2099-01-01"}).json()
    assert done["rows_deleted"] >= usage["tick_rows"]
    state = client.app.state.td  # type: ignore[attr-defined]
    kinds = [r["kind"] for r in state.conn.execute("SELECT kind FROM feed_events")]
    assert kinds.count("ticks_pruned") == 2

"""Outcomes reach the API: on each signal, and summed up in the scorecard."""

import time

from fastapi.testclient import TestClient

from tradedisha.engine.aggregator import Bias
from tradedisha.engine.bias_engine import BiasComputed, OverlayPoint
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.market.session import FeedSession


def _fire(session: FeedSession) -> str:
    """Push a strong bullish minute through the real signal engine; returns the signal id."""
    assert session.signals is not None
    minute_ts = session.clock.now_ms() // 60_000 * 60_000 - 60_000
    bias = Bias(0.8, "Bullish", 80, {}, {}, [], False)
    overlay = OverlayPoint(minute_ts, None, None, None, None, 0)
    session.signals.on_bias(BiasComputed("NIFTY", minute_ts, bias, overlay))
    assert session.signals.gates["NIFTY"].fired, session.signals.gates["NIFTY"]
    return session.signals.active["NIFTY"].id


def test_signal_carries_its_outcome_and_the_scorecard_counts_it(client: TestClient) -> None:
    time.sleep(0.3)  # let the synthetic feed price the chain
    session: FeedSession = client.app.state.td.session  # type: ignore[attr-defined]
    sid = _fire(session)

    fresh = client.get(f"/api/signals/{sid}").json()
    assert fresh["outcome"]["result"] == "open"
    assert fresh["outcome"]["final"] is False

    target = fresh["target_price"] + 1
    tick = Tick(key=fresh["instrument_key"], ts=session.clock.now_ms(), ltp=target)
    session.tick_bus.publish(StampedTick(tick, tick.ts))

    hit = client.get(f"/api/signals/{sid}").json()["outcome"]
    assert hit["result"] == "target"
    assert hit["best_price"] == target
    assert hit["best_pct"] > 0
    listed = client.get("/api/signals").json()
    assert [s["outcome"]["result"] for s in listed if s["id"] == sid] == ["target"]

    rows = {r["scope"]: r for r in client.get("/api/signals/scorecard").json()}
    assert (rows["all"]["rule"], rows["all"]["shadow"]) == ("minute_close", False)
    assert rows["all"]["signals"] >= 1
    assert rows["NIFTY"]["target_pct"] == 100.0
    assert client.get("/api/signals/scorecard?index=banknifty").json() == []


def test_scorecard_takes_a_date_range(client: TestClient) -> None:
    assert client.get("/api/signals/scorecard?from=2020-01-01&to=2020-01-31").json() == []
    assert client.get("/api/signals/scorecard?from=2020-02-01&to=2020-01-01").status_code == 422


def _fire_shadow(session: FeedSession) -> str:
    """A setup plus agreeing order flow, through the real shadow engine."""
    shadow = session.shadow_signals
    assert shadow is not None
    minute_ts = session.clock.now_ms() // 60_000 * 60_000 - 60_000
    bias = Bias(0.4, "Bullish", 40, {}, {}, [], False)
    overlay = OverlayPoint(minute_ts, None, None, None, None, 0)
    for _ in range(50):  # the live flow tracker is calling in too; retry past its readings
        shadow.on_bias(BiasComputed("NIFTY", minute_ts, bias, overlay))
        now = session.clock.now_ms()
        shadow.on_flow("NIFTY", now, 0.9)
        shadow.on_flow("NIFTY", now + 5000, 0.9)
        if "NIFTY" in shadow.active:
            return shadow.active["NIFTY"].id
    raise AssertionError(shadow.gates.get("NIFTY"))


def test_shadow_signal_is_listed_and_scored_but_never_active_or_tradable(
    client: TestClient,
) -> None:
    time.sleep(0.3)
    session: FeedSession = client.app.state.td.session  # type: ignore[attr-defined]
    sid = _fire_shadow(session)

    assert all(s["id"] != sid for s in client.get("/api/signals/active").json())
    listed = next(s for s in client.get("/api/signals").json() if s["id"] == sid)
    assert (listed["shadow"], listed["entry_mode"]) == (True, "trigger")
    assert listed["flow_score"] == 0.9
    assert listed["entry_price"] == listed["entry_ask"]
    assert listed["outcome"]["result"] == "open"

    refused = client.post("/api/paper-trades", json={"signal_id": sid})
    assert refused.status_code == 409
    assert "shadow" in refused.json()["detail"]

    rows = client.get("/api/signals/scorecard").json()
    assert ("trigger", True, "all") in {(r["rule"], r["shadow"], r["scope"]) for r in rows}


def test_flow_readings_are_served(client: TestClient) -> None:
    time.sleep(1.3)  # readings are taken once a second; the first sees almost nothing

    flow = {f["index"]: f for f in client.get("/api/flow").json()}

    assert set(flow) == {"NIFTY", "BANKNIFTY"}
    assert -1 <= flow["NIFTY"]["score"] <= 1
    assert flow["NIFTY"]["fut_book"] is not None
    assert flow["NIFTY"]["live"] is False  # the trigger is the shadow rule by default

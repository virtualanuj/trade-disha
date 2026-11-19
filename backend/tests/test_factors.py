"""Factor switches (Milestone E15): stored per index or metal, over the API and the socket."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tradedisha.api.analysis import BiasOut
from tradedisha.app_state import AppState
from tradedisha.engine.factors import FactorSwitches
from tradedisha.events import EventBus, FactorsChanged
from tradedisha.store.db import connect


async def test_switches_persist_per_scope_and_announce_each_change() -> None:
    conn = connect(":memory:")
    bus = EventBus()
    seen: list[FactorsChanged] = []
    bus.subscribe(FactorsChanged, seen.append)
    sw = FactorSwitches(conn, bus)
    assert sw.off_for("NIFTY") == frozenset()  # every factor on by default

    await sw.set("NIFTY", "crude", enabled=False)
    await sw.set("NIFTY", "gold", enabled=False)
    await sw.set("NIFTY", "gold", enabled=False)  # no change: no event
    assert await sw.set("GOLD", "peer_metal", enabled=False) == {
        "GOLD": ["peer_metal"],
        "NIFTY": ["crude", "gold"],
    }
    assert [e.scope for e in seen] == ["NIFTY", "NIFTY", "GOLD"]

    again = FactorSwitches(conn)  # after a restart
    assert again.off_for("NIFTY") == {"crude", "gold"}
    assert again.off_for("BANKNIFTY") == frozenset()

    await again.set("NIFTY", "crude", enabled=True)
    await again.all_on("GOLD")
    assert FactorSwitches(conn).all_off() == {"NIFTY": ["gold"]}


def test_an_unreadable_stored_value_means_every_factor_is_on() -> None:
    conn = connect(":memory:")
    conn.execute("INSERT INTO app_state (key, value) VALUES ('factors_off', 'not json')")
    assert FactorSwitches(conn).all_off() == {}


def test_the_api_switches_a_factor_for_one_index_only(client: TestClient) -> None:
    assert client.get("/api/factors").json() == {"off": {}}
    r = client.put("/api/factors/NIFTY/ema_cross", json={"enabled": False})
    assert r.status_code == 200
    assert r.json() == {"off": {"NIFTY": ["ema_cross"]}}
    td: AppState = client.app.state.td  # type: ignore[attr-defined]
    assert td.session.factors_off("NIFTY") == {"ema_cross"}
    assert td.session.factors_off("BANKNIFTY") == frozenset()

    client.put("/api/factors/NIFTY/pcr", json={"enabled": False})
    assert client.delete("/api/factors/NIFTY").json() == {"off": {}}


def test_the_api_refuses_an_unknown_scope_or_a_malformed_name(client: TestClient) -> None:
    assert client.put("/api/factors/GOLD/crude", json={"enabled": False}).status_code == 404
    assert client.put("/api/factors/NIFTY/Bad-Name", json={"enabled": False}).status_code == 422
    assert client.delete("/api/factors/FINNIFTY").status_code == 404


def test_the_socket_says_hello_with_the_switches_and_sends_each_change(
    client: TestClient,
) -> None:
    client.put("/api/factors/BANKNIFTY/pcr", json={"enabled": False})
    with client.websocket_connect("/ws") as ws:
        hello = json.loads(ws.receive_text())
        assert hello["payload"]["factors"] == {"off": {"BANKNIFTY": ["pcr"]}}
        client.put("/api/factors/NIFTY/iv_change", json={"enabled": False})
        for _ in range(2000):  # frames queued before it (ticks, chains) come first
            frame = json.loads(ws.receive_text())
            if frame["type"] == "factors":
                break
        else:
            raise AssertionError("no factors frame")
    assert frame["payload"] == {"off": {"BANKNIFTY": ["pcr"], "NIFTY": ["iv_change"]}}


def test_a_breakdown_stored_before_switches_existed_reads_as_on() -> None:
    old = {"name": "pcr", "group": "oi", "score": 0.1, "note": "", "quality": "ok", "value": {}}
    b = BiasOut.model_validate(
        {
            "index": "NIFTY",
            "minute_ts": 0,
            "bias": 0.0,
            "label": "Neutral",
            "strength": 0,
            "is_expiry_day": False,
            "group_scores": {},
            "group_weights": {},
            "indicators": [{**old, "weight": 0.1, "contribution": 0.01}],
        }
    )
    assert b.indicators[0].enabled is True

"""Factor switches in the versioned config (Milestone E16, replacing E15's separate store)."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tradedisha.api.analysis import BiasOut
from tradedisha.app_state import AppState
from tradedisha.config import REPO_ROOT
from tradedisha.engine.bias_engine import run_indicators
from tradedisha.engine.bullion_bias import run_bullion_indicators
from tradedisha.indicators.futures import book_imbalance, futures_oi_buildup, net_volume
from tradedisha.indicators.gift import gift_gap
from tradedisha.indicators.macro import (
    bullion_macro_indicators,
    index_macro_indicators,
    peer_metal,
)
from tradedisha.instruments.resolve import resolve_index
from tradedisha.instruments.synthetic_master import SPEC, build_synthetic_master
from tradedisha.market.chain import ChainState
from tradedisha.parameters import ParameterService, ParameterSet, ParameterValidationError
from tradedisha.parameters.model import BullionFactors, IndexFactors, NiftyFactors
from tradedisha.parameters.schema import describe
from tradedisha.store.db import connect

SHIPPED = REPO_ROOT / "config" / "params.toml"


# -- the model -----------------------------------------------------------------------


def test_every_factor_is_on_by_default_and_an_older_version_loads_all_on() -> None:
    p = ParameterSet()
    for scope in ("NIFTY", "BANKNIFTY", "GOLD", "SILVER"):
        assert p.factors.off_for(scope) == frozenset()
    stored = p.model_dump(mode="json")
    del stored["factors"]  # saved before E16
    assert ParameterSet.model_validate(stored) == p


def test_off_for_maps_each_scope_to_its_own_switches() -> None:
    p = ParameterSet.model_validate(
        {"factors": {"nifty": {"crude": "off", "gift_nifty": "off"}, "gold": {"peer_metal": "off"}}}
    )
    assert p.factors.off_for("NIFTY") == {"crude", "gift_nifty"}
    assert p.factors.off_for("BANKNIFTY") == frozenset()
    assert p.factors.off_for("GOLD") == {"peer_metal"}
    assert p.factors.off_for("SILVER") == frozenset()
    assert p.factors.off_for("FINNIFTY") == frozenset()


def test_a_switch_is_on_or_off_and_names_are_checked() -> None:
    with pytest.raises(ValidationError):
        ParameterSet.model_validate({"factors": {"nifty": {"crude": "maybe"}}})
    with pytest.raises(ValidationError):
        ParameterSet.model_validate({"factors": {"banknifty": {"gift_nifty": "off"}}})


def _index_names(index: str) -> set[str]:
    master = build_synthetic_master(date(2026, 11, 12))
    spot = float(SPEC[index]["base"])
    r = resolve_index(master, index, date(2026, 11, 12), spot, strike_window=3)
    p = ParameterSet()
    names = {x.name for x in run_indicators([], [], None, ChainState.from_resolved(r), p)}
    names |= {x.name for x in index_macro_indicators({}, p.macro)}
    if index == "NIFTY":
        names.add(gift_gap(None, 1, p.macro).name)
    return names


def _bullion_names() -> set[str]:
    p = ParameterSet()
    out = run_bullion_indicators([], p)
    out += [futures_oi_buildup([], p.bullion), net_volume([], p.bullion)]
    out += [book_imbalance([], p.bullion), peer_metal("SILVER", [])]
    out += bullion_macro_indicators({}, p.macro)
    return {x.name for x in out}


def test_every_factor_the_engines_emit_has_a_switch_and_no_switch_is_spare() -> None:
    assert _index_names("NIFTY") == set(NiftyFactors.model_fields)
    assert _index_names("BANKNIFTY") == set(IndexFactors.model_fields)
    assert _bullion_names() == set(BullionFactors.model_fields)


def test_the_shipped_file_seeds_every_switch_on() -> None:
    text = SHIPPED.read_text()
    assert "[factors.nifty]" in text
    assert "[factors.silver]" in text


def test_the_typed_editor_has_no_factor_fields() -> None:
    assert not [f for f in describe(ParameterSet()) if f.group == "factors"]


# -- one flip, one version -------------------------------------------------------------


@pytest.fixture
def svc(tmp_path: Path) -> ParameterService:
    s = ParameterService(connect(tmp_path / "p.sqlite"), SHIPPED)
    s.load()
    return s


def test_a_flip_saves_one_version_with_a_fixed_tag(svc: ParameterService) -> None:
    off = svc.set_factor("NIFTY", "pcr", enabled=False)
    assert (off.version, off.tag) == (2, "Factor NIFTY.pcr: off")
    assert svc.params.factors.off_for("NIFTY") == {"pcr"}
    assert svc.params.factors.off_for("BANKNIFTY") == frozenset()
    same = svc.set_factor("NIFTY", "pcr", enabled=False)  # nothing to change: no version
    assert same.version == 2
    on = svc.set_factor("NIFTY", "pcr", enabled=True)
    assert (on.version, on.tag) == (3, "Factor NIFTY.pcr: on")
    assert svc.set_factor("GOLD", "peer_metal", enabled=False).tag == (
        "Factor GOLD.peer_metal: off"
    )


@pytest.mark.parametrize(("scope", "name"), [("FINNIFTY", "pcr"), ("BANKNIFTY", "gift_nifty")])
def test_a_flip_of_an_unknown_factor_is_refused(
    svc: ParameterService, scope: str, name: str
) -> None:
    with pytest.raises(ParameterValidationError):
        svc.set_factor(scope, name, enabled=False)
    assert svc.current.version == 1


def test_a_typed_save_keeps_the_switches_in_force(svc: ParameterService) -> None:
    svc.set_factor("NIFTY", "crude", enabled=False)
    values = svc.params.model_dump(mode="json")
    del values["factors"]  # the typed editor has no factor fields
    values["bias"]["entry_threshold"] = 0.6
    saved = svc.save_values(values, "higher bar")
    assert saved.params.bias.entry_threshold == 0.6
    assert svc.params.factors.off_for("NIFTY") == {"crude"}  # not reset to all on


# -- over the API and into the bias ----------------------------------------------------


def test_the_api_flips_a_factor_and_announces_the_version(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.receive_text()  # hello
        r = client.put("/api/parameters/factors/NIFTY/ema_cross", json={"enabled": False})
        assert r.status_code == 200
        assert (r.json()["version"], r.json()["tag"]) == (2, "Factor NIFTY.ema_cross: off")
        assert r.json()["params"]["factors"]["nifty"]["ema_cross"] == "off"
        for _ in range(2000):  # frames queued before it (ticks, chains) come first
            frame = json.loads(ws.receive_text())
            if frame["type"] == "parameters":
                break
        else:
            raise AssertionError("no parameters frame")
    assert frame["payload"]["version"] == 2
    td: AppState = client.app.state.td  # type: ignore[attr-defined]
    assert td.session.params().factors.off_for("NIFTY") == {"ema_cross"}


def test_the_api_refuses_an_unknown_scope_or_factor(client: TestClient) -> None:
    put = client.put
    assert put("/api/parameters/factors/FINNIFTY/pcr", json={"enabled": False}).status_code == 422
    bad = put("/api/parameters/factors/BANKNIFTY/gift_nifty", json={"enabled": False})
    assert bad.status_code == 422
    assert bad.json()["detail"] == [
        {"field": "factors", "message": "BANKNIFTY has no factor gift_nifty"}
    ]
    assert client.get("/api/parameters").json()["version"] == 1


def test_the_next_bias_leaves_out_a_factor_switched_off(client: TestClient) -> None:
    client.put("/api/parameters/factors/NIFTY/pcr", json={"enabled": False})
    td: AppState = client.app.state.td  # type: ignore[attr-defined]
    engine = td.session.bias
    assert engine is not None
    for index in ("NIFTY", "BANKNIFTY"):
        engine.evaluate(index, 0)
    nifty = {c.result.name: c for c in engine.latest["NIFTY"].bias.contributions}
    bank = {c.result.name: c for c in engine.latest["BANKNIFTY"].bias.contributions}
    assert (nifty["pcr"].enabled, nifty["pcr"].weight) == (False, 0.0)
    assert bank["pcr"].enabled


def test_the_old_switch_store_is_cleared(tmp_path: Path) -> None:
    db = tmp_path / "old.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE app_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO app_state VALUES ('factors_off', '{\"NIFTY\":[\"pcr\"]}')")
    conn.execute("PRAGMA user_version = 13")
    conn.commit()
    conn.close()
    migrated = connect(db)
    assert migrated.execute("SELECT COUNT(*) FROM app_state").fetchone()[0] == 0


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

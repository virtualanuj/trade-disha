"""ParameterSet validation and the versioned parameter service."""

import sqlite3
from pathlib import Path

import pytest

from tradedisha.config import REPO_ROOT
from tradedisha.parameters import ParameterService, ParameterSet, ParameterValidationError
from tradedisha.parameters.schema import describe
from tradedisha.parameters.service import load_file, parse_params
from tradedisha.store.db import connect

SHIPPED = REPO_ROOT / "config" / "params.toml"


def _with(params: ParameterSet, **bias: float) -> ParameterSet:
    return params.model_copy(update={"bias": params.bias.model_copy(update=bias)})


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return connect(tmp_path / "p.sqlite")


def test_shipped_file_matches_model_defaults() -> None:
    assert load_file(SHIPPED) == ParameterSet()


def test_a_stored_set_reads_back_the_same() -> None:
    p = ParameterSet()
    assert ParameterSet.model_validate(p.model_dump(mode="json")) == p


def test_every_field_is_described_for_the_editor() -> None:
    fields = {f.path: f for f in describe(ParameterSet())}
    assert fields["bias.entry_threshold"].kind == "number"
    assert fields["bias.entry_threshold"].help
    assert (fields["bias.entry_threshold"].gt, fields["bias.entry_threshold"].le) == (0, 1)
    assert fields["trend.ema_fast"].kind == "integer"
    assert fields["signal.entry_mode"].choices == ["minute_close", "trigger"]
    assert fields["signal.last_signal_time"].kind == "time"
    assert fields["signal.expiry_points.NIFTY.target"].kind == "number"
    assert fields["signal.expiry_points.BANKNIFTY.stop"].group == "signal"
    assert all(f.help for f in fields.values())


def test_weights_must_sum_to_one() -> None:
    with pytest.raises(ParameterValidationError) as e:
        parse_params("[weights]\ntrend = 0.5\noi = 0.5\npremium = 0.5\n")
    assert any(err["field"] == "weights" for err in e.value.errors)


def test_unknown_key_and_bad_toml_are_reported() -> None:
    with pytest.raises(ParameterValidationError) as e:
        parse_params("[trend]\nema_fats = 9\n")
    assert e.value.errors[0]["field"] == "trend.ema_fats"
    with pytest.raises(ParameterValidationError) as e2:
        parse_params("[trend\n")
    assert e2.value.errors[0]["field"] == "<toml>"


def test_times_parse_from_strings() -> None:
    p = parse_params('[signal]\nlast_signal_time = "14:30"\n[paper]\nsquare_off_time = "15:10"\n')
    assert p.signal.last_signal_time.hour == 14
    assert p.paper.square_off_time.minute == 10


def test_an_empty_database_takes_version_one_from_the_file(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    f = tmp_path / "p.toml"
    f.write_text("[bias]\nentry_threshold = 0.6\n")
    svc = ParameterService(conn, f)
    loaded = svc.load()
    assert (loaded.version, loaded.tag) == (1, "initial")
    assert svc.params.bias.entry_threshold == 0.6
    assert [(v.version, v.source) for v in svc.versions()] == [(1, "seed")]

    # the file is only the starting point: later edits to it change nothing
    f.write_text("[bias]\nentry_threshold = 0.7\n")
    again = ParameterService(conn, f).load()
    assert (again.version, again.params.bias.entry_threshold) == (1, 0.6)


def test_a_missing_or_invalid_seed_file_is_reported(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    with pytest.raises(ParameterValidationError):
        ParameterService(conn, tmp_path / "nope.toml").load()


def test_saving_makes_a_new_version_with_the_tag(conn: sqlite3.Connection) -> None:
    svc = ParameterService(conn, SHIPPED)
    svc.load()
    saved = svc.save(_with(svc.params, entry_threshold=0.6), "  higher bar  ")
    assert (saved.version, saved.tag) == (2, "higher bar")
    assert svc.current.version == 2
    assert svc.params.bias.entry_threshold == 0.6
    assert [(v.version, v.tag, v.source) for v in svc.versions()] == [
        (2, "higher bar", "edit"),
        (1, "initial", "seed"),
    ]
    # and it is what a restart finds
    assert ParameterService(conn, SHIPPED).load().version == 2


def test_a_save_needs_a_tag_and_a_change(conn: sqlite3.Connection) -> None:
    svc = ParameterService(conn, SHIPPED)
    svc.load()
    changed = _with(svc.params, entry_threshold=0.6)
    for tag in ("", "   ", "x" * 61):
        with pytest.raises(ParameterValidationError) as e:
            svc.save(changed, tag)
        assert e.value.errors[0]["field"] == "tag"
    with pytest.raises(ParameterValidationError) as e2:
        svc.save(svc.params, "same again")
    assert e2.value.errors[0]["field"] == "<params>"
    assert svc.current.version == 1


def test_save_values_validates_and_keeps_the_previous_set_on_failure(
    conn: sqlite3.Connection,
) -> None:
    svc = ParameterService(conn, SHIPPED)
    svc.load()
    values = svc.params.model_dump(mode="json")
    values["bias"]["entry_threshold"] = 0.1  # below the neutral band
    with pytest.raises(ParameterValidationError) as e:
        svc.save_values(values, "too low")
    assert e.value.errors[0]["field"] == "bias"
    assert svc.current.version == 1

    values["bias"]["entry_threshold"] = 0.7
    assert svc.save_values(values, "ok").params.bias.entry_threshold == 0.7


def test_revert_copies_an_old_version_into_a_new_one(conn: sqlite3.Connection) -> None:
    svc = ParameterService(conn, SHIPPED)
    svc.load()
    svc.save(_with(svc.params, entry_threshold=0.6), "higher bar")
    back = svc.revert(1)
    assert (back.version, back.tag) == (3, "Revert to v1")
    assert svc.params.bias.entry_threshold == 0.5
    newest = svc.versions()[0]
    assert (newest.source, newest.reverted_from) == ("revert", 1)
    assert svc.revert(2, "try the higher bar again").tag == "try the higher bar again"

    with pytest.raises(ParameterValidationError) as e:
        svc.revert(99)
    assert e.value.errors[0]["field"] == "version"
    with pytest.raises(ParameterValidationError):
        svc.revert(4)  # already the values in force


def test_a_stored_version_the_model_no_longer_accepts_falls_back_to_the_file(
    conn: sqlite3.Connection,
) -> None:
    svc = ParameterService(conn, SHIPPED)
    svc.load()
    conn.execute(
        "INSERT INTO config_versions (version, tag, created_ts, source, params_json)"
        " VALUES (2, 'from an older build', 1, 'edit', '{\"bias\":{\"gone\":1}}')"
    )
    loaded = ParameterService(conn, SHIPPED).load()
    assert loaded.version == 3
    assert loaded.params == ParameterSet()
    assert "v2" in loaded.tag


def test_setup_threshold_must_sit_between_the_neutral_band_and_the_entry_threshold() -> None:
    ok = parse_params("[bias]\nneutral_band = 0.2\nsetup_threshold = 0.3\nentry_threshold = 0.5\n")
    assert ok.bias.setup_threshold == 0.3
    for bad in (0.2, 0.55):
        with pytest.raises(ParameterValidationError) as e:
            parse_params(f"[bias]\nsetup_threshold = {bad}\n")
        assert e.value.errors[0]["field"] == "bias"


def test_entry_mode_is_minute_close_unless_set_to_trigger() -> None:
    assert ParameterSet().signal.entry_mode == "minute_close"
    assert parse_params('[signal]\nentry_mode = "trigger"\n').signal.entry_mode == "trigger"
    with pytest.raises(ParameterValidationError):
        parse_params('[signal]\nentry_mode = "instant"\n')


def test_flow_mix_weights_must_sum_to_one() -> None:
    assert ParameterSet().flow.trigger_score > 0
    with pytest.raises(ParameterValidationError) as e:
        parse_params("[flow]\nw_fut_book = 0.9\n")
    assert e.value.errors[0]["field"] == "flow"

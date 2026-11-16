"""ParameterSet validation and the TOML service."""

from pathlib import Path

import pytest

from tradedisha.config import REPO_ROOT
from tradedisha.parameters import ParameterService, ParameterSet, ParameterValidationError
from tradedisha.parameters.service import parse_params


def test_shipped_file_matches_model_defaults() -> None:
    shipped = ParameterService(REPO_ROOT / "config" / "params.toml").load().params
    assert shipped == ParameterSet()


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


def test_reload_keeps_previous_on_failure(tmp_path: Path) -> None:
    f = tmp_path / "p.toml"
    f.write_text("[bias]\nentry_threshold = 0.6\n")
    svc = ParameterService(f)
    svc.load()
    assert svc.params.bias.entry_threshold == 0.6

    f.write_text("[bias]\nentry_threshold = 0.1\nneutral_band = 0.2\n")  # band >= threshold
    with pytest.raises(ParameterValidationError):
        svc.reload()
    assert svc.params.bias.entry_threshold == 0.6

    f.write_text("[bias]\nentry_threshold = 0.7\n")
    assert svc.reload().params.bias.entry_threshold == 0.7


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

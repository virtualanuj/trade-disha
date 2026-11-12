"""Instrument resolution rules (spec §5.2)."""

from datetime import date

import pytest

from tradedisha.instruments.resolve import (
    ResolutionError,
    atm_strike,
    infer_strike_step,
    nearest_expiry,
    needs_recenter,
    resolve_index,
)
from tradedisha.instruments.synthetic_master import (
    build_synthetic_master,
    last_weekday_of_month,
    monthly_expiries,
    next_weekdays,
)

TODAY = date(2026, 11, 12)  # a Thursday
NEXT_TUESDAY = date(2026, 11, 17)
LAST_TUESDAY_NOV = date(2026, 11, 24)


def test_atm_rounds_to_nearest_step() -> None:
    assert atm_strike(25_024.9, 50) == 25_000
    assert atm_strike(25_025.0, 50) == 25_050
    assert atm_strike(56_149, 100) == 56_100


def test_infer_strike_step_uses_most_common_gap() -> None:
    assert infer_strike_step([24_900, 24_950, 25_000, 25_100, 25_050]) == 50
    with pytest.raises(ResolutionError):
        infer_strike_step([25_000])


def test_nearest_expiry_includes_today_and_skips_past() -> None:
    exps = [date(2026, 11, 10), date(2026, 11, 12), date(2026, 11, 17)]
    assert nearest_expiry(exps, TODAY) == TODAY
    assert nearest_expiry(exps, date(2026, 11, 13)) == date(2026, 11, 17)
    with pytest.raises(ResolutionError):
        nearest_expiry([date(2026, 11, 10)], TODAY)


def test_synthetic_calendar_helpers() -> None:
    assert next_weekdays(TODAY, 1, 2) == [NEXT_TUESDAY, date(2026, 11, 24)]
    assert last_weekday_of_month(2026, 11, 1) == LAST_TUESDAY_NOV
    assert monthly_expiries(TODAY, 1, 2) == [LAST_TUESDAY_NOV, date(2026, 12, 29)]


def test_resolve_nifty_picks_weekly_expiry_and_window() -> None:
    master = build_synthetic_master(TODAY)
    r = resolve_index(master, "NIFTY", TODAY, 25_012.0, strike_window=10)

    assert r.spot.instrument_key == "NSE_INDEX|Nifty 50"
    assert r.future.expiry == LAST_TUESDAY_NOV
    assert r.options_expiry == NEXT_TUESDAY
    assert r.is_expiry_day is False
    assert r.strike_step == 50
    assert r.atm == 25_000
    assert [p.strike for p in r.strikes][:3] == [24_500, 24_550, 24_600]
    assert len(r.strikes) == 21
    assert r.lot_size == 75
    assert len(r.all_keys) == 2 + 42
    assert r.strikes[10].ce.trading_symbol == "NIFTY17NOV2625000CE"


def test_resolve_banknifty_uses_monthly_expiry() -> None:
    master = build_synthetic_master(TODAY)
    r = resolve_index(master, "BANKNIFTY", TODAY, 56_240.0, strike_window=10)

    assert r.options_expiry == LAST_TUESDAY_NOV
    assert r.strike_step == 100
    assert r.atm == 56_200
    assert r.lot_size == 35


def test_resolve_on_expiry_day_keeps_expiring_contract() -> None:
    master = build_synthetic_master(TODAY)
    r = resolve_index(master, "NIFTY", NEXT_TUESDAY, 25_000.0, strike_window=5)

    assert r.options_expiry == NEXT_TUESDAY
    assert r.is_expiry_day is True


def test_resolve_narrows_window_at_chain_edge() -> None:
    master = build_synthetic_master(TODAY, strikes_each_side=3)
    r = resolve_index(master, "NIFTY", TODAY, 25_000.0, strike_window=10)

    assert len(r.strikes) == 7


def test_resolve_raises_when_index_missing() -> None:
    with pytest.raises(ResolutionError):
        resolve_index([], "NIFTY", TODAY, 25_000.0, strike_window=10)


def test_needs_recenter_threshold() -> None:
    assert needs_recenter(25_000, 25_100, 50, 2) is True
    assert needs_recenter(25_000, 25_050, 50, 2) is False
    assert needs_recenter(25_000, 24_900, 50, 2) is True

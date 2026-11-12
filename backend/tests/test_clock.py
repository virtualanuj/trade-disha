"""Market status rules and holiday parsing."""

from datetime import date, datetime, time
from pathlib import Path

from tradedisha.clock import IST, DrivenClock, MarketClock, load_holidays


def _clock(at: datetime, holidays: frozenset[date] = frozenset()) -> MarketClock:
    return MarketClock(
        market_open=time(9, 15),
        market_close=time(15, 30),
        pre_open_start=time(9, 0),
        holidays=holidays,
        source=lambda: at,
    )


def test_status_through_the_day() -> None:
    thu = date(2026, 11, 12)
    assert _clock(datetime.combine(thu, time(8, 59), tzinfo=IST)).status() == "closed"
    assert _clock(datetime.combine(thu, time(9, 0), tzinfo=IST)).status() == "pre_open"
    assert _clock(datetime.combine(thu, time(9, 15), tzinfo=IST)).status() == "live"
    assert _clock(datetime.combine(thu, time(15, 29, 59), tzinfo=IST)).status() == "live"
    assert _clock(datetime.combine(thu, time(15, 30), tzinfo=IST)).status() == "closed"


def test_weekend_and_holiday() -> None:
    sat = datetime(2026, 11, 14, 11, 0, tzinfo=IST)
    assert _clock(sat).status() == "holiday"
    rep = datetime(2026, 1, 26, 11, 0, tzinfo=IST)
    assert _clock(rep, frozenset({date(2026, 1, 26)})).status() == "holiday"
    assert _clock(rep).status() == "live"


def test_load_holidays_ignores_comments(tmp_path: Path) -> None:
    f = tmp_path / "h.txt"
    f.write_text("# header\n2026-01-26  # Republic Day\n\n2026-08-15\n")
    assert load_holidays(f) == frozenset({date(2026, 1, 26), date(2026, 8, 15)})
    assert load_holidays(tmp_path / "missing.txt") == frozenset()


def test_driven_clock_follows_set_ms() -> None:
    c = DrivenClock(datetime(2026, 11, 12, 9, 0, tzinfo=IST))
    clock = _clock(datetime.now(tz=IST))
    clock_driven = MarketClock(
        market_open=time(9, 15), market_close=time(15, 30), pre_open_start=time(9, 0), source=c
    )
    assert clock_driven.status() == "pre_open"
    c.set_ms(int(datetime(2026, 11, 12, 10, 0, tzinfo=IST).timestamp() * 1000))
    assert clock_driven.status() == "live"
    assert clock.now().tzinfo is not None

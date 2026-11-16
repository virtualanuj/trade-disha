"""Market status rules and holiday parsing."""

from datetime import date, datetime, time
from pathlib import Path

from tradedisha.clock import (
    IST,
    DrivenClock,
    MarketCalendar,
    MarketClock,
    load_calendar,
    load_holidays,
    ms_to_ist,
)


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


def _mcx(at: datetime, cal: MarketCalendar | None = None) -> MarketClock:
    cal = cal or MarketCalendar(frozenset(), {})
    return MarketClock(
        market_open=time(9, 0),
        market_close=time(23, 30),
        pre_open_start=time(9, 0),  # MCX has no pre-open window here
        holidays=cal.holidays,
        late_opens=cal.late_opens,
        source=lambda: at,
    )


def test_mcx_hours_through_the_day() -> None:
    mon = date(2026, 11, 16)
    assert _mcx(datetime.combine(mon, time(8, 59), tzinfo=IST)).status() == "closed"
    assert _mcx(datetime.combine(mon, time(9, 0), tzinfo=IST)).status() == "live"
    assert _mcx(datetime.combine(mon, time(15, 31), tzinfo=IST)).status() == "live"
    assert _mcx(datetime.combine(mon, time(23, 29, 59), tzinfo=IST)).status() == "live"
    assert _mcx(datetime.combine(mon, time(23, 30), tzinfo=IST)).status() == "closed"


def test_mcx_evening_session_on_an_nse_holiday() -> None:
    cal = MarketCalendar(frozenset(), {date(2026, 12, 25): time(17, 0)})
    xmas = date(2026, 12, 25)
    assert _mcx(datetime.combine(xmas, time(11, 0), tzinfo=IST), cal).status() == "closed"
    assert _mcx(datetime.combine(xmas, time(17, 0), tzinfo=IST), cal).status() == "live"
    start, end = _mcx(datetime.combine(xmas, time(11, 0), tzinfo=IST), cal).session_bounds()
    assert ms_to_ist(start).time() == time(17, 0)
    assert ms_to_ist(end).time() == time(23, 30)


def test_mcx_full_holiday() -> None:
    cal = MarketCalendar(frozenset({date(2026, 10, 2)}), {})
    assert _mcx(datetime(2026, 10, 2, 12, 0, tzinfo=IST), cal).status() == "holiday"


def test_load_calendar_reads_late_opens(tmp_path: Path) -> None:
    f = tmp_path / "mcx.txt"
    f.write_text("# header\n2026-10-02  # closed\n2026-12-25 17:00  # evening only\n")
    cal = load_calendar(f)
    assert cal.holidays == frozenset({date(2026, 10, 2)})
    assert cal.late_opens == {date(2026, 12, 25): time(17, 0)}
    assert load_calendar(tmp_path / "missing.txt") == MarketCalendar(frozenset(), {})

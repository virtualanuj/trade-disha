"""Index day statistics for the details view."""

from datetime import date

import httpx

from tradedisha.market.backfill import fetch_52w_range, parse_range
from tradedisha.market.candles import Candle
from tradedisha.market.stats import IndexStats, compute_stats


def _c(minute: int, o: float, h: float, low: float, c: float) -> Candle:
    return Candle("NSE_INDEX|Nifty 50", minute * 60_000, o, h, low, c)


DAY = [_c(0, 25_000, 25_040, 24_980, 25_020), _c(1, 25_020, 25_100, 25_010, 25_090)]


def _stats(**over: object) -> IndexStats:
    args: dict[str, object] = {
        "spot": 25_060.0,
        "fut": 25_095.5,
        "prev_close": 24_900.0,
        "candles": DAY,
        "range_52w": (26_300.0, 21_700.0),
        "vix": 13.2,
        "vix_prev_close": 12.0,
        "updated_ts": 123,
    }
    args.update(over)
    return compute_stats("NIFTY", **args)  # type: ignore[arg-type]


def test_day_figures_change_premium_and_vix() -> None:
    s = _stats()

    assert (s.day_open, s.day_high, s.day_low) == (25_000, 25_100, 24_980)
    assert s.range_pos == round(80 / 120, 4)
    assert (s.prev_close, s.change, s.change_pct) == (24_900.0, 160.0, 0.64)
    assert (s.high_52w, s.low_52w) == (26_300.0, 21_700.0)
    assert s.fut_premium == 35.5
    assert (s.vix, s.vix_change_pct) == (13.2, 10.0)
    assert s.updated_ts == 123


def test_a_tick_beyond_the_forming_candle_moves_the_day_extreme() -> None:
    s = _stats(spot=25_130.0)
    assert s.day_high == 25_130.0
    assert s.range_pos == 1.0


def test_todays_extreme_widens_the_52_week_range() -> None:
    s = _stats(spot=25_060.0, range_52w=(25_050.0, 24_990.0))
    assert (s.high_52w, s.low_52w) == (25_100.0, 24_980.0)


def test_missing_sources_leave_fields_empty_rather_than_wrong() -> None:
    s = _stats(prev_close=None, range_52w=None, vix=None, vix_prev_close=None, fut=None)
    assert (s.change, s.change_pct) == (None, None)
    assert (s.high_52w, s.low_52w) == (None, None)
    assert (s.vix, s.vix_change_pct, s.fut_premium) == (None, None, None)
    assert s.day_open == 25_000  # what is known is still shown


def test_no_range_position_before_the_day_has_a_range() -> None:
    s = _stats(spot=25_000.0, candles=[_c(0, 25_000, 25_000, 25_000, 25_000)])
    assert s.range_pos is None

    empty = _stats(spot=None, candles=[])
    assert (empty.day_open, empty.day_high, empty.day_low, empty.range_pos) == (
        None,
        None,
        None,
        None,
    )


DAILY = [
    ["2026-11-12T00:00:00+05:30", 25_900, 26_010, 25_850, 25_990, 0, 0],
    ["2026-11-11T00:00:00+05:30", 25_700, 25_950, 25_640, 25_900, 0, 0],
    ["2026-03-02T00:00:00+05:30", 22_000, 22_150, 21_743.65, 22_100, 0, 0],
]


def test_52_week_range_is_the_highest_high_and_lowest_low() -> None:
    assert parse_range(DAILY) == (26_010.0, 21_743.65)
    assert parse_range([]) is None


async def test_52_week_fetch_asks_for_the_year_up_to_yesterday() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.raw_path.decode()
        assert path.endswith("/NSE_INDEX%7CNifty%2050/days/1/2026-11-12/2025-11-13")
        return httpx.Response(200, json={"status": "success", "data": {"candles": DAILY}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        found = await fetch_52w_range(client, "tok", "NSE_INDEX|Nifty 50", date(2026, 11, 13))
    assert found == (26_010.0, 21_743.65)

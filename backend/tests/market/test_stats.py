"""Index day statistics for the details view."""

from datetime import date

import httpx

from tradedisha.config import Settings
from tradedisha.market.backfill import fetch_52w_range, parse_range
from tradedisha.market.candles import Candle
from tradedisha.market.stats import (
    SENSEX_KEY,
    VIX_KEY,
    IndexStats,
    SectorQuote,
    compute_stats,
    market_wide_keys,
    sector_key,
    sector_label,
    sector_quotes,
)


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


def test_traded_only_range_skips_placeholder_days() -> None:
    # real MCX GOLD rows: an untraded day early in the contract's life, then real trading
    rows = [
        ["2026-01-30T00:00:00+05:30", 247917.0, 247917.0, 247917.0, 247917.0, 0],
        ["2026-11-12T00:00:00+05:30", 139282.0, 139315.0, 135530.0, 136225.0, 13599],
        ["2026-11-13T00:00:00+05:30", 136502.0, 137587.0, 136055.0, 136705.0, 7227],
    ]
    assert parse_range(rows, traded_only=True) == (139315.0, 135530.0)
    assert parse_range(rows) == (247917.0, 135530.0)  # indices: no volume, keep every day


async def test_52_week_fetch_asks_for_the_year_up_to_yesterday() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.raw_path.decode()
        assert path.endswith("/NSE_INDEX%7CNifty%2050/days/1/2026-11-12/2025-11-13")
        return httpx.Response(200, json={"status": "success", "data": {"candles": DAILY}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        found = await fetch_52w_range(client, "tok", "NSE_INDEX|Nifty 50", date(2026, 11, 13))
    assert found == (26_010.0, 21_743.65)


# -- sector indices (Milestone E11) -------------------------------------------------


def test_sector_key_and_label() -> None:
    assert sector_key("Nifty Auto") == "NSE_INDEX|Nifty Auto"
    assert sector_label("Nifty Fin Service") == "Fin Service"
    assert sector_label("Nifty PSU Bank") == "PSU Bank"
    assert sector_label("NIFTY OIL AND GAS") == "OIL AND GAS"
    assert sector_label("India Consumption") == "India Consumption"  # no prefix to strip


def test_sector_quotes_level_change_and_percent_in_config_order() -> None:
    ltp = {"NSE_INDEX|Nifty IT": 37_880.0, "NSE_INDEX|Nifty Auto": 24_512.4}
    prev = {"NSE_INDEX|Nifty IT": 37_416.0, "NSE_INDEX|Nifty Auto": 24_712.4}
    assert sector_quotes(["Nifty IT", "Nifty Auto"], ltp, prev) == (
        SectorQuote("Nifty IT", "IT", 37_880.0, 37_416.0, 464.0, 1.24),
        SectorQuote("Nifty Auto", "Auto", 24_512.4, 24_712.4, -200.0, -0.81),
    )


def test_a_sector_without_prices_has_empty_fields() -> None:
    ltp = {"NSE_INDEX|Nifty IT": 37_880.0}
    assert sector_quotes(["Nifty IT", "Nifty Metal"], ltp, {}) == (
        SectorQuote("Nifty IT", "IT", 37_880.0, None, None, None),
        SectorQuote("Nifty Metal", "Metal", None, None, None, None),
    )
    assert sector_quotes([], ltp, {}) == ()


def test_compute_stats_carries_the_sectors() -> None:
    sectors = (SectorQuote("Nifty IT", "IT", 1.0, None, None, None),)
    assert _stats(sectors=sectors).sectors == sectors
    assert _stats().sectors == ()


def test_market_wide_keys_are_vix_each_sector_and_sensex_once() -> None:
    settings = Settings(_env_file=None, feed_provider="upstox")
    keys = market_wide_keys(settings)
    assert keys[0] == VIX_KEY
    assert len(keys) == len(set(keys))
    nifty = [sector_key(n) for n in settings.sector_indices["NIFTY"]]
    bank = [sector_key(n) for n in settings.sector_indices["BANKNIFTY"]]
    assert set(keys) == {VIX_KEY, *nifty, *bank, SENSEX_KEY}


def test_the_synthetic_feed_has_no_market_wide_keys() -> None:
    assert market_wide_keys(Settings(_env_file=None, feed_provider="synthetic")) == []


def test_default_sectors_as_decided() -> None:
    sectors = Settings(_env_file=None).sector_indices
    assert [sector_label(n) for n in sectors["NIFTY"]] == [
        "Auto", "FMCG", "IT", "Pharma", "Metal",
        "Energy", "Realty", "Media", "Fin Service", "PSU Bank",
    ]  # fmt: skip
    assert [sector_label(n) for n in sectors["BANKNIFTY"]] == [
        "PSU Bank",
        "Pvt Bank",
        "Fin Service",
    ]

"""Macro data (spec §6.8): currency and crude contracts, the tracker, the evidence view."""

from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from tradedisha.app_state import AppState
from tradedisha.clock import IST, ist_to_ms
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.indicators.macro import dollar_index_proxy
from tradedisha.instruments.models import Instrument
from tradedisha.instruments.upstox_master import parse_commodities, parse_currency_futures
from tradedisha.market.bullion import BullionContract, BullionTracker
from tradedisha.market.candles import MINUTE_MS
from tradedisha.market.macro import (
    MacroTracker,
    build_view,
    load_macro_contracts,
    macro_contracts_from,
)

TODAY = date(2026, 11, 18)


def _exp(d: date) -> int:
    return ist_to_ms(datetime(d.year, d.month, d.day, 12, 30, tzinfo=IST))


def _ccy(underlying: str, expiry: date, token: int, kind: str = "FUT") -> dict[str, Any]:
    """Shaped like the real NSE.json.gz NCD_FO records (checked on 2026-11-18)."""
    return {
        "segment": "NCD_FO",
        "name": underlying,
        "exchange": "NSE",
        "expiry": _exp(expiry),
        "instrument_type": kind,
        "underlying_symbol": underlying,
        "instrument_key": f"NCD_FO|{token}",
        "lot_size": 1,
        "tick_size": 0.25,
        "trading_symbol": f"{underlying} FUT {expiry:%d %b %y}".upper(),
    }


def _crude(expiry: date, token: int, underlying: str = "CRUDEOIL") -> dict[str, Any]:
    return {
        "segment": "MCX_FO",
        "name": "CRUDE OIL",
        "exchange": "MCX",
        "expiry": _exp(expiry),
        "instrument_type": "FUT",
        "underlying_symbol": underlying,
        "instrument_key": f"MCX_FO|{token}",
        "lot_size": 100,
        "tick_size": 100.0,
        "trading_symbol": f"{underlying} FUT {expiry:%d %b %y}".upper(),
    }


NSE_RECORDS = [
    _ccy("USDINR", date(2026, 11, 26), 1),
    _ccy("USDINR", date(2026, 12, 29), 2),
    _ccy("EURINR", date(2026, 11, 26), 3),
    _ccy("GBPINR", date(2026, 11, 26), 4),
    _ccy("JPYINR", date(2026, 11, 26), 5),
    _ccy("USDINR", date(2026, 11, 26), 6, kind="CE"),  # an option: not wanted
    {**_ccy("USDINR", date(2026, 11, 26), 7), "segment": "BCD_FO"},  # another exchange
]
MCX_RECORDS = [
    _crude(date(2026, 11, 18), 10),  # expires today: rolls to the next
    _crude(date(2026, 12, 17), 11),
    _crude(date(2026, 11, 18), 12, "CRUDEOILM"),
]


def _contracts() -> dict[str, Instrument]:
    return macro_contracts_from(
        parse_currency_futures(NSE_RECORDS, ["USDINR", "EURINR", "GBPINR", "JPYINR"]),
        parse_commodities(MCX_RECORDS, ["CRUDEOIL"]),
        TODAY,
    )


# -- contracts ----------------------------------------------------------------------


def test_currency_futures_are_parsed_from_the_nse_file() -> None:
    got = parse_currency_futures(NSE_RECORDS, ["USDINR"])
    assert sorted(i.instrument_key for i in got) == ["NCD_FO|1", "NCD_FO|2"]
    usd = next(i for i in got if i.instrument_key == "NCD_FO|1")
    assert (usd.name, usd.segment, usd.instrument_type) == ("USDINR", "NCD_FO", "FUT")
    assert usd.expiry == date(2026, 11, 26)
    assert usd.tick_size == pytest.approx(0.0025)  # paise in the file


def test_each_macro_name_gets_its_near_month() -> None:
    keys = {name: c.instrument_key for name, c in _contracts().items()}
    assert keys == {
        "usdinr": "NCD_FO|1",
        "eurinr": "NCD_FO|3",
        "gbpinr": "NCD_FO|4",
        "jpyinr": "NCD_FO|5",
        "crude": "MCX_FO|11",  # the expiring one is in delivery
    }


def test_a_missing_contract_is_left_out() -> None:
    got = macro_contracts_from(parse_currency_futures(NSE_RECORDS, ["USDINR"]), [], TODAY)
    assert set(got) == {"usdinr"}


async def test_no_instrument_files_means_no_macro_and_no_error(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(503))
    assert await load_macro_contracts(tmp_path, TODAY, transport=transport) == {}


# -- the tracker and the view ---------------------------------------------------------

T0 = ist_to_ms(datetime(2026, 11, 18, 10, 0, tzinfo=IST))


def _tick(key: str, minute: int, ltp: float, sec: int = 30) -> StampedTick:
    t = Tick(key=key, ts=T0 + minute * MINUTE_MS + sec * 1000, ltp=ltp)
    return StampedTick(t, t.ts)


def _fed(prices: dict[str, list[float]]) -> MacroTracker:
    """A tracker that has seen one tick a minute of each named contract."""
    tracker = MacroTracker(_contracts())
    for name, series in prices.items():
        key = tracker.contracts[name].instrument_key
        for m, p in enumerate(series):
            tracker.on_tick(_tick(key, m, p))
    return tracker


def test_the_tracker_builds_minute_candles_for_its_keys_only() -> None:
    tracker = _fed({"crude": [70.0, 71.0, 72.0]})
    tracker.on_tick(_tick("NSE_INDEX|Nifty 50", 3, 25_000.0))
    assert tracker.keys == {"NCD_FO|1", "NCD_FO|3", "NCD_FO|4", "NCD_FO|5", "MCX_FO|11"}
    assert [c.close for c in tracker.candles.closed("MCX_FO|11")] == [70.0, 71.0]
    assert tracker.last_tick_ts("crude") == T0 + 2 * MINUTE_MS + 30_000
    assert tracker.last_tick_ts("usdinr") is None


def test_the_view_has_closes_up_to_the_minute_with_the_forming_one_and_freshness() -> None:
    tracker = _fed({"crude": [70.0, 71.0, 72.0]})
    now = T0 + 3 * MINUTE_MS
    view = build_view(
        tracker, None, upto_minute_ts=T0 + 2 * MINUTE_MS, now_ms=now, max_age_ms=180_000
    )
    assert view["crude"].closes == (70.0, 71.0, 72.0)  # 72 is the minute still forming
    assert view["crude"].fresh
    earlier = build_view(
        tracker, None, upto_minute_ts=T0 + MINUTE_MS, now_ms=now, max_age_ms=180_000
    )
    assert earlier["crude"].closes == (70.0, 71.0)
    stale = build_view(
        tracker, None, upto_minute_ts=T0 + 2 * MINUTE_MS, now_ms=now + 600_000, max_age_ms=180_000
    )
    assert not stale["crude"].fresh
    assert "usdinr" not in view  # never ticked


def test_the_view_builds_the_dollar_from_all_four_currencies() -> None:
    tracker = _fed(
        {
            "usdinr": [88.0, 88.1],
            "eurinr": [102.0, 102.0],
            "gbpinr": [116.0, 116.0],
            "jpyinr": [57.0, 57.0],
        }
    )
    view = build_view(
        tracker, None, upto_minute_ts=T0 + MINUTE_MS, now_ms=T0 + 2 * MINUTE_MS, max_age_ms=180_000
    )
    expected = (
        dollar_index_proxy(88.0, 102.0, 116.0, 57.0),
        dollar_index_proxy(88.1, 102.0, 116.0, 57.0),
    )
    assert view["dollar"].closes == pytest.approx(expected)
    assert view["dollar"].closes[1] > view["dollar"].closes[0]  # the rupee alone moved
    assert view["dollar"].fresh
    assert math.isclose(view["usdinr"].closes[-1], 88.1)


def test_no_dollar_until_all_four_currencies_have_ticked() -> None:
    tracker = _fed({"usdinr": [88.0], "eurinr": [102.0], "gbpinr": [116.0]})
    view = build_view(tracker, None, upto_minute_ts=T0, now_ms=T0 + MINUTE_MS, max_age_ms=180_000)
    assert "dollar" not in view


def _metal(metal: str, key: str) -> BullionContract:
    inst = Instrument(
        key, f"{metal} FUT", "MCX", "MCX_FO", metal, "FUT", date(2026, 12, 4), None, 1, 1.0
    )
    return BullionContract(metal, inst, None)


def test_gold_and_silver_come_from_the_bullion_tracker() -> None:
    bullion = BullionTracker(
        {"GOLD": _metal("GOLD", "MCX_FO|1"), "SILVER": _metal("SILVER", "MCX_FO|2")}
    )
    for m, p in enumerate([1000.0, 1004.0]):
        bullion.on_tick(_tick("MCX_FO|1", m, p))
    view = build_view(
        None, bullion, upto_minute_ts=T0 + MINUTE_MS, now_ms=T0 + 2 * MINUTE_MS, max_age_ms=180_000
    )
    assert view["gold"].closes == (1000.0, 1004.0)
    assert view["gold"].fresh
    assert "silver" not in view
    assert build_view(None, None, upto_minute_ts=T0, now_ms=T0, max_age_ms=1) == {}


# -- routing in the session -----------------------------------------------------------


@pytest.mark.parametrize("key", ["NCD_FO|7074", "MCX_FO|472789"])
def test_side_market_ticks_never_reach_index_candles_or_liveness(
    client: TestClient, key: str
) -> None:
    td: AppState = client.app.state.td  # type: ignore[attr-defined]
    s = td.session
    assert client.portal is not None
    before = s.last_index_tick_ts
    future = (before or 0) + 10 * MINUTE_MS  # far ahead: would move liveness if it counted
    client.portal.call(s.tick_bus.publish, StampedTick(Tick(key=key, ts=future, ltp=88.0), future))
    assert s.last_index_tick_ts is None or s.last_index_tick_ts < future
    assert s.candles.current(key) is None
    s.bullion_tick_store.flush()
    rows = td.conn.execute("SELECT ltp FROM bullion_ticks WHERE key = ?", (key,)).fetchall()
    assert [r["ltp"] for r in rows] == [88.0]  # recorded with MCX, out of the NSE replay

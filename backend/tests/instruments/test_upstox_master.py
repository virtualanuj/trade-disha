"""Parsing the Upstox instrument file into what the resolver consumes."""

import gzip
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx

from tradedisha.clock import IST, ist_to_ms
from tradedisha.instruments.resolve import resolve_index
from tradedisha.instruments.upstox_master import (
    load_upstox_master,
    master_path,
    parse_master,
)

TODAY = date(2026, 11, 13)


def _exp(d: date) -> int:
    return ist_to_ms(datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=IST))


def _fo(sym: str, kind: str, expiry: date, strike: float, token: int, lot: int) -> dict[str, Any]:
    return {
        "segment": "NSE_FO",
        "name": sym,
        "exchange": "NSE",
        "expiry": _exp(expiry),
        "instrument_type": kind,
        "underlying_symbol": sym,
        "instrument_key": f"NSE_FO|{token}",
        "lot_size": lot,
        "tick_size": 5.0,
        "trading_symbol": f"{sym} {int(strike)} {kind} {expiry:%d %b %y}".upper(),
        "strike_price": strike,
    }


def _records() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [
        {
            "segment": "NSE_INDEX",
            "name": "Nifty 50",
            "exchange": "NSE",
            "instrument_type": "INDEX",
            "instrument_key": "NSE_INDEX|Nifty 50",
            "trading_symbol": "NIFTY",
        },
        {
            "segment": "NSE_INDEX",
            "name": "Nifty Fin Service",
            "exchange": "NSE",
            "instrument_type": "INDEX",
            "instrument_key": "NSE_INDEX|Nifty Fin Service",
            "trading_symbol": "FINNIFTY",
        },
        {"segment": "NSE_EQ", "name": "X", "instrument_type": "EQ", "instrument_key": "NSE_EQ|X"},
    ]
    token = 40_000
    for expiry in (date(2026, 11, 23), date(2026, 12, 29)):
        token += 1
        out.append(_fo("NIFTY", "FUT", expiry, 0.0, token, 65))
    for expiry in (date(2026, 11, 10), date(2026, 11, 17), date(2026, 11, 23)):
        for i in range(-6, 7):
            for kind in ("CE", "PE"):
                token += 1
                out.append(_fo("NIFTY", kind, expiry, 25_000.0 + 50 * i, token, 65))
    out.append(_fo("FINNIFTY", "CE", date(2026, 11, 24), 25_000.0, 99_999, 60))
    return out


def test_parse_keeps_only_the_wanted_index_and_maps_fields() -> None:
    master = parse_master(_records(), ["NIFTY"])

    assert {i.name for i in master} == {"Nifty 50", "NIFTY"}
    opt = next(i for i in master if i.instrument_type == "CE")
    assert opt.instrument_key.startswith("NSE_FO|")
    assert opt.expiry == date(2026, 11, 10)
    assert opt.lot_size == 65
    assert opt.tick_size == 0.05
    fut = next(i for i in master if i.instrument_type == "FUT")
    assert fut.strike is None


def test_resolver_works_on_the_parsed_master() -> None:
    master = parse_master(_records(), ["NIFTY"])
    r = resolve_index(master, "NIFTY", TODAY, 25_031.0, strike_window=2)

    assert r.spot.instrument_key == "NSE_INDEX|Nifty 50"
    assert r.future.expiry == date(2026, 11, 23)
    assert r.options_expiry == date(2026, 11, 17)  # the 10th has passed
    assert r.strike_step == 50
    assert r.atm == 25_050
    assert [p.strike for p in r.strikes] == [24_950, 25_000, 25_050, 25_100, 25_150]
    assert r.lot_size == 65


async def test_master_is_downloaded_once_per_day(tmp_path: Path) -> None:
    calls = 0

    def handle(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=gzip.compress(json.dumps(_records()).encode()))

    transport = httpx.MockTransport(handle)
    first = await load_upstox_master(tmp_path, TODAY, ["NIFTY"], transport=transport)
    second = await load_upstox_master(tmp_path, TODAY, ["NIFTY"], transport=transport)

    assert calls == 1
    assert first == second
    assert master_path(tmp_path, TODAY).exists()

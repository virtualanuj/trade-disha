"""BULLION: MCX contracts, the full quote, snapshot maths, the tracker and the live wiring."""

import gzip
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from tradedisha.app_state import AppState
from tradedisha.clock import IST, epoch_ms_now, ist_to_ms
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.feed.upstox import FullQuote, fetch_quotes, parse_full_quote
from tradedisha.indicators.series import vwap_series
from tradedisha.instruments.resolve import resolve_commodity_months
from tradedisha.instruments.upstox_master import mcx_master_path, parse_commodities
from tradedisha.market.bullion import (
    BullionContract,
    BullionTracker,
    enrich,
    gold_silver_ratio,
    load_contracts,
    merge_tick,
    metal_snapshot,
)
from tradedisha.market.candles import MINUTE_MS, Candle

TODAY = date(2026, 11, 16)


def _exp(d: date) -> int:
    return ist_to_ms(datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=IST))


def _fut(underlying: str, name: str, expiry: date, token: int) -> dict[str, Any]:
    """Shaped like the real MCX.json.gz records (checked on 2026-11-16)."""
    return {
        "segment": "MCX_FO",
        "name": name,
        "exchange": "MCX",
        "expiry": _exp(expiry),
        "instrument_type": "FUT",
        "asset_symbol": underlying,
        "underlying_symbol": underlying,
        "instrument_key": f"MCX_FO|{token}",
        "lot_size": 1,
        "tick_size": 100.0,
        "trading_symbol": f"{underlying} FUT {expiry:%d %b %y}".upper(),
        "strike_price": 0.0,
    }


def _records() -> list[dict[str, Any]]:
    return [
        _fut("GOLD", "GOLD", date(2026, 12, 4), 495213),
        _fut("GOLD", "GOLD", date(2027, 2, 5), 559933),
        _fut("GOLD", "GOLD", date(2027, 4, 5), 569424),
        _fut("GOLDM", "GOLD", date(2026, 12, 4), 575011),  # a mini: same `name`, not wanted
        _fut("GOLDPETAL", "GOLD", date(2026, 11, 30), 574841),
        _fut("SILVER", "SILVER", date(2026, 12, 4), 495214),
        _fut("SILVER", "SILVER", date(2027, 3, 5), 564619),
        _fut("SILVERM", "SILVER", date(2026, 11, 30), 483080),
        {**_fut("GOLD", "GOLD", date(2026, 12, 4), 1), "instrument_type": "CE"},
    ]


def _master() -> list[Any]:
    return parse_commodities(_records(), ["GOLD", "SILVER"])


# -- contracts ----------------------------------------------------------------------


def test_parse_keeps_only_gold_and_silver_futures_by_underlying() -> None:
    master = _master()

    assert sorted(i.instrument_key for i in master) == [
        "MCX_FO|495213",
        "MCX_FO|495214",
        "MCX_FO|559933",
        "MCX_FO|564619",
        "MCX_FO|569424",
    ]
    gold = next(i for i in master if i.instrument_key == "MCX_FO|495213")
    assert (gold.name, gold.exchange, gold.expiry) == ("GOLD", "MCX", date(2026, 12, 4))
    assert gold.tick_size == 1.0  # paise in the file
    assert gold.trading_symbol == "GOLD FUT 04 DEC 26"


@pytest.mark.parametrize(
    ("today", "name", "near", "nxt"),
    [
        (TODAY, "GOLD", "MCX_FO|495213", "MCX_FO|559933"),
        (date(2026, 12, 4), "GOLD", "MCX_FO|559933", "MCX_FO|569424"),  # rolls on expiry day
        (date(2026, 12, 3), "SILVER", "MCX_FO|495214", "MCX_FO|564619"),
        (date(2026, 12, 4), "SILVER", "MCX_FO|564619", None),  # the last one has no next
        (date(2027, 3, 5), "SILVER", None, None),  # nothing left
        (TODAY, "COPPER", None, None),
    ],
)
def test_near_and_next_month(today: date, name: str, near: str | None, nxt: str | None) -> None:
    got = resolve_commodity_months(_master(), name, today)
    if near is None:
        assert got is None
        return
    assert got is not None
    assert got[0].instrument_key == near
    assert (got[1].instrument_key if got[1] else None) == nxt


async def test_load_contracts_downloads_once(tmp_path: Path) -> None:
    calls = 0

    def handle(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=gzip.compress(json.dumps(_records()).encode()))

    transport = httpx.MockTransport(handle)
    first = await load_contracts(tmp_path, TODAY, transport=transport)
    second = await load_contracts(tmp_path, TODAY, transport=transport)

    assert calls == 1
    assert first == second
    assert first["GOLD"].near.instrument_key == "MCX_FO|495213"
    assert first["GOLD"].next is not None
    assert first["GOLD"].next.instrument_key == "MCX_FO|559933"
    assert mcx_master_path(tmp_path, TODAY).exists()


async def test_load_contracts_never_raises(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(503))
    assert await load_contracts(tmp_path, TODAY, transport=transport) == {}


# -- the full quote -------------------------------------------------------------------

# Upstox's answer for GOLD on 2026-11-16 (depth left out).
REAL_QUOTE: dict[str, Any] = {
    "ohlc": {"open": 135853.0, "high": 136055.0, "low": 134385.0, "close": 134914.0},
    "timestamp": "2026-11-16T14:53:59.574+05:30",
    "instrument_token": "MCX_FO|495213",
    "symbol": "GOLD26DECFUT",
    "last_price": 134914.0,
    "volume": 5040,
    "average_price": 135142.9,
    "oi": 15627.0,
    "net_change": -1791.0,
    "total_buy_quantity": 237.0,
    "total_sell_quantity": 153.0,
    "lower_circuit_limit": 132604.0,
    "upper_circuit_limit": 140806.0,
    "last_trade_time": "1794820957000",
    "oi_day_high": 0.0,
    "oi_day_low": 0.0,
}


def test_full_quote_previous_close_is_price_less_net_change() -> None:
    q = parse_full_quote(REAL_QUOTE)
    assert q == FullQuote(
        ltp=134914.0,
        prev_close=136705.0,
        day_open=135853.0,
        day_high=136055.0,
        day_low=134385.0,
        lower_circuit=132604.0,
        upper_circuit=140806.0,
    )


async def test_fetch_quotes_maps_back_to_instrument_keys() -> None:
    seen: list[str] = []

    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.params["instrument_key"])
        return httpx.Response(200, json={"data": {"MCX_FO:GOLD26DECFUT": REAL_QUOTE}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        got = await fetch_quotes(client, "tok", ["MCX_FO|495213"])

    assert seen == ["MCX_FO|495213"]
    assert got["MCX_FO|495213"].upper_circuit == 140806.0


async def test_enrich_fails_soft() -> None:
    contracts = {"GOLD": _contract("GOLD")}
    transport = httpx.MockTransport(lambda _: httpx.Response(500))
    async with httpx.AsyncClient(transport=transport) as client:
        got = await enrich(client, "tok", contracts, TODAY)

    assert got["GOLD"].quote is None
    assert got["GOLD"].range_high is None
    assert got["GOLD"].near == contracts["GOLD"].near


# -- maths ------------------------------------------------------------------------------


def _contract(metal: str, quote: FullQuote | None = None) -> BullionContract:
    months = resolve_commodity_months(_master(), metal, TODAY)
    assert months is not None
    return BullionContract(metal, months[0], months[1], quote=quote)


def test_gold_silver_ratio_compares_per_kilogram() -> None:
    assert gold_silver_ratio(134914.0, 170115.0) == 79.31
    assert gold_silver_ratio(None, 170115.0) is None


def test_merge_tick_keeps_unchanged_fields() -> None:
    old = Tick(key="k", ts=1, ltp=10.0, oi=500, tbq=7)
    new = Tick(key="k", ts=2, ltp=11.0, tbq=9)
    assert merge_tick(old, new) == Tick(key="k", ts=2, ltp=11.0, oi=500, tbq=9)


def test_metal_snapshot_figures() -> None:
    c = BullionContract(
        **{
            **_contract("GOLD").__dict__,
            "quote": parse_full_quote(REAL_QUOTE),
            "range_high": 140000.0,
            "range_low": 90000.0,
        }
    )
    near = Tick(
        key=c.near.instrument_key,
        ts=5,
        ltp=135000.0,
        close_prev=136705.0,
        bid=134990.0,
        ask=135010.0,
        tbq=300,
        tsq=150,
        atp=135100.0,
    )
    nxt = Tick(key="MCX_FO|559933", ts=5, ltp=137025.0)
    s = metal_snapshot(c, near, nxt, (135853.0, 136000.0, 134000.0))

    assert (s.change, s.change_pct) == (-1705.0, -1.25)
    assert s.range_pos == 0.5
    assert s.spread == 20.0
    assert s.buy_sell_ratio == 2.0
    assert (s.lower_circuit, s.upper_circuit) == (132604.0, 140806.0)
    assert (s.next_symbol, s.next_ltp) == ("GOLD FUT 05 FEB 27", 137025.0)
    assert (s.calendar_spread, s.calendar_spread_pct) == (2025.0, 1.5)
    assert (s.range_high, s.range_low) == (140000.0, 90000.0)


def test_metal_snapshot_before_any_tick_uses_the_start_quote() -> None:
    c = _contract("GOLD", parse_full_quote(REAL_QUOTE))
    s = metal_snapshot(c, None, None, (0.0, 0.0, 0.0))
    assert (s.ltp, s.prev_close, s.change) == (134914.0, 136705.0, -1791.0)
    assert (s.day_high, s.range_pos, s.spread, s.calendar_spread) == (None, None, None, None)


def test_vwap_series_is_running_close_times_volume() -> None:
    cs = [
        Candle("k", 0, 1, 1, 1, 100.0, volume=0),
        Candle("k", MINUTE_MS, 1, 1, 1, 100.0, volume=10),
        Candle("k", 2 * MINUTE_MS, 1, 1, 1, 130.0, volume=20),
    ]
    assert vwap_series(cs) == [None, 100.0, 120.0]


# -- tracker -----------------------------------------------------------------------------


def _tracker(closed: list[tuple[str, Candle]] | None = None) -> BullionTracker:
    contracts = {
        "GOLD": _contract("GOLD", parse_full_quote(REAL_QUOTE)),
        "SILVER": _contract("SILVER"),
    }
    sink = closed if closed is not None else []
    return BullionTracker(contracts, on_candle=lambda m, c: sink.append((m, c)))


def _st(key: str, ts: int, ltp: float, **kw: Any) -> StampedTick:  # noqa: ANN401
    return StampedTick(Tick(key=key, ts=ts, ltp=ltp, **kw), ts)


def test_tracker_follows_day_range_candles_and_next_month() -> None:
    closed: list[tuple[str, Candle]] = []
    t = _tracker(closed)
    t0 = 1_794_800_000_000 - 1_794_800_000_000 % MINUTE_MS

    assert t.keys == {"MCX_FO|495213", "MCX_FO|559933", "MCX_FO|495214", "MCX_FO|564619"}
    t.on_tick(_st("MCX_FO|495213", t0, 136100.0, volume=10))  # above the quote's high
    t.on_tick(_st("MCX_FO|559933", t0, 138000.0))
    t.on_tick(_st("NSE_FO|1", t0, 1.0))  # not bullion: ignored
    t.on_tick(_st("MCX_FO|495213", t0 + MINUTE_MS, 136050.0, volume=15))  # closes a minute

    gold = t.snapshot().metals[0]
    assert (gold.day_open, gold.day_high, gold.day_low) == (135853.0, 136100.0, 134385.0)
    assert gold.volume == 15
    assert gold.calendar_spread == 1950.0
    assert [(m, c.close) for m, c in closed] == [("GOLD", 136100.0)]
    assert [c.close for c in t.closed_candles("GOLD")] == [136100.0]


def test_tracker_prefers_the_feeds_day_candle() -> None:
    t = _tracker()
    t.on_tick(_st("MCX_FO|495213", 1, 136100.0, day_open=1.0, day_high=200000.0, day_low=0.5))
    gold = t.snapshot().metals[0]
    assert (gold.day_open, gold.day_high, gold.day_low) == (1.0, 200000.0, 0.5)


def test_tracker_without_ticks_or_quote_has_no_ratio() -> None:
    snap = _tracker().snapshot()
    assert [m.metal for m in snap.metals] == ["GOLD", "SILVER"]
    assert snap.metals[1].ltp is None
    assert snap.ratio is None


# -- live wiring -------------------------------------------------------------------------


def _with_bullion(client: TestClient) -> tuple[AppState, BullionTracker]:
    td: AppState = client.app.state.td  # type: ignore[attr-defined]
    tracker = BullionTracker(
        {"GOLD": _contract("GOLD"), "SILVER": _contract("SILVER")},
        on_candle=td.session._on_bullion_candle,
    )
    td.session.bullion = tracker
    td.session.tick_bus.subscribe(tracker.on_tick)
    return td, tracker


def _publish(client: TestClient, td: AppState, tick: Tick) -> None:
    assert client.portal is not None
    client.portal.call(td.session.tick_bus.publish, StampedTick(tick, epoch_ms_now()))


def test_bullion_ticks_are_tracked_but_not_recorded(client: TestClient) -> None:
    td, _ = _with_bullion(client)
    now = epoch_ms_now()
    _publish(client, td, Tick(key="MCX_FO|495213", ts=now, ltp=134914.0, close_prev=136705.0))
    _publish(client, td, Tick(key="MCX_FO|495214", ts=now, ltp=170115.0))
    assert client.portal is not None
    client.portal.call(td.session.tick_store.flush)

    assert td.session.tick_store.read_day(td.clock.today(), sorted(td.session.bullion_keys)) == []
    body = client.get("/api/bullion").json()
    assert body["ratio"] == 79.31
    gold = body["metals"][0]
    assert (gold["metal"], gold["ltp"], gold["change"]) == ("GOLD", 134914.0, -1791.0)
    assert gold["expiry"] == "2026-12-04"
    assert client.get("/api/bullion/gold/candles").json()["candles"] == []
    assert client.get("/api/bullion/copper/candles").status_code == 404


def test_synthetic_feed_has_no_bullion(client: TestClient) -> None:
    assert client.get("/api/bullion").json() == {"metals": [], "ratio": None}
    assert client.get("/api/bullion/GOLD/candles").status_code == 404


def test_ws_hello_bullion_and_candle_frames(client: TestClient) -> None:
    td, _ = _with_bullion(client)
    t0 = epoch_ms_now() // MINUTE_MS * MINUTE_MS - MINUTE_MS
    with client.websocket_connect("/ws") as ws:
        hello = json.loads(ws.receive_text())
        assert [m["metal"] for m in hello["payload"]["bullion"]["metals"]] == ["GOLD", "SILVER"]
        assert [c["metal"] for c in hello["payload"]["bullion_candles"]] == ["GOLD", "SILVER"]

        # the first tick only sets the volume baseline; the second trades 5
        _publish(client, td, Tick(key="MCX_FO|495213", ts=t0, ltp=135000.0, volume=4))
        _publish(client, td, Tick(key="MCX_FO|495213", ts=t0 + 1_000, ltp=135050.0, volume=9))
        _publish(client, td, Tick(key="MCX_FO|495213", ts=t0 + MINUTE_MS, ltp=135100.0, volume=9))
        seen: dict[str, dict[str, Any]] = {}
        for _ in range(600):
            frame = json.loads(ws.receive_text())
            if frame["type"] in ("bullion", "bullion_candle"):
                seen[frame["type"]] = frame
            if len(seen) == 2:
                break
        else:
            raise AssertionError(f"missing frames, saw {sorted(seen)}")

    assert seen["bullion"]["payload"]["metals"][0]["ltp"] == 135100.0
    candle = seen["bullion_candle"]["payload"]
    assert candle["metal"] == "GOLD"
    assert (candle["candle"]["t"], candle["candle"]["c"], candle["candle"]["v"]) == (
        t0,
        135050.0,
        5,
    )
    assert candle["overlay"]["vwap"] == 135050.0

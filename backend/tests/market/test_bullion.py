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
from tradedisha.clock import IST, DrivenClock, MarketClock, epoch_ms_now, ist_to_ms
from tradedisha.config import Settings
from tradedisha.events import EventBus
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import FeedHealth, Tick
from tradedisha.feed.upstox import FullQuote, fetch_quotes, parse_full_quote
from tradedisha.indicators.futures import MinuteBook
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
from tradedisha.market.session import FeedSession
from tradedisha.metrics.latency import LatencyTracker
from tradedisha.parameters import ParameterService
from tradedisha.store.db import connect

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


# -- hours and liveness (NSE and MCX trade different hours) -------------------------------


class _Connected:
    """A provider stub: only `health()` matters to the liveness checks."""

    name = "upstox"

    def health(self) -> FeedHealth:
        return FeedHealth("connected", None, 0, 0, self.name)


def _hours_session(tmp_path: Path, start: datetime) -> tuple[FeedSession, DrivenClock]:
    mcx_file = tmp_path / "mcx.txt"
    mcx_file.write_text("2026-12-25 17:00\n")
    settings = Settings(
        _env_file=None,
        db_path=tmp_path / "t.sqlite",
        enforce_signal_hours=True,
        mcx_holidays_file=mcx_file,
    )
    driven = DrivenClock(start)
    clock = MarketClock(
        market_open=settings.market_open,
        market_close=settings.market_close,
        pre_open_start=settings.pre_open_start,
        holidays=frozenset({date(2026, 12, 25)}),
        source=driven,
    )
    conn = connect(settings.db_path)
    params = ParameterService(conn, settings.params_path)
    params.load()
    session = FeedSession(
        settings,
        conn,
        clock,
        bus=EventBus(),
        latency=LatencyTracker(),
        params=lambda: params.params,
    )
    session.provider = _Connected()  # type: ignore[assignment]
    tracker = BullionTracker({"GOLD": _contract("GOLD"), "SILVER": _contract("SILVER")})
    session.bullion = tracker
    session.tick_bus.subscribe(session._on_tick)  # as `_start` wires them
    session.tick_bus.subscribe(tracker.on_tick)
    return session, driven


def _ist(h: int, m: int, s: int = 0, day: date = TODAY) -> datetime:
    return datetime(day.year, day.month, day.day, h, m, s, tzinfo=IST)


def _feed_events(session: FeedSession) -> list[str]:
    return [r["kind"] for r in session._conn.execute("SELECT kind FROM feed_events ORDER BY rowid")]


def test_bullion_ticks_do_not_keep_a_silent_index_feed_live(tmp_path: Path) -> None:
    session, driven = _hours_session(tmp_path, _ist(11, 0))
    nse_ts = ist_to_ms(_ist(11, 0))
    session.tick_bus.publish(_st("NSE_INDEX|Nifty 50", nse_ts, 25_000.0))
    assert session.feed_live()
    session._track_gap()

    for sec in range(1, 11):  # gold keeps ticking, the index does not
        driven.set_ms(nse_ts + sec * 1000)
        session.tick_bus.publish(_st("MCX_FO|495213", nse_ts + sec * 1000, 134_900.0))
    session._track_gap()

    assert not session.feed_live()
    assert session.gap_since == nse_ts
    assert session.bullion_status() == ("live", None)


def test_an_mcx_outage_after_the_nse_close_is_noticed_and_logged(tmp_path: Path) -> None:
    session, driven = _hours_session(tmp_path, _ist(20, 0))
    t0 = ist_to_ms(_ist(20, 0))
    session.tick_bus.publish(_st("MCX_FO|495213", t0, 134_900.0))
    session._track_gap()
    assert session.bullion_status() == ("live", None)

    driven.set_ms(t0 + 30_000)  # thirty seconds without a bullion tick
    session._track_gap()
    assert session.bullion_status() == ("stale", t0)

    driven.set_ms(t0 + 40_000)
    session.tick_bus.publish(_st("MCX_FO|495214", t0 + 40_000, 170_100.0))
    session._track_gap()
    assert session.bullion_status() == ("live", None)

    assert _feed_events(session) == ["bullion_gap_start", "bullion_gap_end"]
    assert session.gap_since is None  # the index session is closed: not an index outage


def test_bullion_status_follows_mcx_hours(tmp_path: Path) -> None:
    session, driven = _hours_session(tmp_path, _ist(23, 45))
    assert session.bullion_status() == ("closed", None)

    driven.set_ms(ist_to_ms(_ist(11, 0, day=date(2026, 12, 25))))  # NSE holiday, MCX at 17:00
    assert session.clock.status() == "holiday"
    assert session.bullion_status() == ("closed", None)
    driven.set_ms(ist_to_ms(_ist(17, 30, day=date(2026, 12, 25))))
    assert session.mcx_clock.status() == "live"
    assert session.bullion_status() == ("stale", None)  # MCX open, no tick seen yet

    driven.set_ms(ist_to_ms(_ist(12, 0, day=date(2026, 11, 14))))  # a Saturday
    assert session.bullion_status() == ("holiday", None)


def test_no_bullion_status_without_bullion(tmp_path: Path) -> None:
    session, _ = _hours_session(tmp_path, _ist(11, 0))
    session.bullion = None
    assert session.bullion_status() is None


def test_health_carries_the_bullion_status(client: TestClient) -> None:
    assert client.get("/api/health").json()["bullion"] is None  # synthetic: no bullion
    _with_bullion(client)
    body = client.get("/api/health").json()["bullion"]
    assert body["status"] in {"live", "stale", "closed", "holiday"}  # depends on the wall clock
    assert set(body) == {"status", "since_ms"}


def test_tracker_keeps_the_last_reading_of_each_minute_for_the_bias() -> None:
    t = _tracker()
    t0 = 1_794_800_000_000 - 1_794_800_000_000 % MINUTE_MS
    gold, nxt = "MCX_FO|495213", "MCX_FO|559933"
    t.on_tick(_st(gold, t0, 136000.0, oi=1000, tbq=50, tsq=70, bid_qty5=5, ask_qty5=6))
    t.on_tick(_st(gold, t0 + 30_000, 136010.0, tbq=55))  # OI and the rest carried over
    t.on_tick(_st(nxt, t0 + 40_000, 138000.0, oi=9))  # next month: not read
    t.on_tick(_st(gold, t0 + MINUTE_MS, 136020.0, oi=1010))
    t.on_tick(_st(gold, t0 + 50_000, 1.0, oi=1))  # late for a minute already moved past

    assert t.minute_book("GOLD", t0 + MINUTE_MS) == [
        MinuteBook(t0, 136010.0, 1000, 55, 70, 5, 6),
        MinuteBook(t0 + MINUTE_MS, 136020.0, 1010, 55, 70, 5, 6),
    ]
    assert [b.minute_ts for b in t.minute_book("GOLD", t0)] == [t0]
    assert t.minute_book("SILVER", t0 + MINUTE_MS) == []

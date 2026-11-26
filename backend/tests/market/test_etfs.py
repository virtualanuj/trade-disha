"""Gold BeES and Silver BeES on the BULLION tab: snapshot maths, the tracker, the wiring."""

import json
from datetime import date
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from tradedisha.app_state import AppState
from tradedisha.clock import epoch_ms_now
from tradedisha.config import Settings
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.feed.upstox import FullQuote
from tradedisha.market.etfs import (
    EtfQuote,
    EtfTracker,
    enrich_etfs,
    etf_snapshot,
    etfs_from,
)

TODAY = date(2026, 11, 26)
GOLDBEES = "NSE_EQ|INF204KB17I5"
SILVERBEES = "NSE_EQ|INF204KC1402"
QUOTE = FullQuote(
    ltp=108.0,
    prev_close=107.5,
    day_open=107.8,
    day_high=108.6,
    day_low=107.2,
    lower_circuit=None,
    upper_circuit=None,
)


def _etf(quote: FullQuote | None = None, **kw: float) -> EtfQuote:
    return EtfQuote("GOLD", "GOLDBEES", GOLDBEES, quote=quote, **kw)


def test_the_default_setting_names_both_etfs_by_metal() -> None:
    got = etfs_from(Settings(feed_provider="upstox"))
    assert [(m, e.symbol, e.key) for m, e in got.items()] == [
        ("GOLD", "GOLDBEES", GOLDBEES),
        ("SILVER", "SILVERBEES", SILVERBEES),
    ]


def test_the_synthetic_feed_has_no_etfs() -> None:
    assert etfs_from(Settings(feed_provider="synthetic")) == {}


# -- maths ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tick", "day", "want"),
    [
        # a tick: change on the feed's previous close, position in the day's range
        (
            Tick(GOLDBEES, 5, 108.0, close_prev=106.0, bid=107.99, ask=108.01, atp=107.9),
            (107.0, 109.0, 107.0),
            {"ltp": 108.0, "change": 2.0, "change_pct": 1.89, "range_pos": 0.5, "spread": 0.02},
        ),
        # before any tick: the start quote, its previous close, its day range
        (
            None,
            (107.8, 108.6, 107.2),
            {"ltp": 108.0, "prev_close": 107.5, "change": 0.5, "change_pct": 0.47},
        ),
        # a flat day has no position, and no book means no spread
        (
            Tick(GOLDBEES, 5, 108.0),
            (108.0, 108.0, 108.0),
            {"range_pos": None, "spread": None, "updated_ts": 5},
        ),
    ],
)
def test_etf_snapshot_figures(
    tick: Tick | None, day: tuple[float, float, float], want: dict[str, Any]
) -> None:
    s = etf_snapshot(_etf(QUOTE), tick, day)
    assert {k: getattr(s, k) for k in want} == want
    assert (s.metal, s.symbol) == ("GOLD", "GOLDBEES")


def test_etf_snapshot_widens_the_52_week_range_by_today() -> None:
    e = _etf(range_high=108.2, range_low=70.0)
    s = etf_snapshot(e, Tick(GOLDBEES, 5, 108.5), (108.0, 108.9, 107.9))
    assert (s.range_high, s.range_low) == (108.9, 70.0)


def test_etf_snapshot_with_nothing_known() -> None:
    s = etf_snapshot(_etf(), None, (0.0, 0.0, 0.0))
    assert (s.ltp, s.change, s.day_high, s.range_high, s.updated_ts) == (
        None,
        None,
        None,
        None,
        None,
    )


# -- tracker ----------------------------------------------------------------------------


def _st(key: str, ts: int, ltp: float, **kw: Any) -> StampedTick:  # noqa: ANN401
    return StampedTick(Tick(key, ts, ltp, **kw), ts)


def test_tracker_merges_ticks_and_follows_the_day() -> None:
    tracker = EtfTracker({"GOLD": _etf(QUOTE)})
    tracker.on_tick(_st(GOLDBEES, 1, 108.9, volume=100, bid=108.8))
    tracker.on_tick(_st(GOLDBEES, 2, 107.0))  # carries volume and bid over
    tracker.on_tick(_st("NSE_EQ|OTHER", 3, 5.0))

    [s] = tracker.snapshot()
    assert (s.ltp, s.volume, s.bid) == (107.0, 100, 108.8)
    assert (s.day_open, s.day_high, s.day_low) == (107.8, 108.9, 107.0)
    assert tracker.keys == frozenset({GOLDBEES})


def test_tracker_prefers_the_feeds_day_candle() -> None:
    tracker = EtfTracker({"GOLD": _etf(QUOTE)})
    tracker.on_tick(_st(GOLDBEES, 1, 108.0, day_open=107.0, day_high=110.0, day_low=106.0))
    [s] = tracker.snapshot()
    assert (s.day_open, s.day_high, s.day_low) == (107.0, 110.0, 106.0)


# -- start ------------------------------------------------------------------------------


async def test_enrich_adds_the_quote_and_the_52_week_range() -> None:
    def handle(req: httpx.Request) -> httpx.Response:
        if "market-quote" in req.url.path:
            row = {"instrument_token": GOLDBEES, "last_price": 108.0, "net_change": 0.5}
            return httpx.Response(200, json={"data": {"NSE_EQ:GOLDBEES": row}})
        candles = [["2026-11-25T00:00:00+05:30", 100.0, 109.0, 71.0, 108.0, 1000, 0]]
        return httpx.Response(200, json={"data": {"candles": candles}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        got = await enrich_etfs(client, "tok", {"GOLD": _etf()}, TODAY)

    assert got["GOLD"].quote is not None
    assert got["GOLD"].quote.prev_close == 107.5
    assert (got["GOLD"].range_high, got["GOLD"].range_low) == (109.0, 71.0)


async def test_enrich_fails_soft() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(500))
    async with httpx.AsyncClient(transport=transport) as client:
        got = await enrich_etfs(client, "tok", {"GOLD": _etf()}, TODAY)
    assert got["GOLD"] == _etf()


# -- live wiring -------------------------------------------------------------------------


def _with_etfs(client: TestClient) -> AppState:
    td: AppState = client.app.state.td  # type: ignore[attr-defined]
    td.session.attach_etfs(EtfTracker(etfs_from(Settings(feed_provider="upstox"))))
    return td


def _publish(client: TestClient, td: AppState, tick: Tick) -> None:
    assert client.portal is not None
    client.portal.call(td.session.tick_bus.publish, StampedTick(tick, epoch_ms_now()))


def test_etf_ticks_are_shown_recorded_and_kept_off_the_charts(client: TestClient) -> None:
    td = _with_etfs(client)
    now = epoch_ms_now()
    _publish(client, td, Tick(key=GOLDBEES, ts=now, ltp=108.0, close_prev=107.5))
    assert client.portal is not None
    client.portal.call(td.session.tick_store.flush)

    body = client.get("/api/bullion").json()
    assert [(e["metal"], e["symbol"], e["ltp"]) for e in body["etfs"]] == [
        ("GOLD", "GOLDBEES", 108.0),
        ("SILVER", "SILVERBEES", None),
    ]
    assert body["metals"] == []  # the ETFs never make a metal of their own
    # NSE instruments: recorded in `ticks` like the sector indices, so a replay has them
    assert [t.key for t in td.session.tick_store.read_day(td.clock.today(), [GOLDBEES])] == [
        GOLDBEES
    ]
    assert td.session.candles.current(GOLDBEES) is None


def test_synthetic_feed_has_no_etfs_on_the_api(client: TestClient) -> None:
    assert client.get("/api/bullion").json()["etfs"] == []


def test_an_etf_tick_sends_a_bullion_frame(client: TestClient) -> None:
    td = _with_etfs(client)
    with client.websocket_connect("/ws") as ws:
        hello = json.loads(ws.receive_text())
        assert [e["symbol"] for e in hello["payload"]["bullion"]["etfs"]] == [
            "GOLDBEES",
            "SILVERBEES",
        ]
        _publish(client, td, Tick(key=SILVERBEES, ts=epoch_ms_now(), ltp=150.0))
        for _ in range(600):
            frame = json.loads(ws.receive_text())
            if frame["type"] == "bullion":
                break
        else:
            raise AssertionError("no bullion frame")

    assert frame["payload"]["etfs"][1]["ltp"] == 150.0

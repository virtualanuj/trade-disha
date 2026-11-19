"""GIFT Nifty's overnight snapshot (spec §6.8): fetch, store, and NIFTY's macro group."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from tradedisha.app_state import AppState
from tradedisha.clock import IST, MarketClock, ist_to_ms
from tradedisha.indicators.gift import GiftSnapshot
from tradedisha.market.candles import MINUTE_MS
from tradedisha.market.gift import GiftNifty
from tradedisha.store.db import connect
from tradedisha.store.gift import GiftStore

MONDAY = date(2026, 11, 16)
FRIDAY = date(2026, 11, 13)


def _at(d: date, hh: int, mm: int) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=IST)


def _clock(now: datetime, holidays: frozenset[date] = frozenset()) -> MarketClock:
    return MarketClock(
        market_open=time(9, 15),
        market_close=time(15, 30),
        pre_open_start=time(9, 0),
        holidays=holidays,
        source=lambda: now,
    )


def _row(d: date, hh: int, mm: int, close: float) -> list[Any]:
    """Shaped like Upstox's rows for GLOBAL_INDEX|SGX NIFTY (checked on 2026-11-19)."""
    return [_at(d, hh, mm).isoformat(), close, close, close, close, 0, 0]


def _upstox(seen: list[str], prev: list[list[Any]], today: list[list[Any]]) -> httpx.MockTransport:
    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.path)
        rows = today if "/intraday/" in req.url.path else prev
        return httpx.Response(200, json={"status": "success", "data": {"candles": rows}})

    return httpx.MockTransport(handle)


def test_the_store_round_trips_a_snapshot() -> None:
    store = GiftStore(connect(":memory:"))
    snap = GiftSnapshot(MONDAY, 1, 25000.0, 2, 25100.0)
    assert store.get(MONDAY) is None
    store.put(snap, 99)
    store.put(snap, 100)  # a second fetch replaces, never duplicates
    assert store.get(MONDAY) == snap


async def test_fetch_reads_the_previous_nse_day_and_stores_the_snapshot() -> None:
    conn = connect(":memory:")
    gift = GiftNifty(GiftStore(conn), _clock(_at(MONDAY, 9, 17)))
    seen: list[str] = []
    prev = [_row(FRIDAY, 15, 31, 1.0), _row(FRIDAY, 15, 28, 25000.0), _row(FRIDAY, 9, 0, 2.0)]
    today = [_row(MONDAY, 9, 15, 3.0), _row(MONDAY, 9, 14, 24900.0), _row(MONDAY, 6, 30, 4.0)]
    async with httpx.AsyncClient(transport=_upstox(seen, prev, today)) as client:
        snap = await gift.fetch(client, "tok")

    assert snap is not None
    assert (snap.ref_close, snap.preopen_price) == (25000.0, 24900.0)
    assert snap.move_pct == pytest.approx(-0.4)
    assert any("2026-11-13/2026-11-13" in p for p in seen)  # Friday: the weekend skipped
    assert any("GLOBAL_INDEX%7CSGX%20NIFTY" in p or "GLOBAL_INDEX|SGX NIFTY" in p for p in seen)
    assert GiftStore(conn).get(MONDAY) == snap
    assert gift.snapshot(MONDAY) == snap


async def test_fetch_without_a_price_stores_nothing() -> None:
    conn = connect(":memory:")
    gift = GiftNifty(GiftStore(conn), _clock(_at(MONDAY, 9, 17)))
    async with httpx.AsyncClient(transport=_upstox([], [], [])) as client:
        assert await gift.fetch(client, "tok") is None
    assert GiftStore(conn).get(MONDAY) is None


def test_previous_trading_day_skips_holidays() -> None:
    clock = _clock(_at(MONDAY, 9, 17), frozenset({FRIDAY}))
    gift = GiftNifty(GiftStore(connect(":memory:")), clock)
    assert gift.previous_trading_day(MONDAY) == date(2026, 11, 12)


@pytest.mark.parametrize(
    ("now", "due"),
    [
        (_at(MONDAY, 9, 0), False),  # before the open
        (_at(MONDAY, 9, 15), False),  # the 09:14 candle may not be in yet
        (_at(MONDAY, 9, 16), True),
        (_at(MONDAY, 15, 30), False),  # NSE shut
        (_at(date(2026, 11, 15), 10, 0), False),  # Sunday
    ],
)
def test_due_once_nse_is_open(now: datetime, due: bool) -> None:
    gift = GiftNifty(GiftStore(connect(":memory:")), _clock(now))
    assert gift.due(ist_to_ms(now)) is due


async def test_not_due_again_until_the_retry_interval_or_once_stored() -> None:
    conn = connect(":memory:")
    now = _at(MONDAY, 9, 20)
    gift = GiftNifty(GiftStore(conn), _clock(now))
    async with httpx.AsyncClient(transport=_upstox([], [], [])) as client:
        await gift.fetch(client, "tok")
    t = ist_to_ms(now)
    assert not gift.due(t + 60_000)
    assert gift.due(t + 120_000)
    GiftStore(conn).put(GiftSnapshot(MONDAY, 1, 1.0, 2, 1.0), 0)
    assert not gift.due(t + 120_000)


def test_nifty_gets_the_gift_vote_and_bank_nifty_does_not(client: TestClient) -> None:
    td: AppState = client.app.state.td  # type: ignore[attr-defined]
    s = td.session
    open_ms, _ = s.clock.session_bounds(MONDAY)
    minute = open_ms + 4 * MINUTE_MS  # the 09:19 candle: 5 minutes since the open
    assert s.index_macro("NIFTY", minute) == []  # synthetic: no GIFT service, no macro

    store = GiftStore(td.conn)
    s.gift = GiftNifty(store, s.clock)
    nifty = s.index_macro("NIFTY", minute)
    assert [(r.name, r.quality) for r in nifty] == [("gift_nifty", "warming")]  # no row yet

    store.put(GiftSnapshot(MONDAY, 1, 25000.0, 2, 25125.0), 0)
    (r,) = s.index_macro("NIFTY", minute)
    assert (r.name, r.quality) == ("gift_nifty", "ok")
    assert r.score == pytest.approx(1.0 * (1 - 5 / 30))  # +0.50 % at full 0.50
    assert s.index_macro("BANKNIFTY", minute) == []

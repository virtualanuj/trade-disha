"""Net volume per candle (Milestone E8): through the API, the WebSocket and a replay."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from tests.test_bullion_trading import GOLD_KEY, _desk
from tradedisha.app_state import AppState
from tradedisha.clock import IST, DrivenClock, MarketClock, epoch_ms_now, ist_to_ms
from tradedisha.config import Settings
from tradedisha.events import EventBus
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.instruments.resolve import resolve_index
from tradedisha.instruments.synthetic_master import build_synthetic_master
from tradedisha.market.candles import CandleBuilder, CandleStore
from tradedisha.market.session import FeedSession
from tradedisha.metrics.latency import LatencyTracker
from tradedisha.parameters import ParameterService
from tradedisha.store.db import connect
from tradedisha.store.ticks import TickStore

M = 60_000


def _trades(key: str, t0: int) -> list[Tick]:
    """One minute of a future: 40 bought at the ask, 25 sold at the bid; then the next minute."""
    return [
        Tick(key=key, ts=t0, ltp=100.0, volume=1_000, bid=99.5, ask=100.0),
        Tick(key=key, ts=t0 + 1_000, ltp=100.0, volume=1_040, bid=99.5, ask=100.0),
        Tick(key=key, ts=t0 + 2_000, ltp=99.5, volume=1_065, bid=99.5, ask=100.0),
        Tick(key=key, ts=t0 + M, ltp=99.5, volume=1_065, bid=99.5, ask=100.0),
    ]


def test_index_candles_carry_the_futures_net_volume(client: TestClient) -> None:
    td: AppState = client.app.state.td  # type: ignore[attr-defined]
    fut = td.session.resolved["NIFTY"].future.instrument_key
    # Well ahead of the synthetic feed, so its own ticks for this key arrive late and are
    # ignored; one closed minute of ours.
    t0 = (epoch_ms_now() // M + 600) * M
    assert client.portal is not None
    for t in _trades(fut, t0):
        client.portal.call(td.session.candles.apply, t)

    body = client.get("/api/candles/NIFTY?minutes=400").json()
    mine = [c for c in body["fut_candles"] if c["t"] == t0]
    assert mine == [
        {
            "t": t0,
            "o": 100.0,
            "h": 100.0,
            "l": 99.5,
            "c": 99.5,
            "v": 65,
            "synthetic": False,
            "bv": 40,
            "sv": 25,
        }
    ]
    assert all(c["bv"] is None for c in body["candles"])  # the spot index has no volume


def test_the_futures_candle_frame_carries_net_volume(client: TestClient) -> None:
    td: AppState = client.app.state.td  # type: ignore[attr-defined]
    fut = td.session.resolved["NIFTY"].future.instrument_key
    t0 = (epoch_ms_now() // M + 700) * M
    assert client.portal is not None
    with client.websocket_connect("/ws") as ws:
        ws.receive_text()  # hello
        for t in _trades(fut, t0):
            client.portal.call(td.session.candles.apply, t)
        for _ in range(500):
            frame = json.loads(ws.receive_text())
            p = frame["payload"]
            if frame["type"] == "candle" and p["role"] == "fut" and p["candle"]["t"] == t0:
                break
        else:
            raise AssertionError("no fut candle frame")
    assert (p["candle"]["bv"], p["candle"]["sv"]) == (40, 25)


def test_bullion_candles_carry_net_volume(client: TestClient) -> None:
    td, _ = _desk(client)
    assert td.session.bullion is not None
    t0 = (epoch_ms_now() // M - 3) * M
    assert client.portal is not None
    for t in _trades(GOLD_KEY, t0):
        client.portal.call(td.session.tick_bus.publish, StampedTick(t, t.ts))
    (c,) = client.get("/api/bullion/GOLD/candles").json()["candles"]
    assert (c["v"], c["bv"], c["sv"]) == (65, 40, 25)


async def test_replay_rebuilds_net_volume_from_the_recorded_ticks(tmp_path: Path) -> None:
    day = date(2026, 11, 12)
    settings = Settings(
        _env_file=None,
        db_path=tmp_path / "t.sqlite",
        data_dir=tmp_path,
        feed_provider="replay",
        replay_speed=0,
        indices=["NIFTY"],
        strike_window=2,
    )
    conn = connect(settings.db_path)
    r = resolve_index(build_synthetic_master(day), "NIFTY", day, 25_000.0, strike_window=2)
    fut = r.future.instrument_key
    t0 = ist_to_ms(datetime(2026, 11, 12, 10, 0, tzinfo=IST))
    ticks = [Tick(key=r.spot.instrument_key, ts=t0, ltp=25_000.0), *_trades(fut, t0 + 5_000)]
    store = TickStore(conn)
    for t in ticks:
        store.add(t)
    store.flush()

    driven = DrivenClock(datetime(2026, 11, 12, 10, 0, tzinfo=IST))
    clock = MarketClock(
        market_open=settings.market_open,
        market_close=settings.market_close,
        pre_open_start=settings.pre_open_start,
        source=driven,
    )
    params = ParameterService(conn, settings.params_path)
    params.load()
    session = FeedSession(
        settings,
        conn,
        clock,
        bus=EventBus(),
        latency=LatencyTracker(),
        params=lambda: params.params,
        driven_clock=driven,
    )
    await session.start()
    await session._tasks[0]  # the pump ends when the recording does
    await asyncio.sleep(0)
    await session.stop()

    built = CandleBuilder()
    for t in _trades(fut, t0 + 5_000):
        built.apply(t)
    stored = CandleStore(conn).read(fut, t0, t0 + 10 * M)
    assert (
        [(c.buy_volume, c.sell_volume) for c in stored]
        == [(c.buy_volume, c.sell_volume) for c in built.closed(fut)]
        == [(40, 25)]
    )

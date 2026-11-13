"""Fault injection on replay: a feed outage and a re-centre in one recorded session."""

import asyncio
from datetime import date, datetime
from pathlib import Path

from tradedisha.clock import IST, DrivenClock, MarketClock, ist_to_ms
from tradedisha.config import Settings
from tradedisha.events import EventBus
from tradedisha.feed.provider import Tick
from tradedisha.instruments.resolve import resolve_index
from tradedisha.instruments.synthetic_master import build_synthetic_master
from tradedisha.market.session import FeedSession, parse_drop_ranges
from tradedisha.metrics.latency import LatencyTracker
from tradedisha.parameters import ParameterService
from tradedisha.store.db import connect
from tradedisha.store.ticks import TickStore

DAY = date(2026, 11, 12)


def at(h: int, m: int, s: int = 0) -> int:
    return ist_to_ms(datetime(DAY.year, DAY.month, DAY.day, h, m, s, tzinfo=IST))


def test_drop_ranges_are_read_as_ist_times_on_the_replay_day() -> None:
    assert parse_drop_ranges(["10:01:00-10:01:30", "11:00-11:05"], DAY) == [
        (at(10, 1), at(10, 1, 30)),
        (at(11, 0), at(11, 5)),
    ]


async def test_replayed_outage_is_logged_and_recentre_resubscribes(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        db_path=tmp_path / "t.sqlite",
        data_dir=tmp_path,
        feed_provider="replay",
        replay_speed=0,
        replay_drop=["10:01:00-10:01:30"],
        indices=["NIFTY"],
        strike_window=2,
    )
    conn = connect(settings.db_path)
    master = build_synthetic_master(DAY)
    before = resolve_index(master, "NIFTY", DAY, 25_000.0, strike_window=2)
    spot = before.spot.instrument_key
    store = TickStore(conn)
    for sec in range(181):  # 10:00:00 .. 10:03:00, one spot tick a second
        price = 25_000.0 if sec < 120 else 25_160.0  # jumps three strikes at 10:02
        store.add(Tick(key=spot, ts=at(10, 0) + sec * 1000, ltp=price))
    store.flush()

    driven = DrivenClock(datetime(DAY.year, DAY.month, DAY.day, 10, 0, tzinfo=IST))
    clock = MarketClock(
        market_open=settings.market_open,
        market_close=settings.market_close,
        pre_open_start=settings.pre_open_start,
        source=driven,
    )
    params = ParameterService(settings.params_path)
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
    try:
        await session._tasks[0]  # the pump ends when the recording does
        await asyncio.sleep(0.1)  # let the queued re-subscribe be applied

        # the outage: ticks from 10:01:00 to 10:01:29 never arrived
        assert session.last_gap == (at(10, 0, 59), at(10, 1, 30))
        events = {r["kind"]: r["detail"] for r in conn.execute("SELECT * FROM feed_events")}
        assert events["feed_gap"] == "gap_ms=31000"

        # the re-centre: window moved with the spot and the provider follows it
        after = session.resolved["NIFTY"]
        assert (before.atm, after.atm) == (25_000, 25_150)
        assert events["recentre"].startswith("NIFTY +")
        assert session.provider is not None
        subscribed = session.provider._subscribed  # type: ignore[attr-defined]
        assert set(after.option_keys) <= subscribed
        assert not (set(before.option_keys) - set(after.option_keys)) & subscribed
    finally:
        await session.stop()
        conn.close()

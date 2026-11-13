"""A recorded live day replays against the real instruments of that day."""

import gzip
import json
from datetime import date, datetime
from pathlib import Path

from tests.instruments.test_upstox_master import _records
from tradedisha.clock import IST, DrivenClock, MarketClock, ist_to_ms
from tradedisha.config import Settings
from tradedisha.events import EventBus
from tradedisha.feed.provider import Tick
from tradedisha.instruments.upstox_master import master_path
from tradedisha.market.session import FeedSession
from tradedisha.metrics.latency import LatencyTracker
from tradedisha.parameters import ParameterService
from tradedisha.store.db import connect
from tradedisha.store.ticks import TickStore

DAY = date(2026, 11, 13)


async def test_replay_uses_the_recorded_days_master_and_first_spot(tmp_path: Path) -> None:
    with gzip.open(master_path(tmp_path, DAY), "wt", encoding="utf-8") as fh:
        json.dump(_records(), fh)
    settings = Settings(
        _env_file=None,
        db_path=tmp_path / "live.sqlite",
        data_dir=tmp_path,
        feed_provider="replay",
        replay_speed=0,
        indices=["NIFTY"],
        strike_window=2,
    )
    conn = connect(settings.db_path)
    store = TickStore(conn)
    t0 = ist_to_ms(datetime(2026, 11, 13, 11, 30, tzinfo=IST))
    store.add(Tick(key="NSE_INDEX|Nifty 50", ts=t0, ltp=25_110.0))
    store.add(Tick(key="NSE_INDEX|Nifty 50", ts=t0 + 1000, ltp=25_400.0))
    store.flush()

    driven = DrivenClock(datetime(2026, 12, 1, 20, 0, tzinfo=IST))
    clock = MarketClock(
        market_open=settings.market_open,
        market_close=settings.market_close,
        pre_open_start=settings.pre_open_start,
        holidays=frozenset(),
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
        r = session.resolved["NIFTY"]
        assert session.replay_day == DAY
        assert r.atm == 25_100
        assert r.options_expiry == date(2026, 11, 17)
        assert r.future.instrument_key.startswith("NSE_FO|4")
    finally:
        await session.stop()
        conn.close()

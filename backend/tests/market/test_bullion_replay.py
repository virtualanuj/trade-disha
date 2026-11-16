"""A recorded bullion evening replays through the bullion desk with live-like timing (E6)."""

import gzip
import json
from datetime import date, datetime
from pathlib import Path

from tests.market.test_bullion import _records
from tradedisha.clock import IST, DrivenClock, MarketClock, ist_to_ms
from tradedisha.config import Settings
from tradedisha.events import EventBus
from tradedisha.feed.provider import Tick
from tradedisha.instruments.upstox_master import mcx_master_path
from tradedisha.market.session import FeedSession
from tradedisha.metrics.latency import LatencyTracker
from tradedisha.parameters import ParameterService
from tradedisha.store.db import connect
from tradedisha.store.ticks import TickStore

DAY = date(2026, 11, 12)  # a Thursday
GOLD = "MCX_FO|495213"  # the near GOLD future on that day


def at(h: int, m: int, s: int = 0) -> int:
    return ist_to_ms(datetime(DAY.year, DAY.month, DAY.day, h, m, s, tzinfo=IST))


async def _replay(tmp_path: Path, *, bullion: bool) -> FeedSession:
    with gzip.open(mcx_master_path(tmp_path, DAY), "wt", encoding="utf-8") as fh:
        json.dump(_records(), fh)
    settings = Settings(
        _env_file=None,
        db_path=tmp_path / "live.sqlite",
        data_dir=tmp_path,
        feed_provider="replay",
        replay_speed=0,
        replay_date=DAY.isoformat(),
        replay_bullion=bullion,
        indices=["NIFTY"],
        strike_window=2,
    )
    conn = connect(settings.db_path)
    mcx = TickStore(conn, table="bullion_ticks")
    for i in range(45 * 6):  # 19:00 to 19:45, a tick every 10 s, climbing steadily
        mcx.add(Tick(key=GOLD, ts=at(19, 0) + i * 10_000, ltp=135_000.0 + i * 5, volume=i + 1))
    mcx.flush()
    nse = TickStore(conn)
    nse.add(Tick(key="NSE_INDEX|Nifty 50", ts=at(15, 29), ltp=25_000.0))
    nse.flush()

    driven = DrivenClock(datetime(2026, 12, 1, 9, 0, tzinfo=IST))
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
    await session.stop()
    return session


async def test_a_recorded_bullion_evening_fires_signals_at_the_offset(tmp_path: Path) -> None:
    session = await _replay(tmp_path, bullion=True)
    rows = session._conn.execute(
        "SELECT idx, direction, minute_ts, ts_fired FROM signals ORDER BY ts_fired"
    ).fetchall()
    assert rows, "a steady climb should fire a long GOLD signal"
    first = rows[0]
    assert (first["idx"], first["direction"]) == ("GOLD", "BUY_FUT")
    assert first["ts_fired"] - (first["minute_ts"] + 60_000) == 20_000  # the offset, as live
    assert TickStore(session._conn, table="bullion_ticks").count() == 45 * 6  # not re-recorded


async def test_without_replay_bullion_nse_replay_is_unchanged(tmp_path: Path) -> None:
    session = await _replay(tmp_path, bullion=False)
    assert session.bullion is None
    assert session._conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 0
    assert session.replay_day == DAY

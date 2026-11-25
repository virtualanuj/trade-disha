"""The bias for a minute reads that minute's option chain, whichever tick opens the next.

The spot candle closes on the first spot tick of the next minute and the chain closes its
minute on the first chain tick (spot or option). Both happen on the same tick when the spot
tick comes first; the chain must close before the candle, or the OI and premium votes read
the snapshot of the minute before.
"""

from datetime import date, datetime
from pathlib import Path

from tradedisha.clock import IST, DrivenClock, MarketClock, ist_to_ms
from tradedisha.config import Settings
from tradedisha.engine.bias_engine import BiasComputed
from tradedisha.events import EventBus
from tradedisha.feed.provider import Tick
from tradedisha.instruments.resolve import resolve_index
from tradedisha.instruments.synthetic_master import build_synthetic_master
from tradedisha.market.session import FeedSession
from tradedisha.metrics.latency import LatencyTracker
from tradedisha.parameters import ParameterService
from tradedisha.store.db import connect
from tradedisha.store.ticks import TickStore

DAY = date(2026, 11, 12)
MINUTE = 60_000


def at(h: int, m: int, s: int = 0) -> int:
    return ist_to_ms(datetime(DAY.year, DAY.month, DAY.day, h, m, s, tzinfo=IST))


async def test_bias_reads_the_chain_of_its_own_minute_when_spot_ticks_first(
    tmp_path: Path,
) -> None:
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
    r = resolve_index(build_synthetic_master(DAY), "NIFTY", DAY, 25_000.0, strike_window=2)
    store = TickStore(conn)
    for m in range(6):  # 10:00 .. 10:05; in every minute the spot tick is the first tick
        start = at(10, 0) + m * MINUTE
        store.add(Tick(key=r.spot.instrument_key, ts=start, ltp=25_000.0 + m))
        for i, key in enumerate(r.option_keys):
            store.add(Tick(key=key, ts=start + 500 + i, ltp=100.0 + m, oi=10_000 + m * 100))
    store.flush()

    driven = DrivenClock(datetime(DAY.year, DAY.month, DAY.day, 10, 0, tzinfo=IST))
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
    seen: list[tuple[int, int | None]] = []

    def on_bias(b: BiasComputed) -> None:
        assert session.chains is not None
        history = session.chains.chains["NIFTY"].history
        seen.append((b.minute_ts, history[-1].minute_ts if history else None))

    session.bias_listeners.append(on_bias)
    await session.start()
    try:
        await session._tasks[0]  # the pump ends when the recording does
    finally:
        await session.stop()

    closed = [(m, chain) for m, chain in seen if m < at(10, 5)]  # minutes a later tick closed
    assert [m for m, _ in closed] == [at(10, 0) + m * MINUTE for m in range(5)]
    assert all(chain == m for m, chain in closed), [
        ((m - at(10, 0)) // MINUTE, None if c is None else (c - at(10, 0)) // MINUTE)
        for m, c in closed
    ]

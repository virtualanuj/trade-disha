"""Tick pruning: preview, delete up to and including a date, leave everything else."""

from datetime import date, datetime

from tradedisha.clock import IST, ist_to_ms
from tradedisha.feed.provider import Tick
from tradedisha.market.candles import Candle, CandleStore
from tradedisha.store.db import connect
from tradedisha.store.ticks import TickStore


def _ms(day: int, h: int = 10) -> int:
    return ist_to_ms(datetime(2026, 11, day, h, 0, tzinfo=IST))


def _store() -> TickStore:
    store = TickStore(connect(":memory:"))
    for day, n in ((10, 3), (11, 4), (12, 5)):
        for i in range(n):
            store.add(Tick(key="A", ts=_ms(day) + i, ltp=1.0))
    store.flush()
    return store


def test_usage_previews_what_a_prune_would_remove() -> None:
    u = _store().usage(date(2026, 11, 11))

    assert (u.tick_rows, u.tick_days) == (12, 3)
    assert (u.oldest, u.newest) == (date(2026, 11, 10), date(2026, 11, 12))
    assert (u.prune_rows, u.prune_days) == (7, 2)  # the chosen date is included
    assert 0 < u.prune_bytes_estimate < u.db_bytes


def test_usage_without_a_date_previews_nothing() -> None:
    u = _store().usage()
    assert (u.prune_rows, u.prune_days, u.prune_bytes_estimate) == (0, 0, 0)


async def test_prune_deletes_in_batches_and_touches_only_ticks() -> None:
    store = _store()
    candles = CandleStore(store._conn)
    candles.write(Candle("A", _ms(10), 1, 1, 1, 1))

    result = await store.prune(date(2026, 11, 11), batch=2)

    assert result.rows_deleted == 7
    assert store.count() == 5
    assert store.recorded_days() == [date(2026, 11, 12)]
    assert candles.count() == 1


async def test_prune_of_an_empty_range_is_a_no_op() -> None:
    store = _store()
    result = await store.prune(date(2026, 11, 1))
    assert result.rows_deleted == 0
    assert store.count() == 12

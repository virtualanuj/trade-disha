"""Tick persistence and read-back."""

from datetime import date, datetime

from tradedisha.clock import IST, ist_to_ms
from tradedisha.feed.provider import Tick
from tradedisha.store.db import connect, schema_version
from tradedisha.store.ticks import TickStore


def ms(day: date, h: int, m: int, s: int = 0) -> int:
    return ist_to_ms(datetime(day.year, day.month, day.day, h, m, s, tzinfo=IST))


def test_migrations_apply_once() -> None:
    conn = connect(":memory:")
    assert schema_version(conn) == 6
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "ticks",
        "instruments",
        "feed_events",
        "latency_samples",
        "sessions",
        "chain_minutes",
    } <= tables


def test_batches_and_reads_back_in_order() -> None:
    conn = connect(":memory:")
    store = TickStore(conn, batch_size=3)
    d = date(2026, 11, 12)

    store.add(Tick(key="A", ts=ms(d, 9, 15, 1), ltp=1.0))
    store.add(Tick(key="B", ts=ms(d, 9, 15, 0), ltp=2.0, oi=10))
    assert store.pending == 2
    assert store.count() == 0
    store.add(Tick(key="A", ts=ms(d, 9, 15, 2), ltp=3.0))
    assert store.pending == 0
    assert store.count() == 3

    got = store.read_day(d)
    assert [t.key for t in got] == ["B", "A", "A"]
    assert got[0].oi == 10
    assert store.read_day(d, keys=["A"])[0].ltp == 1.0
    assert store.read_day(date(2026, 11, 13)) == []


def test_recorded_days_newest_first() -> None:
    conn = connect(":memory:")
    store = TickStore(conn)
    store.add(Tick(key="A", ts=ms(date(2026, 11, 10), 10, 0), ltp=1.0))
    store.add(Tick(key="A", ts=ms(date(2026, 11, 12), 10, 0), ltp=1.0))
    store.flush()
    assert store.recorded_days() == [date(2026, 11, 12), date(2026, 11, 10)]


def test_previous_close_is_stored_once_per_key_and_replayed() -> None:
    conn = connect(":memory:")
    store = TickStore(conn)
    t0 = ist_to_ms(datetime(2026, 11, 13, 9, 15, tzinfo=IST))
    store.add(Tick(key="A", ts=t0, ltp=101.0, close_prev=100.0))
    store.add(Tick(key="A", ts=t0 + 1, ltp=102.0, close_prev=100.0))
    store.add(Tick(key="B", ts=t0 + 2, ltp=51.0, close_prev=50.0))
    store.flush()

    stored = [r[0] for r in conn.execute("SELECT close_prev FROM ticks ORDER BY ts")]
    assert stored == [100.0, None, 50.0]
    replayed = store.read_day(datetime(2026, 11, 13, tzinfo=IST).date())
    assert [t.close_prev for t in replayed] == [100.0, None, 50.0]

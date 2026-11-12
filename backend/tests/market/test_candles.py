"""Candle builder: minute boundaries, gap fill, volume deltas, VWAP, stale flush."""

from tradedisha.feed.provider import Tick
from tradedisha.market.candles import CandleBuilder, CandleStore
from tradedisha.store.db import connect

M = 60_000
T0 = 1_700_000_000_000 // M * M  # aligned minute start


def tick(ts: int, ltp: float, vol: int | None = None) -> Tick:
    return Tick(key="F", ts=ts, ltp=ltp, volume=vol)


def test_builds_ohlc_and_closes_on_next_minute() -> None:
    b = CandleBuilder()
    assert b.apply(tick(T0 + 1_000, 100.0)) == []
    assert b.apply(tick(T0 + 20_000, 103.0)) == []
    assert b.apply(tick(T0 + 40_000, 99.0)) == []
    closed = b.apply(tick(T0 + M + 500, 101.0))
    assert len(closed) == 1
    c = closed[0]
    assert (c.open, c.high, c.low, c.close, c.ticks) == (100.0, 103.0, 99.0, 99.0, 3)
    assert c.minute_ts == T0
    assert b.current("F") is not None
    assert b.current("F").open == 101.0  # type: ignore[union-attr]


def test_gap_minutes_are_synthetic_carry_forward() -> None:
    b = CandleBuilder()
    b.apply(tick(T0, 100.0))
    closed = b.apply(tick(T0 + 3 * M, 110.0))
    assert [c.minute_ts for c in closed] == [T0, T0 + M, T0 + 2 * M]
    assert [c.synthetic for c in closed] == [False, True, True]
    assert closed[2].close == 100.0


def test_volume_is_delta_of_cumulative_and_vwap_accumulates() -> None:
    b = CandleBuilder()
    b.apply(tick(T0, 100.0, vol=1_000))
    b.apply(tick(T0 + 10_000, 102.0, vol=1_300))  # +300
    b.apply(tick(T0 + M, 104.0, vol=1_400))  # closes minute 1 with volume 300
    b.apply(tick(T0 + 2 * M, 106.0, vol=1_600))  # closes minute 2: +100 at open tick only
    closed = b.closed("F")
    assert [c.volume for c in closed] == [300, 100]
    # VWAP = (102*300 + 104*100) / 400
    assert b.vwap("F") == (102 * 300 + 104 * 100) / 400


def test_late_tick_is_ignored_and_listener_fires() -> None:
    b = CandleBuilder()
    seen: list[int] = []
    b.on_close(lambda c: seen.append(c.minute_ts))
    b.apply(tick(T0 + M, 100.0))
    assert b.apply(tick(T0 + 10, 50.0)) == []  # earlier minute than current
    b.apply(tick(T0 + 2 * M, 101.0))
    assert seen == [T0 + M]


def test_flush_stale_closes_after_grace() -> None:
    b = CandleBuilder()
    b.apply(tick(T0 + 5_000, 100.0))
    assert b.flush_stale(T0 + M + 1_000) == []
    out = b.flush_stale(T0 + M + 2_500)
    assert len(out) == 1
    assert b.current("F") is None


def test_store_roundtrip() -> None:
    conn = connect(":memory:")
    store = CandleStore(conn)
    b = CandleBuilder()
    b.on_close(store.write)
    b.apply(tick(T0, 100.0))
    b.apply(tick(T0 + M, 101.0))
    rows = store.read("F", T0, T0 + 10 * M)
    assert len(rows) == 1
    assert rows[0].close == 100.0
    assert store.count() == 1

"""Candle builder: minute boundaries, gap fill, volume deltas, VWAP, stale flush."""

import pytest

from tradedisha.feed.provider import Tick
from tradedisha.market.candles import Candle, CandleBuilder, CandleStore, trade_side
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


def _flushed(b: CandleBuilder, seen: list[tuple[int, bool]]) -> None:
    """Minute T0 traded and was closed by the wall-clock flush."""
    b.on_close(lambda c: seen.append((c.minute_ts, c.synthetic)))
    b.apply(tick(T0 + 5_000, 100.0))
    b.flush_stale(T0 + M + 2_500)
    assert seen == [(T0, False)]


@pytest.mark.parametrize(
    ("ts", "closed_after", "current"),
    [
        # a late tick for the flushed minute: dropped, never a second T0
        (T0 + 59_900, [(T0, False)], None),
        # the next minute: opens normally
        (T0 + M + 3_000, [(T0, False)], T0 + M),
        # after a silence: the missed minutes are carried forward, as replay does
        (T0 + 3 * M + 5_000, [(T0, False), (T0 + M, True), (T0 + 2 * M, True)], T0 + 3 * M),
    ],
)
def test_after_a_flush(ts: int, closed_after: list[tuple[int, bool]], current: int | None) -> None:
    b = CandleBuilder()
    seen: list[tuple[int, bool]] = []
    _flushed(b, seen)
    b.apply(tick(ts, 101.0))
    assert seen == closed_after
    assert [c.minute_ts for c in b.closed("F")] == [m for m, _ in closed_after]
    cur = b.current("F")
    assert (cur.minute_ts if cur else None) == current
    assert all(c.close == 100.0 for c in b.closed("F"))  # carried forward from T0


def test_live_and_replay_close_the_same_minutes_across_an_outage() -> None:
    """Live, the flush closes T0 during the silence; replay's clock waits for the next tick."""
    ticks = [tick(T0 + 5_000, 100.0), tick(T0 + 3 * M + 10_000, 101.0), tick(T0 + 4 * M, 102.0)]
    live, replay = CandleBuilder(), CandleBuilder()
    live.apply(ticks[0])
    live.flush_stale(T0 + M + 2_500)  # the half-second timer, early in the silence
    for t in ticks[1:]:
        live.apply(t)
    for t in ticks:
        replay.apply(t)
    expected = [(T0, False), (T0 + M, True), (T0 + 2 * M, True), (T0 + 3 * M, False)]
    assert [(c.minute_ts, c.synthetic) for c in live.closed("F")] == expected
    assert [(c.minute_ts, c.synthetic) for c in replay.closed("F")] == expected


def test_seeded_candles_are_not_carried_forward() -> None:
    """A backfill that ends early must not turn into a burst of synthetic minutes at start."""
    b = CandleBuilder()
    seen: list[int] = []
    b.on_close(lambda c: seen.append(c.minute_ts))
    b.seed("F", [Candle("F", T0, 100, 100, 100, 100)])
    b.apply(tick(T0 + 30 * M, 101.0))
    assert seen == []
    assert b.apply(tick(T0 + 10, 99.0)) == []  # older than the seeded minute: dropped
    assert b.current("F").minute_ts == T0 + 30 * M  # type: ignore[union-attr]


def test_no_carry_forward_overnight() -> None:
    """Left running overnight, the first tick of the morning opens a fresh minute."""
    b = CandleBuilder()
    seen: list[tuple[int, bool]] = []
    _flushed(b, seen)
    b.apply(tick(T0 + 24 * 60 * M, 101.0))  # the next IST day
    assert seen == [(T0, False)]


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


# -- net volume: which side initiated each trade (Milestone E8) -------------------------------


@pytest.mark.parametrize(
    ("ltp", "bid", "ask", "prev_ltp", "prev_side", "side"),
    [
        (101.0, 100.0, 101.0, None, 0, 1),  # at the ask: a buyer paid up
        (101.5, 100.0, 101.0, None, 0, 1),  # through the ask
        (100.0, 100.0, 101.0, None, 0, -1),  # at the bid: a seller hit it
        (99.5, 100.0, 101.0, None, 0, -1),
        (100.5, 100.0, 101.0, 100.2, 0, 1),  # between: tick rule, up from the last trade
        (100.5, 100.0, 101.0, 100.8, 0, -1),  # between, down
        (100.5, 100.0, 101.0, 100.5, -1, -1),  # between, unchanged: keeps the last side
        (100.5, None, None, 100.0, 0, 1),  # no quote yet: tick rule alone
        (100.5, None, None, None, 0, 0),  # nothing known
        (100.5, 100.0, 101.0, None, 0, 0),  # between with no previous trade
    ],
)
def test_trade_side(
    ltp: float,
    bid: float | None,
    ask: float | None,
    prev_ltp: float | None,
    prev_side: int,
    side: int,
) -> None:
    assert trade_side(ltp, bid, ask, prev_ltp, prev_side) == side


def fq(ts: int, ltp: float, vol: int, bid: float, ask: float) -> Tick:
    return Tick(key="F", ts=ts, ltp=ltp, volume=vol, bid=bid, ask=ask)


def test_trades_are_signed_against_the_quote_before_the_tick() -> None:
    b = CandleBuilder()
    b.apply(fq(T0, 100.0, 1_000, 99.5, 100.0))  # first: no trade to sign yet
    # Printed at 100.0, the ask as it stood; the tick's own quote has moved up after it.
    b.apply(fq(T0 + 1_000, 100.0, 1_050, 100.0, 100.5))
    # Printed at 100.0, now the bid (from the last tick): a sell.
    b.apply(fq(T0 + 2_000, 100.0, 1_080, 99.5, 100.0))
    # Between 99.5 and 100.0, up from 100.0? No, down to 99.8: a sell by the tick rule.
    b.apply(fq(T0 + 3_000, 99.8, 1_100, 99.5, 100.0))
    c = b.current("F")
    assert c is not None
    assert (c.volume, c.buy_volume, c.sell_volume) == (100, 50, 50)


def test_net_volume_resets_each_minute_and_gaps_are_zero() -> None:
    b = CandleBuilder()
    b.apply(fq(T0, 100.0, 1_000, 99.5, 100.0))
    b.apply(fq(T0 + 1_000, 100.0, 1_040, 99.5, 100.0))  # 40 bought
    closed = b.apply(fq(T0 + 3 * M, 99.5, 1_040, 99.5, 100.0))  # quiet for two minutes
    b.apply(fq(T0 + 3 * M + 1_000, 99.5, 1_060, 99.5, 100.0))  # 20 sold
    assert [(c.buy_volume, c.sell_volume) for c in closed] == [(40, 0), (0, 0), (0, 0)]
    cur = b.current("F")
    assert cur is not None
    assert (cur.buy_volume, cur.sell_volume) == (0, 20)


def test_no_volume_means_no_side_information() -> None:
    b = CandleBuilder()
    b.apply(tick(T0, 25_000.0))  # an index: no volume field
    closed = b.apply(tick(T0 + 2 * M, 25_010.0))
    assert [(c.buy_volume, c.sell_volume) for c in closed] == [(None, None), (None, None)]


def test_seeded_candles_keep_unknown_sides() -> None:
    b = CandleBuilder()
    b.seed("F", [Candle("F", T0, 1, 1, 1, 1, volume=500)])
    assert b.closed("F")[0].buy_volume is None


def test_store_roundtrip_with_and_without_sides() -> None:
    conn = connect(":memory:")
    store = CandleStore(conn)
    store.write(Candle("F", T0, 1, 2, 0.5, 1.5, 100, buy_volume=60, sell_volume=30))
    store.write_many([Candle("F", T0 + M, 1, 1, 1, 1, 10)])
    got = store.read("F", T0, T0 + 2 * M)
    assert [(c.buy_volume, c.sell_volume) for c in got] == [(60, 30), (None, None)]


# -- other bar sizes, for the chart intervals (E27) ----------------------------------------

S10 = 10_000


def test_ten_second_bars_close_on_their_own_boundary() -> None:
    b = CandleBuilder(bar_ms=S10)
    b.apply(tick(T0 + 1_000, 100.0))
    b.apply(tick(T0 + 9_000, 102.0))
    closed = b.apply(tick(T0 + S10 + 100, 101.0))
    assert [(c.minute_ts, c.open, c.high, c.close) for c in closed] == [(T0, 100.0, 102.0, 102.0)]
    assert b.current("F").minute_ts == T0 + S10  # type: ignore[union-attr]


def test_ten_second_gaps_are_carried_forward_bar_by_bar() -> None:
    b = CandleBuilder(bar_ms=S10)
    b.apply(tick(T0, 100.0))
    closed = b.apply(tick(T0 + 4 * S10 + 1, 110.0))
    assert [c.minute_ts for c in closed] == [T0, T0 + S10, T0 + 2 * S10, T0 + 3 * S10]
    assert [c.synthetic for c in closed] == [False, True, True, True]


def test_ten_second_flush_waits_for_the_bar_end_plus_grace() -> None:
    b = CandleBuilder(bar_ms=S10)
    b.apply(tick(T0 + 1_000, 100.0))
    assert b.flush_stale(T0 + S10 + 1_000) == []
    assert len(b.flush_stale(T0 + S10 + 2_500)) == 1


def test_ten_second_bars_split_volume_and_sides_per_bar() -> None:
    b = CandleBuilder(bar_ms=S10)
    b.apply(Tick(key="F", ts=T0, ltp=100.0, volume=1_000, bid=99.5, ask=100.0))
    b.apply(Tick(key="F", ts=T0 + 5_000, ltp=100.0, volume=1_200, bid=99.5, ask=100.0))  # buy 200
    b.apply(Tick(key="F", ts=T0 + S10, ltp=99.5, volume=1_250, bid=99.5, ask=100.0))  # sell 50
    b.apply(Tick(key="F", ts=T0 + 2 * S10, ltp=99.5, volume=1_250))
    first, second = b.closed("F")
    assert (first.volume, first.buy_volume, first.sell_volume) == (200, 200, 0)
    assert (second.volume, second.buy_volume, second.sell_volume) == (50, 0, 50)


@pytest.mark.parametrize("bar_ms", [M, S10, 30_000])
def test_a_bar_size_must_divide_a_day(bar_ms: int) -> None:
    assert CandleBuilder(bar_ms=bar_ms).bar_ms == bar_ms


def test_a_bar_size_that_does_not_divide_a_minute_is_refused() -> None:
    with pytest.raises(ValueError, match="bar"):
        CandleBuilder(bar_ms=7_000)

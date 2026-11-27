"""The chart's 10 s, 30 s and 5 m bars (E27): display only, beside the 1-minute candles."""

from __future__ import annotations

import pytest

from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.market.candles import CandleBuilder
from tradedisha.market.chart_bars import INTERVALS, ChartBar, ChartBars
from tradedisha.parameters.model import ParameterSet

M = 60_000
T0 = 1_700_000_100_000 // (5 * M) * (5 * M)
SPOT, FUT, GOLD = "NSE_INDEX|Nifty 50", "NSE_FO|FUT", "MCX_FO|GOLD"


class Rig:
    def __init__(self) -> None:
        self.minutes = CandleBuilder()  # the 1-minute candles the 5 m bars come from
        self.seen: list[ChartBar] = []
        self.chart = ChartBars(ParameterSet, self.minutes.closed, self.seen.append)
        self.chart.add("NIFTY", SPOT, FUT)
        self.chart.add("GOLD", GOLD, GOLD)
        self.minutes.on_close(self.chart.on_minute_close)

    def tick(self, key: str, ts: int, ltp: float, vol: int | None = None) -> None:
        t = Tick(key=key, ts=ts, ltp=ltp, volume=vol)
        self.minutes.apply(t)
        self.chart.on_tick(StampedTick(t, ts))


def test_intervals() -> None:
    assert INTERVALS == {"10s": 10_000, "30s": 30_000, "1m": M, "5m": 5 * M}


def test_a_ten_second_close_is_sent_with_its_role_and_the_line_at_that_bar() -> None:
    r = Rig()
    r.tick(SPOT, T0 + 1_000, 100.0)
    r.tick(FUT, T0 + 2_000, 101.0, vol=1_000)
    r.tick(FUT, T0 + 3_000, 101.5, vol=1_100)
    r.tick(SPOT, T0 + 10_500, 100.5)
    r.tick(FUT, T0 + 10_600, 102.0, vol=1_200)
    tens = [b for b in r.seen if b.interval == "10s"]
    assert [(b.name, b.role, b.candle.minute_ts) for b in tens] == [
        ("NIFTY", "price", T0),
        ("NIFTY", "vol", T0),
    ]
    price, vol = tens
    assert price.overlay is not None
    assert price.overlay.minute_ts == T0
    assert vol.overlay is None
    assert vol.candle.volume == 100


def test_a_metal_is_its_own_price_and_volume() -> None:
    r = Rig()
    r.tick(GOLD, T0, 135_000.0, vol=10)
    r.tick(GOLD, T0 + 10_000, 135_010.0, vol=12)
    roles = [(b.name, b.role) for b in r.seen if b.interval == "10s"]
    assert roles == [("GOLD", "price"), ("GOLD", "vol")]


def test_other_keys_are_ignored() -> None:
    r = Rig()
    r.chart.on_tick(StampedTick(Tick(key="NSE_FO|OPTION", ts=T0, ltp=1.0), T0))
    r.chart.on_tick(StampedTick(Tick(key="NSE_FO|OPTION", ts=T0 + M, ltp=1.0), T0 + M))
    assert r.seen == []
    with pytest.raises(KeyError):
        r.chart.bars("BANKNIFTY", "10s")


def test_a_five_minute_bar_is_sent_when_its_last_minute_closes() -> None:
    r = Rig()
    for i in range(6):
        r.tick(SPOT, T0 + i * M + 1, 100.0 + i)
    fives = [b for b in r.seen if b.interval == "5m"]
    assert [(b.role, b.candle.minute_ts, b.candle.open, b.candle.close) for b in fives] == [
        ("price", T0, 100.0, 104.0)
    ]


def test_bars_for_each_interval_and_the_lines_over_them() -> None:
    r = Rig()
    for i in range(12):
        r.tick(SPOT, T0 + i * 30_000 + 1, 100.0 + i)
        r.tick(FUT, T0 + i * 30_000 + 2, 100.0 + i, vol=100 * (i + 1))
    for interval, n in [("10s", 33), ("30s", 11), ("1m", 5), ("5m", 1)]:
        price, vol, lines = r.chart.bars("NIFTY", interval)
        assert len(price) == n, interval
        assert len(lines) == n
        assert vol, interval
    _, _, lines = r.chart.bars("NIFTY", "30s")
    assert lines[-1].vwap is not None


def test_seeding_replays_stored_ticks_without_sending_frames() -> None:
    r = Rig()
    stored = [Tick(key=SPOT, ts=T0 + i * 5_000, ltp=100.0 + i) for i in range(10)]
    r.chart.seed(stored)
    assert r.seen == []
    price, _, _ = r.chart.bars("NIFTY", "10s")
    assert [c.minute_ts for c in price] == [T0 + i * 10_000 for i in range(4)]
    r.tick(SPOT, T0 + 50_000, 120.0)  # live again: the seeded bar closes and is sent
    assert [b.candle.minute_ts for b in r.seen if b.interval == "10s"] == [T0 + 40_000]


def test_flush_closes_a_quiet_bar() -> None:
    r = Rig()
    r.tick(SPOT, T0 + 1_000, 100.0)
    r.chart.flush_stale(T0 + 13_000)
    assert [b.candle.minute_ts for b in r.seen if b.interval == "10s"] == [T0]

"""Synthetic and replay providers honour the provider contract."""

from datetime import date, datetime

from tradedisha.clock import IST, DrivenClock, ist_to_ms
from tradedisha.feed.provider import Tick
from tradedisha.feed.replay import ReplayProvider
from tradedisha.feed.synthetic import SyntheticProvider, SyntheticUniverse
from tradedisha.instruments.resolve import resolve_index
from tradedisha.instruments.synthetic_master import build_synthetic_master
from tradedisha.store.db import connect
from tradedisha.store.ticks import TickStore

TODAY = date(2026, 11, 12)


def _resolved() -> list:  # type: ignore[type-arg]
    master = build_synthetic_master(TODAY)
    return [
        resolve_index(master, "NIFTY", TODAY, 25_000.0, strike_window=2),
        resolve_index(master, "BANKNIFTY", TODAY, 56_000.0, strike_window=1),
    ]


def _universes() -> list[SyntheticUniverse]:
    return [SyntheticUniverse.from_resolved(r) for r in _resolved()]


async def test_synthetic_emits_only_subscribed_keys_with_plausible_prices() -> None:
    resolved = _resolved()
    nifty = resolved[0]
    p = SyntheticProvider(_universes(), ticks_per_second=2000, seed=1)
    await p.connect()
    await p.subscribe([nifty.spot.instrument_key, nifty.future.instrument_key])
    assert p.health().state == "connected"
    assert p.health().subscribed == 2

    seen: list[Tick] = []
    async for t in p.ticks():
        seen.append(t)
        if len(seen) >= 20:
            break
    await p.close()

    keys = {t.key for t in seen}
    assert keys == {nifty.spot.instrument_key, nifty.future.instrument_key}
    spots = [t.ltp for t in seen if t.key == nifty.spot.instrument_key]
    assert all(24_000 < x < 26_000 for x in spots)
    futs = [t for t in seen if t.key == nifty.future.instrument_key]
    assert all(t.volume is not None for t in futs)
    assert p.health().state == "disconnected"


async def test_synthetic_option_ticks_carry_oi_and_iv() -> None:
    resolved = _resolved()
    nifty = resolved[0]
    p = SyntheticProvider(_universes(), ticks_per_second=2000, seed=2)
    await p.connect()
    await p.subscribe(nifty.option_keys)
    first: Tick | None = None
    async for t in p.ticks():
        first = t
        break
    await p.close()
    assert first is not None
    assert first.oi is not None
    assert first.oi > 0
    assert first.iv is not None
    assert first.iv > 0
    assert first.ltp >= 0.05


async def test_replay_emits_recorded_ticks_in_order_and_drives_clock() -> None:
    conn = connect(":memory:")
    store = TickStore(conn)
    t0 = ist_to_ms(datetime(2026, 11, 12, 9, 15, 0, tzinfo=IST))
    for i in range(5):
        store.add(Tick(key="A" if i % 2 == 0 else "B", ts=t0 + i * 1000, ltp=float(i)))
    store.flush()

    clock = DrivenClock(datetime(2026, 11, 12, 9, 0, tzinfo=IST))
    p = ReplayProvider(store, TODAY, speed=0, clock=clock, drop_ranges=[(t0 + 2000, t0 + 3000)])
    await p.connect()
    await p.subscribe(["A", "B"])

    out = [t async for t in p.ticks()]

    assert [t.ltp for t in out] == [0.0, 1.0, 3.0, 4.0]  # tick at t0+2000 dropped
    assert clock().hour == 9
    assert clock().second == 4
    assert p.health().state == "disconnected"
    assert p.emitted == 4


async def test_replay_filters_to_subscribed_keys() -> None:
    conn = connect(":memory:")
    store = TickStore(conn)
    t0 = ist_to_ms(datetime(2026, 11, 12, 10, 0, tzinfo=IST))
    store.add(Tick(key="A", ts=t0, ltp=1.0))
    store.add(Tick(key="B", ts=t0 + 1, ltp=2.0))
    store.flush()
    p = ReplayProvider(store, TODAY, speed=0)
    await p.subscribe(["B"])
    out = [t async for t in p.ticks()]
    assert [t.key for t in out] == ["B"]


async def test_synthetic_health_reports_last_tick() -> None:
    p = SyntheticProvider(_universes(), ticks_per_second=2000, seed=3)
    await p.connect()
    await p.subscribe(["NSE_INDEX|Nifty 50"])
    assert p.health().last_tick_ts is None
    async for _ in p.ticks():
        break
    await p.close()
    assert p.health().last_tick_ts is not None

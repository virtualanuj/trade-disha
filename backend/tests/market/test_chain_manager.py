"""Re-centring and minute persistence through the ChainManager."""

from datetime import date

from tradedisha.events import EventBus
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.instruments.resolve import resolve_index
from tradedisha.instruments.synthetic_master import build_synthetic_master
from tradedisha.market.chain_manager import ChainManager, SubscriptionChange
from tradedisha.store.db import connect

TODAY = date(2026, 11, 12)
SPOT = "NSE_INDEX|Nifty 50"


def _mgr(changes: list[SubscriptionChange]) -> ChainManager:
    master = build_synthetic_master(TODAY)
    resolved = {"NIFTY": resolve_index(master, "NIFTY", TODAY, 25_000.0, strike_window=3)}
    return ChainManager(
        master=master,
        resolved=resolved,
        today=TODAY,
        strike_window=3,
        recenter_strikes=2,
        conn=connect(":memory:"),
        events=EventBus(),
        on_subscription_change=changes.append,
    )


def _tick(mgr: ChainManager, key: str, ts: int, ltp: float, oi: int | None = None) -> None:
    mgr.on_tick(StampedTick(Tick(key=key, ts=ts, ltp=ltp, oi=oi), ts))


def test_recentre_when_atm_moves_two_strikes() -> None:
    changes: list[SubscriptionChange] = []
    mgr = _mgr(changes)
    chain = mgr.chains["NIFTY"]
    assert list(chain.rows) == [24_850, 24_900, 24_950, 25_000, 25_050, 25_100, 25_150]

    _tick(mgr, SPOT, 1_000, 25_060.0)  # ATM 25050: one step, no recentre
    assert chain.atm == 25_000
    assert changes == []

    _tick(mgr, SPOT, 2_000, 25_110.0)  # ATM 25100: two steps -> recentre
    assert chain.atm == 25_100
    assert list(chain.rows) == [24_950, 25_000, 25_050, 25_100, 25_150, 25_200, 25_250]
    assert len(changes) == 1
    assert len(changes[0].add) == 4  # 25200 and 25250, CE and PE
    assert len(changes[0].remove) == 4  # 24850 and 24900
    assert mgr.resolved["NIFTY"].atm == 25_100
    assert len(mgr.pending_window_events) == 1  # no running loop in this test


def test_minute_close_persists_rows() -> None:
    mgr = _mgr([])
    chain = mgr.chains["NIFTY"]
    ce = chain.rows[25_000].ce.key
    _tick(mgr, ce, 60_000, 100.0, oi=1_000)
    _tick(mgr, ce, 61_000, 101.0, oi=1_100)
    assert mgr.minutes_written == 0
    _tick(mgr, ce, 120_500, 102.0, oi=1_300)  # first tick of the next minute closes 60_000
    assert mgr.minutes_written == 7
    assert mgr.store.count("NIFTY") == 7
    assert len(chain.history) == 1

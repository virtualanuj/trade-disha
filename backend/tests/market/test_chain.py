"""Chain derived values against hand-computed answers (spec §7.2)."""

from datetime import date

from tradedisha.feed.provider import Tick
from tradedisha.instruments.resolve import resolve_index
from tradedisha.instruments.synthetic_master import build_synthetic_master
from tradedisha.market.chain import ChainState, classify_buildup

TODAY = date(2026, 11, 12)


def _chain(window: int = 2, spot: float = 25_000.0) -> ChainState:
    master = build_synthetic_master(TODAY)
    return ChainState.from_resolved(
        resolve_index(master, "NIFTY", TODAY, spot, strike_window=window)
    )


def _fill(chain: ChainState, oi: dict[tuple[float, str], int], ts: int = 1_000) -> None:
    for (strike, side), val in oi.items():
        row = chain.rows[strike]
        leg = row.ce if side == "ce" else row.pe
        chain.apply(Tick(key=leg.key, ts=ts, ltp=10.0, oi=val))


def test_window_rows_sorted_and_keys_mapped() -> None:
    c = _chain()
    assert list(c.rows) == [24_900, 24_950, 25_000, 25_050, 25_100]
    assert len(c.keys()) == 10
    assert c.apply(Tick(key="NSE_FO|nope", ts=1, ltp=1.0)) is False


def test_pcr_over_atm_range() -> None:
    c = _chain()
    _fill(c, {(24_900, "ce"): 100, (25_000, "ce"): 300, (25_000, "pe"): 600, (25_100, "pe"): 200})
    assert c.pcr(strike_range=0) == 2.0  # 600 / 300 at ATM only
    assert c.pcr(strike_range=5) == 2.0  # 800 / 400 across the window
    empty = _chain()
    assert empty.pcr() is None


def test_max_pain_is_strike_with_lowest_buyer_payout() -> None:
    c = _chain()
    # Heavy call OI above and put OI below: pain minimised in the middle.
    _fill(
        c,
        {
            (24_900, "pe"): 1_000,
            (24_950, "pe"): 500,
            (25_050, "ce"): 500,
            (25_100, "ce"): 1_000,
            (25_000, "ce"): 50,
            (25_000, "pe"): 50,
        },
    )
    # payout at 25000: puts below worth (25000-24900)*1000 + 50*500 = 125k; calls above 0 -> 125k
    # payout at 24950: puts (50*1000) = 50k; calls (100*500+150*1000)=200k -> 250k
    # payout at 25050: puts (150*1000+100*500+50*50)=202.5k; calls (50*1000)=50k -> 252.5k
    assert c.max_pain() == 25_000


def test_oi_change_since_open_and_since_prev_minute() -> None:
    c = _chain()
    leg = c.rows[25_000].ce
    c.apply(Tick(key=leg.key, ts=1, ltp=100.0, oi=1_000))
    c.apply(Tick(key=leg.key, ts=2, ltp=105.0, oi=1_200))
    assert leg.oi_chg_open == 200
    assert [leg.oi_chg_min] == [None]  # no minute closed yet
    assert leg.chg_pct == 5.0

    c.close_minute(60_000)
    assert [leg.buildup] == ["none"]  # first minute has no previous reference
    c.apply(Tick(key=leg.key, ts=61_000, ltp=110.0, oi=1_500))
    assert leg.oi_chg_min == 300
    c.close_minute(120_000)
    assert [leg.buildup] == ["long_buildup"]
    assert len(c.history) == 2
    assert c.history[-1].minute_ts == 120_000


def test_buildup_classification() -> None:
    assert classify_buildup(1, 1) == "long_buildup"
    assert classify_buildup(-1, 1) == "short_buildup"
    assert classify_buildup(1, -1) == "short_covering"
    assert classify_buildup(-1, -1) == "long_unwinding"
    assert classify_buildup(0, 5) == "none"


def test_set_window_keeps_state_for_surviving_strikes() -> None:
    master = build_synthetic_master(TODAY)
    c = _chain()
    leg = c.rows[25_050].ce
    c.apply(Tick(key=leg.key, ts=1, ltp=50.0, oi=777))

    moved = resolve_index(master, "NIFTY", TODAY, 25_100.0, strike_window=2)
    c.set_window(moved)

    assert list(c.rows) == [25_000, 25_050, 25_100, 25_150, 25_200]
    assert c.rows[25_050].ce.oi == 777
    assert c.rows[25_200].ce.oi is None
    assert c.atm == 25_100

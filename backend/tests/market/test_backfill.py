"""Late-start backfill: today's candles and the opening-OI baseline from Upstox REST."""

from datetime import date, datetime

import httpx
import pytest

from tradedisha.clock import IST, ist_to_ms
from tradedisha.feed.provider import Tick
from tradedisha.feed.upstox import Unauthorized
from tradedisha.instruments.resolve import resolve_index
from tradedisha.instruments.synthetic_master import build_synthetic_master
from tradedisha.market.backfill import (
    OptionSnapshot,
    apply_baseline,
    fetch_intraday_candles,
    fetch_option_chain,
    parse_candles,
    parse_chain,
)
from tradedisha.market.chain import ChainState

TODAY = date(2026, 11, 13)


def _ms(h: int, m: int) -> int:
    return ist_to_ms(datetime(2026, 11, 13, h, m, tzinfo=IST))


ROWS = [  # Upstox sends newest first
    ["2026-11-13T09:17:00+05:30", 25010, 25020, 25005, 25015, 0, 0],
    ["2026-11-13T09:16:00+05:30", 25000, 25012, 24998, 25010, 1200, 0],
    ["2026-11-13T09:15:00+05:30", 24990, 25001, 24985, 25000, 3400, 0],
]


def test_candles_come_back_oldest_first_without_the_minute_in_progress() -> None:
    candles = parse_candles("K", ROWS, before_ms=_ms(9, 17))

    assert [c.minute_ts for c in candles] == [_ms(9, 15), _ms(9, 16)]
    first = candles[0]
    assert (first.open, first.high, first.low, first.close, first.volume) == (
        24990,
        25001,
        24985,
        25000,
        3400,
    )
    assert not first.synthetic


async def test_fetch_candles_encodes_the_key_and_sends_the_token() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.raw_path.decode().endswith("/intraday/NSE_INDEX%7CNifty%2050/minutes/1")
        assert request.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, json={"status": "success", "data": {"candles": ROWS}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        candles = await fetch_intraday_candles(
            client, "tok", "NSE_INDEX|Nifty 50", before_ms=_ms(9, 30)
        )
    assert len(candles) == 3


async def test_fetch_raises_unauthorized_on_401() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(401, json={}))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(Unauthorized):
            await fetch_intraday_candles(client, "tok", "K", before_ms=0)


def _chain() -> ChainState:
    master = build_synthetic_master(TODAY)
    return ChainState.from_resolved(
        resolve_index(master, "NIFTY", TODAY, 25_000.0, strike_window=1)
    )


def _payload(chain: ChainState, *, skip: str | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in chain.rows.values():
        entry: dict[str, object] = {"strike_price": row.strike}
        for name, leg in (("call_options", row.ce), ("put_options", row.pe)):
            if leg.key == skip:
                continue
            entry[name] = {
                "instrument_key": leg.key,
                "market_data": {"ltp": 100.0, "oi": 5_000.0, "prev_oi": 4_000.0},
            }
        rows.append(entry)
    return rows


def test_parse_chain_reads_both_sides_of_every_strike() -> None:
    chain = _chain()
    snaps = parse_chain(_payload(chain))

    assert set(snaps) == set(chain.keys())
    assert next(iter(snaps.values())) == OptionSnapshot(chain.keys()[0], 5_000, 4_000)


def test_baseline_replaces_first_seen_oi_so_change_is_since_the_open() -> None:
    chain = _chain()
    key = chain.keys()[0]
    chain.apply(Tick(key=key, ts=_ms(11, 0), ltp=100.0, oi=5_200))  # late start
    leg = chain.rows[chain.key_set[key][0]].ce
    assert leg.oi_chg_open == 0  # measured from the first tick: wrong after a late start

    done = apply_baseline(chain, parse_chain(_payload(chain)))

    assert done == len(chain.keys())
    assert leg.oi_chg_open == 1_200
    assert chain.oi_baseline == "session_open"
    chain.apply(Tick(key=key, ts=_ms(11, 1), ltp=101.0, oi=5_300))
    assert leg.oi_chg_open == 1_300  # later ticks do not disturb the baseline


def test_a_missing_leg_leaves_the_chain_flagged_partial() -> None:
    chain = _chain()
    missing = chain.keys()[-1]
    apply_baseline(chain, parse_chain(_payload(chain, skip=missing)))
    assert chain.oi_baseline == "partial"


def test_baseline_can_be_limited_to_newly_added_strikes() -> None:
    chain = _chain()
    first, second = chain.keys()[:2]
    assert apply_baseline(chain, parse_chain(_payload(chain)), only={second}) == 1
    assert chain.oi_baseline == "partial"
    assert first in chain.key_set


async def test_fetch_option_chain_asks_for_the_resolved_expiry() -> None:
    chain = _chain()

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.params["instrument_key"] == "NSE_INDEX|Nifty 50"
        assert request.url.params["expiry_date"] == "2026-11-17"
        return httpx.Response(200, json={"status": "success", "data": _payload(chain)})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        snaps = await fetch_option_chain(client, "tok", "NSE_INDEX|Nifty 50", date(2026, 11, 17))
    assert len(snaps) == len(chain.keys())

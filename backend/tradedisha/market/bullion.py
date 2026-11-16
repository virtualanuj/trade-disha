"""BULLION: gold and silver MCX futures, shown for reference on their own tab. Spec §6.6.

Display only: no indicator, signal or paper trade reads these, and their ticks are not
recorded (MCX trades until 23:30 and the replay clock follows recorded ticks). They have
their own candle builder, because the shared one drives the bias engine.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from datetime import date
from pathlib import Path

import httpx

from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.feed.upstox import FullQuote, fetch_quotes
from tradedisha.instruments.models import Instrument
from tradedisha.instruments.resolve import resolve_commodity_months
from tradedisha.instruments.upstox_master import load_mcx_master
from tradedisha.market.backfill import fetch_52w_range, fetch_intraday_candles
from tradedisha.market.candles import MINUTE_MS, Candle, CandleBuilder

log = logging.getLogger(__name__)

METALS: tuple[str, ...] = ("GOLD", "SILVER")
GOLD_PER_KG = 100  # GOLD is quoted per 10 g, SILVER per kg
CANDLE_HISTORY = 900  # minutes: MCX runs 09:00 to 23:30


@dataclass(frozen=True)
class BullionContract:
    """One metal's near and next futures, with what is fetched once at start."""

    metal: str
    near: Instrument
    next: Instrument | None
    quote: FullQuote | None = None  # near contract, at start
    range_high: float | None = None  # the contract's high over the last year, to yesterday
    range_low: float | None = None


@dataclass(frozen=True)
class MetalSnapshot:
    metal: str
    trading_symbol: str
    expiry: date | None
    lot_size: int
    ltp: float | None
    prev_close: float | None
    change: float | None
    change_pct: float | None
    day_open: float | None
    day_high: float | None
    day_low: float | None
    range_pos: float | None  # 0 at the day's low, 1 at the high
    atp: float | None
    volume: int | None
    oi: int | None
    bid: float | None
    ask: float | None
    bid_qty: int | None
    ask_qty: int | None
    spread: float | None  # ask minus bid
    tbq: int | None
    tsq: int | None
    buy_sell_ratio: float | None  # total buy over total sell quantity
    range_high: float | None
    range_low: float | None
    lower_circuit: float | None
    upper_circuit: float | None
    next_symbol: str | None
    next_expiry: date | None
    next_ltp: float | None
    calendar_spread: float | None  # next minus near
    calendar_spread_pct: float | None
    updated_ts: int | None


@dataclass(frozen=True)
class BullionSnapshot:
    metals: list[MetalSnapshot]
    ratio: float | None  # gold per kg over silver per kg


# -- pure maths -------------------------------------------------------------------


def _pct(value: float | None, base: float | None) -> float | None:
    if value is None or not base:
        return None
    return round((value - base) / base * 100, 2)


def _diff(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else round(a - b, 2)


def merge_tick(old: Tick | None, new: Tick) -> Tick:
    """`new` with every field it leaves as None ("unchanged") carried over from `old`."""
    if old is None:
        return new
    carried = {f.name: getattr(old, f.name) for f in fields(Tick) if getattr(new, f.name) is None}
    return replace(new, **carried)


def metal_snapshot(
    c: BullionContract, near: Tick | None, next_: Tick | None, day: tuple[float, float, float]
) -> MetalSnapshot:
    """One metal's view; `day` is (open, high, low) as tracked so far."""
    q = c.quote
    ltp = near.ltp if near else (q.ltp if q else None)
    prev = (near.close_prev if near else None) or (q.prev_close if q else None)
    d_open, d_high, d_low = day
    span = d_high - d_low if d_high and d_low else 0
    pos = round((ltp - d_low) / span, 3) if ltp is not None and span > 0 else None
    tbq, tsq = (near.tbq, near.tsq) if near else (None, None)
    # the year to yesterday, widened by today
    hi = max(c.range_high, d_high) if c.range_high else None
    lo = min(c.range_low, d_low) if c.range_low and d_low else c.range_low
    next_ltp = next_.ltp if next_ else None
    return MetalSnapshot(
        metal=c.metal,
        trading_symbol=c.near.trading_symbol,
        expiry=c.near.expiry,
        lot_size=c.near.lot_size,
        ltp=ltp,
        prev_close=prev,
        change=_diff(ltp, prev),
        change_pct=_pct(ltp, prev),
        day_open=d_open or None,
        day_high=d_high or None,
        day_low=d_low or None,
        range_pos=pos,
        atp=near.atp if near else None,
        volume=near.volume if near else None,
        oi=near.oi if near else None,
        bid=near.bid if near else None,
        ask=near.ask if near else None,
        bid_qty=near.bid_qty if near else None,
        ask_qty=near.ask_qty if near else None,
        spread=_diff(near.ask, near.bid) if near else None,
        tbq=tbq,
        tsq=tsq,
        buy_sell_ratio=round(tbq / tsq, 2) if tbq and tsq else None,
        range_high=hi,
        range_low=lo,
        lower_circuit=q.lower_circuit if q else None,
        upper_circuit=q.upper_circuit if q else None,
        next_symbol=c.next.trading_symbol if c.next else None,
        next_expiry=c.next.expiry if c.next else None,
        next_ltp=next_ltp,
        calendar_spread=_diff(next_ltp, ltp),
        calendar_spread_pct=_pct(next_ltp, ltp),
        updated_ts=near.ts if near else None,
    )


def gold_silver_ratio(gold: float | None, silver: float | None) -> float | None:
    """How many kilograms of silver one kilogram of gold buys."""
    if not gold or not silver:
        return None
    return round(gold * GOLD_PER_KG / silver, 2)


# -- live state -------------------------------------------------------------------


class BullionTracker:
    """Latest tick per bullion contract, the day's range, and the near contracts' candles."""

    def __init__(
        self,
        contracts: dict[str, BullionContract],
        on_candle: Callable[[str, Candle], None] | None = None,
    ) -> None:
        self.contracts = contracts
        self.candles = CandleBuilder(max_history=CANDLE_HISTORY)
        self._latest: dict[str, Tick] = {}
        self._day: dict[str, tuple[float, float, float]] = {}
        self._metal_of_near = {c.near.instrument_key: m for m, c in contracts.items()}
        keys = set(self._metal_of_near)
        keys.update(c.next.instrument_key for c in contracts.values() if c.next)
        self.keys: frozenset[str] = frozenset(keys)
        for m, c in contracts.items():
            q = c.quote
            if q is not None:
                self._day[m] = (q.day_open or 0.0, q.day_high or 0.0, q.day_low or 0.0)
        if on_candle is not None:
            self.candles.on_close(lambda cd: on_candle(self._metal_of_near[cd.key], cd))

    def on_tick(self, st: StampedTick) -> None:
        t = st.tick
        if t.key not in self.keys:
            return
        self._latest[t.key] = merge_tick(self._latest.get(t.key), t)
        metal = self._metal_of_near.get(t.key)
        if metal is None:
            return  # a next-month contract: price only
        o, h, low = self._day.get(metal, (0.0, 0.0, 0.0))
        self._day[metal] = (
            t.day_open or o or t.ltp,
            t.day_high or max(h, t.ltp),
            t.day_low or (min(low, t.ltp) if low else t.ltp),
        )
        self.candles.apply(t)

    def seed(self, metal: str, candles: list[Candle]) -> None:
        self.candles.seed(self.contracts[metal].near.instrument_key, candles)

    def closed_candles(self, metal: str) -> list[Candle]:
        c = self.contracts.get(metal)
        return self.candles.closed(c.near.instrument_key) if c else []

    def snapshot(self) -> BullionSnapshot:
        metals = []
        for m, c in self.contracts.items():
            nxt = self._latest.get(c.next.instrument_key) if c.next else None
            day = self._day.get(m, (0.0, 0.0, 0.0))
            metals.append(metal_snapshot(c, self._latest.get(c.near.instrument_key), nxt, day))
        by = {s.metal: s.ltp for s in metals}
        return BullionSnapshot(metals, gold_silver_ratio(by.get("GOLD"), by.get("SILVER")))


# -- start ------------------------------------------------------------------------


async def load_contracts(
    data_dir: Path, today: date, *, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, BullionContract]:
    """Metal -> near and next futures. Never raises: the NSE feed must start without it."""
    try:
        master = await load_mcx_master(data_dir, today, METALS, transport=transport)
    except Exception as exc:
        log.warning("MCX instrument file unavailable, no bullion: %s", type(exc).__name__)
        return {}
    out: dict[str, BullionContract] = {}
    for metal in METALS:
        months = resolve_commodity_months(master, metal, today)
        if months is None:
            log.warning("no MCX %s future after %s", metal, today)
        else:
            out[metal] = BullionContract(metal, months[0], months[1])
    return out


async def enrich(
    client: httpx.AsyncClient, token: str, contracts: dict[str, BullionContract], today: date
) -> dict[str, BullionContract]:
    """Add the start-of-day quote and the contract's one-year range; each fails soft."""
    try:
        quotes = await fetch_quotes(
            client, token, [c.near.instrument_key for c in contracts.values()]
        )
    except Exception as exc:
        log.warning("bullion quote failed: %s", type(exc).__name__)
        quotes = {}
    out: dict[str, BullionContract] = {}
    for m, c in contracts.items():
        rng: tuple[float, float] | None = None
        try:
            rng = await fetch_52w_range(
                client, token, c.near.instrument_key, today, traded_only=True
            )
        except Exception as exc:
            log.warning("bullion range failed for %s: %s", m, type(exc).__name__)
        out[m] = replace(
            c,
            quote=quotes.get(c.near.instrument_key),
            range_high=rng[0] if rng else None,
            range_low=rng[1] if rng else None,
        )
    return out


async def backfill(
    client: httpx.AsyncClient, token: str, tracker: BullionTracker, now_ms: int
) -> None:
    """Today's closed 1-minute candles of each near contract, so the chart starts full."""
    this_minute = now_ms - now_ms % MINUTE_MS
    for m, c in tracker.contracts.items():
        try:
            got = await fetch_intraday_candles(
                client, token, c.near.instrument_key, before_ms=this_minute
            )
        except Exception as exc:
            log.warning("bullion candle backfill failed for %s: %s", m, type(exc).__name__)
            continue
        tracker.seed(m, got)

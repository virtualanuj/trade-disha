"""Gold BeES and Silver BeES: the NSE gold and silver ETFs on the BULLION tab. Spec §6.6.

Display only: no bias, no signals, no paper trades. They are NSE cash instruments, so unlike
the MCX futures they keep NSE hours, count as NSE ticks and are recorded in `ticks` like
the sector indices; this tracker only keeps the latest tick and the day's range per ETF.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import date

import httpx

from tradedisha.config import Settings
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.feed.upstox import FullQuote, fetch_quotes
from tradedisha.market.backfill import fetch_52w_range
from tradedisha.market.bullion import day_position, diff, merge_tick, pct, widen_day, year_range

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class EtfQuote:
    """One ETF, with what is fetched once at start."""

    metal: str  # the metal whose card it sits under
    symbol: str
    key: str
    quote: FullQuote | None = None
    range_high: float | None = None  # 52-week high, to yesterday
    range_low: float | None = None


@dataclass(frozen=True)
class EtfSnapshot:
    metal: str
    symbol: str
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
    bid: float | None
    ask: float | None
    bid_qty: int | None
    ask_qty: int | None
    spread: float | None
    range_high: float | None  # 52 weeks, widened by today
    range_low: float | None
    updated_ts: int | None


def etf_snapshot(e: EtfQuote, t: Tick | None, day: tuple[float, float, float]) -> EtfSnapshot:
    """One ETF's view; `day` is (open, high, low) as tracked so far."""
    q = e.quote
    ltp = t.ltp if t else (q.ltp if q else None)
    prev = (t.close_prev if t else None) or (q.prev_close if q else None)
    d_open, d_high, d_low = day
    hi, lo = year_range(e.range_high, e.range_low, day)
    return EtfSnapshot(
        metal=e.metal,
        symbol=e.symbol,
        ltp=ltp,
        prev_close=prev,
        change=diff(ltp, prev),
        change_pct=pct(ltp, prev),
        day_open=d_open or None,
        day_high=d_high or None,
        day_low=d_low or None,
        range_pos=day_position(ltp, day),
        atp=t.atp if t else None,
        volume=t.volume if t else None,
        bid=t.bid if t else None,
        ask=t.ask if t else None,
        bid_qty=t.bid_qty if t else None,
        ask_qty=t.ask_qty if t else None,
        spread=diff(t.ask, t.bid) if t else None,
        range_high=hi,
        range_low=lo,
        updated_ts=t.ts if t else None,
    )


class EtfTracker:
    """Latest tick and the day's range per ETF, keyed by the metal it sits under."""

    def __init__(self, etfs: dict[str, EtfQuote]) -> None:
        self.etfs = etfs
        self._metal_of = {e.key: m for m, e in etfs.items()}
        self.keys: frozenset[str] = frozenset(self._metal_of)
        self._latest: dict[str, Tick] = {}
        self._day: dict[str, tuple[float, float, float]] = {}
        for m, e in etfs.items():
            q = e.quote
            if q is not None:
                self._day[m] = (q.day_open or 0.0, q.day_high or 0.0, q.day_low or 0.0)

    def on_tick(self, st: StampedTick) -> None:
        t = st.tick
        metal = self._metal_of.get(t.key)
        if metal is None:
            return
        self._latest[t.key] = merge_tick(self._latest.get(t.key), t)
        self._day[metal] = widen_day(self._day.get(metal, (0.0, 0.0, 0.0)), t)

    def snapshot(self) -> list[EtfSnapshot]:
        return [
            etf_snapshot(e, self._latest.get(e.key), self._day.get(m, (0.0, 0.0, 0.0)))
            for m, e in self.etfs.items()
        ]


def etfs_from(settings: Settings) -> dict[str, EtfQuote]:
    """Metal -> its ETF, from settings; none on the synthetic feed (it has no NSE stocks)."""
    if settings.feed_provider == "synthetic":
        return {}
    return {m: EtfQuote(m, sym, key) for m, (sym, key) in settings.bullion_etfs.items()}


async def enrich_etfs(
    client: httpx.AsyncClient, token: str, etfs: dict[str, EtfQuote], today: date
) -> dict[str, EtfQuote]:
    """Add the start-of-day quote and the 52-week range; each fails soft."""
    try:
        quotes = await fetch_quotes(client, token, [e.key for e in etfs.values()])
    except Exception as exc:
        log.warning("ETF quote failed: %s", type(exc).__name__)
        quotes = {}
    out: dict[str, EtfQuote] = {}
    for m, e in etfs.items():
        rng: tuple[float, float] | None = None
        try:
            rng = await fetch_52w_range(client, token, e.key, today)
        except Exception as exc:
            log.warning("ETF range failed for %s: %s", e.symbol, type(exc).__name__)
        out[m] = replace(
            e,
            quote=quotes.get(e.key),
            range_high=rng[0] if rng else None,
            range_low=rng[1] if rng else None,
        )
    return out

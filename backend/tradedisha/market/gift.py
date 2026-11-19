"""GIFT Nifty's overnight move, fetched once a day for NIFTY's opening-gap vote. Spec §6.8.

Upstox carries GIFT Nifty as a global index (`GLOBAL_INDEX|SGX NIFTY`, from its global
instrument file) refreshed every 120 s, with candles from the REST API; the WebSocket is
not used. Only the overnight move is wanted, so once NSE has opened the service fetches the
previous NSE day's and today's 1-minute candles, keeps GIFT's price at the previous close
and just before the open, and stores it, so a replay of the day reads the same row.
Every failure is logged and leaves the vote warming; the index feed never waits on it.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx

from tradedisha.clock import MarketClock, epoch_ms_now, ms_to_ist
from tradedisha.indicators.gift import GiftSnapshot, snapshot_from
from tradedisha.market.backfill import fetch_day_candles, fetch_intraday_candles
from tradedisha.market.candles import MINUTE_MS
from tradedisha.store.gift import GiftStore

log = logging.getLogger(__name__)

GIFT_NIFTY_KEY = "GLOBAL_INDEX|SGX NIFTY"  # still named after SGX, where it traded until 2023
RETRY_MS = 120_000  # GIFT's refresh interval on Upstox
MAX_LOOKBACK_DAYS = 14


class GiftNifty:
    """Today's snapshot: read from the store, or fetched from Upstox once NSE is open."""

    def __init__(self, store: GiftStore, clock: MarketClock) -> None:
        self._store = store
        self._clock = clock
        self._cache: dict[date, GiftSnapshot] = {}
        self._last_try_ms: int | None = None

    def snapshot(self, day: date) -> GiftSnapshot | None:
        if day not in self._cache:
            snap = self._store.get(day)
            if snap is None:
                return None
            self._cache[day] = snap
        return self._cache[day]

    def previous_trading_day(self, day: date) -> date | None:
        d = day
        for _ in range(MAX_LOOKBACK_DAYS):
            d -= timedelta(days=1)
            if self._clock.is_trading_day(d):
                return d
        return None

    def due(self, now_ms: int) -> bool:
        """A minute after the open on a trading day, with no snapshot yet, not tried lately."""
        day = ms_to_ist(now_ms).date()
        if not self._clock.is_trading_day(day) or self.snapshot(day) is not None:
            return False
        open_ms, close_ms = self._clock.session_bounds(day)
        if not open_ms + MINUTE_MS <= now_ms < close_ms:
            return False
        return self._last_try_ms is None or now_ms - self._last_try_ms >= RETRY_MS

    async def fetch(self, client: httpx.AsyncClient, token: str) -> GiftSnapshot | None:
        """Fetch and store today's snapshot; None (and logged) if Upstox lacks a price."""
        now = self._clock.now_ms()
        self._last_try_ms = now
        day = ms_to_ist(now).date()
        prev = self.previous_trading_day(day)
        if prev is None:
            return None
        open_ms, _ = self._clock.session_bounds(day)
        _, prev_close_ms = self._clock.session_bounds(prev)
        prev_candles = await fetch_day_candles(client, token, GIFT_NIFTY_KEY, prev)
        today = await fetch_intraday_candles(client, token, GIFT_NIFTY_KEY, before_ms=open_ms)
        snap = snapshot_from(
            [(c.minute_ts, c.close) for c in prev_candles],
            [(c.minute_ts, c.close) for c in today],
            day=day,
            prev_close_ms=prev_close_ms,
            open_ms=open_ms,
        )
        if snap is None:
            log.warning(
                "no GIFT Nifty overnight reading for %s (%d candles on %s, %d today)",
                day,
                len(prev_candles),
                prev,
                len(today),
            )
            return None
        self._store.put(snap, epoch_ms_now())
        self._cache[day] = snap
        log.info(
            "GIFT Nifty %.1f -> %.1f (%+.2f%%) overnight for %s",
            snap.ref_close,
            snap.preopen_price,
            snap.move_pct,
            day,
        )
        return snap

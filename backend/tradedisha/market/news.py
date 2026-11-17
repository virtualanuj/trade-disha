"""Headlines for the heaviest index stocks, from Upstox's news API (spec §6.7).

Display only: nothing here reaches the bias, the signals or the paper trades, and nothing is
stored. Upstox carries news for stocks only (index, F&O and MCX keys return nothing), so the
stocks come from a hand-edited list. `NewsService` runs apart from `FeedSession`, so it can
never hold up the market feed, and every failure is caught and shown, not raised.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx

from tradedisha.clock import epoch_ms_now
from tradedisha.events import AuthChanged, EventBus, NewsChanged, ParametersChanged
from tradedisha.feed.upstox import Unauthorized, fetch_news

log = logging.getLogger(__name__)

MAX_NEWS_KEYS = 30  # Upstox takes at most 30 instrument keys in one call
REQUEST_TIMEOUT_S = 15.0

NewsStatus = Literal["needs_login", "loading", "ok", "error"]


# the stock list's index column: which index a stock moves, for the colour of its chip
INDEX_CODES: dict[str, tuple[str, ...]] = {
    "N": ("NIFTY",),
    "B": ("BANKNIFTY",),
    "NB": ("NIFTY", "BANKNIFTY"),
}


@dataclass(frozen=True, slots=True)
class NewsStock:
    symbol: str  # shown on the headline's chip: "HDFCBANK"
    key: str  # Upstox instrument key: "NSE_EQ|INE040A01034"
    indices: tuple[str, ...] = ()  # the indices it is in: ("NIFTY", "BANKNIFTY")


def load_news_stocks(path: Path) -> tuple[NewsStock, ...]:
    """Parse the stock list: one `SYMBOL INSTRUMENT_KEY [N|B|NB]` per line, '#' comments.

    The optional third column says which index the stock is in (NIFTY, BANK NIFTY or both).
    A missing file is an empty list. A malformed line, an unknown index code, a repeated
    key or more than `MAX_NEWS_KEYS` stocks raise ValueError.
    """
    if not path.exists():
        return ()
    out: list[NewsStock] = []
    keys: set[str] = set()
    for n, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) not in (2, 3) or "|" not in parts[1]:
            raise ValueError(f"line {n}: expected 'SYMBOL SEGMENT|ID [N|B|NB]', got {line!r}")
        symbol, key = parts[0], parts[1]
        code = parts[2] if len(parts) == 3 else None
        if code is not None and code not in INDEX_CODES:
            raise ValueError(f"line {n}: index must be N, B or NB, got {code!r}")
        if key in keys:
            raise ValueError(f"line {n}: {key} is listed twice")
        keys.add(key)
        out.append(NewsStock(symbol, key, INDEX_CODES[code] if code else ()))
    if len(out) > MAX_NEWS_KEYS:
        raise ValueError(f"{len(out)} stocks listed; Upstox takes at most {MAX_NEWS_KEYS}")
    return tuple(out)


@dataclass(frozen=True, slots=True)
class Headline:
    heading: str
    summary: str | None
    link: str | None
    published_ts: int  # epoch ms
    symbols: tuple[str, ...]  # every listed stock the story was attached to


def _text(v: object) -> str | None:
    return v.strip() if isinstance(v, str) and v.strip() else None


def parse_news(data: Mapping[str, Any], symbol_of: Mapping[str, str]) -> list[Headline]:
    """One headline per story, newest first.

    Upstox lists news per instrument key and attaches one story to several stocks, so items
    with the same article link (or, without one, the same heading) become one headline
    carrying every stock's symbol. Items without a heading or a numeric time are skipped.
    """
    merged: dict[str, Headline] = {}
    for key, items in data.items():
        if not isinstance(items, list):
            continue
        symbol = symbol_of.get(key, key)
        for item in items:
            if not isinstance(item, dict):
                continue
            heading = _text(item.get("heading"))
            ts = item.get("published_time")
            if heading is None or isinstance(ts, bool) or not isinstance(ts, int | float):
                continue
            link = _text(item.get("article_link"))
            ident = link or heading
            seen = merged.get(ident)
            if seen is None:
                merged[ident] = Headline(
                    heading, _text(item.get("summary")), link, int(ts), (symbol,)
                )
                continue
            symbols = seen.symbols if symbol in seen.symbols else (*seen.symbols, symbol)
            merged[ident] = Headline(
                seen.heading, seen.summary, seen.link, max(seen.published_ts, int(ts)), symbols
            )
    return sorted(merged.values(), key=lambda h: h.published_ts, reverse=True)


class TokenSource(Protocol):
    """What the service needs from `AuthService`."""

    @property
    def token(self) -> str | None: ...

    async def mark_expired(self) -> None: ...


def _describe(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"Upstox replied HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "Upstox did not answer in time"
    if isinstance(exc, httpx.HTTPError):
        return f"Could not reach Upstox ({type(exc).__name__})"
    return f"{type(exc).__name__}: {exc}"


class NewsService:
    """Polls Upstox for headlines while the login is valid and announces changes."""

    def __init__(
        self,
        *,
        auth: TokenSource,
        events: EventBus,
        stocks: tuple[NewsStock, ...],
        poll_seconds: Callable[[], float],  # read before every wait: the config can change it
        config_error: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._auth = auth
        self._events = events
        self._stocks = stocks
        self._symbol_of = {s.key: s.symbol for s in stocks}
        self._poll_seconds = poll_seconds
        self._config_error = config_error
        self._transport = transport
        self._items: list[Headline] = []
        self._error: str | None = config_error
        self._status: NewsStatus
        if config_error is not None:
            self._status = "error"
        else:
            self._status = "needs_login" if auth.token is None else "loading"
        self._fetched_at: int | None = None
        self._fetch_now = asyncio.Event()  # a login: fetch without waiting
        self._reschedule = asyncio.Event()  # the config was saved: the interval may differ
        self._task: asyncio.Task[None] | None = None
        events.subscribe(AuthChanged, self._on_auth)
        events.subscribe(ParametersChanged, self._on_params)

    @property
    def stocks(self) -> tuple[NewsStock, ...]:
        return self._stocks

    @property
    def items(self) -> list[Headline]:
        return self._items

    @property
    def status(self) -> NewsStatus:
        return self._status

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def fetched_at(self) -> int | None:
        """Epoch ms of the last successful fetch."""
        return self._fetched_at

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="news")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def _on_auth(self, ev: AuthChanged) -> None:
        if ev.state == "valid":
            self._fetch_now.set()

    def _on_params(self, _: ParametersChanged) -> None:
        self._reschedule.set()

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            self._fetch_now.clear()
            started = loop.time()
            try:
                await self.refresh()
            except Exception:
                log.exception("headlines refresh failed")
            # Wait out the interval from this fetch. A config save re-reads the interval
            # (a shorter one may already be due) without fetching early; a login fetches now.
            while not self._fetch_now.is_set():
                self._reschedule.clear()
                wait = started + self._poll_seconds() - loop.time()
                if wait <= 0:
                    break
                await self._sleep_or_wake(wait)

    async def _sleep_or_wake(self, seconds: float) -> None:
        waiters = [
            asyncio.ensure_future(self._fetch_now.wait()),
            asyncio.ensure_future(self._reschedule.wait()),
        ]
        try:
            await asyncio.wait(waiters, timeout=seconds, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for w in waiters:
                w.cancel()

    # -- one fetch ---------------------------------------------------------

    async def refresh(self) -> None:
        """Fetch once and publish `NewsChanged` if the list or its status changed."""
        if self._config_error is not None:
            return
        token = self._auth.token
        if token is None:
            await self._update("needs_login", self._items, None)
            return
        if not self._stocks:
            await self._update("ok", [], None)
            return
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=REQUEST_TIMEOUT_S
            ) as client:
                data = await fetch_news(client, token, [s.key for s in self._stocks])
        except Unauthorized:
            log.warning("Upstox refused the token for headlines")
            await self._auth.mark_expired()
            await self._update("needs_login", self._items, None)
            return
        except Exception as exc:
            message = _describe(exc)
            log.warning("headlines not fetched: %s", message)
            await self._update("error", self._items, message)
            return
        self._fetched_at = epoch_ms_now()
        await self._update("ok", parse_news(data, self._symbol_of), None)

    async def _update(self, status: NewsStatus, items: list[Headline], error: str | None) -> None:
        if (status, items, error) == (self._status, self._items, self._error):
            return
        self._status, self._items, self._error = status, items, error
        await self._events.publish(NewsChanged())

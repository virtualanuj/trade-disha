"""Live market data from Upstox: the V3 websocket feed, decoded into Ticks (spec §6.2).

Flow: ask REST for a one-time websocket address, connect, send a binary JSON subscribe
request in `full` mode, then decode protobuf `FeedResponse` messages. On any drop the
provider reconnects with exponential backoff and re-subscribes everything.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol

import httpx
from websockets.asyncio.client import connect as _ws_connect

from tradedisha.feed.provider import FeedHealth, FeedState, Tick
from tradedisha.feed.upstox_proto import MarketDataFeed_pb2 as pb

log = logging.getLogger(__name__)

AUTHORIZE_URL = "https://api.upstox.com/v3/feed/market-data-feed/authorize"
LTP_URLS = (
    "https://api.upstox.com/v3/market-quote/ltp",
    "https://api.upstox.com/v2/market-quote/ltp",
)
MODE = "full"
MAX_MESSAGE_BYTES = 16 * 1024 * 1024
BACKOFF_START_S = 1.0
BACKOFF_CAP_S = 30.0


class Unauthorized(RuntimeError):  # noqa: N818 - reads better at call sites
    """Upstox rejected the access token."""


class FeedSocket(Protocol):
    """The slice of a websocket connection the provider uses."""

    async def send(self, message: bytes) -> None: ...
    async def close(self) -> None: ...
    def __aiter__(self) -> AsyncIterator[str | bytes]: ...


SocketFactory = Callable[[str], Awaitable[FeedSocket]]


async def _open_socket(url: str) -> FeedSocket:
    return await _ws_connect(url, max_size=MAX_MESSAGE_BYTES)


# -- decoding ---------------------------------------------------------------------


def _pos(value: float) -> float | None:
    """proto3 sends 0 for "not present"; a Tick says None for "unchanged"."""
    return value if value > 0 else None


def _nonzero(value: float) -> float | None:
    return value if value != 0 else None


def _tick(key: str, ts: int, feed: pb.Feed) -> Tick | None:
    kind = feed.WhichOneof("FeedUnion")
    if kind == "ltpc":
        return _from_ltpc(key, ts, feed.ltpc)
    if kind == "firstLevelWithGreeks":
        g = feed.firstLevelWithGreeks
        return _from_market(key, ts, g.ltpc, g.firstDepth, g.optionGreeks, g.vtt, g.oi, g.iv)
    if kind != "fullFeed":
        return None
    full = feed.fullFeed
    if full.WhichOneof("FullFeedUnion") == "indexFF":
        return _from_ltpc(key, ts, full.indexFF.ltpc)
    m = full.marketFF
    best = m.marketLevel.bidAskQuote[0] if m.marketLevel.bidAskQuote else None
    return _from_market(key, ts, m.ltpc, best, m.optionGreeks, m.vtt, m.oi, m.iv)


def _from_market(
    key: str,
    ts: int,
    ltpc: pb.LTPC,
    best: pb.Quote | None,
    greeks: pb.OptionGreeks,
    vtt: int,
    oi: float,
    iv: float,
) -> Tick | None:
    if ltpc.ltp <= 0:
        return None
    return Tick(
        key=key,
        ts=ts or ltpc.ltt,
        ltp=ltpc.ltp,
        volume=int(vtt) if vtt > 0 else None,
        oi=int(oi) if oi > 0 else None,
        bid=_pos(best.bidP) if best is not None else None,
        ask=_pos(best.askP) if best is not None else None,
        iv=_pos(iv),
        delta=_nonzero(greeks.delta),
        close_prev=_pos(ltpc.cp),
    )


def _from_ltpc(key: str, ts: int, ltpc: pb.LTPC) -> Tick | None:
    if ltpc.ltp <= 0:
        return None
    return Tick(key=key, ts=ts or ltpc.ltt, ltp=ltpc.ltp, close_prev=_pos(ltpc.cp))


def decode(msg: pb.FeedResponse) -> list[Tick]:
    """One Tick per instrument in the message. Market-status messages carry none.

    The tick time is the feed's own send time (`currentTs`), not the last trade time: an
    option whose OI or quotes change without a trade keeps an old trade time, which would
    make live data look stale.
    """
    if msg.type == pb.market_info:
        return []
    ticks: list[Tick] = []
    for key, feed in msg.feeds.items():
        tick = _tick(key, int(msg.currentTs), feed)
        if tick is not None:
            ticks.append(tick)
    return ticks


# -- REST helpers -----------------------------------------------------------------


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


async def fetch_ltp(client: httpx.AsyncClient, token: str, keys: list[str]) -> dict[str, float]:
    """Last traded price per instrument key, from the quote API."""
    last_status = 0
    for url in LTP_URLS:
        resp = await client.get(
            url, params={"instrument_key": ",".join(keys)}, headers=_bearer(token)
        )
        last_status = resp.status_code
        if resp.status_code == 401:
            raise Unauthorized("quote request rejected")
        if resp.status_code != 200:
            continue
        out: dict[str, float] = {}
        for label, row in (resp.json().get("data") or {}).items():
            key = str(row.get("instrument_token") or str(label).replace(":", "|", 1))
            price = row.get("last_price")
            if isinstance(price, int | float) and price > 0:
                out[key] = float(price)
        if all(k in out for k in keys):
            return out
    raise RuntimeError(f"Upstox quote API gave no price for {keys} (HTTP {last_status})")


# -- provider ---------------------------------------------------------------------


class UpstoxProvider:
    """`token` is read afresh on every (re)connect, so a new login is picked up by itself."""

    name = "upstox"

    def __init__(
        self,
        *,
        token: Callable[[], str | None],
        on_unauthorized: Callable[[], Awaitable[None]] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        socket_factory: SocketFactory = _open_socket,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._token = token
        self._on_unauthorized = on_unauthorized
        self._transport = transport
        self._socket_factory = socket_factory
        self._sleep = sleep
        self._subscribed: set[str] = set()
        self._ws: FeedSocket | None = None
        self._state: FeedState = "disconnected"
        self._last_ts: int | None = None
        self._reconnects = 0
        self._closed = False
        self._ever_connected = False

    # -- provider protocol -------------------------------------------------

    async def connect(self) -> None:
        """One attempt now; if it fails, `ticks()` keeps retrying with backoff."""
        await self._try_open()

    async def subscribe(self, keys: list[str]) -> None:
        new = [k for k in keys if k not in self._subscribed]
        self._subscribed.update(new)
        await self._request("sub", new)

    async def unsubscribe(self, keys: list[str]) -> None:
        gone = [k for k in keys if k in self._subscribed]
        self._subscribed.difference_update(gone)
        await self._request("unsub", gone)

    async def close(self) -> None:
        self._closed = True
        self._state = "disconnected"
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                log.debug("closing the Upstox socket failed", exc_info=True)

    def health(self) -> FeedHealth:
        return FeedHealth(
            self._state, self._last_ts, self._reconnects, len(self._subscribed), self.name
        )

    async def ticks(self) -> AsyncIterator[Tick]:
        delay = BACKOFF_START_S
        while not self._closed:
            ws = self._ws
            if ws is None:
                await self._sleep(delay)
                delay = min(delay * 2, BACKOFF_CAP_S)
                if self._closed or not await self._try_open():
                    continue
                ws = self._ws
                if ws is None:
                    continue
            try:
                async for raw in ws:
                    if isinstance(raw, str):
                        continue
                    delay = BACKOFF_START_S  # data is flowing; next drop retries quickly
                    for tick in decode(pb.FeedResponse.FromString(raw)):
                        self._last_ts = tick.ts
                        yield tick
            except Exception as exc:
                if not self._closed:
                    log.warning("Upstox feed dropped: %s", type(exc).__name__)
            if self._ws is ws:
                self._ws = None
            if not self._closed:
                self._state = "disconnected"

    # -- internals ---------------------------------------------------------

    async def _authorized_url(self, token: str) -> str:
        async with httpx.AsyncClient(transport=self._transport, timeout=15) as client:
            resp = await client.get(AUTHORIZE_URL, headers=_bearer(token))
        if resp.status_code == 401:
            raise Unauthorized("feed authorisation rejected")
        resp.raise_for_status()
        url = (resp.json().get("data") or {}).get("authorized_redirect_uri")
        if not isinstance(url, str) or not url:
            raise RuntimeError("Upstox gave no websocket address")
        return url

    async def _try_open(self) -> bool:
        token = self._token()
        if token is None:
            self._state = "disconnected"  # waiting for the trader to log in again
            return False
        self._state = "connecting"
        try:
            ws = await self._socket_factory(await self._authorized_url(token))
        except Unauthorized:
            log.warning("Upstox rejected the access token; login needed")
            self._state = "disconnected"
            if self._on_unauthorized is not None:
                await self._on_unauthorized()
            return False
        except Exception as exc:
            log.warning("Upstox feed connect failed: %s", type(exc).__name__)
            self._state = "disconnected"
            return False
        self._ws = ws
        self._state = "connected"
        if self._ever_connected:
            self._reconnects += 1
        self._ever_connected = True
        await self._request("sub", sorted(self._subscribed))
        return True

    async def _request(self, method: str, keys: list[str]) -> None:
        """Send a subscribe/unsubscribe request. Lost requests are replayed on reconnect."""
        ws = self._ws
        if ws is None or not keys:
            return
        body = {
            "guid": uuid.uuid4().hex,
            "method": method,
            "data": {"mode": MODE, "instrumentKeys": keys},
        }
        try:
            await ws.send(json.dumps(body).encode())
        except Exception as exc:
            log.warning("Upstox %s request failed: %s", method, type(exc).__name__)

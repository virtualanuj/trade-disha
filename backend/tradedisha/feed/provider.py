"""The one interface every market-data source satisfies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

FeedState = Literal["connecting", "connected", "disconnected"]


@dataclass(frozen=True, slots=True)
class Tick:
    """One market-data update for one instrument. `None` means "unchanged"."""

    key: str
    ts: int  # exchange timestamp, epoch ms
    ltp: float
    volume: int | None = None  # cumulative day volume
    oi: int | None = None
    bid: float | None = None
    ask: float | None = None
    iv: float | None = None
    delta: float | None = None
    close_prev: float | None = None


@dataclass(frozen=True, slots=True)
class FeedHealth:
    state: FeedState
    last_tick_ts: int | None
    reconnects: int
    subscribed: int
    provider: str


class MarketDataProvider(Protocol):
    """Live (Upstox), synthetic, and replay providers are interchangeable behind this."""

    name: str

    async def connect(self) -> None: ...
    async def subscribe(self, keys: list[str]) -> None: ...
    async def unsubscribe(self, keys: list[str]) -> None: ...
    def ticks(self) -> AsyncIterator[Tick]: ...
    async def close(self) -> None: ...
    def health(self) -> FeedHealth: ...

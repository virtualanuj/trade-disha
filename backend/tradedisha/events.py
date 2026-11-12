"""In-process event bus and the domain events that travel on it."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedHealthChanged:
    state: str
    last_tick_ts: int | None
    reconnects: int
    subscribed: int
    provider: str


@dataclass(frozen=True)
class AuthChanged:
    state: str


@dataclass(frozen=True)
class WindowChanged:
    index: str
    atm: float
    strikes: tuple[float, ...]


@dataclass(frozen=True)
class ParametersChanged:
    loaded_at: int
    effective_from_minute_ts: int


Event = FeedHealthChanged | AuthChanged | WindowChanged | ParametersChanged
E = TypeVar("E", bound=Event)
Handler = Callable[[Any], Awaitable[None] | None]


class EventBus:
    """Typed publish/subscribe. Handlers may be sync or async; errors are logged, not raised."""

    def __init__(self) -> None:
        self._handlers: dict[type[object], list[Handler]] = defaultdict(list)

    def subscribe(
        self, event_type: type[E], handler: Callable[[E], Awaitable[None] | None]
    ) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: Event) -> None:
        for handler in list(self._handlers[type(event)]):
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                log.exception("event handler failed for %s", type(event).__name__)

"""Fan-out of every tick to its consumers, with the ingest timestamp attached."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from tradedisha.feed.provider import Tick

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StampedTick:
    tick: Tick
    t_in: int  # epoch ms when the backend received it


TickConsumer = Callable[[StampedTick], None]


class TickBus:
    """Consumers are synchronous and must be fast; anything slow buffers internally."""

    def __init__(self) -> None:
        self._consumers: list[TickConsumer] = []

    def subscribe(self, consumer: TickConsumer) -> None:
        self._consumers.append(consumer)

    def publish(self, stamped: StampedTick) -> None:
        for consumer in self._consumers:
            try:
                consumer(stamped)
            except Exception:
                log.exception("tick consumer failed")

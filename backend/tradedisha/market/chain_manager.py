"""Keeps one ChainState per index fed from the tick bus, closes minutes, re-centres.

Re-centring (spec §5.3): when the spot's ATM has moved `recenter_strikes` or more from
the window centre, resolve a new window from the master, subscribe the new keys,
unsubscribe the ones that fell out, and publish WindowChanged. Subscription changes are
async, so they are queued for the session to apply.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from tradedisha.events import EventBus, WindowChanged
from tradedisha.feed.bus import StampedTick
from tradedisha.instruments.models import Instrument, ResolvedIndex
from tradedisha.instruments.resolve import atm_strike, needs_recenter, resolve_index
from tradedisha.market.chain import ChainState
from tradedisha.store.chain import ChainMinuteStore

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubscriptionChange:
    index: str
    add: list[str]
    remove: list[str]


class ChainManager:
    def __init__(
        self,
        *,
        master: list[Instrument],
        resolved: dict[str, ResolvedIndex],
        today: date,
        strike_window: int,
        recenter_strikes: int,
        conn: sqlite3.Connection,
        events: EventBus,
        on_subscription_change: Callable[[SubscriptionChange], None] | None = None,
    ) -> None:
        self._master = master
        self.resolved = resolved
        self._today = today
        self._window = strike_window
        self._recenter = recenter_strikes
        self.store = ChainMinuteStore(conn)
        self._events = events
        self._on_change = on_subscription_change
        self.chains: dict[str, ChainState] = {
            idx: ChainState.from_resolved(r) for idx, r in resolved.items()
        }
        self._spot_keys = {r.spot.instrument_key: idx for idx, r in resolved.items()}
        self._current_minute: dict[str, int] = {}
        self.pending_window_events: list[WindowChanged] = []
        self._tasks: set[asyncio.Task[None]] = set()
        self.minutes_written = 0

    # -- tick bus consumer ---------------------------------------------------

    def on_tick(self, st: StampedTick) -> None:
        t = st.tick
        idx = self._spot_keys.get(t.key)
        if idx is not None:
            chain = self.chains[idx]
            chain.set_spot(t.ltp)
            self._maybe_recenter(idx, t.ltp)
            self._maybe_close_minute(idx, t.ts)
            return
        for idx, chain in self.chains.items():
            if chain.apply(t):
                self._maybe_close_minute(idx, t.ts)
                return

    # -- minute close ----------------------------------------------------------

    def _maybe_close_minute(self, idx: str, ts: int) -> None:
        minute = ts // 60_000
        current = self._current_minute.get(idx)
        if current is None:
            self._current_minute[idx] = minute
            return
        if minute > current:
            snap = self.chains[idx].close_minute(current * 60_000)
            self.minutes_written += self.store.write(self.chains[idx], snap)
            self._current_minute[idx] = minute

    # -- re-centring -----------------------------------------------------------

    def _maybe_recenter(self, idx: str, spot: float) -> None:
        chain = self.chains[idx]
        new_atm = atm_strike(spot, chain.step)
        if not needs_recenter(chain.atm, new_atm, chain.step, self._recenter):
            return
        old = self.resolved[idx]
        new = resolve_index(self._master, idx, self._today, spot, strike_window=self._window)
        old_keys, new_keys = set(old.option_keys), set(new.option_keys)
        self.resolved[idx] = new
        chain.set_window(new)
        change = SubscriptionChange(
            idx, add=sorted(new_keys - old_keys), remove=sorted(old_keys - new_keys)
        )
        log.info(
            "recentre %s atm %s -> %s (+%d/-%d)",
            idx,
            old.atm,
            new.atm,
            len(change.add),
            len(change.remove),
        )
        if self._on_change:
            self._on_change(change)
        event = WindowChanged(idx, new.atm, tuple(p.strike for p in new.strikes))
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self.pending_window_events.append(event)
        else:
            task = loop.create_task(self._events.publish(event))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

"""Factor switches: evidence the trader has left out of one index's or metal's bias (E15).

Every factor is on until switched off in the Evidence panel. A switch is per scope (NIFTY,
BANKNIFTY, GOLD, SILVER) and applies from that scope's next bias evaluation. Switches are
not parameters: a click makes no config version. Each stored bias minute and signal marks
every factor `enabled` instead, so what was off is still on record. Kept in the
`app_state` table under one key, so they survive a restart.
"""

from __future__ import annotations

import json
import logging
import sqlite3

from tradedisha.events import EventBus, FactorsChanged

log = logging.getLogger(__name__)

KEY = "factors_off"


class FactorSwitches:
    def __init__(self, conn: sqlite3.Connection, events: EventBus | None = None) -> None:
        self._conn = conn
        self._events = events
        self._off: dict[str, frozenset[str]] = self._load()

    def _load(self) -> dict[str, frozenset[str]]:
        row = self._conn.execute("SELECT value FROM app_state WHERE key = ?", (KEY,)).fetchone()
        if row is None:
            return {}
        try:
            raw = json.loads(row[0])
            return {str(k): frozenset(str(n) for n in v) for k, v in raw.items() if v}
        except (ValueError, AttributeError, TypeError):
            log.warning("factor switches in app_state unreadable: every factor is on")
            return {}

    def off_for(self, scope: str) -> frozenset[str]:
        return self._off.get(scope, frozenset())

    def all_off(self) -> dict[str, list[str]]:
        """Scope -> the factors switched off, sorted; scopes with none are left out."""
        return {k: sorted(v) for k, v in sorted(self._off.items()) if v}

    async def set(self, scope: str, name: str, *, enabled: bool) -> dict[str, list[str]]:
        """Switch one factor on or off for one scope, store it, and announce it."""
        now = self.off_for(scope)
        new = now - {name} if enabled else now | {name}
        if new != now:
            if new:
                self._off[scope] = new
            else:
                self._off.pop(scope, None)
            self._save()
            log.info("factor %s %s for %s", name, "on" if enabled else "off", scope)
            if self._events is not None:
                await self._events.publish(FactorsChanged(scope))
        return self.all_off()

    async def all_on(self, scope: str) -> dict[str, list[str]]:
        """Switch every factor of one scope back on."""
        if self._off.pop(scope, None) is not None:
            self._save()
            log.info("every factor on for %s", scope)
            if self._events is not None:
                await self._events.publish(FactorsChanged(scope))
        return self.all_off()

    def _save(self) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
                (KEY, json.dumps(self.all_off(), separators=(",", ":"))),
            )

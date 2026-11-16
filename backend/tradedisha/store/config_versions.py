"""Saved versions of the tunable parameters. Spec §3.2.

Versions are numbered from 1 and never changed or removed; the highest is in force.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

Source = Literal["seed", "edit", "revert"]

_COLS = "version, tag, created_ts, source, reverted_from, params_json"


@dataclass(frozen=True)
class ConfigVersion:
    version: int
    tag: str
    created_ts: int
    source: Source
    reverted_from: int | None
    params_json: str


class ConfigVersionStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def latest(self) -> ConfigVersion | None:
        r = self._conn.execute(
            f"SELECT {_COLS} FROM config_versions ORDER BY version DESC LIMIT 1"
        ).fetchone()
        return ConfigVersion(*r) if r else None

    def get(self, version: int) -> ConfigVersion | None:
        r = self._conn.execute(
            f"SELECT {_COLS} FROM config_versions WHERE version = ?", (version,)
        ).fetchone()
        return ConfigVersion(*r) if r else None

    def list(self) -> list[ConfigVersion]:
        """Newest first."""
        sql = f"SELECT {_COLS} FROM config_versions ORDER BY version DESC"
        return [ConfigVersion(*r) for r in self._conn.execute(sql)]

    def insert(
        self,
        *,
        tag: str,
        created_ts: int,
        source: Source,
        params_json: str,
        reverted_from: int | None = None,
    ) -> ConfigVersion:
        latest = self.latest()
        v = ConfigVersion(
            (latest.version if latest else 0) + 1,
            tag,
            created_ts,
            source,
            reverted_from,
            params_json,
        )
        with self._conn:
            self._conn.execute(
                f"INSERT INTO config_versions ({_COLS}) VALUES (?,?,?,?,?,?)",
                (v.version, v.tag, v.created_ts, v.source, v.reverted_from, v.params_json),
            )
        return v

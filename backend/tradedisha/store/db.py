"""Connection setup and versioned SQL migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(path: Path | str) -> sqlite3.Connection:
    """Open (creating if needed) with WAL and incremental vacuum, and apply migrations."""
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
    conn.execute("PRAGMA foreign_keys=ON")
    migrate(conn)
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def migrate(conn: sqlite3.Connection) -> None:
    """Apply NNN_*.sql files above the current user_version, in order, each in a transaction."""
    current = schema_version(conn)
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(sql_file.name.split("_", 1)[0])
        if version <= current:
            continue
        # executescript commits any open transaction and runs the file as one batch;
        # wrap the file in BEGIN/COMMIT ourselves so a failing migration leaves nothing behind.
        conn.executescript(
            f"BEGIN;\n{sql_file.read_text()}\nPRAGMA user_version={version};\nCOMMIT;"
        )

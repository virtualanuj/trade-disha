"""Give the space of deleted ticks back to the disk. Run it with the app stopped.

    uv run python -m tradedisha.tools.compact             # the database in .env
    uv run python -m tradedisha.tools.compact --db PATH

A database made before the connection set `auto_vacuum` first has it off, so deleting
ticks (Data, Delete ticks) frees pages inside the file but never shrinks the file. This
rewrites the file once with VACUUM and turns incremental vacuum on, after which every
delete gives its space back. Nothing in the data changes. It needs free disk space about
the size of the data kept, and takes a while on a large file.
"""

from __future__ import annotations

import argparse
import socket
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tradedisha.config import load_settings


@dataclass(frozen=True)
class CompactResult:
    bytes_before: int
    bytes_after: int
    auto_vacuum: int  # 2: incremental


def _file_bytes(db: Path) -> int:
    wal = db.with_name(db.name + "-wal")
    return db.stat().st_size + (wal.stat().st_size if wal.exists() else 0)


def app_running(host: str, port: int) -> bool:
    """Something answers on the app's address: VACUUM would block its writes."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def compact(db: Path) -> CompactResult:
    before = _file_bytes(db)
    conn = sqlite3.connect(db, isolation_level=None)
    try:
        conn.execute("PRAGMA auto_vacuum=INCREMENTAL")  # takes effect with the VACUUM
        conn.execute("VACUUM")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        mode = int(conn.execute("PRAGMA auto_vacuum").fetchone()[0])
    finally:
        conn.close()
    return CompactResult(before, _file_bytes(db), mode)


def main(argv: Sequence[str] | None = None) -> None:
    base = load_settings()
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--db", type=Path, default=base.db_path, help="database file")
    args = parser.parse_args(argv)
    db: Path = args.db
    if not db.exists():
        raise SystemExit(f"no database at {db}")
    if app_running(base.bind_host, base.bind_port):
        raise SystemExit(
            f"TradeDisha is running on {base.bind_host}:{base.bind_port}; stop it first, "
            "then run this again"
        )
    sys.stdout.write(f"compacting {db} ...\n")
    r = compact(db)
    mb = 1024 * 1024
    sys.stdout.write(
        f"{r.bytes_before / mb:,.0f} MB -> {r.bytes_after / mb:,.0f} MB; "
        f"incremental vacuum {'on' if r.auto_vacuum == 2 else 'OFF'}\n"
    )


if __name__ == "__main__":
    main()

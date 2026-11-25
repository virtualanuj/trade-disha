"""Connection setup: a new database file reclaims the space of deleted rows."""

from pathlib import Path

from tradedisha.store.db import connect


def test_a_new_database_file_uses_incremental_vacuum(tmp_path: Path) -> None:
    # auto_vacuum only takes on a file before its first table; WAL must not come first
    conn = connect(tmp_path / "new.sqlite")
    assert conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 2  # INCREMENTAL
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_reopening_keeps_the_mode(tmp_path: Path) -> None:
    connect(tmp_path / "db.sqlite").close()
    conn = connect(tmp_path / "db.sqlite")
    assert conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 2

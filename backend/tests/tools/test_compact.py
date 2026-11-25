"""The compact command: a one-off VACUUM that turns on incremental vacuum for an old file."""

import socket
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from tradedisha.tools.compact import app_running, compact, main


def _old_file(path: Path) -> None:
    """A file made the way the app made them before the fix: WAL first, so auto_vacuum 0."""
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA auto_vacuum=INCREMENTAL")  # ignored: too late for this file
    conn.execute("CREATE TABLE ticks (ts INTEGER, ltp REAL, pad TEXT)")
    conn.executemany(
        "INSERT INTO ticks VALUES (?, ?, ?)", ((i, float(i), "x" * 200) for i in range(20_000))
    )
    conn.execute("DELETE FROM ticks WHERE ts < 19000")  # pages freed but kept in the file
    conn.close()


def test_compact_shrinks_an_old_file_and_turns_on_incremental_vacuum(tmp_path: Path) -> None:
    db = tmp_path / "old.sqlite"
    _old_file(db)
    before = sqlite3.connect(db)
    assert before.execute("PRAGMA auto_vacuum").fetchone()[0] == 0
    assert before.execute("PRAGMA freelist_count").fetchone()[0] > 0
    before.close()

    result = compact(db)

    assert result.auto_vacuum == 2
    assert result.bytes_after < result.bytes_before / 4
    after = sqlite3.connect(db)
    assert after.execute("PRAGMA auto_vacuum").fetchone()[0] == 2
    assert after.execute("PRAGMA freelist_count").fetchone()[0] == 0
    assert after.execute("SELECT COUNT(*) FROM ticks").fetchone()[0] == 1000  # nothing lost
    assert after.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


@pytest.fixture
def listening() -> Iterator[int]:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    yield srv.getsockname()[1]
    srv.close()


def test_app_running_sees_a_listener(listening: int) -> None:
    assert app_running("127.0.0.1", listening) is True


def test_app_running_is_false_on_a_free_port() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    assert app_running("127.0.0.1", free) is False


def test_main_refuses_while_the_app_is_up(
    tmp_path: Path, listening: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "old.sqlite"
    _old_file(db)
    monkeypatch.setenv("TRADEDISHA_BIND_PORT", str(listening))
    with pytest.raises(SystemExit, match="stop it first"):
        main(["--db", str(db)])
    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 0  # untouched


def test_main_refuses_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="no database"):
        main(["--db", str(tmp_path / "nope.sqlite")])

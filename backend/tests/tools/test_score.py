"""The headless scorer: replays recorded days in a scratch database and sums them up."""

import gzip
import json
from datetime import date, datetime
from pathlib import Path

from tests.instruments.test_upstox_master import _records
from tradedisha.clock import IST, ist_to_ms
from tradedisha.config import Settings
from tradedisha.engine.outcomes import ScoreRow
from tradedisha.feed.provider import Tick
from tradedisha.instruments.upstox_master import master_path
from tradedisha.store.db import connect
from tradedisha.store.ticks import TickStore
from tradedisha.tools.score import copy_day, format_rows, score_days

DAY = date(2026, 11, 13)
REPO_PARAMS = Path(__file__).resolve().parents[3] / "config" / "params.toml"


def _recorded(tmp_path: Path) -> Path:
    with gzip.open(master_path(tmp_path, DAY), "wt", encoding="utf-8") as fh:
        json.dump(_records(), fh)
    db = tmp_path / "live.sqlite"
    conn = connect(db)
    store = TickStore(conn)
    t0 = ist_to_ms(datetime(2026, 11, 13, 11, 30, tzinfo=IST))
    store.add(Tick(key="NSE_INDEX|Nifty 50", ts=t0, ltp=25_110.0, bid_qty5=10))
    store.add(Tick(key="NSE_INDEX|Nifty 50", ts=t0 + 1000, ltp=25_120.0))
    store.add(Tick(key="NSE_INDEX|Nifty 50", ts=t0 + 86_400_000, ltp=25_300.0))  # next day
    store.flush()
    conn.close()
    return db


def test_copy_day_takes_only_that_days_ticks_with_every_column(tmp_path: Path) -> None:
    src = _recorded(tmp_path)
    dst = tmp_path / "scratch.sqlite"

    copied = copy_day(src, dst, DAY)

    assert copied == 2
    got = TickStore(connect(dst)).read_day(DAY)
    assert [t.ltp for t in got] == [25_110.0, 25_120.0]
    assert got[0].bid_qty5 == 10


async def test_score_days_replays_without_touching_the_recorded_database(tmp_path: Path) -> None:
    src = _recorded(tmp_path)

    rows = await score_days(
        [DAY],
        db_path=src,
        data_dir=tmp_path,
        params_path=REPO_PARAMS,
        base=Settings(_env_file=None, indices=["NIFTY"], strike_window=2),
    )

    assert rows == []  # two ticks fire nothing
    conn = connect(src)
    assert conn.execute("SELECT COUNT(*) FROM ticks").fetchone()[0] == 3
    for table in ("bias_minutes", "signals", "signal_outcomes", "feed_events"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_format_rows_is_a_readable_table() -> None:
    rows = [
        ScoreRow("minute_close", False, "all", 4, 3, 66.7, 33.3, 0.0, 21.5, -9.25, 0.4),
        ScoreRow("trigger", True, "NIFTY", 1, 0, None, None, None, None, None, None),
    ]

    lines = format_rows(rows).splitlines()

    assert lines[0].split() == [
        "rule", "scope", "signals", "scored", "target%", "stop%", "neither%", "best%", "worst%",
        "late",
    ]  # fmt: skip
    assert lines[1].split() == [
        "minute_close", "all", "4", "3", "66.7", "33.3", "0.0", "21.5", "-9.25", "0.4",
    ]  # fmt: skip
    assert lines[2].split() == ["trigger", "(shadow)", "NIFTY", "1", "0", *["-"] * 6]
    assert format_rows([]) == "no signals"

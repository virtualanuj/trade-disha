"""Replay recorded days and print how their signals turned out.

    uv run python -m tradedisha.tools.score --days 2026-11-12 2026-11-13
    uv run python -m tradedisha.tools.score --params /path/to/trial-params.toml

Each day's ticks are copied into a scratch database and replayed as fast as possible
through the same pipeline the app runs, with the given parameter file. The recorded
database is opened read-only and never written to, so trying a parameter change costs
nothing. Run it twice, with the current file and a trial one, to compare.
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import astuple, fields
from datetime import date, datetime
from pathlib import Path

from tradedisha.clock import IST, DrivenClock, MarketClock, load_holidays
from tradedisha.config import Settings, load_settings
from tradedisha.engine.outcomes import Outcome, ScoreRow, scorecard
from tradedisha.engine.signals import Signal
from tradedisha.events import EventBus
from tradedisha.market.session import FeedSession
from tradedisha.metrics.latency import LatencyTracker
from tradedisha.parameters import ParameterService
from tradedisha.store.db import connect
from tradedisha.store.ticks import COLS, day_bounds_ms

COPY_BATCH = 20_000
HEADINGS = (
    "rule",
    "scope",
    "signals",
    "scored",
    "target%",
    "stop%",
    "neither%",
    "best%",
    "worst%",
    "late",
)


def _read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def recorded_days(db_path: Path) -> list[date]:
    """IST dates with ticks in the recorded database, oldest first."""
    src = _read_only(db_path)
    try:
        rows = src.execute(
            "SELECT DISTINCT date(ts / 1000, 'unixepoch', '+5 hours', '+30 minutes') FROM ticks"
        ).fetchall()
    finally:
        src.close()
    return sorted(date.fromisoformat(r[0]) for r in rows)


def copy_day(src_path: Path, dst_path: Path, day: date) -> int:
    """Copy one day's ticks into a fresh database; returns how many."""
    src = _read_only(src_path)
    dst = connect(dst_path)
    try:
        # A database recorded before newer columns existed simply lacks them.
        have = {r[1] for r in src.execute("PRAGMA table_info(ticks)")}
        cols = [c for c in COLS if c in have]
        start, end = day_bounds_ms(day)
        cur = src.execute(
            f"SELECT {', '.join(cols)} FROM ticks WHERE ts >= ? AND ts < ? ORDER BY ts, rowid",
            (start, end),
        )
        insert = f"INSERT INTO ticks ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
        copied = 0
        while batch := cur.fetchmany(COPY_BATCH):
            with dst:
                dst.executemany(insert, batch)
            copied += len(batch)
        return copied
    finally:
        src.close()
        dst.close()


async def _replay(settings: Settings, day: date) -> tuple[list[Signal], dict[str, Outcome]]:
    """Run one copied day through the whole pipeline and collect its scored signals."""
    driven = DrivenClock(datetime.combine(day, settings.pre_open_start, tzinfo=IST))
    clock = MarketClock(
        market_open=settings.market_open,
        market_close=settings.market_close,
        pre_open_start=settings.pre_open_start,
        holidays=load_holidays(settings.holidays_file),
        source=driven,
    )
    params = ParameterService(settings.params_path)
    params.load()
    conn = connect(settings.db_path)
    session = FeedSession(
        settings,
        conn,
        clock,
        bus=EventBus(),
        latency=LatencyTracker(),
        params=lambda: params.params,
        driven_clock=driven,
    )
    try:
        await session.start()
        await session.feed_ended.wait()
        assert session.signals is not None
        assert session.outcomes is not None
        start, end = day_bounds_ms(day)
        session.outcomes.tick(end)  # nothing more will come: close every open horizon
        signals = session.signals.store.read(start, end)
        return signals, session.outcomes.store.for_signals(signals)
    finally:
        await session.stop()
        conn.close()


async def score_days(
    days: Sequence[date],
    *,
    db_path: Path,
    data_dir: Path,
    params_path: Path,
    base: Settings | None = None,
) -> list[ScoreRow]:
    """Replay each day in its own scratch database and score them all together."""
    signals: list[Signal] = []
    outcomes: dict[str, Outcome] = {}
    base = base or load_settings()
    for day in days:
        with tempfile.TemporaryDirectory(prefix="tradedisha-score-") as scratch:
            scratch_db = Path(scratch) / "day.sqlite"
            copy_day(db_path, scratch_db, day)
            settings = base.model_copy(
                update={
                    "db_path": scratch_db,
                    "data_dir": data_dir,
                    "params_path": params_path,
                    "feed_provider": "replay",
                    "replay_date": day.isoformat(),
                    "replay_speed": 0.0,
                    "replay_drop": [],
                    "enforce_signal_hours": True,
                }
            )
            day_signals, day_outcomes = await _replay(settings, day)
        signals += day_signals
        outcomes |= day_outcomes
    return scorecard(signals, outcomes)


def format_rows(rows: Sequence[ScoreRow]) -> str:
    if not rows:
        return "no signals"
    table: list[tuple[str, ...]] = [HEADINGS]
    for r in rows:
        rule = f"{r.rule} (shadow)" if r.shadow else r.rule
        cells = astuple(r)[2:]
        table.append((rule, *("-" if v is None else str(v) for v in cells)))
    widths = [max(len(line[i]) for line in table) for i in range(len(HEADINGS))]
    return "\n".join(
        "  ".join(
            cell.ljust(w) if i < 2 else cell.rjust(w)
            for i, (cell, w) in enumerate(zip(line, widths, strict=True))
        )
        for line in table
    )


def main(argv: Sequence[str] | None = None) -> None:
    base = load_settings()
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--days", nargs="*", type=date.fromisoformat, help="default: all recorded")
    parser.add_argument("--db", type=Path, default=base.db_path, help="recorded database")
    parser.add_argument("--params", type=Path, default=base.params_path, help="parameter file")
    args = parser.parse_args(argv)
    days = args.days or recorded_days(args.db)
    if not days:
        raise SystemExit(f"no recorded ticks in {args.db}")
    rows = asyncio.run(
        score_days(
            days, db_path=args.db, data_dir=base.data_dir, params_path=args.params, base=base
        )
    )
    span = f"{days[0].isoformat()} to {days[-1].isoformat()}"
    sys.stdout.write(f"{len(days)} day(s), {span}, parameters {args.params}\n")
    sys.stdout.write(format_rows(rows) + "\n")


assert len(HEADINGS) == len(fields(ScoreRow)) - 1  # rule and shadow share a column

if __name__ == "__main__":
    main()

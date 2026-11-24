"""US data releases that pause bullion signals (Milestone E18, spec §9a).

CPI, payrolls and Fed decisions move gold and silver sharply, so a 1-minute trend signal
just before or after one is mostly noise. The releases come from a hand-kept file
(`config/us-events.txt`), one per line in IST, read once at start like the holiday files:

    YYYY-MM-DD HH:MM  label   # comment

The window around each release, and what it stops, are bullion parameters.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from tradedisha.clock import IST, ist_to_ms

MINUTE_MS = 60_000


@dataclass(frozen=True)
class UsEvent:
    ts_ms: int  # the release time
    label: str


def load_us_events(path: Path) -> tuple[UsEvent, ...]:
    """The releases in `path`, sorted by time; none when the file is missing.

    A malformed line raises `ValueError` naming the file and line, so a typo is never
    silently skipped.
    """
    if not path.exists():
        return ()
    events: list[UsEvent] = []
    for n, raw in enumerate(path.read_text().splitlines(), start=1):
        parts = raw.split("#", 1)[0].split(maxsplit=2)
        if not parts:
            continue
        try:
            day, hhmm, *label = parts
            if len(hhmm) != len("HH:MM"):
                raise ValueError(hhmm)
            when = datetime.combine(date.fromisoformat(day), time.fromisoformat(hhmm), IST)
        except ValueError:
            msg = f"{path.name} line {n}: expected 'YYYY-MM-DD HH:MM label', got {raw!r}"
            raise ValueError(msg) from None
        events.append(UsEvent(ist_to_ms(when), label[0].strip() if label else "US data"))
    return tuple(sorted(events, key=lambda e: e.ts_ms))


def event_in_window(
    events: Sequence[UsEvent], now_ms: int, before_minutes: int, after_minutes: int
) -> UsEvent | None:
    """The first release whose window `[release - before, release + after)` holds `now`."""
    for e in events:
        if e.ts_ms - before_minutes * MINUTE_MS <= now_ms < e.ts_ms + after_minutes * MINUTE_MS:
            return e
    return None

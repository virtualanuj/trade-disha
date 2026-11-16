"""The single source of time and market status for the backend.

No other module reads the system clock directly. In live and synthetic modes the clock
follows the wall clock; in replay mode it is driven by replayed tick timestamps so a
session replayed in the evening still sees 09:15 to 15:30.
"""

from __future__ import annotations

import time as _time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

MarketStatus = Literal["pre_open", "live", "closed", "holiday"]


def epoch_ms_now() -> int:
    """Wall-clock epoch milliseconds. Used only for latency stamping."""
    return _time.time_ns() // 1_000_000


def ms_to_ist(ms: int) -> datetime:
    """Convert epoch milliseconds to an aware IST datetime."""
    return datetime.fromtimestamp(ms / 1000, tz=UTC).astimezone(IST)


def ist_to_ms(dt: datetime) -> int:
    """Convert an aware datetime to epoch milliseconds."""
    return int(dt.timestamp() * 1000)


def load_holidays(path: Path) -> frozenset[date]:
    """Parse a holiday file: one YYYY-MM-DD per line, '#' comments allowed."""
    if not path.exists():
        return frozenset()
    days: set[date] = set()
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            days.add(date.fromisoformat(line))
    return frozenset(days)


@dataclass(frozen=True)
class MarketCalendar:
    """Days an exchange is shut, and days it opens late (an evening-only session)."""

    holidays: frozenset[date]
    late_opens: Mapping[date, time]


def load_calendar(path: Path) -> MarketCalendar:
    """Parse `YYYY-MM-DD` (closed all day) or `YYYY-MM-DD HH:MM` (opens then) lines."""
    if not path.exists():
        return MarketCalendar(frozenset(), {})
    days: set[date] = set()
    late: dict[date, time] = {}
    for raw in path.read_text().splitlines():
        parts = raw.split("#", 1)[0].split()
        if not parts:
            continue
        day = date.fromisoformat(parts[0])
        if len(parts) > 1:
            late[day] = time.fromisoformat(parts[1])
        else:
            days.add(day)
    return MarketCalendar(frozenset(days), late)


class MarketClock:
    """Answers "what time is it" and "what is the market doing" from one time source."""

    def __init__(
        self,
        *,
        market_open: time,
        market_close: time,
        pre_open_start: time,
        holidays: frozenset[date] = frozenset(),
        late_opens: Mapping[date, time] | None = None,
        source: Callable[[], datetime] | None = None,
    ) -> None:
        self._open = market_open
        self._close = market_close
        self._pre_open = pre_open_start
        self._holidays = holidays
        self._late_opens = dict(late_opens or {})
        self._source = source or (lambda: datetime.now(tz=IST))

    def with_hours(
        self, *, market_open: time, market_close: time, calendar: MarketCalendar
    ) -> MarketClock:
        """Another exchange's hours on the same time source (so replay drives both)."""
        return MarketClock(
            market_open=market_open,
            market_close=market_close,
            pre_open_start=market_open,  # no pre-open window
            holidays=calendar.holidays,
            late_opens=calendar.late_opens,
            source=self._source,
        )

    def now(self) -> datetime:
        """Current time as an aware IST datetime."""
        return self._source().astimezone(IST)

    def now_ms(self) -> int:
        return ist_to_ms(self.now())

    def today(self) -> date:
        return self.now().date()

    def is_trading_day(self, day: date | None = None) -> bool:
        d = day or self.today()
        return d.weekday() < 5 and d not in self._holidays

    def open_time(self, day: date | None = None) -> time:
        """When the session opens on a day: the usual time, or a late open."""
        return self._late_opens.get(day or self.today(), self._open)

    def status(self) -> MarketStatus:
        now = self.now()
        if not self.is_trading_day(now.date()):
            return "holiday"
        t = now.time()
        opens = self.open_time(now.date())
        if self._pre_open <= t < opens and opens == self._open:
            return "pre_open"
        if opens <= t < self._close:
            return "live"
        return "closed"

    def session_bounds(self, day: date | None = None) -> tuple[int, int]:
        """Epoch-ms start and end of the trading session on a day."""
        d = day or self.today()
        start = datetime.combine(d, self.open_time(d), tzinfo=IST)
        end = datetime.combine(d, self._close, tzinfo=IST)
        return ist_to_ms(start), ist_to_ms(end)


class DrivenClock:
    """A time source advanced explicitly, used by the replay provider."""

    def __init__(self, start: datetime) -> None:
        self._now = start.astimezone(IST)

    def __call__(self) -> datetime:
        return self._now

    def set_ms(self, ms: int) -> None:
        self._now = ms_to_ist(ms)

    def advance(self, delta: timedelta) -> None:
        self._now += delta

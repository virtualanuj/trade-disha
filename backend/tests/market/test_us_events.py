"""The US data-release calendar behind the bullion event pause (Milestone E18)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from tradedisha.clock import IST, ist_to_ms
from tradedisha.market.us_events import UsEvent, event_in_window, load_us_events

M = 60_000


def at(day: int, h: int, m: int) -> int:
    return ist_to_ms(datetime(2026, 12, day, h, m, tzinfo=IST))


def test_a_missing_file_means_no_events(tmp_path: Path) -> None:
    assert load_us_events(tmp_path / "absent.txt") == ()


def test_events_are_read_sorted_with_comments_and_blank_lines_skipped(tmp_path: Path) -> None:
    f = tmp_path / "us-events.txt"
    f.write_text(
        "# US data releases, IST\n"
        "\n"
        "2026-12-10 19:00  CPI  # November CPI\n"
        "2026-12-04 19:00 Non-farm payrolls\n"
        "   # an indented comment\n"
        "2026-12-17 00:30  FOMC decision\n"
    )
    assert load_us_events(f) == (
        UsEvent(at(4, 19, 0), "Non-farm payrolls"),
        UsEvent(at(10, 19, 0), "CPI"),
        UsEvent(at(17, 0, 30), "FOMC decision"),
    )


def test_an_event_without_a_label_is_named_after_its_time(tmp_path: Path) -> None:
    f = tmp_path / "us-events.txt"
    f.write_text("2026-12-10 19:00\n")
    assert load_us_events(f) == (UsEvent(at(10, 19, 0), "US data"),)


@pytest.mark.parametrize(
    "line",
    ["2026-12-10  CPI", "2026-12-10 7pm CPI", "10/12/2026 19:00 CPI", "2026-13-01 19:00 CPI"],
)
def test_a_bad_line_fails_with_its_line_number(tmp_path: Path, line: str) -> None:
    f = tmp_path / "us-events.txt"
    f.write_text(f"# header\n2026-12-04 19:00 NFP\n{line}\n")
    with pytest.raises(ValueError, match=r"us-events\.txt line 3"):
        load_us_events(f)


CPI = UsEvent(at(10, 19, 0), "CPI")


@pytest.mark.parametrize(
    ("now", "before", "after", "inside"),
    [
        (at(10, 18, 44), 15, 15, False),  # a minute before the window
        (at(10, 18, 45), 15, 15, True),  # the window opens
        (at(10, 19, 0), 15, 15, True),  # the release
        (at(10, 19, 15) - 1, 15, 15, True),  # the last millisecond
        (at(10, 19, 15), 15, 15, False),  # the window has closed
        (at(10, 19, 0), 0, 0, False),  # both zero: no pause
        (at(10, 18, 59), 0, 10, False),  # nothing before the release
        (at(10, 19, 0), 0, 10, True),
        (at(10, 18, 30), 30, 0, True),
        (at(10, 19, 0), 30, 0, False),  # nothing from the release on
    ],
)
def test_the_window_runs_from_before_the_release_to_after_it(
    now: int, before: int, after: int, inside: bool
) -> None:
    assert (event_in_window((CPI,), now, before, after) == CPI) is inside


def test_overlapping_windows_name_the_earlier_release() -> None:
    nfp = UsEvent(at(10, 19, 0), "Non-farm payrolls")
    claims = UsEvent(at(10, 19, 10), "Jobless claims")
    events = (nfp, claims)
    assert event_in_window(events, at(10, 19, 5), 15, 15) == nfp
    assert event_in_window(events, at(10, 19, 20), 15, 15) == claims
    assert event_in_window((), at(10, 19, 5), 15, 15) is None

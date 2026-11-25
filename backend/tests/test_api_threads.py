"""Routes run on the event loop that owns the engines, never in FastAPI's threadpool.

A plain `def` route runs in a worker thread while the loop goes on handling ticks, so a
check-then-act in an engine (is the signal still active? then open a trade) can be passed
twice, and a dict or deque the loop is changing can be read mid-change.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import threading
import time

import pytest
from fastapi import APIRouter
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from tests.test_scorecard_api import _fire
from tradedisha import api
from tradedisha.market.session import FeedSession

# Routes that touch nothing the loop changes and may block, so they stay in the threadpool.
THREADED = {
    "usage",  # counts the ticks table (hundreds of MB); reads SQLite only
    "login",  # builds a redirect URL
}


def _routes() -> list[APIRoute]:
    """Every route of every router in `tradedisha.api` (the app wraps included routers)."""
    out: list[APIRoute] = []
    for mod in pkgutil.iter_modules(api.__path__):
        router = getattr(importlib.import_module(f"tradedisha.api.{mod.name}"), "router", None)
        if isinstance(router, APIRouter):
            out += [r for r in router.routes if isinstance(r, APIRoute)]
    return out


def test_every_route_but_the_listed_ones_runs_on_the_loop() -> None:
    routes = _routes()
    assert len(routes) > 30  # the walk found the routers
    sync = sorted(
        r.endpoint.__name__ for r in routes if not inspect.iscoroutinefunction(r.endpoint)
    )
    assert sync == sorted(THREADED)


def test_two_clicks_on_one_signal_open_one_trade(client: TestClient) -> None:
    time.sleep(0.3)  # let the synthetic feed price the chain
    session: FeedSession = client.app.state.td.session  # type: ignore[attr-defined]
    sid = _fire(session)
    start = threading.Barrier(2)
    codes: list[int] = []

    def click() -> None:
        start.wait()
        codes.append(client.post("/api/paper-trades", json={"signal_id": sid}).status_code)

    threads = [threading.Thread(target=click) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(codes) == [201, 409]
    assert session.paper is not None
    assert len(session.paper.open_trades) == 1
    assert session.bank.summary().open_trades == 1


def test_a_failing_housekeeping_step_does_not_stop_the_others(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before, one exception (a deque changed mid-read) ended the loop for good: no more
    lapses, square-off or gap tracking."""
    session: FeedSession = client.app.state.td.session  # type: ignore[attr-defined]
    assert session.paper is not None
    ticks: list[int] = []

    def broken() -> None:
        raise RuntimeError("deque mutated during iteration")

    monkeypatch.setattr(session.tick_store, "flush", broken)
    monkeypatch.setattr(session.paper, "tick", ticks.append)
    time.sleep(1.3)  # the loop runs every 0.5 s
    assert len(ticks) >= 2

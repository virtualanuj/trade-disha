"""The rates strip's market-wide quotes (SENSEX): maths, the API and the `quotes` frame."""

import json

from fastapi.testclient import TestClient

from tradedisha.app_state import AppState
from tradedisha.clock import epoch_ms_now
from tradedisha.config import Settings
from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.market.stats import SENSEX_KEY, MarketQuote, market_quotes, market_wide_keys


def test_sensex_is_a_market_wide_key_on_the_live_feed() -> None:
    assert SENSEX_KEY == "BSE_INDEX|SENSEX"
    assert SENSEX_KEY in market_wide_keys(Settings(_env_file=None, feed_provider="upstox"))
    assert SENSEX_KEY in market_wide_keys(Settings(_env_file=None, feed_provider="replay"))


def test_market_quotes_change_on_the_previous_close() -> None:
    got = market_quotes({SENSEX_KEY: 80_911.05}, {SENSEX_KEY: 80_605.95}, {SENSEX_KEY: 7})
    assert got == (MarketQuote("SENSEX", 80_911.05, 80_605.95, 305.1, 0.38, 7),)


def test_market_quotes_before_any_tick() -> None:
    assert market_quotes({}, {}, {}) == (MarketQuote("SENSEX", None, None, None, None, None),)


def test_market_quotes_without_a_previous_close() -> None:
    [q] = market_quotes({SENSEX_KEY: 80_911.05}, {}, {SENSEX_KEY: 7})
    assert (q.ltp, q.change, q.change_pct) == (80_911.05, None, None)


# -- API and frames ----------------------------------------------------------------------


def _publish(client: TestClient, tick: Tick) -> None:
    td: AppState = client.app.state.td  # type: ignore[attr-defined]
    assert client.portal is not None
    client.portal.call(td.session.tick_bus.publish, StampedTick(tick, epoch_ms_now()))


def test_quotes_api_follows_the_ticks(client: TestClient) -> None:
    assert client.get("/api/quotes").json() == [
        {
            "name": "SENSEX",
            "ltp": None,
            "prev_close": None,
            "change": None,
            "change_pct": None,
            "updated_ts": None,
        }
    ]
    now = epoch_ms_now()
    _publish(client, Tick(key=SENSEX_KEY, ts=now, ltp=80_911.05, close_prev=80_605.95))
    [q] = client.get("/api/quotes").json()
    assert (q["ltp"], q["change_pct"], q["updated_ts"]) == (80_911.05, 0.38, now)


def test_a_sensex_tick_sends_a_quotes_frame(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        hello = json.loads(ws.receive_text())
        assert [q["name"] for q in hello["payload"]["quotes"]] == ["SENSEX"]
        _publish(client, Tick(key=SENSEX_KEY, ts=epoch_ms_now(), ltp=80_911.05))
        for _ in range(600):
            frame = json.loads(ws.receive_text())
            if frame["type"] == "quotes":
                break
        else:
            raise AssertionError("no quotes frame")

    assert frame["payload"][0]["ltp"] == 80_911.05
    assert isinstance(frame["t_src"], int)

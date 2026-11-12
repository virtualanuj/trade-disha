"""Health endpoint: app, market status, auth, feed."""

from __future__ import annotations

from fastapi import APIRouter

from tradedisha import __version__
from tradedisha.api.deps import State
from tradedisha.api.schemas import FeedHealthOut, HealthResponse
from tradedisha.app_state import AppState
from tradedisha.clock import epoch_ms_now

router = APIRouter()


def feed_health_out(state: AppState) -> FeedHealthOut:
    h = state.session.health()
    age = None if h.last_tick_ts is None else max(0, epoch_ms_now() - h.last_tick_ts)
    return FeedHealthOut(
        state=h.state,
        last_tick_ts=h.last_tick_ts,
        tick_age_ms=age,
        reconnects=h.reconnects,
        subscribed=h.subscribed,
        provider=h.provider,
    )


def build_health(state: AppState) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app="tradedisha",
        version=__version__,
        milestone=1,
        market_status=state.clock.status(),
        now_ms=state.clock.now_ms(),
        auth=state.auth.state(),
        feed=feed_health_out(state),
        replay_day=state.session.replay_day.isoformat() if state.session.replay_day else None,
    )


@router.get("/health", response_model=HealthResponse)
def health(state: State) -> HealthResponse:
    return build_health(state)

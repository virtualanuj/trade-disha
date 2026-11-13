"""Health endpoint: app, market status, auth, feed."""

from __future__ import annotations

from fastapi import APIRouter

from tradedisha import __version__
from tradedisha.api.deps import State
from tradedisha.api.schemas import BannerOut, FeedHealthOut, HealthResponse
from tradedisha.app_state import AppState
from tradedisha.clock import epoch_ms_now
from tradedisha.config import Settings

router = APIRouter()


def serves_frontend(settings: Settings) -> bool:
    """True when this backend also serves the built web app (`make start`)."""
    return settings.serve_frontend and (settings.frontend_dist / "index.html").is_file()


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


def status_banner(state: AppState) -> BannerOut | None:
    """Why the screen is not live, most important reason first. None when all is well."""
    auth = state.auth.state()
    if auth == "missing":
        return BannerOut(code="login_missing", level="error")
    if auth == "expired":
        return BannerOut(code="login_expired", level="error")
    session = state.session
    if session.enforce_hours:
        market = state.clock.status()
        if market != "live":
            code = "market_closed" if market == "closed" else market
            return BannerOut(code=code, level="info")
    if not session.started:
        return BannerOut(code="feed_not_started", level="error")
    if not session.feed_live():
        since = session.gap_since or session.health().last_tick_ts
        return BannerOut(code="feed_gap", level="error", since_ms=since)
    return None


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
        feed_live=state.session.feed_live(),
        banner=status_banner(state),
        serves_frontend=serves_frontend(state.settings),
    )


@router.get("/health", response_model=HealthResponse)
def health(state: State) -> HealthResponse:
    return build_health(state)

"""FastAPI application factory and entry point."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from datetime import datetime

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tradedisha.api.chain import router as chain_router
from tradedisha.api.health import router as health_router
from tradedisha.api.instruments import router as instruments_router
from tradedisha.api.metrics import router as metrics_router
from tradedisha.api.ws import WsHub
from tradedisha.api.ws import router as ws_router
from tradedisha.app_state import AppState
from tradedisha.auth import AuthService
from tradedisha.clock import IST, DrivenClock, MarketClock, load_holidays
from tradedisha.config import Settings, load_settings
from tradedisha.events import EventBus
from tradedisha.market.session import FeedSession
from tradedisha.metrics.latency import LatencyTracker, sample_loop_lag
from tradedisha.store.db import connect

log = logging.getLogger(__name__)


def build_state(settings: Settings) -> AppState:
    """Construct every long-lived component. No I/O beyond opening the database."""
    driven: DrivenClock | None = None
    source = None
    if settings.feed_provider == "replay":
        driven = DrivenClock(datetime.now(tz=IST))
        source = driven
    clock = MarketClock(
        market_open=settings.market_open,
        market_close=settings.market_close,
        pre_open_start=settings.pre_open_start,
        holidays=load_holidays(settings.holidays_file),
        source=source,
    )
    conn = connect(settings.db_path)
    events = EventBus()
    latency = LatencyTracker()
    session = FeedSession(settings, conn, clock, bus=events, latency=latency, driven_clock=driven)
    auth = AuthService(required=settings.feed_provider == "upstox")
    return AppState(
        settings=settings,
        conn=conn,
        clock=clock,
        events=events,
        latency=latency,
        auth=auth,
        session=session,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Settings can be injected for tests."""
    cfg = settings or load_settings()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = build_state(cfg)
        app.state.td = state
        hub = WsHub(state)
        app.state.ws_hub = hub
        lag_task = asyncio.create_task(sample_loop_lag(state.latency), name="loop-lag")
        await state.session.start()
        hub.start()
        log.info("feed=%s indices=%s", cfg.feed_provider, ",".join(state.session.resolved))
        try:
            yield
        finally:
            await hub.stop()
            await state.session.stop()
            lag_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await lag_task
            state.conn.close()

    app = FastAPI(title="TradeDisha", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(instruments_router, prefix="/api")
    app.include_router(chain_router, prefix="/api")
    app.include_router(metrics_router, prefix="/api")
    app.include_router(ws_router)
    return app


def run() -> None:
    """Start the development server."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_settings()
    uvicorn.run(
        "tradedisha.main:create_app",
        factory=True,
        host=settings.bind_host,
        port=settings.bind_port,
        reload=True,
    )

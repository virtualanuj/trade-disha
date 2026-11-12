"""FastAPI application factory and entry point."""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tradedisha.api.health import router as health_router
from tradedisha.config import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Settings can be injected for tests."""
    settings = settings or load_settings()
    app = FastAPI(title="TradeDisha")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api")
    return app


def run() -> None:
    """Start the development server."""
    settings = load_settings()
    uvicorn.run(
        "tradedisha.main:create_app",
        factory=True,
        host=settings.bind_host,
        port=settings.bind_port,
        reload=True,
    )

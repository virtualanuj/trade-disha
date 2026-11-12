"""FastAPI dependency that hands routers the shared AppState."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from tradedisha.app_state import AppState


def get_state(request: Request) -> AppState:
    return cast(AppState, request.app.state.td)


State = Annotated[AppState, Depends(get_state)]

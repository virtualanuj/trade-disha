"""Upstox login: send the browser to Upstox, take the code it comes back with (spec §4)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from tradedisha.api.deps import State
from tradedisha.api.health import serves_frontend
from tradedisha.auth import AuthError

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/auth/login")
def login(app: State) -> RedirectResponse:
    if not app.auth.required:
        raise HTTPException(status_code=400, detail="This feed needs no login.")
    try:
        return RedirectResponse(app.auth.begin_login(), status_code=302)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/auth/callback")
async def callback(
    app: State,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    if not code or not state:
        raise HTTPException(status_code=400, detail="Upstox did not send a login code.")
    try:
        await app.auth.complete_login(code, state)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        await app.session.start()
    except Exception as exc:
        log.exception("login succeeded but the feed did not start")
        raise HTTPException(
            status_code=502, detail=f"Logged in, but the feed did not start: {exc}"
        ) from exc
    home = "/" if serves_frontend(app.settings) else app.settings.frontend_url
    return RedirectResponse(home, status_code=302)

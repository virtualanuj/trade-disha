"""Broker authentication: the daily Upstox OAuth login and the token it yields (spec §4).

The access token lives in the `sessions` table of the local, gitignored database. It is
never logged and never leaves this machine except in requests to Upstox.
"""

from __future__ import annotations

import secrets
import sqlite3
from collections.abc import Callable
from datetime import datetime, time, timedelta
from typing import Literal
from urllib.parse import urlencode

import httpx

from tradedisha.clock import IST, epoch_ms_now, ist_to_ms, ms_to_ist
from tradedisha.config import Settings
from tradedisha.events import AuthChanged, EventBus

AuthState = Literal["missing", "valid", "expired", "not_required"]

DIALOG_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
TOKEN_EXPIRY_IST = time(3, 30)  # Upstox invalidates every token at 03:30 IST
MAX_PENDING_LOGINS = 16


class AuthError(RuntimeError):
    """Login could not start or complete; the message is safe to show the trader."""


def token_expiry_ms(obtained_ms: int) -> int:
    """The first 03:30 IST strictly after the token was obtained."""
    obtained = ms_to_ist(obtained_ms)
    cutoff = datetime.combine(obtained.date(), TOKEN_EXPIRY_IST, tzinfo=IST)
    if cutoff <= obtained:
        cutoff += timedelta(days=1)
    return ist_to_ms(cutoff)


class AuthService:
    """Tracks whether a usable broker login exists. Synthetic and replay feeds need none."""

    def __init__(
        self,
        *,
        required: bool,
        settings: Settings,
        conn: sqlite3.Connection,
        events: EventBus,
        now_ms: Callable[[], int] = epoch_ms_now,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.required = required
        self._settings = settings
        self._conn = conn
        self._events = events
        self._now_ms = now_ms
        self._transport = transport
        self._pending: list[str] = []  # `state` values of logins in flight

    # -- state -------------------------------------------------------------

    def _latest(self) -> sqlite3.Row | None:
        row: sqlite3.Row | None = self._conn.execute(
            "SELECT id, token, expires_at FROM sessions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row

    def state(self) -> AuthState:
        if not self.required:
            return "not_required"
        row = self._latest()
        if row is None:
            return "missing"
        return "valid" if self._now_ms() < int(row["expires_at"]) else "expired"

    @property
    def token(self) -> str | None:
        """The access token while it is valid, otherwise None."""
        if self.state() != "valid":
            return None
        row = self._latest()
        return str(row["token"]) if row is not None else None

    async def mark_expired(self) -> None:
        """Upstox rejected the token before its nominal expiry (e.g. revoked)."""
        row = self._latest()
        if row is None or self.state() != "valid":
            return
        self._conn.execute(
            "UPDATE sessions SET expires_at = ? WHERE id = ?", (self._now_ms(), row["id"])
        )
        await self._events.publish(AuthChanged("expired"))

    # -- login flow --------------------------------------------------------

    def _credentials(self) -> tuple[str, str, str]:
        s = self._settings
        if not s.upstox_api_key or not s.upstox_api_secret:
            raise AuthError(
                "Upstox credentials are not set. Put TRADEDISHA_UPSTOX_API_KEY and "
                "TRADEDISHA_UPSTOX_API_SECRET in .env and restart the backend."
            )
        return s.upstox_api_key, s.upstox_api_secret, s.upstox_redirect_uri

    def begin_login(self) -> str:
        """The Upstox page to send the browser to."""
        key, _, redirect = self._credentials()
        nonce = secrets.token_urlsafe(24)
        self._pending = [*self._pending, nonce][-MAX_PENDING_LOGINS:]
        query = urlencode(
            {"response_type": "code", "client_id": key, "redirect_uri": redirect, "state": nonce}
        )
        return f"{DIALOG_URL}?{query}"

    async def complete_login(self, code: str, state: str) -> None:
        """Exchange the one-time code Upstox sent back for an access token and store it."""
        if state not in self._pending:
            raise AuthError("Login did not start from this app, or was already used. Try again.")
        self._pending.remove(state)
        key, secret, redirect = self._credentials()
        form = {
            "code": code,
            "client_id": key,
            "client_secret": secret,
            "redirect_uri": redirect,
            "grant_type": "authorization_code",
        }
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=15) as client:
                resp = await client.post(
                    TOKEN_URL, data=form, headers={"accept": "application/json"}
                )
        except httpx.HTTPError as exc:
            raise AuthError(f"Could not reach Upstox: {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise AuthError(f"Upstox refused the login (HTTP {resp.status_code}): {_reason(resp)}")
        token = resp.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise AuthError("Upstox replied without an access token.")
        now = self._now_ms()
        self._conn.execute(
            "INSERT INTO sessions (token, obtained_at, expires_at) VALUES (?, ?, ?)",
            (token, now, token_expiry_ms(now)),
        )
        await self._events.publish(AuthChanged("valid"))


def _reason(resp: httpx.Response) -> str:
    """Upstox's own error text, without echoing anything we sent."""
    try:
        errors = resp.json().get("errors") or []
        return "; ".join(str(e.get("message", "")) for e in errors) or "no reason given"
    except (ValueError, AttributeError):
        return "no reason given"

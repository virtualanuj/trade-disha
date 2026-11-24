"""The Upstox login: state, the 03:30 expiry rule, and the code-for-token exchange."""

from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from tradedisha.auth import AuthError, AuthService, token_expiry_ms
from tradedisha.clock import IST, ist_to_ms
from tradedisha.config import Settings
from tradedisha.events import AuthChanged, EventBus
from tradedisha.store.db import connect


def _ms(year: int, month: int, day: int, hour: int, minute: int) -> int:
    return ist_to_ms(datetime(year, month, day, hour, minute, tzinfo=IST))


class Clock:
    def __init__(self, ms: int) -> None:
        self.ms = ms

    def __call__(self) -> int:
        return self.ms


def _service(
    handler: httpx.MockTransport | None = None,
    *,
    key: str = "the-key",
    clock: Clock | None = None,
    events: EventBus | None = None,
) -> AuthService:
    settings = Settings(
        _env_file=None,
        db_path=Path(":memory:"),
        feed_provider="upstox",
        upstox_api_key=key,
        upstox_api_secret="the-secret" if key else "",
    )
    return AuthService(
        required=True,
        settings=settings,
        conn=connect(":memory:"),
        events=events or EventBus(),
        now_ms=clock or Clock(_ms(2026, 11, 13, 11, 0)),
        transport=handler,
    )


def _token_endpoint(seen: list[httpx.Request], status: int = 200) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if status != 200:
            return httpx.Response(status, json={"errors": [{"message": "Invalid Auth code"}]})
        return httpx.Response(200, json={"access_token": "tok-123", "user_id": "X"})

    return httpx.MockTransport(handle)


def test_token_expires_at_the_next_0330_ist() -> None:
    assert token_expiry_ms(_ms(2026, 11, 13, 11, 0)) == _ms(2026, 11, 14, 3, 30)
    assert token_expiry_ms(_ms(2026, 11, 13, 2, 0)) == _ms(2026, 11, 13, 3, 30)
    assert token_expiry_ms(_ms(2026, 11, 13, 3, 30)) == _ms(2026, 11, 14, 3, 30)


def test_login_url_carries_key_redirect_and_a_fresh_state() -> None:
    auth = _service()
    a = parse_qs(urlparse(auth.begin_login()).query)
    b = parse_qs(urlparse(auth.begin_login()).query)

    assert a["client_id"] == ["the-key"]
    assert a["response_type"] == ["code"]
    assert a["redirect_uri"] == ["http://127.0.0.1:8000/api/auth/callback"]
    assert a["state"] != b["state"]


def test_login_refuses_to_start_without_credentials() -> None:
    with pytest.raises(AuthError, match="TRADEDISHA_UPSTOX_API_KEY"):
        _service(key="").begin_login()


async def test_login_stores_the_token_until_0330_then_expires() -> None:
    seen: list[httpx.Request] = []
    clock = Clock(_ms(2026, 11, 13, 11, 0))
    events = EventBus()
    changes: list[str] = []
    events.subscribe(AuthChanged, lambda e: changes.append(e.state))
    auth = _service(_token_endpoint(seen), clock=clock, events=events)
    assert auth.state() == "missing"

    state = parse_qs(urlparse(auth.begin_login()).query)["state"][0]
    await auth.complete_login("the-code", state)

    form = parse_qs(seen[0].content.decode())
    assert form["code"] == ["the-code"]
    assert form["client_secret"] == ["the-secret"]
    assert form["grant_type"] == ["authorization_code"]
    assert auth.state() == "valid"
    assert auth.token == "tok-123"
    assert changes == ["valid"]

    clock.ms = _ms(2026, 11, 14, 3, 31)
    assert auth.state() == "expired"
    assert auth.token is None


async def test_callback_with_an_unknown_or_reused_state_is_rejected() -> None:
    seen: list[httpx.Request] = []
    auth = _service(_token_endpoint(seen))
    with pytest.raises(AuthError):
        await auth.complete_login("code", "forged")
    state = parse_qs(urlparse(auth.begin_login()).query)["state"][0]
    await auth.complete_login("code", state)
    with pytest.raises(AuthError):
        await auth.complete_login("code", state)
    assert len(seen) == 1


async def test_refused_exchange_reports_upstox_reason_and_stays_logged_out() -> None:
    auth = _service(_token_endpoint([], status=401))
    state = parse_qs(urlparse(auth.begin_login()).query)["state"][0]
    with pytest.raises(AuthError, match="Invalid Auth code"):
        await auth.complete_login("bad", state)
    assert auth.state() == "missing"


async def test_mark_expired_ends_a_valid_login() -> None:
    auth = _service(_token_endpoint([]))
    state = parse_qs(urlparse(auth.begin_login()).query)["state"][0]
    await auth.complete_login("code", state)
    await auth.mark_expired()
    assert auth.state() == "expired"


def _upstox(seen: list[httpx.Request], logout: int | Exception = 200) -> httpx.MockTransport:
    """Token exchange, then the logout call answering with `logout`."""

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/logout"):
            if isinstance(logout, Exception):
                raise logout
            return httpx.Response(logout, json={"status": "success", "data": True})
        return httpx.Response(200, json={"access_token": "tok-123", "user_id": "X"})

    return httpx.MockTransport(handle)


async def _logged_in(transport: httpx.MockTransport, events: EventBus) -> AuthService:
    auth = _service(transport, events=events)
    state = parse_qs(urlparse(auth.begin_login()).query)["state"][0]
    await auth.complete_login("code", state)
    return auth


async def test_logout_revokes_the_token_at_upstox_and_forgets_it() -> None:
    seen: list[httpx.Request] = []
    events = EventBus()
    changes: list[str] = []
    events.subscribe(AuthChanged, lambda e: changes.append(e.state))
    auth = await _logged_in(_upstox(seen), events)

    await auth.logout()

    call = seen[-1]
    assert (call.method, str(call.url)) == ("DELETE", "https://api.upstox.com/v2/logout")
    assert call.headers["authorization"] == "Bearer tok-123"
    assert auth.state() == "missing"
    assert auth.token is None
    assert changes == ["valid", "missing"]


@pytest.mark.parametrize("answer", [500, 401, httpx.ConnectError("down")])
async def test_logout_still_ends_the_local_login_when_upstox_fails(
    answer: int | Exception,
) -> None:
    auth = await _logged_in(_upstox([], logout=answer), EventBus())
    await auth.logout()
    assert auth.state() == "missing"


async def test_logout_without_a_token_calls_nobody() -> None:
    seen: list[httpx.Request] = []
    auth = _service(_upstox(seen))
    await auth.logout()
    assert seen == []
    assert auth.state() == "missing"

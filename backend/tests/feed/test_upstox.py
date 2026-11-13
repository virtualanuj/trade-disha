"""The Upstox adapter: protobuf decoding, subscribe requests, reconnection."""

import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import pytest

from tradedisha.feed.provider import Tick
from tradedisha.feed.upstox import Unauthorized, UpstoxProvider, decode, fetch_ltp
from tradedisha.feed.upstox_proto import MarketDataFeed_pb2 as pb

NOW = 1_794_548_100_000


def _message() -> pb.FeedResponse:
    msg = pb.FeedResponse(type=pb.live_feed, currentTs=NOW)
    msg.feeds["NSE_INDEX|Nifty 50"].fullFeed.indexFF.ltpc.CopyFrom(
        pb.LTPC(ltp=25_010.5, ltt=NOW - 400, cp=24_950.0)
    )
    opt = msg.feeds["NSE_FO|41001"].fullFeed.marketFF
    opt.ltpc.CopyFrom(pb.LTPC(ltp=120.5, ltt=NOW - 90_000, cp=131.0))
    opt.marketLevel.bidAskQuote.add(bidQ=65, bidP=120.4, askQ=130, askP=120.6)
    opt.marketLevel.bidAskQuote.add(bidQ=65, bidP=120.3, askQ=130, askP=120.7)
    opt.optionGreeks.delta = -0.42
    opt.vtt = 9_000
    opt.oi = 1_234_500.0
    opt.iv = 0.1375
    return msg


def test_decode_index_and_option() -> None:
    by_key = {t.key: t for t in decode(_message())}

    assert by_key["NSE_INDEX|Nifty 50"] == Tick(
        key="NSE_INDEX|Nifty 50", ts=NOW, ltp=25_010.5, close_prev=24_950.0
    )
    assert by_key["NSE_FO|41001"] == Tick(
        key="NSE_FO|41001",
        ts=NOW,  # feed time, not the 90-second-old last trade
        ltp=120.5,
        volume=9_000,
        oi=1_234_500,
        bid=120.4,
        ask=120.6,
        iv=0.1375,
        delta=-0.42,
        close_prev=131.0,
    )


def test_decode_treats_proto_zeros_as_unchanged_and_skips_priceless_feeds() -> None:
    msg = pb.FeedResponse(type=pb.live_feed, currentTs=NOW)
    msg.feeds["NSE_FO|1"].fullFeed.marketFF.ltpc.ltp = 10.0
    msg.feeds["NSE_FO|2"].fullFeed.marketFF.oi = 5.0  # no price at all

    ticks = decode(msg)

    assert ticks == [Tick(key="NSE_FO|1", ts=NOW, ltp=10.0)]


def test_decode_ignores_market_status_messages() -> None:
    assert decode(pb.FeedResponse(type=pb.market_info, currentTs=NOW)) == []


class FakeSocket:
    """Yields queued frames, then drops the connection."""

    def __init__(self, frames: list[bytes]) -> None:
        self.frames = frames
        self.sent: list[dict[str, object]] = []
        self.closed = False

    async def send(self, message: bytes) -> None:
        self.sent.append(json.loads(message))

    async def close(self) -> None:
        self.closed = True

    async def __aiter__(self) -> AsyncIterator[str | bytes]:
        for f in self.frames:
            yield f
        raise ConnectionError("dropped")


def _authorize(status: int = 200) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer tok"
        if status != 200:
            return httpx.Response(status, json={})
        return httpx.Response(200, json={"data": {"authorized_redirect_uri": "wss://feed/x"}})

    return httpx.MockTransport(handle)


async def _no_sleep(_: float) -> None:
    await asyncio.sleep(0)


async def test_subscribes_in_full_mode_and_resubscribes_after_a_drop() -> None:
    frame = _message().SerializeToString()
    sockets = [FakeSocket([frame]), FakeSocket([frame])]
    opened: list[str] = []

    async def factory(url: str) -> FakeSocket:
        opened.append(url)
        return sockets[len(opened) - 1]

    p = UpstoxProvider(
        token=lambda: "tok", transport=_authorize(), socket_factory=factory, sleep=_no_sleep
    )
    await p.connect()
    assert p.health().state == "connected"
    await p.subscribe(["NSE_INDEX|Nifty 50", "NSE_FO|41001"])

    seen: list[Tick] = []
    async for t in p.ticks():
        seen.append(t)
        if len(seen) == 4:
            break
    await p.close()

    assert opened == ["wss://feed/x", "wss://feed/x"]
    first = sockets[0].sent[0]
    assert first["method"] == "sub"
    assert first["data"] == {
        "mode": "full",
        "instrumentKeys": ["NSE_INDEX|Nifty 50", "NSE_FO|41001"],
    }
    assert sockets[1].sent[0]["data"] == {
        "mode": "full",
        "instrumentKeys": ["NSE_FO|41001", "NSE_INDEX|Nifty 50"],
    }
    h = p.health()
    assert (h.reconnects, h.subscribed, h.last_tick_ts, h.state) == (1, 2, NOW, "disconnected")
    assert sockets[1].closed


async def test_unsubscribe_sends_only_known_keys() -> None:
    sock = FakeSocket([])

    async def factory(_: str) -> FakeSocket:
        return sock

    p = UpstoxProvider(token=lambda: "tok", transport=_authorize(), socket_factory=factory)
    await p.connect()
    await p.subscribe(["A", "B"])
    await p.unsubscribe(["B", "C"])

    assert sock.sent[1]["method"] == "unsub"
    assert sock.sent[1]["data"] == {"mode": "full", "instrumentKeys": ["B"]}
    assert p.health().subscribed == 1


async def test_rejected_token_reports_unauthorized_and_stays_disconnected() -> None:
    told: list[bool] = []

    async def on_unauthorized() -> None:
        told.append(True)

    async def factory(_: str) -> FakeSocket:
        raise AssertionError("must not connect without authorisation")

    p = UpstoxProvider(
        token=lambda: "tok",
        on_unauthorized=on_unauthorized,
        transport=_authorize(401),
        socket_factory=factory,
    )
    await p.connect()

    assert told == [True]
    assert p.health().state == "disconnected"


async def test_no_token_means_no_connection_attempt() -> None:
    async def factory(_: str) -> FakeSocket:
        raise AssertionError("must not connect without a token")

    p = UpstoxProvider(token=lambda: None, socket_factory=factory)
    await p.connect()
    assert p.health().state == "disconnected"


async def test_fetch_ltp_maps_prices_back_to_instrument_keys() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.params["instrument_key"] == "NSE_INDEX|Nifty 50,NSE_INDEX|Nifty Bank"
        return httpx.Response(
            200,
            json={
                "data": {
                    "NSE_INDEX:Nifty 50": {
                        "last_price": 25_010.5,
                        "instrument_token": "NSE_INDEX|Nifty 50",
                    },
                    "NSE_INDEX:Nifty Bank": {"last_price": 56_100},
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        out = await fetch_ltp(client, "tok", ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"])

    assert out == {"NSE_INDEX|Nifty 50": 25_010.5, "NSE_INDEX|Nifty Bank": 56_100.0}


async def test_fetch_ltp_raises_unauthorized_on_401() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(401, json={}))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(Unauthorized):
            await fetch_ltp(client, "tok", ["NSE_INDEX|Nifty 50"])

"""WebSocket push: `hello` snapshot on connect, then `tick`, `chain`, `candle`, `bias`,
`health` and `parameters` frames.

Every frame carries t_src (exchange ts of the newest data in it), t_in (backend ingest of
that data) and t_out (send time) so the browser can compute per-hop latency.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tradedisha.api.analysis import (
    bias_out,
    candle_out,
    candles_response,
    overlay_out,
    parameters_out,
)
from tradedisha.api.chain import chain_out
from tradedisha.api.health import build_health
from tradedisha.api.instruments import resolved_out
from tradedisha.app_state import AppState
from tradedisha.clock import epoch_ms_now
from tradedisha.engine.bias_engine import BiasComputed
from tradedisha.events import FeedHealthChanged, ParametersChanged, WindowChanged
from tradedisha.feed.bus import StampedTick
from tradedisha.market.candles import Candle
from tradedisha.market.chain import ChainState

log = logging.getLogger(__name__)
router = APIRouter()

SLOW_CLIENT_LIMIT = 64  # queued frames before we drop the client


class WsHub:
    """Fans backend state out to every connected browser."""

    def __init__(self, state: AppState) -> None:
        self._state = state
        self._clients: set[asyncio.Queue[str]] = set()
        self._dirty: dict[str, int] = {}  # index -> t_in of newest price tick since last push
        self._chain_dirty: dict[str, int] = {}  # index -> t_in of newest option tick
        self._health_dirty = False
        self._immediate: list[str] = []  # frames to send on the next pusher pass
        self._task: asyncio.Task[None] | None = None
        state.session.tick_bus.subscribe(self._on_tick)
        state.session.candle_listeners.append(self._on_candle)
        state.session.bias_listeners.append(self._on_bias)
        state.events.subscribe(FeedHealthChanged, self._on_health)
        state.events.subscribe(WindowChanged, self._on_window)
        state.events.subscribe(ParametersChanged, self._on_params)

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._task = asyncio.create_task(self._pusher(), name="ws-pusher")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    # -- inbound -----------------------------------------------------------

    def _on_tick(self, st: StampedTick) -> None:
        index = self._index_for(st.tick.key)
        if index is not None:
            self._dirty[index] = st.t_in
            return
        mgr = self._state.session.chains
        if mgr is not None:
            for idx, chain in mgr.chains.items():
                if st.tick.key in chain.key_set:
                    self._chain_dirty[idx] = st.t_in
                    return

    def _on_candle(self, c: Candle) -> None:
        index = self._index_for(c.key)
        if index is None:
            return
        r = self._state.session.resolved[index]
        role = "spot" if c.key == r.spot.instrument_key else "fut"
        payload = {"index": index, "role": role, "candle": candle_out(c).model_dump()}
        self._immediate.append(self._frame("candle", payload, t_src=c.minute_ts, t_in=None))

    def _on_bias(self, b: BiasComputed) -> None:
        payload = {
            "bias": bias_out(b).model_dump(),
            "overlay": overlay_out(b.overlays).model_dump(),
        }
        self._immediate.append(self._frame("bias", payload, t_src=b.minute_ts, t_in=None))

    def _on_health(self, _: FeedHealthChanged) -> None:
        self._health_dirty = True

    def _on_window(self, ev: WindowChanged) -> None:
        self._chain_dirty[ev.index] = epoch_ms_now()

    def _on_params(self, ev: ParametersChanged) -> None:
        payload = {
            **parameters_out(self._state).model_dump(mode="json"),
            "effective_from_minute_ts": ev.effective_from_minute_ts,
        }
        self._immediate.append(self._frame("parameters", payload, t_src=None, t_in=None))

    def _index_for(self, key: str) -> str | None:
        for r in self._state.session.resolved.values():
            if key in (r.spot.instrument_key, r.future.instrument_key):
                return r.index
        return None

    # -- outbound ----------------------------------------------------------

    def _frame(self, type_: str, payload: object, *, t_src: int | None, t_in: int | None) -> str:
        return json.dumps(
            {
                "type": type_,
                "ts": epoch_ms_now(),
                "t_src": t_src,
                "t_in": t_in,
                "t_out": epoch_ms_now(),
                "payload": payload,
            },
            separators=(",", ":"),
        )

    def _prices_payload(self, index: str) -> dict[str, object]:
        r = self._state.session.resolved[index]
        p = self._state.session.prices
        sk, fk = r.spot.instrument_key, r.future.instrument_key
        return {
            "index": index,
            "spot_ltp": p.ltp.get(sk),
            "spot_ts": p.ts.get(sk),
            "fut_ltp": p.ltp.get(fk),
            "fut_ts": p.ts.get(fk),
        }

    def _chains(self) -> dict[str, ChainState]:
        mgr = self._state.session.chains
        return dict(mgr.chains) if mgr else {}

    def hello(self) -> str:
        s = self._state
        engine = s.session.bias
        latest = list(engine.latest.values()) if engine else []
        payload = {
            "health": build_health(s).model_dump(),
            "instruments": [resolved_out(r).model_dump() for r in s.session.resolved.values()],
            "prices": [self._prices_payload(i) for i in s.session.resolved],
            "chains": [chain_out(c).model_dump() for c in self._chains().values()],
            "candles": [candles_response(s, i, 400).model_dump() for i in s.session.resolved],
            "bias": [bias_out(b).model_dump() for b in latest],
            "parameters": parameters_out(s).model_dump(mode="json"),
        }
        return self._frame("hello", payload, t_src=None, t_in=None)

    def _broadcast(self, frame: str) -> None:
        for q in list(self._clients):
            if q.qsize() >= SLOW_CLIENT_LIMIT:
                self._clients.discard(q)  # reader will see the sentinel and close
                q.put_nowait("")
                continue
            q.put_nowait(frame)

    async def _pusher(self) -> None:
        """Leading-edge throttle per channel; immediate frames go out on the next pass."""
        interval_ms = 1000.0 / self._state.settings.ws_tick_hz
        chain_interval_ms = 1000.0 / self._state.settings.ws_chain_hz
        last_push: dict[str, float] = {}
        last_chain_push: dict[str, float] = {}
        while True:
            await asyncio.sleep(interval_ms / 4000)
            if not self._clients:
                self._dirty.clear()
                self._chain_dirty.clear()
                self._immediate.clear()
                self._health_dirty = False
                continue
            now = epoch_ms_now()
            if self._immediate:
                frames, self._immediate = self._immediate, []
                for f in frames:
                    self._broadcast(f)
            for index in list(self._dirty):
                if now - last_push.get(index, 0.0) < interval_ms:
                    continue
                t_in = self._dirty.pop(index)
                last_push[index] = now
                payload = self._prices_payload(index)
                stamps = [v for v in (payload["spot_ts"], payload["fut_ts"]) if isinstance(v, int)]
                frame = self._frame("tick", payload, t_src=max(stamps, default=None), t_in=t_in)
                self._broadcast(frame)
                self._state.latency.record("in_to_out", epoch_ms_now() - t_in)
            mgr = self._state.session.chains
            for index in list(self._chain_dirty):
                if mgr is None or now - last_chain_push.get(index, 0.0) < chain_interval_ms:
                    continue
                t_in = self._chain_dirty.pop(index)
                last_chain_push[index] = now
                chain = mgr.chains[index]
                payload = chain_out(chain).model_dump()
                self._broadcast(self._frame("chain", payload, t_src=chain.updated_ts, t_in=t_in))
            if self._health_dirty:
                self._health_dirty = False
                payload = build_health(self._state).model_dump()
                self._broadcast(self._frame("health", payload, t_src=None, t_in=None))

    # -- per-connection ----------------------------------------------------

    async def serve(self, ws: WebSocket) -> None:
        await ws.accept()
        q: asyncio.Queue[str] = asyncio.Queue()
        self._clients.add(q)
        await ws.send_text(self.hello())

        async def reader() -> None:
            while True:
                msg = await ws.receive_text()
                if msg == '{"type":"ping"}':
                    await ws.send_text(self._frame("pong", None, t_src=None, t_in=None))

        async def writer() -> None:
            while True:
                frame = await q.get()
                if frame == "":
                    await ws.close(code=1008, reason="client too slow")
                    return
                await ws.send_text(frame)

        tasks = [asyncio.create_task(reader()), asyncio.create_task(writer())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                exc = t.exception()
                if exc and not isinstance(exc, WebSocketDisconnect):
                    log.debug("ws task ended: %r", exc)
        finally:
            self._clients.discard(q)
            for t in tasks:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    hub: WsHub = ws.app.state.ws_hub
    with contextlib.suppress(WebSocketDisconnect):
        await hub.serve(ws)

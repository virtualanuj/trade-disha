"""WebSocket push: `hello` snapshot on connect, then `tick`, `chain`, `candle`, `bias`,
`bullion`, `bullion_candle`, `chart_bar`, `health` and `parameters` frames.

Every frame carries t_src (exchange ts of the newest data in it), t_in (backend ingest of
that data) and t_out (send time) so the browser can compute per-hop latency.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from tradedisha.api.analysis import (
    bias_out,
    candle_out,
    candles_response,
    overlay_out,
    parameters_out,
)
from tradedisha.api.bullion import all_bullion_candles, bullion_out, vwap_overlays
from tradedisha.api.chain import chain_out
from tradedisha.api.health import build_health
from tradedisha.api.instruments import resolved_out
from tradedisha.api.news import news_out
from tradedisha.api.paper import bank_out, open_trades, today_trades, trade_out
from tradedisha.api.signals import (
    active_signals,
    flow_out,
    flow_readings,
    gates,
    signal_out,
    today_signals,
)
from tradedisha.api.stats import all_quotes, all_stats
from tradedisha.app_state import AppState
from tradedisha.clock import epoch_ms_now
from tradedisha.engine.bias_engine import BiasComputed
from tradedisha.engine.paper import PaperTrade
from tradedisha.engine.signals import Signal
from tradedisha.events import (
    AuthChanged,
    FeedHealthChanged,
    NewsChanged,
    ParametersChanged,
    WindowChanged,
)
from tradedisha.feed.bus import StampedTick
from tradedisha.market.candles import Candle
from tradedisha.market.chain import ChainState
from tradedisha.market.chart_bars import ChartBar
from tradedisha.market.flow import FlowReading
from tradedisha.market.stats import STRIP_QUOTES

log = logging.getLogger(__name__)
router = APIRouter()

SLOW_CLIENT_LIMIT = 64  # queued frames before we drop the client
OPEN_TRADES_PUSH_MS = 1000
STRIP_KEYS = frozenset(k for _, k in STRIP_QUOTES)  # SENSEX: the `quotes` frame


class WsHub:
    """Fans backend state out to every connected browser."""

    def __init__(self, state: AppState) -> None:
        self._state = state
        self._clients: set[asyncio.Queue[str]] = set()
        self._dirty: dict[str, int] = {}  # index -> t_in of newest price tick since last push
        self._chain_dirty: dict[str, int] = {}  # index -> t_in of newest option tick
        self._bullion_dirty: int | None = None  # t_in of newest gold / silver tick
        self._last_bullion_push = 0.0
        self._quotes_dirty: int | None = None  # t_in of newest strip-quote tick (SENSEX)
        self._last_quotes_push = 0.0
        self._health_dirty = False
        # Frames to send on the next pusher pass; a callable is built then (see `_on_bias`).
        self._immediate: list[str | Callable[[], str]] = []
        self._flow_pending: dict[str, FlowReading] = {}
        self._task: asyncio.Task[None] | None = None
        state.session.tick_bus.subscribe(self._on_tick)
        state.session.candle_listeners.append(self._on_candle)
        state.session.bias_listeners.append(self._on_bias)
        state.session.signal_listeners.append(self._on_signal)
        state.session.trade_listeners.append(self._on_trade)
        state.session.flow_listeners.append(self._on_flow)
        state.session.bullion_candle_listeners.append(self._on_bullion_candle)
        state.session.chart_bar_listeners.append(self._on_chart_bar)
        state.events.subscribe(FeedHealthChanged, self._on_health)
        state.events.subscribe(AuthChanged, self._on_health)
        state.events.subscribe(WindowChanged, self._on_window)
        state.events.subscribe(ParametersChanged, self._on_params)
        state.events.subscribe(NewsChanged, self._on_news)

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
        session = self._state.session
        if st.tick.key in session.bullion_keys or st.tick.key in session.etf_keys:
            self._bullion_dirty = st.t_in
            return
        if st.tick.key in STRIP_KEYS:
            self._quotes_dirty = st.t_in
            return
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

    def _on_bullion_candle(self, metal: str, c: Candle) -> None:
        bullion = self._state.session.bullion
        day = bullion.closed_candles(metal) if bullion else [c]
        overlay = vwap_overlays(day or [c])[-1]
        payload = {
            "metal": metal,
            "candle": candle_out(c).model_dump(),
            "overlay": overlay.model_dump(),
        }
        self._immediate.append(self._frame("bullion_candle", payload, t_src=c.minute_ts, t_in=None))

    def _on_chart_bar(self, bar: ChartBar) -> None:
        """A 10 s, 30 s or 5 m bar closed (E27): every client gets it; a page keeps it only
        for a chart it has loaded."""
        payload = {
            "name": bar.name,
            "interval": bar.interval,
            "role": bar.role,
            "candle": candle_out(bar.candle).model_dump(),
            "overlay": overlay_out(bar.overlay).model_dump() if bar.overlay else None,
        }
        frame = self._frame("chart_bar", payload, t_src=bar.candle.minute_ts, t_in=None)
        self._immediate.append(frame)

    def _gates(self) -> list[dict[str, object]]:
        return [g.model_dump() for g in gates(self._state)]

    def _on_bias(self, b: BiasComputed) -> None:
        # The hub hears the bias before the signal engines evaluate the minute (they are
        # wired later, at feed start), so the gates are read when the frame is sent.
        payload: dict[str, object] = {
            "bias": bias_out(b).model_dump(),
            "overlay": overlay_out(b.overlays).model_dump(),
        }
        self._immediate.append(
            lambda: self._frame(
                "bias", payload | {"gates": self._gates()}, t_src=b.minute_ts, t_in=None
            )
        )

    def _on_signal(self, s: Signal) -> None:
        # A reversal is announced before the entry rule has run: gates are read on sending.
        payload: dict[str, object] = {"signal": signal_out(self._state, s).model_dump()}
        t_src = s.status_ts
        self._immediate.append(
            lambda: self._frame(
                "signal", payload | {"gates": self._gates()}, t_src=t_src, t_in=None
            )
        )

    def _on_flow(self, r: FlowReading) -> None:
        """About one a second per index; the newest replaces any not yet sent."""
        self._flow_pending[r.index] = r

    def _on_trade(self, t: PaperTrade) -> None:
        payload = {"trades": [trade_out(self._state, t).model_dump()]}
        self._immediate.append(self._frame("paper_trade", payload, t_src=None, t_in=None))
        self._push_bank()

    def _push_bank(self) -> None:
        """The paper bank moves when a trade opens or closes, or the opening balance changes."""
        payload = bank_out(self._state).model_dump()
        self._immediate.append(self._frame("bank", payload, t_src=None, t_in=None))

    def _on_health(self, _: FeedHealthChanged | AuthChanged) -> None:
        self._health_dirty = True

    def _on_window(self, ev: WindowChanged) -> None:
        self._chain_dirty[ev.index] = epoch_ms_now()

    def _on_params(self, ev: ParametersChanged) -> None:
        payload = {
            **parameters_out(self._state).model_dump(mode="json"),
            "effective_from_minute_ts": ev.effective_from_minute_ts,
        }
        self._immediate.append(self._frame("parameters", payload, t_src=None, t_in=None))
        self._push_bank()  # a new opening balance is a deposit or withdrawal: record it now

    def _on_news(self, _: NewsChanged) -> None:
        news = self._state.news
        payload = news_out(self._state).model_dump()
        self._immediate.append(self._frame("news", payload, t_src=news.fetched_at, t_in=None))

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
                # the market clock (in replay, the recorded day's): the page's times read it
                "t_mkt": self._state.clock.now_ms(),
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
        engine, desk = s.session.bias, s.session.bullion_desk
        latest = list(engine.latest.values()) if engine else []
        latest += list(desk.bias.latest.values()) if desk else []  # GOLD / SILVER
        payload = {
            "health": build_health(s).model_dump(),
            "instruments": [resolved_out(r).model_dump() for r in s.session.resolved.values()],
            "prices": [self._prices_payload(i) for i in s.session.resolved],
            "chains": [chain_out(c).model_dump() for c in self._chains().values()],
            "candles": [candles_response(s, i, 400).model_dump() for i in s.session.resolved],
            "bias": [bias_out(b).model_dump() for b in latest],
            "parameters": parameters_out(s).model_dump(mode="json"),
            "signals_active": [x.model_dump() for x in active_signals(s)],
            "signals_today": [x.model_dump() for x in today_signals(s)],
            "gates": [g.model_dump() for g in gates(s)],
            "flow": [f.model_dump() for f in flow_readings(s)],
            "paper_trades": [t.model_dump() for t in today_trades(s)],
            "bank": bank_out(s).model_dump(),
            "stats": [x.model_dump() for x in all_stats(s)],
            "quotes": [x.model_dump() for x in all_quotes(s)],
            "bullion": bullion_out(s).model_dump(mode="json"),
            "bullion_candles": [x.model_dump() for x in all_bullion_candles(s, 900)],
            "news": news_out(s).model_dump(),
        }
        return self._frame("hello", payload, t_src=None, t_in=None)

    def _broadcast_built(self, frame: str | Callable[[], str]) -> None:
        """Send a queued frame, building it now if it was queued as a builder."""
        if isinstance(frame, str):
            self._broadcast(frame)
            return
        try:
            built = frame()
        except Exception:  # a frame that cannot be built must not stop the pusher
            log.exception("building a websocket frame failed")
            return
        self._broadcast(built)

    def _broadcast(self, frame: str) -> None:
        for q in list(self._clients):
            if q.qsize() >= SLOW_CLIENT_LIMIT:
                self._clients.discard(q)  # reader will see the sentinel and close
                q.put_nowait("")
                continue
            q.put_nowait(frame)

    def _push_every_second(self, last_stats: dict[str, str]) -> None:
        """Live P&L of open trades, live levels of waiting signals, index details if moved."""
        live = open_trades(self._state)
        if live:
            payload = {"trades": [t.model_dump() for t in live]}
            self._broadcast(self._frame("paper_trade", payload, t_src=None, t_in=None))
        waiting = active_signals(self._state)
        if waiting:
            payload = {"signals": [s.model_dump() for s in waiting]}
            self._broadcast(self._frame("signal_live", payload, t_src=None, t_in=None))
        for st in all_stats(self._state):
            body = st.model_dump()
            fingerprint = json.dumps(body, sort_keys=True)
            if last_stats.get(st.index) != fingerprint:
                last_stats[st.index] = fingerprint
                self._broadcast(self._frame("stats", body, t_src=None, t_in=None))

    def _push_bullion(self, now: float, interval_ms: float) -> None:
        """The whole bullion snapshot in one frame, throttled like `tick`; display only."""
        t_in = self._bullion_dirty
        if t_in is None or now - self._last_bullion_push < interval_ms:
            return
        self._bullion_dirty = None
        self._last_bullion_push = now
        body = bullion_out(self._state)
        stamps = [m.updated_ts for m in body.metals if m.updated_ts is not None]
        payload = body.model_dump(mode="json")
        frame = self._frame("bullion", payload, t_src=max(stamps, default=None), t_in=t_in)
        self._broadcast(frame)

    def _push_quotes(self, now: float, interval_ms: float) -> None:
        """The strip's market-wide quotes (SENSEX) in one frame, throttled like `tick`."""
        t_in = self._quotes_dirty
        if t_in is None or now - self._last_quotes_push < interval_ms:
            return
        self._quotes_dirty = None
        self._last_quotes_push = now
        quotes = all_quotes(self._state)
        stamps = [q.updated_ts for q in quotes if q.updated_ts is not None]
        payload = [q.model_dump() for q in quotes]
        self._broadcast(self._frame("quotes", payload, t_src=max(stamps, default=None), t_in=t_in))

    def _drop_pending(self) -> None:
        """With nobody connected, nothing waits to be sent: the next hello carries it all."""
        self._dirty.clear()
        self._chain_dirty.clear()
        self._bullion_dirty = None
        self._quotes_dirty = None
        self._immediate.clear()
        self._health_dirty = False

    async def _pusher(self) -> None:
        """Leading-edge throttle per channel; immediate frames go out on the next pass."""
        interval_ms = 1000.0 / self._state.settings.ws_tick_hz
        chain_interval_ms = 1000.0 / self._state.settings.ws_chain_hz
        last_push: dict[str, float] = {}
        last_chain_push: dict[str, float] = {}
        last_trades_push = 0.0
        last_stats: dict[str, str] = {}
        while True:
            await asyncio.sleep(interval_ms / 4000)
            if not self._clients:
                self._drop_pending()
                continue
            now = epoch_ms_now()
            if self._immediate:
                frames, self._immediate = self._immediate, []
                for f in frames:
                    self._broadcast_built(f)
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
            self._push_bullion(now, interval_ms)
            self._push_quotes(now, interval_ms)
            mgr = self._state.session.chains
            for index in list(self._chain_dirty):
                if mgr is None or now - last_chain_push.get(index, 0.0) < chain_interval_ms:
                    continue
                t_in = self._chain_dirty.pop(index)
                last_chain_push[index] = now
                chain = mgr.chains[index]
                payload = chain_out(chain).model_dump()
                self._broadcast(self._frame("chain", payload, t_src=chain.updated_ts, t_in=t_in))
            if now - last_trades_push >= OPEN_TRADES_PUSH_MS:
                last_trades_push = now
                self._push_every_second(last_stats)
            if self._flow_pending:
                pending, self._flow_pending = self._flow_pending, {}
                for r in pending.values():
                    payload = flow_out(self._state, r).model_dump()
                    self._broadcast(self._frame("flow", payload, t_src=r.ts, t_in=None))
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

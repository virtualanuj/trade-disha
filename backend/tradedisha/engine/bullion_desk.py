"""The bullion trading pipeline in one place (spec §9a): bias -> signals -> paper trades.

Built by `FeedSession` once the MCX contracts are loaded. It runs on the MCX clock and on
bullion liveness, never on NSE's, and it shares only the stores and the listener lists
(so the existing `bias`, `signal` and `paper_trade` frames carry bullion too).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from tradedisha.clock import MarketClock
from tradedisha.engine.bias_engine import BiasComputed
from tradedisha.engine.bullion_bias import BullionBiasEngine
from tradedisha.engine.bullion_signals import BullionSignalEngine
from tradedisha.engine.paper import PaperTrade, PaperTradeManager, Price, bullion_rules
from tradedisha.engine.signals import Signal
from tradedisha.feed.bus import StampedTick
from tradedisha.indicators import IndicatorResult
from tradedisha.market.bullion import BullionTracker
from tradedisha.market.candles import MINUTE_MS
from tradedisha.parameters.model import ParameterSet


class BullionDesk:
    def __init__(  # noqa: PLR0913 -- injected collaborators
        self,
        *,
        tracker: BullionTracker,
        clock: MarketClock,
        params: Callable[[], ParameterSet],
        conn: sqlite3.Connection,
        feed_live: Callable[[], bool],
        enforce_hours: bool,
        price: Callable[[str], Price | None],
        last_recorded: Callable[[str, int], Price | None] | None = None,
        on_bias: Callable[[BiasComputed], None] | None = None,
        on_signal: Callable[[Signal], None] | None = None,
        on_trade: Callable[[PaperTrade], None] | None = None,
        config_version: Callable[[], int | None] | None = None,
        macro: Callable[[int], list[IndicatorResult]] | None = None,
    ) -> None:
        self._clock = clock
        self._on_bias_out = on_bias
        self.bias = BullionBiasEngine(
            tracker=tracker, params=params, conn=conn, on_bias=self._on_bias, macro=macro
        )
        self.signals = BullionSignalEngine(
            tracker=tracker,
            clock=clock,
            params=params,
            conn=conn,
            feed_live=feed_live,
            enforce_hours=enforce_hours,
            on_signal=on_signal,
            config_version=config_version,
        )
        self.paper = PaperTradeManager(
            clock=clock,
            params=params,
            conn=conn,
            signals=self.signals,
            price=price,
            feed_live=feed_live,
            enforce_hours=enforce_hours,
            last_recorded=last_recorded,
            on_trade=on_trade,
            rules=bullion_rules(),
        )
        self.bias.attach()
        self.eval_lags_ms: list[int] = []  # since the last `housekeeping` call

    def _on_bias(self, b: BiasComputed) -> None:
        now = self._clock.now_ms()
        self.eval_lags_ms.append(now - (b.minute_ts + MINUTE_MS))
        self.signals.on_bias(b, now)
        self.paper.on_bias(b)
        if self._on_bias_out:
            self._on_bias_out(b)

    def on_tick(self, st: StampedTick) -> None:
        """Bullion ticks also run due evaluations, on the market clock, so a fast replay
        times them exactly as live did; housekeeping covers a quiet market."""
        self.bias.run_due(self._clock.now_ms())
        self.paper.on_tick(st)

    def housekeeping(self, now_ms: int) -> list[int]:
        """Twice a second: evaluate the minutes now due, lapse signals, square off.

        Returns how late each evaluation ran after its minute closed (the offset, roughly).
        """
        self.bias.run_due(now_ms)
        self.signals.tick(now_ms)
        self.paper.tick(now_ms)
        lags, self.eval_lags_ms = self.eval_lags_ms, []
        return lags

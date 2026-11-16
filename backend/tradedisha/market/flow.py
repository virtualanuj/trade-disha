"""Order flow: who is leaning on the book and who is paying up. Spec §8.5.

Three parts per index, each from -1 (selling) to +1 (buying):

- futures book: resting bid quantity against ask quantity;
- futures trades: traded volume signed by whether it printed at the ask or at the bid;
- options: flow in the ATM call minus flow in the ATM put.

They are smoothed over a few seconds and mixed into one score. A part with no data is
unknown and left out of the mix, never counted as zero. Time is the tick's own timestamp,
so a day replayed at any speed reads the same as it did live.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from tradedisha.feed.bus import StampedTick
from tradedisha.feed.provider import Tick
from tradedisha.instruments.models import ResolvedIndex
from tradedisha.market.chain import ChainState
from tradedisha.parameters.model import ParameterSet

KEEP_MS = 300_000  # the longest window the parameters allow
EVAL_MS = 1000


def _imbalance(buy: int | None, sell: int | None) -> float | None:
    if buy is None or sell is None or buy + sell <= 0:
        return None
    return (buy - sell) / (buy + sell)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


class KeyFlow:
    """Order-flow memory for one instrument."""

    def __init__(self) -> None:
        self._bid: float | None = None
        self._ask: float | None = None
        self._bid_qty5: int | None = None
        self._ask_qty5: int | None = None
        self._tbq: int | None = None
        self._tsq: int | None = None
        self._volume: int | None = None
        self._book: deque[tuple[int, float]] = deque()  # (ts, imbalance)
        self._trades: deque[tuple[int, int, int]] = deque()  # (ts, signed qty, qty)

    def apply(self, t: Tick) -> None:
        self._trade(t)  # judged against the quote as it stood before this tick
        if t.bid is not None:
            self._bid = t.bid
        if t.ask is not None:
            self._ask = t.ask
        fresh = False
        for name in ("bid_qty5", "ask_qty5", "tbq", "tsq"):
            value = getattr(t, name)
            if value is not None:
                setattr(self, f"_{name}", value)
                fresh = True
        if fresh:
            parts = [
                x
                for x in (
                    _imbalance(self._bid_qty5, self._ask_qty5),
                    _imbalance(self._tbq, self._tsq),
                )
                if x is not None
            ]
            if parts:
                self._book.append((t.ts, sum(parts) / len(parts)))
        self._drop_old(t.ts)

    def _trade(self, t: Tick) -> None:
        if t.volume is None:
            return
        last, self._volume = self._volume, t.volume
        if last is None or t.volume <= last or self._bid is None or self._ask is None:
            return
        qty = t.volume - last
        side = 1 if t.ltp >= self._ask else -1 if t.ltp <= self._bid else 0
        self._trades.append((t.ts, side * qty, qty))

    def _drop_old(self, now: int) -> None:
        while self._book and self._book[0][0] < now - KEEP_MS:
            self._book.popleft()
        while self._trades and self._trades[0][0] < now - KEEP_MS:
            self._trades.popleft()

    def book(self, now: int, window_ms: float) -> float | None:
        """Mean book imbalance over the window; None when nothing was seen in it."""
        return _mean([x for ts, x in self._book if ts >= now - window_ms])

    def trades(self, now: int, window_ms: float) -> float | None:
        """Net signed volume over total volume in the window; None when nothing traded."""
        recent = [(s, q) for ts, s, q in self._trades if ts >= now - window_ms]
        total = sum(q for _, q in recent)
        return sum(s for s, _ in recent) / total if total else None

    def flow(self, now: int, window_ms: float) -> float | None:
        """Book and trades together, for a leg where either may be missing."""
        return _mean(
            [x for x in (self.book(now, window_ms), self.trades(now, window_ms)) if x is not None]
        )


@dataclass(frozen=True)
class FlowReading:
    index: str
    ts: int
    score: float | None  # None when no part has data
    fut_book: float | None
    fut_trades: float | None
    options: float | None  # ATM call flow minus ATM put flow, halved to stay within -1..+1


class FlowTracker:
    def __init__(
        self,
        *,
        params: Callable[[], ParameterSet],
        resolved: dict[str, ResolvedIndex],
        chains: dict[str, ChainState],
        on_flow: Callable[[FlowReading], None] | None = None,
    ) -> None:
        self._params = params
        self._chains = chains
        self._on_flow = on_flow
        self._fut = {i: r.future.instrument_key for i, r in resolved.items()}
        self._index_of_fut = {key: i for i, key in self._fut.items()}
        self._keys: dict[str, KeyFlow] = {}
        self._last_eval: dict[str, int] = {}
        self.latest: dict[str, FlowReading] = {}

    def on_tick(self, st: StampedTick) -> None:
        t = st.tick
        index = self._index_of_fut.get(t.key)
        if index is None:
            index = next((i for i, c in self._chains.items() if t.key in c.key_set), None)
            if index is None:
                return
        state = self._keys.get(t.key)
        if state is None:
            state = self._keys[t.key] = KeyFlow()
        state.apply(t)
        last = self._last_eval.get(index)
        if last is not None and t.ts - last < EVAL_MS:
            return
        self._last_eval[index] = t.ts
        reading = self.latest[index] = self.reading(index, t.ts)
        if self._on_flow:
            self._on_flow(reading)

    def reading(self, index: str, now: int) -> FlowReading:
        p = self._params().flow
        window = p.window_seconds * 1000
        fut = self._keys.get(self._fut[index])
        fut_book = fut.book(now, window) if fut else None
        fut_trades = fut.trades(now, window) if fut else None
        options = self._options(index, now, window)
        mix = [
            (w, x)
            for w, x in (
                (p.w_fut_book, fut_book),
                (p.w_fut_trades, fut_trades),
                (p.w_options, options),
            )
            if x is not None and w > 0
        ]
        weight = sum(w for w, _ in mix)
        score = sum(w * x for w, x in mix) / weight if weight else None
        return FlowReading(index, now, score, fut_book, fut_trades, options)

    def _options(self, index: str, now: int, window: float) -> float | None:
        chain = self._chains[index]
        row = chain.rows.get(chain.atm)
        if row is None:
            return None
        ce, pe = self._keys.get(row.ce.key), self._keys.get(row.pe.key)
        ce_flow = ce.flow(now, window) if ce else None
        pe_flow = pe.flow(now, window) if pe else None
        if ce_flow is None or pe_flow is None:
            return None
        return (ce_flow - pe_flow) / 2

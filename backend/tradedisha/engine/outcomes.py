"""Scores every signal by what its option did next. Spec §9.5.

A signal is followed from the moment it fires, whether or not anyone traded it and
whatever became of it (lapsed, reversed, traded), until the horizon or the square-off
time. The first of target or stop to be touched is the result; the best and worst prices
keep being followed to the end, so a stop that was hit just before a run to the target
shows up as exactly that.

Time comes from tick timestamps and the caller's `tick(now)`, never the wall clock, so a
day replayed at any speed scores the same as it did live.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import astuple, dataclass, fields, replace
from datetime import datetime
from typing import Any, Literal

from tradedisha.clock import IST, ist_to_ms, ms_to_ist
from tradedisha.engine.signals import Signal, SignalStore
from tradedisha.feed.bus import StampedTick
from tradedisha.parameters.model import ParameterSet

Result = Literal["open", "target", "stop", "neither"]

MINUTE_MS = 60_000
PRE_MOVE_MINUTES = 10
CHECKPOINTS = (("px_1m", 1), ("px_5m", 5), ("px_15m", 15))


@dataclass(frozen=True)
class Outcome:
    signal_id: str
    end_ts: int
    result: Result
    result_ts: int | None
    best_price: float
    best_ts: int
    worst_price: float
    worst_ts: int
    px_1m: float | None = None
    px_5m: float | None = None
    px_15m: float | None = None
    spot_at_fire: float | None = None
    spot_pre_move: float | None = None
    spot_best_move: float | None = None
    final: bool = False

    @property
    def late_share(self) -> float | None:
        """Share of the whole favourable spot move that had already happened at firing."""
        if self.spot_pre_move is None or self.spot_best_move is None:
            return None
        before, after = max(self.spot_pre_move, 0.0), max(self.spot_best_move, 0.0)
        return before / (before + after) if before + after > 0 else None


_COLS = [f.name for f in fields(Outcome)]


class OutcomeStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, o: Outcome) -> None:
        with self._conn:
            self._conn.execute(
                f"INSERT OR REPLACE INTO signal_outcomes ({', '.join(_COLS)})"
                f" VALUES ({', '.join('?' * len(_COLS))})",
                astuple(o),
            )

    def get(self, signal_id: str) -> Outcome | None:
        r = self._conn.execute(
            f"SELECT {', '.join(_COLS)} FROM signal_outcomes WHERE signal_id = ?", (signal_id,)
        ).fetchone()
        return self._row(r) if r else None

    def unfinished(self) -> list[Outcome]:
        sql = f"SELECT {', '.join(_COLS)} FROM signal_outcomes WHERE final = 0"
        return [self._row(r) for r in self._conn.execute(sql)]

    def for_signals(self, signals: Iterable[Signal]) -> dict[str, Outcome]:
        out: dict[str, Outcome] = {}
        for s in signals:
            o = self.get(s.id)
            if o is not None:
                out[s.id] = o
        return out

    @staticmethod
    def _row(r: sqlite3.Row) -> Outcome:
        return Outcome(**{**{c: r[c] for c in _COLS}, "final": bool(r["final"])})


@dataclass
class _Tracked:
    signal: Signal
    outcome: Outcome
    last_ltp: float | None
    dirty: bool = False


class OutcomeTracker:
    def __init__(
        self,
        *,
        params: Callable[[], ParameterSet],
        conn: sqlite3.Connection,
        spot_keys: dict[str, str],
        spot_before: Callable[[str, int], float | None],
        on_outcome: Callable[[Outcome], None] | None = None,
    ) -> None:
        self._params = params
        self.store = OutcomeStore(conn)
        self._spot_keys = spot_keys
        self._index_of_spot = {key: index for index, key in spot_keys.items()}
        self._spot_before = spot_before
        self._on_outcome = on_outcome
        self._spot: dict[str, float] = {}  # index -> last spot seen
        self._open: dict[str, _Tracked] = {}
        signals = SignalStore(conn)
        for o in self.store.unfinished():
            s = signals.get(o.signal_id)
            if s is not None:
                # The price while we were down is unknown; marks wait for the next tick.
                self._open[s.id] = _Tracked(s, o, None)

    # -- inputs ----------------------------------------------------------------

    def on_signal(self, s: Signal) -> None:
        """Start following a newly fired signal. Later status changes do not matter here."""
        if s.status != "active" or s.id in self._open or self.store.get(s.id) is not None:
            return
        spot = self._spot.get(s.index)
        before = self._spot_before(s.index, s.ts_fired - PRE_MOVE_MINUTES * MINUTE_MS)
        sign = _sign(s)
        o = Outcome(
            signal_id=s.id,
            end_ts=self._end_ts(s),
            result="open",
            result_ts=None,
            best_price=s.entry_price,
            best_ts=s.ts_fired,
            worst_price=s.entry_price,
            worst_ts=s.ts_fired,
            spot_at_fire=spot,
            spot_pre_move=(
                round(sign * (spot - before), 2)
                if spot is not None and before is not None
                else None
            ),
            spot_best_move=0.0 if spot is not None else None,
        )
        self._open[s.id] = _Tracked(s, o, s.entry_price)
        self._publish(self._open[s.id])

    def on_tick(self, st: StampedTick) -> None:
        t = st.tick
        index = self._index_of_spot.get(t.key)
        if index is not None:
            self._spot[index] = t.ltp
        if not self._open:
            return
        self._advance(t.ts)
        for tr in self._open.values():
            if t.ts < tr.signal.ts_fired:
                continue
            if t.key == tr.signal.instrument_key:
                self._price(tr, t.ltp, t.ts)
            elif index == tr.signal.index:
                self._spot_move(tr, t.ltp)

    def tick(self, now_ms: int) -> None:
        """Time passing without ticks: marks, horizon ends, and saving what has moved."""
        self._advance(now_ms)
        self.flush()

    def flush(self) -> None:
        for tr in self._open.values():
            if tr.dirty:
                self.store.upsert(tr.outcome)
                tr.dirty = False

    def get(self, signal_id: str) -> Outcome | None:
        tr = self._open.get(signal_id)
        return tr.outcome if tr is not None else self.store.get(signal_id)

    # -- rules -----------------------------------------------------------------

    def _end_ts(self, s: Signal) -> int:
        p = self._params()
        fired = ms_to_ist(s.ts_fired)
        square_off = ist_to_ms(datetime.combine(fired.date(), p.paper.square_off_time, tzinfo=IST))
        horizon = s.ts_fired + p.signal.outcome_horizon_minutes * MINUTE_MS
        return min(horizon, square_off) if square_off > s.ts_fired else horizon

    def _advance(self, now: int) -> None:
        for tr in list(self._open.values()):
            o = tr.outcome
            marks: dict[str, Any] = {}
            for name, minutes in CHECKPOINTS:
                due = tr.signal.ts_fired + minutes * MINUTE_MS
                if (
                    tr.last_ltp is not None
                    and getattr(o, name) is None
                    and due <= min(now, o.end_ts)
                ):
                    marks[name] = tr.last_ltp
            if marks:
                tr.outcome = o = replace(o, **marks)
                tr.dirty = True
            if now >= o.end_ts:
                if o.result == "open":
                    o = replace(o, result="neither", result_ts=o.end_ts)
                tr.outcome = replace(o, final=True)
                del self._open[tr.signal.id]
                self._publish(tr)

    def _price(self, tr: _Tracked, ltp: float, ts: int) -> None:
        o = tr.outcome
        tr.last_ltp = ltp
        if ltp > o.best_price:
            o = replace(o, best_price=ltp, best_ts=ts)
        if ltp < o.worst_price:
            o = replace(o, worst_price=ltp, worst_ts=ts)
        resolved = False
        if o.result == "open":
            if ltp >= tr.signal.target_price:
                o, resolved = replace(o, result="target", result_ts=ts), True
            elif ltp <= tr.signal.stop_price:
                o, resolved = replace(o, result="stop", result_ts=ts), True
        if o is not tr.outcome:
            tr.outcome = o
            tr.dirty = True
        if resolved:
            self._publish(tr)

    def _spot_move(self, tr: _Tracked, spot: float) -> None:
        o = tr.outcome
        if o.spot_at_fire is None or o.spot_best_move is None:
            return
        move = round(_sign(tr.signal) * (spot - o.spot_at_fire), 2)
        if move > o.spot_best_move:
            tr.outcome = replace(o, spot_best_move=move)
            tr.dirty = True

    def _publish(self, tr: _Tracked) -> None:
        self.store.upsert(tr.outcome)
        tr.dirty = False
        if self._on_outcome:
            self._on_outcome(tr.outcome)


def _sign(s: Signal) -> float:
    return 1.0 if s.direction == "BUY_CE" else -1.0


# -- scorecard -----------------------------------------------------------------


@dataclass(frozen=True)
class ScoreRow:
    rule: str  # the entry rule that fired these signals: minute_close | trigger
    shadow: bool  # fired by the rule that was not live at the time
    scope: str  # "all" or an index
    signals: int
    scored: int  # those with a result; the rates and averages are over these
    target_pct: float | None
    stop_pct: float | None
    neither_pct: float | None
    avg_best_pct: float | None  # best option price reached, as % over the entry price
    avg_worst_pct: float | None
    avg_late_share: float | None  # 0 = fired at the start of the move, 1 = at its end


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _score(
    rule: str, shadow: bool, scope: str, signals: list[Signal], outcomes: dict[str, Outcome]
) -> ScoreRow:
    done = [(s, o) for s in signals if (o := outcomes.get(s.id)) and o.result != "open"]

    def rate(result: Result) -> float | None:
        if not done:
            return None
        return round(100 * sum(1 for _, o in done if o.result == result) / len(done), 1)

    return ScoreRow(
        rule=rule,
        shadow=shadow,
        scope=scope,
        signals=len(signals),
        scored=len(done),
        target_pct=rate("target"),
        stop_pct=rate("stop"),
        neither_pct=rate("neither"),
        avg_best_pct=_mean([(o.best_price / s.entry_price - 1) * 100 for s, o in done]),
        avg_worst_pct=_mean([(o.worst_price / s.entry_price - 1) * 100 for s, o in done]),
        avg_late_share=_mean([o.late_share for _, o in done if o.late_share is not None]),
    )


def scorecard(signals: list[Signal], outcomes: dict[str, Outcome]) -> list[ScoreRow]:
    """Per entry rule, live rules first: one row for everything, then one per index."""
    rows: list[ScoreRow] = []
    for shadow, rule in sorted({(s.shadow, s.entry_mode) for s in signals}):
        group = [s for s in signals if s.shadow == shadow and s.entry_mode == rule]
        rows.append(_score(rule, shadow, "all", group, outcomes))
        for index in sorted({s.index for s in group}, reverse=True):
            rows.append(
                _score(rule, shadow, index, [s for s in group if s.index == index], outcomes)
            )
    return rows

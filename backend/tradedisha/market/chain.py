"""In-memory option chain for one index, with the derived values the dashboard shows.

Everything here is incremental per tick and pure with respect to time: the caller tells
the chain when a minute has closed. Spec §7.2.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from tradedisha.feed.provider import Tick
from tradedisha.instruments.models import ResolvedIndex

BuildUp = Literal["long_buildup", "short_buildup", "short_covering", "long_unwinding", "none"]


def classify_buildup(d_price: float, d_oi: float) -> BuildUp:
    """Standard OI reading from the signs of price and OI change over a period."""
    if d_price == 0 or d_oi == 0:
        return "none"
    if d_price > 0:
        return "long_buildup" if d_oi > 0 else "short_covering"
    return "short_buildup" if d_oi > 0 else "long_unwinding"


@dataclass
class LegState:
    key: str
    ltp: float | None = None
    open_ltp: float | None = None  # first LTP seen this session
    oi: int | None = None
    oi_open: int | None = None  # first OI seen this session (or backfilled)
    oi_prev_min: int | None = None
    ltp_prev_min: float | None = None
    iv: float | None = None
    delta: float | None = None
    volume: int | None = None
    last_ts: int | None = None
    buildup: BuildUp = "none"

    def apply(self, t: Tick) -> None:
        self.ltp = t.ltp
        if self.open_ltp is None:
            self.open_ltp = t.ltp
        if t.oi is not None:
            self.oi = t.oi
            if self.oi_open is None:
                self.oi_open = t.oi
        if t.iv is not None:
            self.iv = t.iv
        if t.delta is not None:
            self.delta = t.delta
        if t.volume is not None:
            self.volume = t.volume
        self.last_ts = t.ts

    @property
    def chg_pct(self) -> float | None:
        if self.ltp is None or not self.open_ltp:
            return None
        return (self.ltp - self.open_ltp) / self.open_ltp * 100

    @property
    def oi_chg_open(self) -> int | None:
        if self.oi is None or self.oi_open is None:
            return None
        return self.oi - self.oi_open

    @property
    def oi_chg_min(self) -> int | None:
        if self.oi is None or self.oi_prev_min is None:
            return None
        return self.oi - self.oi_prev_min

    def close_minute(self) -> None:
        d_price = (self.ltp or 0) - (
            self.ltp_prev_min if self.ltp_prev_min is not None else (self.ltp or 0)
        )
        d_oi = (self.oi or 0) - (
            self.oi_prev_min if self.oi_prev_min is not None else (self.oi or 0)
        )
        self.buildup = classify_buildup(d_price, d_oi)
        self.ltp_prev_min = self.ltp
        self.oi_prev_min = self.oi


@dataclass
class StrikeRow:
    strike: float
    ce: LegState
    pe: LegState


@dataclass(frozen=True)
class ChainDerived:
    atm: float
    pcr: float | None
    max_pain: float | None
    total_ce_oi: int
    total_pe_oi: int
    oi_baseline: Literal["session_open", "partial"]
    updated_ts: int | None


@dataclass(frozen=True)
class ChainSnapshotMinute:
    minute_ts: int
    atm: float
    pcr: float | None
    max_pain: float | None


@dataclass
class ChainState:
    index: str
    expiry: date
    step: float
    rows: dict[float, StrikeRow] = field(default_factory=dict)
    atm: float = 0.0
    spot: float | None = None
    history: deque[ChainSnapshotMinute] = field(default_factory=lambda: deque(maxlen=60))
    oi_baseline: Literal["session_open", "partial"] = "session_open"
    updated_ts: int | None = None
    _by_key: dict[str, tuple[float, str]] = field(default_factory=dict, repr=False)

    # -- construction / window changes -----------------------------------

    @classmethod
    def from_resolved(cls, r: ResolvedIndex) -> ChainState:
        c = cls(index=r.index, expiry=r.options_expiry, step=r.strike_step, atm=r.atm)
        c.set_window(r)
        return c

    def set_window(self, r: ResolvedIndex) -> None:
        """Adopt a (re-centred) strike window, keeping state for strikes that remain."""
        keep: dict[float, StrikeRow] = {}
        for pair in r.strikes:
            row = self.rows.get(pair.strike)
            if row is None:
                row = StrikeRow(
                    strike=pair.strike,
                    ce=LegState(pair.ce.instrument_key),
                    pe=LegState(pair.pe.instrument_key),
                )
            keep[pair.strike] = row
        self.rows = dict(sorted(keep.items()))
        self._by_key = {}
        for row in self.rows.values():
            self._by_key[row.ce.key] = (row.strike, "ce")
            self._by_key[row.pe.key] = (row.strike, "pe")
        self.atm = r.atm

    def keys(self) -> list[str]:
        return list(self._by_key)

    @property
    def key_set(self) -> dict[str, tuple[float, str]]:
        return self._by_key

    # -- ticks -----------------------------------------------------------

    def apply(self, t: Tick) -> bool:
        """Apply an option tick. Returns False if the key is not in this chain."""
        hit = self._by_key.get(t.key)
        if hit is None:
            return False
        strike, side = hit
        row = self.rows[strike]
        (row.ce if side == "ce" else row.pe).apply(t)
        self.updated_ts = t.ts
        return True

    def set_spot(self, spot: float) -> None:
        self.spot = spot

    def close_minute(self, minute_ts: int) -> ChainSnapshotMinute:
        for row in self.rows.values():
            row.ce.close_minute()
            row.pe.close_minute()
        snap = ChainSnapshotMinute(minute_ts, self.atm, self.pcr(), self.max_pain())
        self.history.append(snap)
        return snap

    # -- derived values --------------------------------------------------

    def strikes_within(self, n: int) -> list[StrikeRow]:
        lo, hi = self.atm - n * self.step, self.atm + n * self.step
        return [r for s, r in self.rows.items() if lo - 1e-9 <= s <= hi + 1e-9]

    def pcr(self, strike_range: int = 5) -> float | None:
        rows = self.strikes_within(strike_range)
        ce = sum(r.ce.oi or 0 for r in rows)
        pe = sum(r.pe.oi or 0 for r in rows)
        return None if ce == 0 else round(pe / ce, 3)

    def max_pain(self) -> float | None:
        """Strike at which total option-buyer payout is lowest."""
        rows = [r for r in self.rows.values() if r.ce.oi is not None or r.pe.oi is not None]
        if not rows:
            return None
        best: tuple[float, float] | None = None
        for cand in rows:
            k = cand.strike
            payout = 0.0
            for r in rows:
                payout += (r.ce.oi or 0) * max(0.0, k - r.strike)
                payout += (r.pe.oi or 0) * max(0.0, r.strike - k)
            if best is None or payout < best[1]:
                best = (k, payout)
        return best[0] if best else None

    def derived(self) -> ChainDerived:
        return ChainDerived(
            atm=self.atm,
            pcr=self.pcr(),
            max_pain=self.max_pain(),
            total_ce_oi=sum(r.ce.oi or 0 for r in self.rows.values()),
            total_pe_oi=sum(r.pe.oi or 0 for r in self.rows.values()),
            oi_baseline=self.oi_baseline,
            updated_ts=self.updated_ts,
        )

    def max_abs_oi_chg(self) -> int:
        return max(
            (abs(v) for r in self.rows.values() for v in (r.ce.oi_chg_open, r.pe.oi_chg_open) if v),
            default=0,
        )

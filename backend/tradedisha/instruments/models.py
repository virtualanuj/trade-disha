"""Instrument records and the resolved subscription set for one index."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

InstrumentType = Literal["INDEX", "FUT", "CE", "PE"]


@dataclass(frozen=True, slots=True)
class Instrument:
    instrument_key: str
    trading_symbol: str
    exchange: str
    segment: str
    name: str  # underlying name, e.g. NIFTY, BANKNIFTY
    instrument_type: InstrumentType
    expiry: date | None
    strike: float | None
    lot_size: int
    tick_size: float


@dataclass(frozen=True, slots=True)
class StrikePair:
    strike: float
    ce: Instrument
    pe: Instrument


@dataclass(frozen=True, slots=True)
class ResolvedIndex:
    index: str
    spot: Instrument
    future: Instrument
    options_expiry: date
    is_expiry_day: bool
    strike_step: float
    atm: float
    strikes: tuple[StrikePair, ...]
    lot_size: int

    @property
    def all_keys(self) -> list[str]:
        keys = [self.spot.instrument_key, self.future.instrument_key]
        for pair in self.strikes:
            keys.append(pair.ce.instrument_key)
            keys.append(pair.pe.instrument_key)
        return keys

    @property
    def option_keys(self) -> list[str]:
        return [
            k for pair in self.strikes for k in (pair.ce.instrument_key, pair.pe.instrument_key)
        ]

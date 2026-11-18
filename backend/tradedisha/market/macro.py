"""Macro data: the dollar (through NSE currency futures) and MCX crude. Spec §6.8.

Read by the macro group of the index and bullion bias (spec §8.6). Like bullion these are
side markets: their ticks have their own candle builder and never reach the shared one
(which drives the index bias) or index liveness, and they are recorded with the MCX ticks
in `bullion_ticks` (currency trades to 17:00, crude to 23:30). Gold and silver are read
from the bullion tracker, not subscribed twice. Loading never stops the index feed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import httpx

from tradedisha.feed.bus import StampedTick
from tradedisha.indicators.macro import MacroSeries, align_closes, dollar_index_proxy
from tradedisha.instruments.models import Instrument
from tradedisha.instruments.resolve import resolve_commodity_months
from tradedisha.instruments.upstox_master import (
    load_currency_master,
    load_mcx_master,
    master_path,
    mcx_master_path,
    read_commodities,
    read_currency_futures,
)
from tradedisha.market.backfill import fetch_intraday_candles
from tradedisha.market.bullion import BullionTracker
from tradedisha.market.candles import MINUTE_MS, Candle, CandleBuilder

log = logging.getLogger(__name__)

# macro name -> Upstox underlying symbol
CURRENCIES: dict[str, str] = {
    "usdinr": "USDINR",
    "eurinr": "EURINR",
    "gbpinr": "GBPINR",
    "jpyinr": "JPYINR",
}
COMMODITIES: dict[str, str] = {"crude": "CRUDEOIL"}
DOLLAR_LEGS = ("usdinr", "eurinr", "gbpinr", "jpyinr")
METAL_NAMES = {"gold": "GOLD", "silver": "SILVER"}
CANDLE_HISTORY = 900  # minutes: crude runs 09:00 to 23:30


class MacroTracker:
    """Latest tick time and 1-minute candles of each macro contract (near month)."""

    def __init__(self, contracts: dict[str, Instrument]) -> None:
        self.contracts = contracts
        self.candles = CandleBuilder(max_history=CANDLE_HISTORY)
        self._name_of = {c.instrument_key: n for n, c in contracts.items()}
        self.keys: frozenset[str] = frozenset(self._name_of)
        self._last_ts: dict[str, int] = {}

    def on_tick(self, st: StampedTick) -> None:
        t = st.tick
        name = self._name_of.get(t.key)
        if name is None:
            return
        if t.ts > self._last_ts.get(name, 0):
            self._last_ts[name] = t.ts
        self.candles.apply(t)

    def seed(self, name: str, candles: list[Candle]) -> None:
        self.candles.seed(self.contracts[name].instrument_key, candles)

    def last_tick_ts(self, name: str) -> int | None:
        return self._last_ts.get(name)

    def minute_closes(self, name: str, upto_minute_ts: int) -> list[tuple[int, float]]:
        c = self.contracts.get(name)
        return [] if c is None else _minute_closes(self.candles, c.instrument_key, upto_minute_ts)


def _minute_closes(
    builder: CandleBuilder, key: str, upto_minute_ts: int
) -> list[tuple[int, float]]:
    """(minute, close) up to and including `upto_minute_ts`, the forming minute too."""
    out = [(c.minute_ts, c.close) for c in builder.closed(key) if c.minute_ts <= upto_minute_ts]
    forming = builder.current(key)
    if forming is not None and forming.minute_ts <= upto_minute_ts:
        if out and out[-1][0] == forming.minute_ts:
            out[-1] = (forming.minute_ts, forming.close)
        else:
            out.append((forming.minute_ts, forming.close))
    return out


def build_view(
    macro: MacroTracker | None,
    bullion: BullionTracker | None,
    *,
    upto_minute_ts: int,
    now_ms: int,
    max_age_ms: int,
) -> dict[str, MacroSeries]:
    """The evidence each macro indicator reads, as of `upto_minute_ts`.

    Names: usdinr, crude, dollar (the proxy, once all four currencies have ticked), gold and
    silver (from the bullion tracker). A name with no price yet is left out.
    """

    def fresh(ts: int | None) -> bool:
        return ts is not None and now_ms - ts <= max_age_ms

    view: dict[str, MacroSeries] = {}
    if macro is not None:
        for name in ("usdinr", "crude"):
            closes = macro.minute_closes(name, upto_minute_ts)
            if closes:
                view[name] = MacroSeries(
                    tuple(c for _, c in closes), fresh(macro.last_tick_ts(name))
                )
        rows = align_closes([macro.minute_closes(n, upto_minute_ts) for n in DOLLAR_LEGS])
        if rows:
            view["dollar"] = MacroSeries(
                tuple(dollar_index_proxy(*r) for r in rows),
                all(fresh(macro.last_tick_ts(n)) for n in DOLLAR_LEGS),
            )
    if bullion is not None:
        for name, metal in METAL_NAMES.items():
            if metal not in bullion.contracts:
                continue
            closes = _minute_closes(bullion.candles, bullion.near_key(metal), upto_minute_ts)
            last = bullion.ltp(metal)
            if closes:
                view[name] = MacroSeries(
                    tuple(c for _, c in closes), fresh(last.ts if last else None)
                )
    return view


# -- start ------------------------------------------------------------------------


def macro_contracts_from(
    currencies: Iterable[Instrument], commodities: Iterable[Instrument], today: date
) -> dict[str, Instrument]:
    """Macro name -> its near-month future; a name without one is left out (logged)."""
    master = [*currencies, *commodities]
    out: dict[str, Instrument] = {}
    for name, symbol in {**CURRENCIES, **COMMODITIES}.items():
        months = resolve_commodity_months(master, symbol, today)
        if months is None:
            log.warning("no %s future after %s: macro %s left out", symbol, today, name)
        else:
            out[name] = months[0]
    return out


async def load_macro_contracts(
    data_dir: Path, today: date, *, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, Instrument]:
    """Live: today's contracts, downloading the instrument files if needed. Never raises."""
    currencies: list[Instrument] = []
    commodities: list[Instrument] = []
    try:
        currencies = await load_currency_master(
            data_dir, today, CURRENCIES.values(), transport=transport
        )
    except Exception as exc:
        log.warning("NSE currency futures unavailable: %s", type(exc).__name__)
    try:
        commodities = await load_mcx_master(
            data_dir, today, COMMODITIES.values(), transport=transport
        )
    except Exception as exc:
        log.warning("MCX crude unavailable: %s", type(exc).__name__)
    return macro_contracts_from(currencies, commodities, today)


async def recorded_macro_contracts(data_dir: Path, day: date) -> dict[str, Instrument]:
    """Replay: that day's contracts from its cached instrument files; no network."""
    currencies: list[Instrument] = []
    commodities: list[Instrument] = []
    nse, mcx = master_path(data_dir, day), mcx_master_path(data_dir, day)
    if await asyncio.to_thread(nse.exists):
        currencies = await asyncio.to_thread(read_currency_futures, nse, CURRENCIES.values())
    if await asyncio.to_thread(mcx.exists):
        commodities = await asyncio.to_thread(read_commodities, mcx, COMMODITIES.values())
    return macro_contracts_from(currencies, commodities, day)


async def backfill(
    client: httpx.AsyncClient, token: str, tracker: MacroTracker, now_ms: int
) -> None:
    """Today's closed 1-minute candles of each contract, so the window is full at once."""
    this_minute = now_ms - now_ms % MINUTE_MS
    for name, c in tracker.contracts.items():
        try:
            got = await fetch_intraday_candles(
                client, token, c.instrument_key, before_ms=this_minute
            )
        except Exception as exc:
            log.warning("macro candle backfill failed for %s: %s", name, type(exc).__name__)
            continue
        tracker.seed(name, got)

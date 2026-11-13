"""The real instrument master: Upstox's daily file of everything tradable on NSE (spec §5.1).

The file is public (no login). It is downloaded once per day into the data folder and kept,
so a recorded session can later be replayed against the instruments of its own day.
"""

from __future__ import annotations

import asyncio
import gzip
import json
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path
from typing import Any, cast

import httpx

from tradedisha.clock import ms_to_ist
from tradedisha.instruments.models import Instrument, InstrumentType
from tradedisha.instruments.resolve import INDEX_SPOT_NAMES

MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
PAISE = 100.0  # the master quotes tick size in paise


def master_path(data_dir: Path, day: date) -> Path:
    return data_dir / f"instruments-{day.isoformat()}.json.gz"


def parse_master(records: Iterable[Mapping[str, Any]], indices: Iterable[str]) -> list[Instrument]:
    """Keep the spot index plus the futures and options of each wanted index."""
    wanted = set(indices)
    spot_names = {INDEX_SPOT_NAMES.get(i, i) for i in wanted}
    out: list[Instrument] = []
    for r in records:
        segment = r.get("segment")
        kind = r.get("instrument_type")
        if segment == "NSE_INDEX" and kind == "INDEX" and r.get("name") in spot_names:
            out.append(
                Instrument(
                    instrument_key=str(r["instrument_key"]),
                    trading_symbol=str(r.get("trading_symbol", r["name"])),
                    exchange="NSE",
                    segment="NSE_INDEX",
                    name=str(r["name"]),
                    instrument_type="INDEX",
                    expiry=None,
                    strike=None,
                    lot_size=1,
                    tick_size=0.05,
                )
            )
        elif (
            segment == "NSE_FO"
            and kind in ("FUT", "CE", "PE")
            and r.get("underlying_symbol") in wanted
            and r.get("expiry")
        ):
            out.append(
                Instrument(
                    instrument_key=str(r["instrument_key"]),
                    trading_symbol=str(r["trading_symbol"]),
                    exchange="NSE",
                    segment="NSE_FO",
                    name=str(r["underlying_symbol"]),
                    instrument_type=cast(InstrumentType, kind),
                    expiry=ms_to_ist(int(r["expiry"])).date(),
                    strike=None if kind == "FUT" else float(r["strike_price"]),
                    lot_size=int(r["lot_size"]),
                    tick_size=float(r.get("tick_size", 5.0)) / PAISE,
                )
            )
    return out


def read_master(path: Path, indices: Iterable[str]) -> list[Instrument]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return parse_master(json.load(fh), indices)


async def load_upstox_master(
    data_dir: Path,
    day: date,
    indices: Iterable[str],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[Instrument]:
    """Today's master, downloading it first if this is the first start of the day."""
    path = master_path(data_dir, day)
    if not path.exists():
        async with httpx.AsyncClient(
            transport=transport, timeout=60, follow_redirects=True
        ) as client:
            resp = await client.get(MASTER_URL)
            resp.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(resp.content)
        tmp.replace(path)  # never leave a half-written file to be trusted tomorrow
    return await asyncio.to_thread(read_master, path, list(indices))

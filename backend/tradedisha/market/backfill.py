"""What the app missed by starting after the market opened. Spec §6.5.

Two things are fetched from Upstox REST: today's 1-minute candles for spot and futures, so
EMA/VWAP/supertrend have history at once, and the option-chain snapshot, whose previous
close OI is the baseline for "OI change since open".
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from tradedisha.feed.upstox import Unauthorized
from tradedisha.market.candles import MINUTE_MS, Candle
from tradedisha.market.chain import ChainState

log = logging.getLogger(__name__)

INTRADAY_URL = "https://api.upstox.com/v3/historical-candle/intraday/{key}/minutes/1"
CHAIN_URL = "https://api.upstox.com/v2/option/chain"
DAILY_URL = "https://api.upstox.com/v3/historical-candle/{key}/days/1/{to}/{frm}"
YEAR_DAYS = 365


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _check(resp: httpx.Response, what: str) -> Any:  # noqa: ANN401 - decoded JSON
    if resp.status_code == 401:
        raise Unauthorized(f"{what} rejected")
    resp.raise_for_status()
    return resp.json().get("data")


# -- candles ----------------------------------------------------------------------


def parse_candles(key: str, rows: Iterable[list[Any]], *, before_ms: int) -> list[Candle]:
    """Upstox rows `[iso time, o, h, l, c, volume, oi]` -> closed candles, oldest first.

    The minute still in progress (`>= before_ms`) is left for the live feed to build.
    """
    out: list[Candle] = []
    for row in rows:
        minute = int(datetime.fromisoformat(str(row[0])).timestamp() * 1000)
        minute -= minute % MINUTE_MS
        if minute >= before_ms:
            continue
        out.append(
            Candle(
                key,
                minute,
                float(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                int(row[5] or 0),
            )
        )
    out.sort(key=lambda c: c.minute_ts)
    return out


async def fetch_intraday_candles(
    client: httpx.AsyncClient, token: str, key: str, *, before_ms: int
) -> list[Candle]:
    url = INTRADAY_URL.format(key=quote(key, safe=""))
    data = _check(await client.get(url, headers=_bearer(token)), "candle request")
    return parse_candles(key, (data or {}).get("candles") or [], before_ms=before_ms)


def parse_range(rows: Iterable[list[Any]]) -> tuple[float, float] | None:
    """(highest high, lowest low) over daily candle rows `[time, o, h, l, c, ...]`."""
    highs: list[float] = []
    lows: list[float] = []
    for row in rows:
        high, low = float(row[2]), float(row[3])
        if high > 0 and low > 0:
            highs.append(high)
            lows.append(low)
    return (max(highs), min(lows)) if highs else None


async def fetch_52w_range(
    client: httpx.AsyncClient, token: str, key: str, today: date
) -> tuple[float, float] | None:
    """The 52-week high and low up to yesterday, from a year of daily candles."""
    url = DAILY_URL.format(
        key=quote(key, safe=""),
        to=(today - timedelta(days=1)).isoformat(),
        frm=(today - timedelta(days=YEAR_DAYS)).isoformat(),
    )
    data = _check(await client.get(url, headers=_bearer(token)), "daily candle request")
    return parse_range((data or {}).get("candles") or [])


# -- option chain -----------------------------------------------------------------


@dataclass(frozen=True)
class OptionSnapshot:
    key: str
    oi: int | None
    prev_oi: int | None  # open interest at the previous close: today's baseline


def _side(leg: Mapping[str, Any] | None) -> OptionSnapshot | None:
    if not leg or not leg.get("instrument_key"):
        return None
    md = leg.get("market_data") or {}

    def whole(name: str) -> int | None:
        v = md.get(name)
        return int(v) if isinstance(v, int | float) and v >= 0 else None

    return OptionSnapshot(str(leg["instrument_key"]), whole("oi"), whole("prev_oi"))


def parse_chain(rows: Iterable[Mapping[str, Any]]) -> dict[str, OptionSnapshot]:
    out: dict[str, OptionSnapshot] = {}
    for row in rows:
        for name in ("call_options", "put_options"):
            snap = _side(row.get(name))
            if snap is not None:
                out[snap.key] = snap
    return out


async def fetch_option_chain(
    client: httpx.AsyncClient, token: str, underlying_key: str, expiry: date
) -> dict[str, OptionSnapshot]:
    resp = await client.get(
        CHAIN_URL,
        params={"instrument_key": underlying_key, "expiry_date": expiry.isoformat()},
        headers=_bearer(token),
    )
    return parse_chain(_check(resp, "option-chain request") or [])


def apply_baseline(
    chain: ChainState, snaps: Mapping[str, OptionSnapshot], *, only: set[str] | None = None
) -> int:
    """Set opening OI on the chain's legs from a snapshot. Returns how many legs were set.

    The chain is marked `session_open` only when every leg in the window has a baseline.
    """
    done = 0
    for key in chain.key_set:
        if only is not None and key not in only:
            continue
        snap = snaps.get(key)
        if snap is None or snap.prev_oi is None:
            continue
        chain.set_baseline(key, snap.prev_oi, snap.oi)
        done += 1
    chain.oi_baseline = "session_open" if chain.all_baselined() else "partial"
    return done

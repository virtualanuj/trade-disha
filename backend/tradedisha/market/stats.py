"""Day statistics for one index, for the details view. Spec §7.4.

Display only: no indicator, signal or paper trade reads these.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from tradedisha.config import Settings
from tradedisha.market.candles import Candle

VIX_KEY = "NSE_INDEX|India VIX"
SENSEX_KEY = "BSE_INDEX|SENSEX"
SECTOR_PREFIX = "Nifty "
# The rates strip's quotes that no other view carries (Milestone E22): name -> key.
STRIP_QUOTES: tuple[tuple[str, str], ...] = (("SENSEX", SENSEX_KEY),)


@dataclass(frozen=True)
class SectorQuote:
    """A sector index beside the index it helps explain (Milestone E11)."""

    name: str  # Upstox NSE_INDEX name: "Nifty Fin Service"
    label: str  # shown: "Fin Service"
    ltp: float | None = None
    prev_close: float | None = None
    change: float | None = None  # points
    change_pct: float | None = None


def sector_key(name: str) -> str:
    return f"NSE_INDEX|{name}"


def sector_label(name: str) -> str:
    """The name without its "Nifty " prefix, any case: "Nifty PSU Bank" -> "PSU Bank"."""
    if name.lower().startswith(SECTOR_PREFIX.lower()):
        return name[len(SECTOR_PREFIX) :]
    return name


@dataclass(frozen=True)
class MarketQuote:
    """A market-wide rate on the rates strip, such as SENSEX (Milestone E22). Display only."""

    name: str
    ltp: float | None
    prev_close: float | None
    change: float | None
    change_pct: float | None
    updated_ts: int | None


def market_wide_keys(settings: Settings) -> list[str]:
    """India VIX, every configured sector index and the strip's quotes, each once; none on
    the synthetic feed."""
    if settings.feed_provider == "synthetic":  # the generated market has none of them
        return []
    keys = [VIX_KEY]
    for names in settings.sector_indices.values():
        keys += [k for k in map(sector_key, names) if k not in keys]
    keys += [k for _, k in STRIP_QUOTES if k not in keys]
    return keys


def market_quotes(
    ltp: Mapping[str, float], close_prev: Mapping[str, float], ts: Mapping[str, int]
) -> tuple[MarketQuote, ...]:
    """Each strip quote's price and change on the previous close; unknown ones stay None."""
    out: list[MarketQuote] = []
    for name, key in STRIP_QUOTES:
        price, prev = ltp.get(key), close_prev.get(key)
        change = round(price - prev, 2) if price is not None and prev else None
        out.append(MarketQuote(name, price, prev, change, _pct(price, prev), ts.get(key)))
    return tuple(out)


@dataclass(frozen=True)
class IndexStats:
    index: str
    day_open: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    range_pos: float | None = None  # 0 at the day's low, 1 at the day's high
    prev_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    fut_premium: float | None = None  # futures LTP minus spot LTP
    vix: float | None = None
    vix_change_pct: float | None = None
    updated_ts: int | None = None
    sectors: tuple[SectorQuote, ...] = ()


def _pct(value: float | None, base: float | None) -> float | None:
    if value is None or not base:
        return None
    return round((value - base) / base * 100, 2)


def sector_quotes(
    names: Iterable[str], ltp: Mapping[str, float], close_prev: Mapping[str, float]
) -> tuple[SectorQuote, ...]:
    """Level and change for each sector, in the order given; unknown prices stay None."""
    out: list[SectorQuote] = []
    for name in names:
        key = sector_key(name)
        price, prev = ltp.get(key), close_prev.get(key)
        change = round(price - prev, 2) if price is not None and prev else None
        out.append(SectorQuote(name, sector_label(name), price, prev, change, _pct(price, prev)))
    return tuple(out)


def compute_stats(  # noqa: PLR0913 -- one argument per source of the view
    index: str,
    *,
    spot: float | None,
    fut: float | None,
    prev_close: float | None,
    candles: Iterable[Candle],
    range_52w: tuple[float, float] | None,
    vix: float | None,
    vix_prev_close: float | None,
    updated_ts: int | None,
    sectors: tuple[SectorQuote, ...] = (),
) -> IndexStats:
    """`candles` are today's spot candles in time order, the forming one last.

    `range_52w` is (high, low) for the year up to yesterday; today's extremes widen it, so
    a new 52-week high or low shows the moment it is made.
    """
    day = list(candles)
    day_open = day[0].open if day else None
    day_high = max((c.high for c in day), default=None)
    day_low = min((c.low for c in day), default=None)
    if spot is not None:  # the latest tick may be ahead of the candle being formed
        day_high = spot if day_high is None else max(day_high, spot)
        day_low = spot if day_low is None else min(day_low, spot)

    range_pos = None
    if spot is not None and day_high is not None and day_low is not None and day_high > day_low:
        range_pos = round((spot - day_low) / (day_high - day_low), 4)

    high_52w = low_52w = None
    if range_52w is not None:
        high_52w, low_52w = range_52w
        if day_high is not None:
            high_52w = max(high_52w, day_high)
        if day_low is not None:
            low_52w = min(low_52w, day_low)

    return IndexStats(
        index=index,
        day_open=day_open,
        day_high=day_high,
        day_low=day_low,
        range_pos=range_pos,
        prev_close=prev_close,
        change=round(spot - prev_close, 2) if spot is not None and prev_close else None,
        change_pct=_pct(spot, prev_close),
        high_52w=high_52w,
        low_52w=low_52w,
        fut_premium=round(fut - spot, 2) if fut is not None and spot is not None else None,
        vix=vix,
        vix_change_pct=_pct(vix, vix_prev_close),
        updated_ts=updated_ts,
        sectors=sectors,
    )

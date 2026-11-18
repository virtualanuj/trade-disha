"""Bullion positioning and order flow: futures OI, net volume, the book. Spec §9a.

Bullion has no option chain, so its open-interest and order-flow evidence come from the
near future itself. Open interest and the order book are read from one reading per minute
(the last tick of the minute, kept by the bullion tracker); net volume from the 1-minute
candles, whose trades are signed against the quote (Milestone E8).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from tradedisha.indicators import IndicatorResult, clamp, warming
from tradedisha.market.candles import MINUTE_MS, Candle
from tradedisha.parameters.model import Bullion

# The reading compared against may be this much older than the window (a quiet contract),
# but no more: across a feed gap the change would not be a window's change.
OI_GAP_MINUTES = 5


@dataclass(frozen=True)
class MinuteBook:
    """The near future as it stood at the end of one minute."""

    minute_ts: int
    ltp: float
    oi: int | None
    tbq: int | None  # total buy quantity pending on the exchange
    tsq: int | None
    bid_qty5: int | None  # quantity over the five book levels
    ask_qty5: int | None


def _at_or_before(rows: Sequence[MinuteBook], ts: int) -> MinuteBook | None:
    """The reading in force at `ts`: the last one at or before it. `rows` is in time order."""
    found = None
    for r in rows:
        if r.minute_ts > ts:
            break
        found = r
    return found


def futures_oi_buildup(book: Sequence[MinuteBook], p: Bullion) -> IndicatorResult:
    """Price change against open-interest change over `oi_window_minutes`.

    New positions behind a move (OI up) count fully: long build-up is bullish, short
    build-up bearish. Positions closing (OI down) count `oi_unwind_factor` as much: short
    covering is bullish, long unwinding bearish. Strength is the OI change over
    `oi_full_pct`; a price move under `oi_price_flat_pct` reads nothing.
    """
    name, n = "futures_oi", p.oi_window_minutes
    rows = [r for r in book if r.oi]
    if not rows:
        return warming(name, "oi", n + 1, 0)
    now = rows[-1]
    back = now.minute_ts - n * MINUTE_MS
    then = _at_or_before(rows, back)
    if then is None or not then.oi or then.ltp <= 0:
        return warming(name, "oi", n + 1, (now.minute_ts - rows[0].minute_ts) // MINUTE_MS + 1)
    if back - then.minute_ts > OI_GAP_MINUTES * MINUTE_MS:
        return IndicatorResult(
            name, "oi", 0.0, f"no reading near {n} min back (feed gap)", "warming"
        )
    assert now.oi is not None
    dp = (now.ltp - then.ltp) / then.ltp * 100
    doi = (now.oi - then.oi) / then.oi * 100
    moves = f"price {dp:+.2f}%, OI {doi:+.2f}% in {n} min"
    value = {"price_pct": dp, "oi_pct": doi, "oi": float(now.oi)}
    if abs(dp) < p.oi_price_flat_pct:
        return IndicatorResult(name, "oi", 0.0, f"price flat: {moves}", value=value)
    if doi == 0:
        return IndicatorResult(name, "oi", 0.0, f"OI unchanged: {moves}", value=value)
    up = dp > 0
    if doi > 0:
        kind, factor = ("long build-up" if up else "short build-up"), 1.0
    else:
        kind, factor = ("short covering" if up else "long unwinding"), p.oi_unwind_factor
    strength = clamp(abs(doi) / p.oi_full_pct, 0.0, 1.0)
    score = (1.0 if up else -1.0) * factor * strength
    return IndicatorResult(name, "oi", score, f"{kind}: {moves}", value=value)


def net_volume(candles: Sequence[Candle], p: Bullion) -> IndicatorResult:
    """Buyer- less seller-initiated volume over the last `flow_window_minutes`, as a share of
    all traded volume, over `flow_trades_full`.

    A minute without side information (backfilled at start) cannot be judged, so the vote
    warms until a whole window of live minutes has closed; a quiet minute counts as zero.
    """
    name, n = "net_volume", p.flow_window_minutes
    recent = [c for c in candles[-n:] if c.buy_volume is not None and c.sell_volume is not None]
    if len(recent) < n:
        return warming(name, "flow", n, len(recent))
    buy = sum(c.buy_volume or 0 for c in recent)
    sell = sum(c.sell_volume or 0 for c in recent)
    value = {"buy": float(buy), "sell": float(sell), "minutes": float(n)}
    if buy + sell == 0:
        return IndicatorResult(name, "flow", 0.0, f"no trades in {n} min", value=value)
    ratio = (buy - sell) / (buy + sell)
    value["net_share"] = ratio
    return IndicatorResult(
        name,
        "flow",
        clamp(ratio / p.flow_trades_full),
        f"net {'buying' if ratio >= 0 else 'selling'} {abs(ratio):.0%} of {buy + sell:,} "
        f"traded in {n} min",
        value=value,
    )


def _imbalance(buy: int | None, sell: int | None) -> float | None:
    if buy is None or sell is None or buy + sell <= 0:
        return None
    return (buy - sell) / (buy + sell)


def _book_lean(r: MinuteBook) -> float | None:
    """Mean of the total-quantity and five-level imbalances that have data."""
    parts = [
        x for x in (_imbalance(r.tbq, r.tsq), _imbalance(r.bid_qty5, r.ask_qty5)) if x is not None
    ]
    return sum(parts) / len(parts) if parts else None


def book_imbalance(book: Sequence[MinuteBook], p: Bullion) -> IndicatorResult:
    """The book's lean now against its average over the last `flow_book_minutes` readings.

    MCX books lean to one side for hours (silver's pending sell quantity often runs well
    above its buy quantity), so the raw lean would hold the vote on one side. Only a change
    in the lean counts: `(lean now - average) / flow_book_full`.
    """
    name, n = "book_imbalance", p.flow_book_minutes
    leans = [x for x in (_book_lean(r) for r in book) if x is not None]
    if len(leans) < n:
        return warming(name, "flow", n, len(leans))
    window = leans[-n:]
    now, mean = window[-1], sum(window) / n
    dev = now - mean
    return IndicatorResult(
        name,
        "flow",
        clamp(dev / p.flow_book_full),
        f"book lean {now:+.2f} against {mean:+.2f} over {n} min",
        value={"imbalance": now, "average": mean, "deviation": dev},
    )

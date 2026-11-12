"""Pure functions that pick the instruments TradeDisha subscribes to for one index.

Rules (spec §5.2):
- spot: the index instrument
- future: nearest monthly future with expiry >= today
- options: nearest expiry >= today among that index's options (weekly or monthly, the data
  decides); same-day expiry is included
- strikes: ATM ± window at that expiry, using the strike step inferred from the master
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from datetime import date
from itertools import pairwise

from tradedisha.instruments.models import Instrument, ResolvedIndex, StrikePair

INDEX_SPOT_NAMES: dict[str, str] = {"NIFTY": "Nifty 50", "BANKNIFTY": "Nifty Bank"}


class ResolutionError(RuntimeError):
    """The master lacks something we need."""


def atm_strike(spot: float, step: float) -> float:
    """Nearest strike; exact midpoints round up (not banker's rounding)."""
    return math.floor(spot / step + 0.5) * step


def infer_strike_step(strikes: Iterable[float]) -> float:
    """Most common gap between adjacent distinct strikes."""
    ordered = sorted(set(strikes))
    if len(ordered) < 2:
        raise ResolutionError("cannot infer strike step from fewer than two strikes")
    gaps = Counter(round(b - a, 2) for a, b in pairwise(ordered))
    return gaps.most_common(1)[0][0]


def nearest_expiry(expiries: Iterable[date], today: date) -> date:
    candidates = sorted(e for e in expiries if e >= today)
    if not candidates:
        raise ResolutionError(f"no expiry on or after {today}")
    return candidates[0]


def _find_spot(master: list[Instrument], index: str) -> Instrument:
    wanted = INDEX_SPOT_NAMES.get(index, index)
    for inst in master:
        if inst.instrument_type == "INDEX" and inst.name == wanted:
            return inst
    raise ResolutionError(f"spot instrument for {index} not in master")


def resolve_index(
    master: list[Instrument],
    index: str,
    today: date,
    spot_price: float,
    *,
    strike_window: int,
) -> ResolvedIndex:
    """Select spot, future, expiry and the ATM ± window option pairs for an index."""
    spot = _find_spot(master, index)
    futures = [
        i for i in master if i.name == index and i.instrument_type == "FUT" and i.expiry is not None
    ]
    options = [
        i
        for i in master
        if i.name == index
        and i.instrument_type in ("CE", "PE")
        and i.expiry is not None
        and i.strike is not None
    ]
    if not futures:
        raise ResolutionError(f"no futures for {index}")
    if not options:
        raise ResolutionError(f"no options for {index}")

    fut_expiry = nearest_expiry((f.expiry for f in futures if f.expiry), today)
    future = next(f for f in futures if f.expiry == fut_expiry)

    opt_expiry = nearest_expiry((o.expiry for o in options if o.expiry), today)
    at_expiry = [o for o in options if o.expiry == opt_expiry]
    step = infer_strike_step(o.strike for o in at_expiry if o.strike is not None)
    atm = atm_strike(spot_price, step)

    by_strike: dict[float, dict[str, Instrument]] = {}
    for o in at_expiry:
        assert o.strike is not None
        by_strike.setdefault(o.strike, {})[o.instrument_type] = o

    pairs: list[StrikePair] = []
    for offset in range(-strike_window, strike_window + 1):
        strike = round(atm + offset * step, 2)
        legs = by_strike.get(strike)
        if legs is None or "CE" not in legs or "PE" not in legs:
            continue  # edge of the listed chain; window is simply narrower there
        pairs.append(StrikePair(strike=strike, ce=legs["CE"], pe=legs["PE"]))
    if not pairs:
        raise ResolutionError(f"no complete CE/PE pairs around ATM {atm} for {index}")

    return ResolvedIndex(
        index=index,
        spot=spot,
        future=future,
        options_expiry=opt_expiry,
        is_expiry_day=opt_expiry == today,
        strike_step=step,
        atm=atm,
        strikes=tuple(pairs),
        lot_size=pairs[0].ce.lot_size,
    )


def needs_recenter(current_atm: float, new_atm: float, step: float, recenter_strikes: int) -> bool:
    """True when ATM has moved at least `recenter_strikes` steps from the window centre."""
    return abs(new_atm - current_atm) >= recenter_strikes * step - 1e-9

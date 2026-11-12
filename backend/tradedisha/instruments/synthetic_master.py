"""A generated instrument master for development and tests.

Shapes match what the Upstox master provides, so the resolver is exercised the same way.
Lot sizes and strike steps are the current NSE values; expiry weekdays are a parameter
because NSE has changed them before.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from tradedisha.instruments.models import Instrument, InstrumentType

SPEC: dict[str, dict[str, float | int | str]] = {
    "NIFTY": {"spot_name": "Nifty 50", "step": 50, "lot": 75, "base": 25_000},
    "BANKNIFTY": {"spot_name": "Nifty Bank", "step": 100, "lot": 35, "base": 56_000},
}

TUESDAY = 1


def next_weekdays(start: date, weekday: int, count: int) -> list[date]:
    """`count` dates on or after `start` falling on `weekday` (Mon=0)."""
    first = start + timedelta(days=(weekday - start.weekday()) % 7)
    return [first + timedelta(weeks=i) for i in range(count)]


def last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    last = date(year, month, monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def monthly_expiries(start: date, weekday: int, count: int) -> list[date]:
    """Last `weekday` of each month, on or after `start`, for `count` months."""
    out: list[date] = []
    y, m = start.year, start.month
    while len(out) < count:
        d = last_weekday_of_month(y, m, weekday)
        if d >= start:
            out.append(d)
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _symbol(name: str, expiry: date, strike: float | None, kind: str) -> str:
    exp = expiry.strftime("%d%b%y").upper()
    if strike is None:
        return f"{name}{exp}{kind}"
    return f"{name}{exp}{int(strike)}{kind}"


def build_synthetic_master(
    today: date,
    *,
    strikes_each_side: int = 30,
    weekly_weekday: int = TUESDAY,
) -> list[Instrument]:
    """Spot, three monthly futures, and option chains for both indices."""
    master: list[Instrument] = []
    for name, spec in SPEC.items():
        step = float(spec["step"])
        lot = int(spec["lot"])
        base = float(spec["base"])
        spot_name = str(spec["spot_name"])

        master.append(
            Instrument(
                instrument_key=f"NSE_INDEX|{spot_name}",
                trading_symbol=spot_name,
                exchange="NSE",
                segment="NSE_INDEX",
                name=spot_name,
                instrument_type="INDEX",
                expiry=None,
                strike=None,
                lot_size=1,
                tick_size=0.05,
            )
        )
        for exp in monthly_expiries(today, weekly_weekday, 3):
            sym = _symbol(name, exp, None, "FUT")
            master.append(
                Instrument(
                    instrument_key=f"NSE_FO|{sym}",
                    trading_symbol=sym,
                    exchange="NSE",
                    segment="NSE_FO",
                    name=name,
                    instrument_type="FUT",
                    expiry=exp,
                    strike=None,
                    lot_size=lot,
                    tick_size=0.05,
                )
            )
        if name == "NIFTY":
            expiries = next_weekdays(today, weekly_weekday, 4)
        else:
            expiries = monthly_expiries(today, weekly_weekday, 2)
        centre = round(base / step) * step
        for exp in expiries:
            for i in range(-strikes_each_side, strikes_each_side + 1):
                strike = centre + i * step
                kinds: tuple[InstrumentType, ...] = ("CE", "PE")
                for kind in kinds:
                    sym = _symbol(name, exp, strike, kind)
                    master.append(
                        Instrument(
                            instrument_key=f"NSE_FO|{sym}",
                            trading_symbol=sym,
                            exchange="NSE",
                            segment="NSE_FO",
                            name=name,
                            instrument_type=kind,
                            expiry=exp,
                            strike=strike,
                            lot_size=lot,
                            tick_size=0.05,
                        )
                    )
    return master

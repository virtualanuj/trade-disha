"""Resolved instruments per index."""

from __future__ import annotations

from fastapi import APIRouter

from tradedisha.api.deps import State
from tradedisha.api.schemas import InstrumentOut, ResolvedIndexOut, StrikePairOut
from tradedisha.instruments.models import Instrument, ResolvedIndex

router = APIRouter()


def _inst(i: Instrument) -> InstrumentOut:
    return InstrumentOut(
        instrument_key=i.instrument_key,
        trading_symbol=i.trading_symbol,
        instrument_type=i.instrument_type,
        expiry=i.expiry.isoformat() if i.expiry else None,
        strike=i.strike,
        lot_size=i.lot_size,
    )


def resolved_out(r: ResolvedIndex) -> ResolvedIndexOut:
    return ResolvedIndexOut(
        index=r.index,
        spot=_inst(r.spot),
        future=_inst(r.future),
        options_expiry=r.options_expiry.isoformat(),
        is_expiry_day=r.is_expiry_day,
        strike_step=r.strike_step,
        atm=r.atm,
        lot_size=r.lot_size,
        strikes=[StrikePairOut(strike=p.strike, ce=_inst(p.ce), pe=_inst(p.pe)) for p in r.strikes],
    )


@router.get("/instruments", response_model=list[ResolvedIndexOut])
def instruments(state: State) -> list[ResolvedIndexOut]:
    return [resolved_out(r) for r in state.session.resolved.values()]

"""Option chain snapshot per index."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from tradedisha.api.deps import State
from tradedisha.api.schemas import ChainOut, ChainRowOut, LegOut
from tradedisha.app_state import AppState
from tradedisha.market.chain import ChainState, LegState

router = APIRouter()


def _leg(leg: LegState) -> LegOut:
    return LegOut(
        ltp=leg.ltp,
        chg_pct=None if leg.chg_pct is None else round(leg.chg_pct, 2),
        oi=leg.oi,
        oi_chg_open=leg.oi_chg_open,
        oi_chg_min=leg.oi_chg_min,
        iv=leg.iv,
        buildup=leg.buildup,
    )


def chain_out(c: ChainState) -> ChainOut:
    d = c.derived()
    return ChainOut(
        index=c.index,
        expiry=c.expiry.isoformat(),
        step=c.step,
        atm=d.atm,
        spot=c.spot,
        pcr=d.pcr,
        max_pain=d.max_pain,
        total_ce_oi=d.total_ce_oi,
        total_pe_oi=d.total_pe_oi,
        oi_baseline=d.oi_baseline,
        max_abs_oi_chg=c.max_abs_oi_chg(),
        updated_ts=d.updated_ts,
        rows=[ChainRowOut(strike=r.strike, ce=_leg(r.ce), pe=_leg(r.pe)) for r in c.rows.values()],
    )


def get_chain(state: AppState, index: str) -> ChainState:
    mgr = state.session.chains
    if mgr is None or index not in mgr.chains:
        raise HTTPException(status_code=404, detail=f"unknown index {index}")
    return mgr.chains[index]


@router.get("/chain/{index}", response_model=ChainOut)
def chain(index: str, state: State) -> ChainOut:
    return chain_out(get_chain(state, index.upper()))

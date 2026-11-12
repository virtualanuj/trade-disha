"""Latency metrics: read summaries, accept browser-side samples."""

from __future__ import annotations

from fastapi import APIRouter, Response

from tradedisha.api.deps import State
from tradedisha.api.schemas import ClientLatencyIn, HopOut, MetricsResponse
from tradedisha.metrics.latency import HopSummary

router = APIRouter()

MAX_CLIENT_SAMPLES = 2000


def _out(s: HopSummary) -> HopOut:
    return HopOut(hop=s.hop, n=s.n, p50=s.p50, p95=s.p95, p99=s.p99, max=s.max)


@router.get("/metrics", response_model=MetricsResponse)
def metrics(state: State) -> MetricsResponse:
    return MetricsResponse(
        last_1m=[_out(s) for s in state.latency.summaries(last_ms=60_000)],
        last_15m=[_out(s) for s in state.latency.summaries()],
    )


@router.post("/metrics/client", status_code=204)
def client_metrics(body: ClientLatencyIn, state: State) -> Response:
    for v in body.out_to_recv_ms[:MAX_CLIENT_SAMPLES]:
        state.latency.record("out_to_recv", v)
    for v in body.recv_to_paint_ms[:MAX_CLIENT_SAMPLES]:
        state.latency.record("recv_to_paint", v)
    return Response(status_code=204)

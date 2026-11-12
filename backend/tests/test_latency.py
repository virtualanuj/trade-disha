"""Percentile maths for the latency tracker."""

from tradedisha.metrics.latency import LatencyTracker, percentile


def test_percentile_nearest_rank() -> None:
    vals = [float(i) for i in range(1, 101)]
    assert percentile(vals, 0.50) == 50.0
    assert percentile(vals, 0.95) == 95.0
    assert percentile(vals, 0.99) == 99.0
    assert percentile([], 0.5) == 0.0


def test_tracker_ignores_negative_and_summarises() -> None:
    t = LatencyTracker()
    for v in (5, 10, 15, -3):
        t.record("src_to_in", v)
    s = t.summary("src_to_in")
    assert s.n == 3
    assert s.p50 == 10
    assert s.max == 15
    assert t.summary("in_to_out").n == 0

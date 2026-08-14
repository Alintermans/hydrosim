"""The collector's trace resampler (pure python, no shared memory needed)."""

from collector.__main__ import TRACE_POINTS, resample_trace


def synth_samples(n=400):
    # a clean full lap: spline 0..1, elapsed grows to ~140s, circleish coords
    import math
    out = []
    for i in range(n):
        p = i / (n - 1)
        out.append((p, int(p * 140_000),
                    500 + 300 * math.cos(p * 6.28), 400 + 220 * math.sin(p * 6.28)))
    return out


def test_resample_produces_uniform_points():
    trace = resample_trace(synth_samples())
    assert trace and len(trace["t"]) == TRACE_POINTS
    assert trace["t"] == sorted(trace["t"])          # elapsed is monotonic
    assert trace["t"][0] == 0
    assert trace["t"][-1] < 140_000


def test_resample_refuses_partial_laps():
    partial = [s for s in synth_samples() if s[0] < 0.6]  # out-lap fragment
    assert resample_trace(partial) is None
    assert resample_trace(synth_samples(20)) is None      # too few samples

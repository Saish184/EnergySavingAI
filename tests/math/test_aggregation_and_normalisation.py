"""Mathematical facts about aggregation, weather and size normalisation that any score design must account for.

Classified per test: UNIVERSAL (a mathematical identity) or POLICY (demonstrates the consequence of a design choice).
These tests do not require any particular four-pillar formula.
"""
import math

import numpy as np
import pytest

from mathcore import heating_degree_hours, totals

W = {"Use": 0.40, "Waste": 0.25, "Timing": 0.20, "Health": 0.15}  # documented weights (no code available)


def geo(p, w, floor=0.0):
    return math.prod(max(p[k], floor) ** w[k] for k in w)


def arith(p, w):
    return sum(w[k] * p[k] for k in w)


def test_UNIVERSAL_weighted_geometric_zero_annihilates():
    assert geo({"Use": 95, "Waste": 95, "Timing": 95, "Health": 0}, W) == 0.0
    assert arith({"Use": 95, "Waste": 95, "Timing": 95, "Health": 0}, W) == pytest.approx(80.75)


def test_UNIVERSAL_geometric_elasticity_equals_weight():
    p = {"Use": 60, "Waste": 70, "Timing": 50, "Health": 80}
    for k, w in W.items():
        q = dict(p); q[k] *= 1.01
        assert math.log(geo(q, W) / geo(p, W)) / math.log(1.01) == pytest.approx(w)


def test_UNIVERSAL_geometric_rank_invariant_to_rescaling_a_pillar_arithmetic_is_not():
    a = {"Use": 80, "Waste": 30, "Timing": 60, "Health": 60}   # arithmetic 60.5
    b = {"Use": 50, "Waste": 70, "Timing": 60, "Health": 60}   # arithmetic 58.5
    for k in W:
        a2, b2 = dict(a), dict(b); a2[k] *= 3; b2[k] *= 3
        assert (geo(a, W) > geo(b, W)) == (geo(a2, W) > geo(b2, W))
    # arithmetic: tripling Waste for both flats flips the ranking (scale of a pillar acts as a hidden weight)
    a3, b3 = {**a, "Waste": a["Waste"] * 3}, {**b, "Waste": b["Waste"] * 3}
    assert (arith(a, W) > arith(b, W)) != (arith(a3, W) > arith(b3, W))


def test_POLICY_floor_choice_dominates_zero_pillar_scores():
    p = {"Use": 90, "Waste": 90, "Timing": 90, "Health": 0}
    vals = {f: geo(p, W, floor=f) for f in (0.0, 1.0, 5.0, 10.0)}
    assert vals[0.0] == 0 and vals[1.0] < vals[5.0] < vals[10.0]
    assert vals[10.0] / vals[1.0] == pytest.approx(10 ** 0.15)        # floor ratio^weight: an arbitrary constant matters


def test_UNIVERSAL_weather_normalised_heating_is_invariant_to_weather_when_behaviour_fixed(flats):
    fd = flats["F007"]
    out = fd.outdoor.dropna()
    for shift in (-3.0, 0.0, 3.0):
        t = out + shift
        kwh = float((0.12 * (12 - t)).clip(lower=0).sum())               # same behaviour (validated heater curve)
        hdh = heating_degree_hours(t, 12.0)
        assert kwh / hdh == pytest.approx(0.12)                           # behaviour metric constant
    raw = [float((0.12 * (12 - (out + s))).clip(lower=0).sum()) for s in (-3.0, 3.0)]
    assert raw[0] > 1.5 * raw[1]                                          # raw kWh punishes weather, not behaviour


def test_POLICY_size_normalisation_changes_which_flat_looks_worst(flats):
    nh = {fl: totals(fd, channels=["A01", "A02", "A03", "A04", "A05", "A06"])["kwh"] for fl, fd in flats.items()}
    per_flat = max(nh, key=nh.get)
    per_res = max(nh, key=lambda f: nh[f] / flats[f].residents)
    per_m2 = max(nh, key=lambda f: nh[f] / flats[f].floor_area_m2)
    assert per_flat == "F005" and per_res == "F004" and per_m2 == "F004"

"""The project engine (backend/app/core) audited by the INDEPENDENT invariant suite and checked against the
validated opportunity analysis (reports/opportunities.json, produced by a separate pipeline)."""
import sys

import pytest

import invariants as inv
from common import ROOT
from engine_model import EngineLensModel

sys.path.insert(0, str(ROOT / "backend"))
from app.core import counterfactual as CF  # noqa: E402
from app.core.evaluate import evaluate, prepare  # noqa: E402
from app.loader import load  # noqa: E402


@pytest.fixture(scope="module")
def audits(flats):
    return {lens: inv.run_all(EngineLensModel(lens), flats) for lens in ("apartment", "resident")}


@pytest.mark.parametrize("lens", ["apartment", "resident"])
def test_engine_passes_every_universal_invariant(audits, lens):
    bad = [r for r in audits[lens] if r["cls"] == "universal" and r["passed"] is False]
    assert not bad, bad


@pytest.mark.parametrize("lens", ["apartment", "resident"])
def test_engine_no_pillar_falls_under_any_validated_reduction(audits, lens):
    bad = [r for r in audits[lens] if r["check"] == "no pillar decreases under pure reduction" and r["passed"] is False]
    assert not bad, bad


@pytest.fixture(scope="module")
def engine():
    ds, _ = load()
    prepare(ds)
    return ds, evaluate(ds, with_sensitivity=False)


@pytest.mark.parametrize("oid,aid,params,role", [
    ("O3_F002_refrigerator_step", "FS-F002-A01", {}, "central"),
    ("O4_F004_daytime_electronics", "SB-F004-A05", {}, "central"),
    ("O4_F004_daytime_electronics", "SB-F004-A05", {"only_when_unoccupied": True}, "lower"),
    ("O2_F005_elevated_base_load", "BL-F005-A06", {"avoidable_fraction": 0.5}, "central"),
    ("O2_F005_elevated_base_load", "BL-F005-A06", {"avoidable_fraction": 1.0}, "upper_measured"),
    ("O2_F005_elevated_base_load", "BL-F005-A06", {"avoidable_fraction": 0.25}, "lower"),
    ("O1_F007_heating_unoccupied", "HU-F007-A07", {}, "central"),
    ("O1_F007_heating_unoccupied", "HU-F007-A07", {"min_absence_hours": 1}, "upper_measured"),
    ("O1_F007_heating_unoccupied", "HU-F007-A07", {"min_absence_hours": 3}, "lower"),
])
def test_engine_reproduces_validated_savings(engine, opportunities, oid, aid, params, role):
    ds, ev = engine
    r = CF.run_scenario(ds, "return_to_baseline", {"anomaly_id": aid, "params": params}, before=ev)
    s = next(x for x in opportunities[oid]["scenarios"] if x["role"] == role)
    assert -r["delta_28d"]["kwh"] == pytest.approx(s["kwh"], abs=0.006)
    assert -r["delta_28d"]["sek"] == pytest.approx(s["value_spot_hourly_sek"], abs=0.006)
    assert -r["delta_28d"]["co2_kg"] == pytest.approx(s["co2e_kg"], abs=0.0006)
    assert r["valuation"]["sek_by_tariff"]["monthly_average_spot"] == pytest.approx(s["value_spot_timeavg_sek"], abs=0.006)


def test_engine_reproduces_validated_dishwasher_timing(engine, opportunities):
    ds, ev = engine
    per_flat = opportunities["O5_dishwasher_price_timing"]["observed_evidence"]["central_saving_per_flat_spot_sek_28d"]
    tot_sek = tot_co2 = 0.0
    for fl in ds.flat_ids:
        r = CF.run_scenario(ds, "shift_flexible_load", {"flat_id": fl, "channel": "A04"}, before=ev)
        assert -r["delta_28d"]["sek"] == pytest.approx(per_flat[fl], abs=0.006)
        assert r["valuation"]["sek_by_tariff"]["monthly_average_spot"] == 0.0
        tot_sek += -r["delta_28d"]["sek"]
        tot_co2 += -r["delta_28d"]["co2_kg"]
    c = next(x for x in opportunities["O5_dishwasher_price_timing"]["scenarios"] if x["role"] == "central")
    assert tot_sek == pytest.approx(c["value_spot_hourly_sek"], abs=0.01)
    assert tot_co2 == pytest.approx(c["co2e_kg"], abs=0.001)


def test_engine_f002_interval_matches_corrected_14_day_ci(engine, opportunities):
    ds, ev = engine
    r = CF.run_scenario(ds, "return_to_baseline", {"anomaly_id": "FS-F002-A01"}, before=ev)
    lo, hi = r["uncertainty"]["sampling_ci95"]["kwh"]
    assert r["window"]["days"] == 14
    assert lo < 23.36 < hi and hi - lo < 1.0            # 14-day window CI (not the zero-padded 28-day one)

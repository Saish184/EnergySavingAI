"""Regression tests for the seven defects found in the audit of the original engine (docs/math/saish_engine_audit.md).
Each test states the requirement positively and fails on the original formulas."""
import numpy as np
import pandas as pd
import pytest

from app import config as C
from app.core import counterfactual as CF
from app.core.evaluate import evaluate
from app.core.hourly import CHANNELS, AdjustedTrajectory, combine
from app.core.interventions import ops_for
from app.core.pillars import adjusted_matrix


def _scaled(loaded, fl, factor):
    X = pd.DataFrame(adjusted_matrix(loaded.flats[fl], None, loaded.refs), columns=CHANNELS)
    return AdjustedTrajectory.of(X * factor)


def test_D1_frozen_references_peer_invariance(loaded, ev):
    """Another flat's consumption change must not move this flat's score."""
    ev2 = evaluate(loaded, {"F003": _scaled(loaded, "F003", 5.0)}, with_sensitivity=False)
    for lens in C.LENSES:
        a, b = ev["lenses"][lens].drop(index="F003"), ev2["lenses"][lens].drop(index="F003")
        np.testing.assert_allclose(a["score"].to_numpy(), b["score"].to_numpy(), atol=1e-12)


def test_D2_missing_readings_are_neither_zero_nor_regime_mixed(loaded, ev):
    """Deleting typical pre-step F002 fridge readings must not act like zero consumption (local, frozen imputation)."""
    fd = loaded.flats["F002"]
    col = fd.kwh["A01"].loc[:335].dropna()
    cells = (col - col.median()).abs().sort_values().index[:24]
    from app.core.pillars import partition, pillars
    def score_with(k):
        p = partition(fd.with_kwh(k), None, loaded.anomalies, loaded.refs)
        return pillars(fd, p, loaded.refs)["apartment"]["use"]
    k_nan, k_zero = fd.kwh.copy(), fd.kwh.copy()
    k_nan.loc[cells, "A01"] = np.nan
    k_zero.loc[cells, "A01"] = 0.0
    s0 = ev["lenses"]["apartment"].loc["F002", "use"]
    d_nan, d_zero = score_with(k_nan) - s0, score_with(k_zero) - s0
    assert abs(d_nan) < 0.5 * abs(d_zero)


@pytest.mark.parametrize("lens", ["apartment", "resident"])
def test_D3_every_intervention_raises_or_keeps_both_lenses(ds, ev, lens):
    for a in ds.anomalies:
        r = CF.run_scenario(ds, "return_to_baseline", {"anomaly_id": a["id"]}, before=ev)
        assert r["score_change"][lens] >= -1e-9, (a["id"], r["score_change"])
        for k, v in r["after"][lens]["pillars"].items():
            assert v >= r["before"][lens]["pillars"][k] - 1e-9, (a["id"], k)


def test_D4_peak_hours_cover_the_price_peak_and_dishwasher_shift_is_found(ds, ev, opportunities):
    assert {9, 20} <= ds.refs.peak_hours
    tot = 0.0
    for fl in ds.flat_ids:
        r = CF.run_scenario(ds, "shift_flexible_load", {"flat_id": fl, "channel": "A04"}, before=ev)
        assert -r["delta_28d"]["sek"] > 0, fl
        tot += -r["delta_28d"]["sek"]
    assert tot == pytest.approx(opportunities["O5"]["central_sek"], abs=0.01)


def test_D5_heater_intervention_bounded_by_evidence(ds, ev, opportunities):
    a = ds.anomaly("HU-F007-A07")
    r = CF.run_scenario(ds, "return_to_baseline", {"anomaly_id": a["id"]}, before=ev)
    assert -r["delta_28d"]["kwh"] == pytest.approx(opportunities["O1"]["central_kwh"], abs=0.01)
    assert -r["delta_28d"]["kwh"] <= opportunities["O1"]["upper_kwh"] + 0.01
    upper = CF.run_scenario(ds, "return_to_baseline", {"anomaly_id": a["id"], "params": {"min_absence_hours": 1}}, before=ev)
    assert -upper["delta_28d"]["kwh"] == pytest.approx(opportunities["O1"]["upper_kwh"], abs=0.01)
    occ = ds.flats["F007"].occupants.to_numpy()
    tr, _ = combine(ds.flats["F007"].kwh, ops_for(ds, a, {"min_absence_hours": 1})[0])
    touched = tr.delta["A07"].to_numpy() != 0
    assert (occ[touched] == 0).all()


def test_D6_no_pillar_falls_under_pure_reductions(loaded, ev):
    for fl in loaded.flat_ids:
        ev2 = evaluate(loaded, {fl: _scaled(loaded, fl, 0.95)}, with_sensitivity=False)
        for lens in C.LENSES:
            for k in C.LENSES[lens]:
                assert ev2["lenses"][lens].loc[fl, k] >= ev["lenses"][lens].loc[fl, k] - 1e-9, (fl, lens, k)


def test_D7_shift_into_missing_hour_conserves_energy_and_energy_pillars(ds, ev):
    a = next(x for x in ds.anomalies if x["id"] == "PK-F007-A04")
    r = CF.run_scenario(ds, "return_to_baseline", {"anomaly_id": a["id"]}, before=ev)
    assert r["missing_hour_moves"] >= 1
    assert abs(r["delta_28d"]["kwh"]) < 1e-9
    for lens in C.LENSES:
        assert r["after"][lens]["pillars"]["use"] == pytest.approx(r["before"][lens]["pillars"]["use"], abs=1e-9)
        assert r["after"][lens]["pillars"]["timing"] > r["before"][lens]["pillars"]["timing"]


def test_detection_alpha_must_be_attainable(monkeypatch):
    from app.core import detect
    monkeypatch.setattr(C, "DETECTION_ALPHA", 0.001)
    with pytest.raises(ValueError):
        detect.check_test_resolution()

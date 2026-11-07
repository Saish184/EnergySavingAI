import numpy as np
import pytest

from app import config as C
from app.core import counterfactual as CF
from app.core import interventions as IV
from app.core.hourly import combine


def test_shift_flexible_load_keeps_kwh(ds, ev):
    for a in [x for x in ds.anomalies if x["type"] == "peak_usage"]:
        fd = ds.flats[a["flat_id"]]
        tr, _ = combine(fd.kwh, IV.ops_for(ds, a)[0])
        assert abs(np.nansum(tr.delta.to_numpy())) < 1e-9                  # energy conserved
        assert tr.base.isna().equals(fd.kwh.isna())                          # missing stays missing
        assert (np.nan_to_num(tr.effective().to_numpy()) >= -1e-12).all()


def test_shift_never_raises_spot_cost(ds, ev):
    for fl in ds.flat_ids:
        res = CF.run_scenario(ds, "shift_flexible_load", {"flat_id": fl, "channel": "A04"}, before=ev)
        assert abs(res["delta_28d"]["kwh"]) < 1e-9
        assert res["delta_28d"]["sek"] <= 1e-9


def test_shift_rejects_heater_and_inflexible(ds, ev):
    with pytest.raises(ValueError):
        CF.run_scenario(ds, "shift_flexible_load", {"flat_id": "F001", "channel": "A07"}, before=ev)
    with pytest.raises(ValueError):
        CF.run_scenario(ds, "shift_flexible_load", {"flat_id": "F001", "channel": "A01"}, before=ev)


def test_reductions_never_increase_kwh_and_keep_missing(ds):
    for a in [x for x in ds.anomalies if x["type"] != "peak_usage"]:
        fd = ds.flats[a["flat_id"]]
        tr, _ = combine(fd.kwh, IV.ops_for(ds, a)[0])
        d = tr.delta.to_numpy()
        assert (d <= 1e-12).all(), a["id"]
        assert tr.base.isna().equals(fd.kwh.isna())


def test_fault_post_level_option(ds, ev):
    a = ds.anomaly("FS-F002-A01")
    own = CF.run_scenario(ds, "return_to_baseline", {"anomaly_id": a["id"]}, before=ev)
    peer = CF.run_scenario(ds, "return_to_baseline", {"anomaly_id": a["id"], "params": {"post_level": "peer_mean"}}, before=ev)
    assert -peer["delta_28d"]["kwh"] < -own["delta_28d"]["kwh"]          # peer level (0.0526) is above the pre-step mean
    with pytest.raises(ValueError):
        CF.run_scenario(ds, "return_to_baseline", {"anomaly_id": a["id"], "params": {"bogus": 1}}, before=ev)


def test_reduce_away_usage(ds, ev):
    res = CF.run_scenario(ds, "reduce_away_usage", {"flat_id": "F004", "fraction": 0.5}, before=ev)
    assert res["delta_28d"]["kwh"] < 0
    empty = CF.run_scenario(ds, "reduce_away_usage", {"flat_id": "F003", "fraction": 0.5}, before=ev)
    assert empty["delta_28d"]["kwh"] == 0 and empty["assumptions"]
    with pytest.raises(ValueError):
        CF.run_scenario(ds, "reduce_away_usage", {"flat_id": "F004", "fraction": 1.5}, before=ev)


def test_original_dataset_untouched(ds, ev):
    before = {fl: fd.kwh.copy() for fl, fd in ds.flats.items()}
    CF.run_scenario(ds, "return_to_baseline", {"anomaly_id": "FS-F002-A01"}, before=ev)
    CF.run_scenario(ds, "shift_flexible_load", {"flat_id": "F007", "channel": "A04"}, before=ev)
    CF.run_scenario(ds, "reduce_away_usage", {"flat_id": "F004", "fraction": 0.5}, before=ev)
    for fl, k in before.items():
        assert k.equals(ds.flats[fl].kwh)


def test_scenario_output_shape(ds, ev):
    res = CF.run_scenario(ds, "return_to_baseline", {"anomaly_id": ds.anomalies[0]["id"]}, before=ev)
    assert set(res["delta_28d"]) == {"kwh", "sek", "co2_kg"}
    for lens in C.LENSES:
        assert "score" in res["before"][lens] and "score" in res["after"][lens]
    assert res["assumptions"] and res["ladder"] and res["uncertainty"]["sampling_ci95"]
    lad = res["ladder"][0]
    for k in ("observed_kwh", "expected_baseline_kwh", "unexplained_excess_kwh", "avoidable_estimate_kwh", "counterfactual_kwh"):
        assert k in lad


def test_combined_interventions_no_double_counting(ds, ev):
    its = [{"anomaly_id": "FS-F002-A01"}, {"anomaly_id": "PK-F002-A04"}, {"anomaly_id": "PK-F002-A03"}]
    res = CF.run_scenario(ds, "apply_interventions", {"flat_id": "F002", "items": its}, before=ev)
    parts = [CF.run_scenario(ds, "return_to_baseline", {"anomaly_id": i["anomaly_id"]}, before=ev) for i in its]
    for k in ("kwh", "sek", "co2_kg"):
        assert abs(res["delta_28d"][k] - sum(p["delta_28d"][k] for p in parts)) < 1e-9   # disjoint cells: exact sum
    assert abs(res["overlap"]["kwh"]) < 1e-9

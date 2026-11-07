import numpy as np
import pytest

from app import config as C
from app.core import counterfactual as CF


def test_shift_flexible_load_keeps_kwh(ds):
    for flat in ds.flat_ids:
        for ch in C.CHANNELS:
            if ch in C.HEATER_CHANNELS:
                continue
            new, _ = CF.shift_flexible_load(ds, flat, ch)
            assert abs(new.readings["kwh"].sum() - ds.readings["kwh"].sum()) < 1e-9
            assert new.readings["kwh"].isna().sum() == ds.readings["kwh"].isna().sum()
            assert (new.readings["kwh"].dropna() >= -1e-12).all()


def test_shift_never_raises_spot_cost(ds, ev):
    res = CF.run_scenario(ds, "shift_flexible_load", {"flat_id": "F007", "channel": "A04"}, before=ev)
    assert abs(res["delta_28d"]["kwh"]) < 1e-9
    assert res["delta_28d"]["sek"] <= 1e-9


def test_shift_rejects_heater(ds):
    with pytest.raises(ValueError):
        CF.shift_flexible_load(ds, "F001", "A07")


def test_return_to_baseline_never_increases_kwh(ds):
    for a in ds.anomalies:
        new, _ = CF.return_to_baseline(ds, a["id"])
        before, after = ds.readings["kwh"].to_numpy(), new.readings["kwh"].to_numpy()
        both = ~np.isnan(before)
        assert (after[both] <= before[both] + 1e-12).all(), a["id"]
        assert np.isnan(after[~both]).all()                  # missing stays missing
        assert not any(x["id"] == a["id"] for x in new.anomalies)


def test_return_to_baseline_peer_fallback(ds):
    a = ds.anomalies[0]
    a["baseline_kwh_per_h"] = float("nan")
    new, asm = CF.return_to_baseline(ds, a["id"])
    assert any("peer median" in s for s in asm)
    assert new.readings["kwh"].sum() <= ds.readings["kwh"].sum() + 1e-9


def test_reduce_away_usage(ds, ev):
    res = CF.run_scenario(ds, "reduce_away_usage", {"flat_id": "F002", "fraction": 0.5}, before=ev)
    assert res["delta_28d"]["kwh"] <= 0
    with pytest.raises(ValueError):
        CF.reduce_away_usage(ds, "F002", 1.5)


def test_original_dataset_untouched(ds):
    before = ds.readings["kwh"].copy()
    CF.return_to_baseline(ds, ds.anomalies[0]["id"])
    CF.shift_flexible_load(ds, "F007", "A04")
    CF.reduce_away_usage(ds, "F002", 0.5)
    assert before.equals(ds.readings["kwh"])


def test_scenario_output_shape(ds, ev):
    res = CF.run_scenario(ds, "return_to_baseline", {"anomaly_id": ds.anomalies[0]["id"]}, before=ev)
    assert set(res["delta_28d"]) == {"kwh", "sek", "co2_kg"}
    for lens in C.LENSES:
        assert "score" in res["before"][lens] and "score" in res["after"][lens]
    assert res["assumptions"]

"""Reproduce and compare the teammate's engine (branch saish, ddc02ce) on our validated data.

  export SAISH_BACKEND=/path/to/read-only/checkout/of/origin/saish/backend
  python analysis/score_audit/compare_saish.py        -> reports/saish_engine_comparison.json

Sections: scores (3 anomaly-translation variants, both lenses) | counterfactuals vs validated savings |
constant sensitivity (config overridden IN MEMORY only) | size elasticity | composition of Timing 'flex' and
Waste 'avoidable' | peak-hour definition vs prices. The teammate's files are never written.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import PROCESSED, REPORTS  # noqa: E402
import saish_engine as S  # noqa: E402

C, loader, evaluate, cf, Dataset = S._import()
import importlib  # noqa: E402
metrics, P = importlib.import_module("saish_app.core.metrics"), importlib.import_module("saish_app.core.pillars")

r2 = lambda v, n=3: None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), n)
OUT: dict = {"commit": S.EXPECTED_COMMIT, "assumed_anomaly_translation": S.VALIDATED, "variants": S.VARIANTS}

# 1. scores --------------------------------------------------------------------------------------------
OUT["scores"] = {}
for v in S.VARIANTS:
    ev = evaluate.evaluate(S.dataset(variant=v), with_sensitivity=True)
    OUT["scores"][v] = {lens: {fl: {k: (r2(x, 2) if not isinstance(x, str) else x) for k, x in row.items()}
                               for fl, row in t.to_dict("index").items()} for lens, t in ev["lenses"].items()}
    if v == "A_O2_as_resident":
        d = ev["detail"]["apartment"]
        OUT["detail_A"] = {"use_x": {k: r2(x) for k, x in d["use_x"].items()}, "use_bench": r2(d["use_bench"]),
                           "avoidable_away_kwh": {k: r2(x, 2) for k, x in d["avoidable_away_kwh"].items()},
                           "cti": {k: r2(x) for k, x in d["cti"].items()},
                           "sensitivity_apartment": {fl: {k: r2(x, 1) for k, x in row.items()} for fl, row in ev["sensitivity"]["apartment"].to_dict("index").items()}}

# 2. counterfactuals vs validated -------------------------------------------------------------------------
opp = {o["id"][:2]: o for o in json.loads((REPORTS / "opportunities.json").read_text())["opportunities"]}
val = lambda oid, role: next(s for s in opp[oid]["scenarios"] if s["role"] == role)
ds = S.dataset(variant="A_O2_as_resident")
before = evaluate.evaluate(ds, with_sensitivity=False)


def run(sc, params):
    r = cf.run_scenario(ds, sc, params, before)
    return {"d_kwh": r2(-r["delta_28d"]["kwh"], 2), "d_sek": r2(-r["delta_28d"]["sek"], 2), "d_co2_kg": r2(-r["delta_28d"]["co2_kg"], 3),
            "score_change": {k: r2(x, 2) for k, x in r["score_change"].items()},
            "pillars_before": {k: r2(x, 1) for k, x in r["before"]["apartment"]["pillars"].items()},
            "pillars_after": {k: r2(x, 1) for k, x in r["after"]["apartment"]["pillars"].items()},
            "annual_kwh_projection": r2(-r["projection_annual"]["kwh"]["value"], 1),
            "moved_note": [a for a in r["assumptions"] if "moved" in a]}


cmp = {
    "F002 fridge repair": {"teammate": run("return_to_baseline", {"anomaly_id": "O3"}),
                           "validated_central": {k: val("O3", "central")[k] for k in ("kwh", "value_spot_hourly_sek", "co2e_kg")}},
    "F007 heater (heater_pattern return_to_baseline)": {"teammate": run("return_to_baseline", {"anomaly_id": "O1"}),
                                                        "validated_central": {k: val("O1", "central")[k] for k in ("kwh", "value_spot_hourly_sek", "co2e_kg")},
                                                        "validated_upper_measured": val("O1", "upper_measured")["kwh"]},
    "F004 away_usage return_to_baseline": {"teammate": run("return_to_baseline", {"anomaly_id": "O4"}),
                                           "validated_central": val("O4", "central")["kwh"], "validated_lower_unoccupied": val("O4", "lower")["kwh"]},
    "F004 reduce_away_usage fraction=1": {"teammate": run("reduce_away_usage", {"flat_id": "F004", "fraction": 1.0})},
    "F005 night_baseload return_to_baseline": {"teammate": run("return_to_baseline", {"anomaly_id": "O2"}),
                                               "validated_full_excess": val("O2", "upper_measured")["kwh"], "validated_central_theta_0_5": val("O2", "central")["kwh"]},
}
shift = {}
for fl in ds.flat_ids:
    rr = cf.run_scenario(ds, "shift_flexible_load", {"flat_id": fl, "channel": "A04"}, before)
    shift[fl] = {"d_sek": r2(-rr["delta_28d"]["sek"], 3), "note": [a for a in rr["assumptions"] if "moved" in a][0]}
cmp["Dishwasher shift_flexible_load A04 (all flats)"] = {
    "teammate_per_flat": shift, "teammate_fleet_sek": r2(sum(v["d_sek"] for v in shift.values()), 2),
    "validated_fleet_sek_21h": val("O5", "central")["value_spot_hourly_sek"], "validated_fleet_co2_21h": val("O5", "central")["co2e_kg"]}
OUT["counterfactual_comparison"] = cmp

# 3. sensitivity to hard-coded constants (in memory) ------------------------------------------------------
def rank_scores():
    t = evaluate.evaluate(ds, with_sensitivity=False)["lenses"]["apartment"]
    return t.sort_values("score", ascending=False).index.tolist(), t.score.round(1).to_dict()


base_rank, _ = rank_scores()
sens = {"baseline_rank": base_rank}
for attr, vals in [("USE_BENCH_PERCENTILE", [10, 30]), ("BASELOAD_PERCENTILE", [5, 20]),
                   ("WASTE_FULL_PENALTY_SHARE", [0.25, 1.0]), ("HEALTH_FAULT_MULTIPLIER", [1.0, 4.0])]:
    orig = getattr(C, attr)
    for v in vals:
        setattr(C, attr, v)
        if attr == "USE_BENCH_PERCENTILE":
            P.use_pillar.__defaults__ = (C.PERIOD_DAYS, v)
        rk, sc = rank_scores()
        sens[f"{attr}={v}"] = {"rank": rk, "rank_changed": rk != base_rank, "scores": sc}
        setattr(C, attr, orig)
        if attr == "USE_BENCH_PERCENTILE":
            P.use_pillar.__defaults__ = (C.PERIOD_DAYS, orig)
OUT["constant_sensitivity"] = sens

# 4. household-size elasticity ----------------------------------------------------------------------------
t = pd.read_csv(PROCESSED / "analytical_table.csv")
okk = t[~t.energy_missing]
n = t.groupby("flat_id").residents.first()
el = {}
for lab, d in (("excl_heater", okk[okk.appliance_code != "A07"]), ("incl_heater", okk)):
    b, _ = np.polyfit(np.log(n), np.log(d.groupby("flat_id").energy_kwh.sum()), 1)
    el[lab] = r2(b)
OUT["size_elasticity"] = {"assumed_by_engine": 0.5, "observed_log_log": el}

# 5. composition ------------------------------------------------------------------------------------------
e = metrics.enrich(ds.readings, ds.flats, ds.prices, ds.context)
flex = e[~e.is_heater].groupby(["flat_id", "channel"]).above_base.sum().unstack()
share = flex.div(flex.sum(axis=1), axis=0) * 100
aw = e[e.occupants_home.eq(0) & ~e.is_heater].groupby(["flat_id", "channel"]).above_base.sum().unstack()
OUT["timing_flex_composition_pct"] = {fl: {c: r2(v, 1) for c, v in row.items()} for fl, row in share.to_dict("index").items()}
OUT["timing_flex_share_A03_A04_mean_pct"] = r2((share["A03"] + share["A04"]).mean(), 1)
OUT["waste_avoidable_away_by_channel_kwh"] = {fl: {c: r2(v, 2) for c, v in row.items()} for fl, row in aw.to_dict("index").items()}

# 6. peak hours vs prices ---------------------------------------------------------------------------------
H = ds.prices.copy()
H["lh"] = H.timestamp_utc.dt.tz_convert("Europe/Stockholm").dt.hour
pm = H.groupby("lh").spot.mean()
OUT["peak_definition"] = {"engine_PEAK_HOURS_LOCAL": sorted(C.PEAK_HOURS_LOCAL),
                          "mean_spot_by_local_hour": {int(h): r2(v) for h, v in pm.items()},
                          "hours_above_0_8_SEK": [int(h) for h, v in pm.items() if v > 0.8]}

(REPORTS / "saish_engine_comparison.json").write_text(json.dumps(OUT, indent=2, default=str) + "\n")
print("written reports/saish_engine_comparison.json")

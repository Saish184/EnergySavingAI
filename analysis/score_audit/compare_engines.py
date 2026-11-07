"""Original engine (saish@ddc02ce) vs improved engine (backend/app/core on mina), on the validated data.

  python analysis/score_audit/compare_engines.py          # improved engine + its sensitivity
  SAISH_BACKEND=/path/to/saish/backend python ...          # + original engine side by side

Writes reports/engine_comparison.json and reports/engine_comparison.md. Deterministic.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import REPORTS, ROOT  # noqa: E402

sys.path.insert(0, str(ROOT / "backend"))
from app import config as C  # noqa: E402
from app.core import counterfactual as CF  # noqa: E402
from app.core.evaluate import evaluate, prepare  # noqa: E402
from app.loader import load  # noqa: E402

r = lambda v, n=2: None if v is None else round(float(v), n)
OUT: dict = {}
J = {o["id"][:2]: o for o in json.loads((REPORTS / "opportunities.json").read_text())["opportunities"]}
val = lambda oid, role: next(s for s in J[oid]["scenarios"] if s["role"] == role)


def fresh():
    ds, _ = load()
    return prepare(ds)


ds = fresh()
ev = evaluate(ds)
OUT["references"] = ev["references"]
OUT["new_scores"] = {lens: {fl: {k: r(v, 1) for k, v in row.items() if k != "band"} | {"band": row["band"]}
                            for fl, row in t.to_dict("index").items()} for lens, t in ev["lenses"].items()}
OUT["new_detected"] = [{"id": a["id"], "type": a["type"], "status": a["status"].name, "responsibility": a["responsibility"],
                        "excess_kwh": r(a["excess_kwh"]), "evidence": a["evidence"]} for a in ds.anomalies]

cases = [("F002 fridge repair", "FS-F002-A01", {}, ("O3", "central")),
         ("F004 daytime electronics", "SB-F004-A05", {}, ("O4", "central")),
         ("F005 base load (full excess)", "BL-F005-A06", {}, ("O2", "upper_measured")),
         ("F005 base load (theta 0.5)", "BL-F005-A06", {"avoidable_fraction": 0.5}, ("O2", "central")),
         ("F007 heater, unoccupied >= 2 h", "HU-F007-A07", {}, ("O1", "central"))]
cmp = {}
for label, aid, p, (oid, role) in cases:
    res = CF.run_scenario(ds, "return_to_baseline", {"anomaly_id": aid, "params": p}, before=ev)
    v = val(oid, role)
    cmp[label] = {"new": {"kwh": r(-res["delta_28d"]["kwh"]), "sek": r(-res["delta_28d"]["sek"]), "co2_kg": r(-res["delta_28d"]["co2_kg"], 3),
                          "score_change": {k: r(x) for k, x in res["score_change"].items()},
                          "ci95_kwh": [r(x) for x in res["uncertainty"]["sampling_ci95"]["kwh"]],
                          "scenario_range_kwh": [r(x) for x in res["uncertainty"]["scenario_range"]["kwh"]]},
                  "validated": {"kwh": v["kwh"], "sek": v["value_spot_hourly_sek"], "co2_kg": v["co2e_kg"]}}
dish = [CF.run_scenario(ds, "shift_flexible_load", {"flat_id": fl, "channel": "A04"}, before=ev) for fl in ds.flat_ids]
cmp["Dishwasher timing (all flats)"] = {"new": {"kwh": r(sum(-x["delta_28d"]["kwh"] for x in dish)), "sek": r(sum(-x["delta_28d"]["sek"] for x in dish)),
                                                "co2_kg": r(sum(-x["delta_28d"]["co2_kg"] for x in dish), 3),
                                                "score_change_mean": {lens: r(np.mean([x["score_change"][lens] for x in dish])) for lens in C.LENSES}},
                                        "validated": {"kwh": 0.0, "sek": val("O5", "central")["value_spot_hourly_sek"], "co2_kg": val("O5", "central")["co2e_kg"]}}
OUT["counterfactuals"] = cmp

# ---------------------------------------------------------------- sensitivity of the improved engine's choices
def ranks(lens="apartment"):
    e = evaluate(fresh(), with_sensitivity=False)["lenses"][lens]
    return e.sort_values("score", ascending=False).index.tolist(), e.score.round(1).to_dict()


base_rank, _ = ranks()
sens = {"baseline_rank": base_rank, "baseline_resident_rank": ranks("resident")[0]}
for attr, vals in [("EQUIVALENCE_EXPONENT", [0.33, 1.0]), ("USE_BENCH_PERCENTILE", [10, 30]), ("MIN_ABSENCE_HOURS", [1, 3]),
                   ("DETECTION_ALPHA", [0.05, 0.001]), ("CONTINUOUS_MAX_ZERO_SHARE", [0.1, 0.75])]:
    orig = getattr(C, attr)
    for v in vals:
        setattr(C, attr, v)
        if attr == "DETECTION_ALPHA" and v <= 1 / (C.PERMUTATIONS + 1):
            setattr(C, "PERMUTATIONS", 9999)          # keep the test able to reach alpha (resolution guard)
        rk, sc = ranks()
        n_anoms = len(fresh().anomalies)
        sens[f"{attr}={v}"] = {"rank": rk, "rank_changed": rk != base_rank, "scores": sc, "anomalies": n_anoms}
        setattr(C, attr, orig)
        C.PERMUTATIONS = 999
OUT["sensitivity"] = sens

# ---------------------------------------------------------------- original engine (optional)
if os.environ.get("SAISH_BACKEND"):
    orig = json.loads((REPORTS / "saish_engine_comparison.json").read_text())
    OUT["original_scores"] = orig["scores"]["A_O2_as_resident"]
    OUT["original_counterfactuals"] = orig["counterfactual_comparison"]
    aud = json.loads((REPORTS / "score_audit.json").read_text())
    OUT["invariants"] = {m["model"]: m["summary"] for m in aud.get("engine", []) + (aud.get("teammate_models_all_lenses") or [])}
(REPORTS / "engine_comparison.json").write_text(json.dumps(OUT, indent=2, default=str) + "\n")

# ---------------------------------------------------------------- markdown
md = ["# Original vs improved engine", "", "_Generated by `analysis/score_audit/compare_engines.py` on the validated data._", ""]
if "original_scores" in OUT:
    o = OUT["original_scores"]
    md += ["## Scores (apartment / resident lens)", "", "| Flat | Original apartment | Improved apartment | Original resident | Improved resident |",
           "|---|---:|---:|---:|---:|"]
    for fl in sorted(OUT["new_scores"]["apartment"]):
        md.append(f"| {fl} | {o['apartment'][fl]['score']:.1f} ({o['apartment'][fl]['band']}) | {OUT['new_scores']['apartment'][fl]['score']:.1f} "
                  f"({OUT['new_scores']['apartment'][fl]['band']}) | {o['resident'][fl]['score']:.1f} | {OUT['new_scores']['resident'][fl]['score']:.1f} |")
    md += ["", "## Universal invariants (independent suite)", "", "| Model | Universal checks failed | Policy inconsistencies |", "|---|---:|---:|"]
    md += [f"| {k} | {v['universal']['failed']}/{v['universal']['checks']} | {v['policy']['failed']}/{v['policy']['checks']} |" for k, v in OUT["invariants"].items()]
md += ["", "## Counterfactual savings (28 observed days or the pattern's window; spot SEK if hourly tariff)", "",
       "| Case | Validated kWh / SEK / kg | Improved engine kWh / SEK / kg | Score change (apartment, resident) |", "|---|---|---|---|"]
for k, v in cmp.items():
    n = v["new"]
    sc = n.get("score_change") or n.get("score_change_mean")
    md.append(f"| {k} | {v['validated']['kwh']} / {v['validated']['sek']} / {v['validated']['co2_kg']} | {n['kwh']} / {n['sek']} / {n['co2_kg']} | "
              f"{sc['apartment']:+.2f}, {sc['resident']:+.2f} |")
if "original_counterfactuals" in OUT:
    oc = OUT["original_counterfactuals"]
    md += ["", "Original engine on the same cases: F002 repair "
           f"{oc['F002 fridge repair']['teammate']['d_kwh']} kWh (resident score {oc['F002 fridge repair']['teammate']['score_change']['resident']:+.2f}); "
           f"F007 heater {oc['F007 heater (heater_pattern return_to_baseline)']['teammate']['d_kwh']} kWh; "
           f"dishwasher {oc['Dishwasher shift_flexible_load A04 (all flats)']['teammate_fleet_sek']} SEK."]
md += ["", "## Sensitivity of the improved engine's modelling choices (apartment ranking)", "", f"Baseline ranking: {', '.join(base_rank)}", "",
       "| Choice | Anomalies detected | Ranking changed | Ranking |", "|---|---:|---|---|"]
md += [f"| {k} | {v['anomalies']} | {'yes' if v['rank_changed'] else 'no'} | {', '.join(v['rank'])} |" for k, v in sens.items() if isinstance(v, dict)]
(REPORTS / "engine_comparison.md").write_text("\n".join(md) + "\n")
print("written reports/engine_comparison.{json,md}")

"""What-if scenarios (API layer over core/savings.py). Every scenario is an hourly intervention on one flat; scores
before/after use the same frozen references. Physically plausible only: nothing creates energy, shifts keep kWh,
reductions are bounded by the detector's evidence (e.g. heating is only removed in hours with nobody home).

  return_to_baseline   {"anomaly_id", optional "params"}: the anomaly's own intervention (repair / reduce / shift)
  shift_flexible_load  {"channel" (default first flexible), optional "params"}: the flat's peak_usage anomaly on that channel
  reduce_away_usage    {"fraction"}: every resident-attributable reduction pattern of the flat, only in hours with nobody home
  apply_interventions  {"items": [{"anomaly_id", "params"}], "tariff": {...}}: several interventions combined, no double counting
"""
from __future__ import annotations

from .. import config as C
from . import savings as SV

SCENARIOS = ("return_to_baseline", "shift_flexible_load", "reduce_away_usage", "apply_interventions")


def _empty(flat_id: str, scenario: str, params: dict, reason: str, before: dict) -> dict:
    snap = SV._snap(before, flat_id)
    zero = {"kwh": 0.0, "sek": 0.0, "co2_kg": 0.0}
    return {"scenario": scenario, "params": params, "flat_id": flat_id, "label": "scenario", "horizon": "28d measured counterfactual",
            "delta_28d": zero, "before": snap, "after": snap, "score_change": {lens: 0.0 for lens in C.LENSES},
            "projection_annual": SV.project_triplet(None, False, reason), "assumptions": [reason], "items": []}


def items_for(ds, scenario: str, params: dict) -> tuple[str, list[dict], list[str]]:
    if scenario == "return_to_baseline":
        a = ds.anomaly(params["anomaly_id"])
        return a["flat_id"], [{"anomaly_id": a["id"], "params": params.get("params")}], []
    fl = params["flat_id"]
    if scenario == "shift_flexible_load":
        ch = params.get("channel") or sorted(C.FLEXIBLE_CHANNELS)[0]
        if ch in C.HEATER_CHANNELS:
            raise ValueError("heater-like load is not treated as shiftable")
        if ch not in C.FLEXIBLE_CHANNELS:
            raise ValueError(f"{ch} is not a flexible channel (flexible: {sorted(C.FLEXIBLE_CHANNELS)})")
        a = [x for x in ds.anomalies if x["flat_id"] == fl and x["type"] == "peak_usage" and x["channel"] == ch]
        return fl, [{"anomaly_id": x["id"], "params": params.get("params")} for x in a], ([] if a else [f"no {ch} runs in peak-price hours"])
    if scenario == "reduce_away_usage":
        frac = float(params.get("fraction", C.AWAY_REDUCTION_DEFAULT))
        if not 0 <= frac <= 1:
            raise ValueError("fraction must be between 0 and 1")
        a = [x for x in ds.anomalies if x["flat_id"] == fl and x["type"] in ("scheduled_block", "heater_pattern")]
        its = [{"anomaly_id": x["id"], "params": {"adoption": frac, **({"only_when_unoccupied": True} if x["type"] == "scheduled_block" else {})}}
               for x in a]
        return fl, its, ([] if a else ["no use-while-away pattern detected for this flat"])
    if scenario == "apply_interventions":
        its = params.get("items") or []
        return fl, its, ([] if its else ["no interventions given"])
    raise ValueError(f"unknown scenario {scenario}; choose one of {SCENARIOS}")


def run_scenario(ds, scenario: str, params: dict, before: dict | None = None, tariff: dict | None = None) -> dict:
    from .evaluate import evaluate
    before = before or evaluate(ds, with_sensitivity=False)
    fl, its, notes = items_for(ds, scenario, params)
    if not its:
        return _empty(fl, scenario, params, "; ".join(notes), before)
    r = SV.run(ds, its, before=before, tariff=tariff or params.get("tariff"))
    assumptions = [f"{it['anomaly_id']}: {it['type']} with {it['params']}" for it in r["items"]] + [
        "other flats unchanged; frozen references (benchmarks, imputations, anomaly levels) reused",
        "SEK = spot price only, excludes network fee, energy tax, VAT"]
    return {"scenario": scenario, "params": params, "flat_id": fl, "label": "scenario", "horizon": "28d measured counterfactual",
            "delta_28d": {"kwh": -r["delta"]["kwh"], "sek": -r["delta"]["sek_spot_hourly"], "co2_kg": -r["delta"]["co2e_kg"]},
            "before": r["scores"]["before"], "after": r["scores"]["after"], "score_change": r["scores"]["change"],
            "projection_annual": r["projection_annual"], "assumptions": assumptions + notes, **{k: r[k] for k in
            ("items", "kind", "window", "ladder", "valuation", "uncertainty", "overlap", "missing_hour_moves")}}

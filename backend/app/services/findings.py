"""Finding = engine-detected anomaly + claim level + responsibility + evidence + savings ladder + uncertainty.
The main unit both interfaces show. All numbers come from core/savings.py (one calculation for both views).
Field names of the original contract are kept; new fields are additive (docs/data_contract.md)."""
from __future__ import annotations

from .. import config as C
from ..core import attribution, claims, metrics
from ..core import savings as SV

TYPE_TITLES = {
    "fault_step_change": "Sudden lasting increase",
    "base_load_outlier": "Always-on load above other flats",
    "scheduled_block": "Device running at fixed hours, also when nobody is home",
    "heater_pattern": "Heater-like use while nobody is home",
    "peak_usage": "Runs in expensive peak hours",
}
METHODS = {
    "fault_step_change": "hourly kWh above the pre-step level removed from the step onwards (repair)",
    "base_load_outlier": "always-on load above the other flats' floor removed (capped at the measured excess)",
    "scheduled_block": "use above the other flats' level at the flagged hours removed",
    "heater_pattern": "heater-like use removed only in hours with nobody home (absences >= 2 h)",
    "peak_usage": "runs moved to the first later non-peak hour (same kWh)",
}


def _wording(a: dict) -> str:
    if a["responsibility"] == "unknown" and a["status"] in (claims.Status.DETECTED, claims.Status.PLAUSIBLE):
        return attribution.note("unknown")
    return claims.wording(a["status"], a["responsibility"])


def build_finding(ds, ev: dict, a: dict) -> dict:
    r = SV.run(ds, [{"anomaly_id": a["id"], "params": None}], before=ev, tariff={"type": "unknown"})
    lad = r["ladder"][0]
    shift = r["kind"] == "shift"
    d = r["delta"]
    days = r["window"]["days"]
    assumed = metrics.assumed_type(a["channel"])
    scenario = "shift_flexible_load" if shift else "return_to_baseline"
    assumptions = [
        f"{a['appliance_id']} treated as {assumed} (ASSUMPTION: channels are unlabelled)",
        f"counterfactual: {METHODS[a['type']]}",
        "SEK = spot price only, excludes network fee, energy tax, VAT; depends on the student's tariff",
        "frozen references (other flats, benchmarks, imputations) unchanged",
    ]
    if a["type"] == "heater_pattern":
        assumptions.append("occupancy is a simulated sensor estimate; heating need on return (rebound) not modelled in the central case")
    return {
        "id": a["id"], "flat_id": a["flat_id"], "appliance_id": a["appliance_id"], "channel": a["channel"],
        "assumed_type": assumed, "assumed_type_is_assumption": True, "type": a["type"],
        "title": TYPE_TITLES.get(a["type"], a["type"]), "status": a["status"].name, "status_level": int(a["status"]),
        "wording": _wording(a), "responsibility": a["responsibility"], "responsibility_note": attribution.note(a["responsibility"]),
        "counts_as": {"health": "possible equipment fault (apartment lens only)", "waste": "possible avoidable use",
                      None: "timing opportunity (not waste)"}[_counts(a)],
        "window": {"start": a["start"], "end": a["end"], "days": claims.duration_days(a["start"], a["end"])},
        "evidence": {"text": a["evidence"], "statistics": a["stats"], "confidence": None,
                     "confidence_note": "no probability is claimed; status follows the stated statistical criterion",
                     "baseline_kwh_per_h": a["baseline_kwh_per_h"], "observed_kwh_per_h": a["observed_kwh_per_h"],
                     "reported_excess_kwh": a["excess_kwh"]},
        "quantities": lad,
        "avoidable_28d": {"kwh": d["kwh"], "sek": d["sek_spot_hourly"], "co2_kg": d["co2e_kg"],
                          "horizon": f"measured counterfactual over {days:g} observed days", "window_days": days,
                          "label": "potential (if followed fully)", "scenario": scenario, "method": METHODS[a["type"]],
                          "kind": r["kind"]},
        "valuation": r["valuation"],
        "score_if_fixed": {lens: {"before": r["scores"]["before"][lens]["score"], "after": r["scores"]["after"][lens]["score"]}
                           for lens in C.LENSES},
        "projection_annual": r["projection_annual"],
        "assumptions": assumptions,
        "uncertainty": {**r["uncertainty"], "detector_confidence": None,
                        "projection_range_sek": [r["projection_annual"]["sek"]["low"], r["projection_annual"]["sek"]["high"]]},
        "tiers": {"potential": {"kwh": d["kwh"], "sek_if_hourly_spot": d["sek_spot_hourly"], "co2_kg": d["co2e_kg"]},
                  "estimated_realized": None, "estimated_realized_reason": "needs the student's confirmation and adoption estimate",
                  "verified": (a.get("verification") or {}).get("saving_kwh"), "verified_reason": "needs >= 7 days of post-change data"},
        "verification": a.get("verification"),
        "simulated": bool((a.get("verification") or {}).get("simulated", False)),
    }


def _counts(a: dict):
    from ..core.pillars import counts_in
    return counts_in(a)


def build_findings(ds, ev: dict) -> list[dict]:
    out = [build_finding(ds, ev, a) for a in ds.anomalies]
    return sorted(out, key=lambda f: (-(f["avoidable_28d"]["sek"] or 0), f["id"]))

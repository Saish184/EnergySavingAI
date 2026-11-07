"""Finding = anomaly + claim level + responsibility + counterfactual + projection.
The main unit the frontend shows. All numbers come from the engine."""
from __future__ import annotations

from .. import config as C
from ..core import attribution, claims, metrics
from ..core.counterfactual import run_scenario
from ..core.dataset import Dataset

TYPE_TITLES = {
    "fault_step_change": "Sudden lasting increase",
    "peer_outlier": "Much higher than the same channel in other flats",
    "heater_pattern": "Heater-like use pattern",
    "away_usage": "Use while nobody is home",
    "night_baseload": "High night-time base load",
    "peak_usage": "Use in expensive peak hours",
}


def _wording(a: dict) -> str:
    if a["responsibility"] == "unknown" and a["status"] < claims.Status.CONFIRMED:
        return attribution.note("unknown")
    return claims.WORDING[a["status"]]


def counterfactual_for(a: dict) -> tuple[str, dict, str]:
    """Physically plausible fix per pattern type."""
    if a["type"] == "peak_usage" and a["channel"] not in C.HEATER_CHANNELS:
        return ("shift_flexible_load", {"flat_id": a["flat_id"], "channel": a["channel"]},
                "engine re-run with peak-hour load moved to the cheapest hour within 12 h (same kWh)")
    return ("return_to_baseline", {"anomaly_id": a["id"]},
            "engine re-run with this appliance capped at its baseline inside the anomaly window")


def build_finding(ds: Dataset, ev: dict, a: dict) -> dict:
    scenario, params, method = counterfactual_for(a)
    cf = run_scenario(ds, scenario, params, before=ev)
    d = cf["delta_28d"]
    avoidable = {"kwh": -d["kwh"], "sek": -d["sek"], "co2_kg": -d["co2_kg"],
                 "horizon": "28d measured", "label": "measured counterfactual",
                 "scenario": scenario, "method": method}
    proj = {k: {**v, "value": -v["value"], "low": -v["high"], "high": -v["low"],
                "basis_28d": -v["basis_28d"], "bootstrap_low": -v["bootstrap_high"],
                "bootstrap_high": -v["bootstrap_low"]}
            for k, v in cf["projection_annual"].items()}
    assumed = metrics.assumed_type(a["channel"])
    assumptions = [
        f"{a['appliance_id']} treated as {assumed} (ASSUMPTION: channels are unlabelled)",
        *cf["assumptions"],
        "SEK = spot price only, excludes network fee, energy tax, VAT",
    ]
    if a["responsibility"] == "unknown":
        assumptions.append("heating use is NOT counted as waste unless a person confirms it")
    return {
        "id": a["id"],
        "flat_id": a["flat_id"],
        "appliance_id": a["appliance_id"],
        "channel": a["channel"],
        "assumed_type": assumed,
        "assumed_type_is_assumption": True,
        "type": a["type"],
        "title": TYPE_TITLES.get(a["type"], a["type"]),
        "status": a["status"].name,
        "status_level": int(a["status"]),
        "wording": _wording(a),
        "responsibility": a["responsibility"],
        "responsibility_note": attribution.note(a["responsibility"]),
        "window": {"start": a["start"], "end": a["end"], "days": claims.duration_days(a["start"], a["end"])},
        "evidence": {
            "text": a.get("evidence"),
            "confidence": a["confidence"],
            "baseline_kwh_per_h": a["baseline_kwh_per_h"],
            "observed_kwh_per_h": a["observed_kwh_per_h"],
            "reported_excess_kwh": a["excess_kwh"],
        },
        "avoidable_28d": avoidable,
        "score_if_fixed": {lens: {"before": cf["before"][lens]["score"], "after": cf["after"][lens]["score"]}
                           for lens in ("apartment", "resident")},
        "projection_annual": proj,
        "assumptions": assumptions,
        "uncertainty": {
            "detector_confidence": a["confidence"],
            "projection_range_sek": [proj["sek"]["low"], proj["sek"]["high"]],
            "note": "range = max of ±30% and day-bootstrap; synthetic data",
        },
        "verification": a.get("verification"),
        "simulated": bool((a.get("verification") or {}).get("simulated", False)),
    }


def build_findings(ds: Dataset, ev: dict) -> list[dict]:
    out = [build_finding(ds, ev, a) for a in ds.anomalies]
    return sorted(out, key=lambda f: -(f["projection_annual"]["sek"]["value"] or 0))

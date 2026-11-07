"""Hackathon sustainability case, generated from the engine (no hand-typed numbers).

    python analysis/sustainability_case.py     -> reports/sustainability_case.{json,md}

Every figure comes from backend AppState / core.savings on the validated data. Combined effects are computed by the
engine on each flat's hourly trajectory (no double counting); only flats are summed (they are disjoint).
Per-resident figures are averages of a flat's shared household action, never "each student saves".
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("FEC_DATA_SOURCE", "processed")
os.environ["FEC_LLM_PROVIDER"] = "template"
os.environ["FEC_LLM_BACKGROUND"] = "0"
os.environ["ANTHROPIC_API_KEY"] = ""

from app.core import savings as SV  # noqa: E402
from app.state import AppState  # noqa: E402

OWNER = {"manager": "building manager (equipment)", "resident": "residents (behaviour)", "unknown": "needs confirmation (heating)"}


def combined(s: AppState, fl: str, ids: list[str], tariff: dict | None = None) -> dict | None:
    if not ids:
        return None
    r = SV.run(s.ds, [{"anomaly_id": i, "params": None} for i in ids], before=s.ev, tariff=tariff or {"type": "unknown"})
    return {"kwh": r["delta"]["kwh"], "sek_hourly_spot": r["delta"]["sek_spot_hourly"], "co2_kg": r["delta"]["co2e_kg"],
            "sek_by_tariff": r["valuation"]["sek_by_tariff"], "overlap_kwh": r["overlap"]["kwh"], "window_days": r["window"]["days"]}


def main():
    s = AppState()
    tot = s.ev["totals"]
    flats = s.ds.flat_ids
    residents = {fl: int(tot.loc[fl, "residents"]) for fl in flats}
    out = {"source": "engine (backend AppState) on data/processed/analytical_table.csv", "references_hash": s.ev["references"]["hash"],
           "observed": {"period": "2026-10-01..2026-10-28 (28 days, UTC)", "flats": len(flats), "residents": sum(residents.values()),
                        "kwh": float(tot["kwh"].sum()), "sek_spot": float(tot["sek"].sum()), "co2_kg": float(tot["co2_kg"].sum()),
                        "by_flat": {fl: {"kwh": float(tot.loc[fl, "kwh"]), "sek_spot": float(tot.loc[fl, "sek"]),
                                         "co2_kg": float(tot.loc[fl, "co2_kg"]), "residents": residents[fl]} for fl in flats}},
           "interventions": [], "groups": {}, "per_flat": {}}

    for f in s.findings:
        p = f["projection_annual"]
        out["interventions"].append({
            "id": f["id"], "flat_id": f["flat_id"], "title": f["title"], "appliance": f["assumed_type"] + " (inferred)",
            "owner": OWNER[f["responsibility"]], "status": f["status"], "wording": f["wording"],
            "kind": f["avoidable_28d"]["kind"], "window_days": f["avoidable_28d"]["window_days"],
            "kwh_avoided": f["avoidable_28d"]["kwh"] if f["avoidable_28d"]["kind"] == "reduction" else 0.0,
            "kwh_moved": f["quantities"]["kwh_moved"],
            "sek_by_tariff": f["valuation"]["sek_by_tariff"], "co2_kg": f["avoidable_28d"]["co2_kg"],
            "ci95_kwh": f["uncertainty"]["sampling_ci95"]["kwh"], "ci95_sek_hourly": f["uncertainty"]["sampling_ci95"]["sek_spot_hourly"],
            "scenario_range_kwh": (f["uncertainty"]["scenario_range"] or {}).get("kwh"),
            "annual": None if p["kwh"]["value"] is None else {k: {"value": p[k]["value"], "low": p[k]["low"], "high": p[k]["high"]} for k in ("kwh", "sek", "co2_kg")},
            "annual_reason": p["kwh"].get("reason"),
        })

    def group_ids(fl, pred):
        return [a["id"] for a in s.ds.anomalies if a["flat_id"] == fl and pred(a)]

    groups = {
        "manager_equipment": lambda a: a["responsibility"] == "manager",
        "resident_reductions": lambda a: a["responsibility"] in ("resident", "unknown") and a["type"] != "peak_usage",
        "resident_timing_shifts": lambda a: a["type"] == "peak_usage",
        "all": lambda a: True,
    }
    for g, pred in groups.items():
        rows = {fl: combined(s, fl, group_ids(fl, pred)) for fl in flats}
        rows = {fl: r for fl, r in rows.items() if r}
        out["groups"][g] = {
            "flats": sorted(rows),
            "kwh": sum(r["kwh"] for r in rows.values()), "sek_hourly_spot": sum(r["sek_hourly_spot"] for r in rows.values()),
            "sek_monthly_average": sum(r["sek_by_tariff"]["monthly_average_spot"] for r in rows.values()),
            "co2_kg": sum(r["co2_kg"] for r in rows.values()), "overlap_kwh": sum(r["overlap_kwh"] for r in rows.values()),
        }
    for fl in flats:
        rc = combined(s, fl, group_ids(fl, lambda a: a["responsibility"] in ("resident", "unknown")))
        if rc:
            n = residents[fl]
            out["per_flat"][fl] = {"residents": n, "resident_controlled": rc,
                                   "per_resident_average": {"kwh": rc["kwh"] / n, "sek_hourly_spot": rc["sek_hourly_spot"] / n, "co2_kg": rc["co2_kg"] / n},
                                   "label": "average per resident of this flat's shared household action; not an individual saving"}
    annual = [i for i in out["interventions"] if i["annual"]]
    out["annual_supported"] = {"ids": [i["id"] for i in annual],
                               "kwh_central_sum": sum(i["annual"]["kwh"]["value"] for i in annual),
                               "sek_central_sum": sum(i["annual"]["sek"]["value"] for i in annual),
                               "co2_central_sum": sum(i["annual"]["co2_kg"]["value"] for i in annual),
                               "note": "sum of central projections for persistent patterns only; the per-item p5-p95 ranges are not additive"}
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "sustainability_case.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    (ROOT / "reports" / "sustainability_case.md").write_text(render(out), encoding="utf-8")
    print("wrote reports/sustainability_case.{json,md}")


def n(x, d=1):
    return "–" if x is None else f"{x:,.{d}f}"


def render(o: dict) -> str:
    ob = o["observed"]
    g = o["groups"]
    L = [
        "# Sustainability case (generated from the engine)",
        "",
        f"_`python analysis/sustainability_case.py`, references hash `{o['references_hash']}`. Synthetic data: the figures demonstrate the method, not real-world savings._",
        "",
        "## 1. Observed (measured, 28 days)",
        "",
        f"{ob['flats']} flats, {ob['residents']} residents, {ob['period']}: **{n(ob['kwh'])} kWh**, **{n(ob['sek_spot'], 2)} SEK** (spot-energy component only, not a bill), **{n(ob['co2_kg'], 2)} kg CO₂e** (synthetic average factors).",
        "",
        "## 2. What acting on the findings could change (simulated by the engine)",
        "",
        "Each group is applied together on each flat's hourly data (no double counting); flats are then summed. Windows: 28 observed days, except the F002 fault (14 days, from its start).",
        "",
        "| Group | Who acts | kWh avoided | SEK if hourly spot | SEK if monthly average | kg CO₂e |",
        "|---|---|---:|---:|---:|---:|",
        f"| Equipment repair | building manager | {n(g['manager_equipment']['kwh'], 2)} | {n(g['manager_equipment']['sek_hourly_spot'], 2)} | {n(g['manager_equipment']['sek_monthly_average'], 2)} | {n(g['manager_equipment']['co2_kg'], 3)} |",
        f"| Behaviour: always-on, fixed-hour, heating while away | residents | {n(g['resident_reductions']['kwh'], 2)} | {n(g['resident_reductions']['sek_hourly_spot'], 2)} | {n(g['resident_reductions']['sek_monthly_average'], 2)} | {n(g['resident_reductions']['co2_kg'], 3)} |",
        f"| Timing: washer/dishwasher after the peak | residents | {n(g['resident_timing_shifts']['kwh'], 2)} (shift: same kWh) | {n(g['resident_timing_shifts']['sek_hourly_spot'], 2)} | {n(g['resident_timing_shifts']['sek_monthly_average'], 2)} | {n(g['resident_timing_shifts']['co2_kg'], 3)} |",
        f"| **All findings** | | **{n(g['all']['kwh'], 2)}** | **{n(g['all']['sek_hourly_spot'], 2)}** | {n(g['all']['sek_monthly_average'], 2)} | **{n(g['all']['co2_kg'], 3)}** |",
        "",
        f"kWh avoided = {n(100 * g['all']['kwh'] / ob['kwh'], 1)} % of observed portfolio use (windows of 14–28 days, so this is indicative). Shifting saves money only on an hourly spot contract and saves **0 kWh**; its CO₂e effect comes from the destination hours' factors. With electricity included in rent a student saves 0 SEK.",
        "",
        "## 3. Per finding",
        "",
        "| Finding | Flat | Who | Kind | Window | kWh avoided | kWh moved | SEK hourly spot (95 % range) | kg CO₂e | Annual |",
        "|---|---|---|---|---:|---:|---:|---|---:|---|",
    ]
    for i in o["interventions"]:
        ann = (f"{n(i['annual']['kwh']['value'], 0)} kWh ({n(i['annual']['kwh']['low'], 0)}–{n(i['annual']['kwh']['high'], 0)}), "
               f"{n(i['annual']['sek']['value'], 0)} SEK" if i["annual"] else "not extrapolated")
        L.append(f"| {i['title']} ({i['appliance']}) | {i['flat_id']} | {i['owner']} | {i['kind']} | {n(i['window_days'], 0)} d | {n(i['kwh_avoided'], 2)} | {n(i['kwh_moved'], 2)} | "
                 f"{n(i['sek_by_tariff']['hourly_spot'], 2)} ({n(i['ci95_sek_hourly'][0], 2)}–{n(i['ci95_sek_hourly'][1], 2)}) | {n(i['co2_kg'], 3)} | {ann} |")
    a = o["annual_supported"]
    L += [
        "",
        "## 4. Annual projections (only where the data supports one)",
        "",
        f"Supported for persistent equipment / always-on / fixed-hour patterns only: {', '.join(a['ids'])}. Central values sum to **{n(a['kwh_central_sum'], 0)} kWh**, **{n(a['sek_central_sum'], 0)} SEK** (hourly spot) and **{n(a['co2_central_sum'], 1)} kg CO₂e** per year, assuming the October pattern persists unchanged; {a['note']}.",
        "",
        "Not extrapolated: heating while away (weather-dependent) and timing shifts (price-dependent). Four autumn weeks cannot establish their annual effect; rebound effects are only covered by the stated scenario ranges.",
        "",
        "## 5. Per resident (defensible allocation)",
        "",
        "Resident-controlled actions are shared household actions. The table shows each flat's combined resident-controlled potential and its average per resident of **that flat**. It is not divided across all 25 students, and equipment repairs are not attributed to residents.",
        "",
        "| Flat | Residents | kWh (flat) | SEK hourly spot (flat) | kg CO₂e (flat) | kWh per resident (avg) | SEK per resident (avg) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for fl, r in o["per_flat"].items():
        rc, pr = r["resident_controlled"], r["per_resident_average"]
        L.append(f"| {fl} | {r['residents']} | {n(rc['kwh'], 2)} | {n(rc['sek_hourly_spot'], 2)} | {n(rc['co2_kg'], 3)} | {n(pr['kwh'], 2)} | {n(pr['sek_hourly_spot'], 2)} |")
    L += [
        "",
        "## 6. Assumptions and uncertainty",
        "",
        "- Appliance identities are inferred from load shapes (no labels in the data).",
        "- “Avoidable” is a simulation if the household acts fully (adoption 1); each finding also has an assumption range (e.g. F005 15.7–62.8 kWh) and a 95 % day-bootstrap range.",
        "- Findings are statistical patterns (PLAUSIBLE), not confirmed faults or confirmed waste; a technician or resident confirms.",
        "- SEK is the spot-energy component only (excl. VAT, network fees, energy tax, markup, fixed fees), conditional on the contract.",
        "- Carbon uses the synthetic operational hourly factor (not marginal or lifecycle).",
        "- Occupancy is a simulated sensor estimate; missing readings are excluded, never treated as zero.",
        "",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    main()

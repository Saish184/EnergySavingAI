"""Final consistency audit across opportunities.json, eda_results.json and the Markdown reports.

Checks every scenario for: an explicit time period, kWh/SEK/kgCO2e arithmetic consistency, interval sanity,
tariff labelling, and the measured / inferred / hypothetical separation. Writes reports/consistency_audit.md.
Exit code 1 on any failure.   Run: python analysis/audit_consistency.py
"""
import json
import sys

import pandas as pd

from common import PROCESSED, REPORTS

J = json.loads((REPORTS / "opportunities.json").read_text())
EDA = json.loads((REPORTS / "eda_results.json").read_text())
hours = pd.read_csv(PROCESSED / "prices_clean.csv")
P_MIN, P_MAX = hours.spot_sek_per_kwh.min(), hours.spot_sek_per_kwh.max()
C_MIN, C_MAX = hours.carbon_gco2e_per_kwh.min(), hours.carbon_gco2e_per_kwh.max()
AVG = J["valuation"]["time_average_spot_sek_per_kwh"]
rows, fails = [], 0


def check(area, name, ok, detail=""):
    global fails
    fails += not ok
    rows.append((area, name, "PASS" if ok else "FAIL", detail))


ENUM = {"measured", "inferred", "hypothetical", "simulated", "unknown"}
for o in J["opportunities"]:
    oid = o["id"].split("_")[0]
    check(oid, "exactly one central scenario", sum(s["role"] == "central" for s in o["scenarios"]) == 1)
    ec = o["evidence_classification"]
    check(oid, "evidence vocabulary is the fixed enum", set(ec.values()) <= ENUM, ec)
    check(oid, "consumption=measured, pattern=measured, identity=inferred, avoidability=hypothetical, savings=simulated",
          (ec["consumption"], ec["pattern"], ec["appliance_identity"], ec["avoidability"], ec["savings"])
          == ("measured", "measured", "inferred", "hypothetical", "simulated"))
    check(oid, "waste unconfirmed and not verified", o["waste_status"] == "unconfirmed" and o["verification_status"] == "not_verified")
    for s in o["scenarios"]:
        tag = f"{oid}/{s['role']}"
        p = s.get("period", {})
        check(tag, "period labelled (UTC window, hours, label)",
              all(k in p for k in ("window_start_utc", "window_end_utc_exclusive", "window_hours", "label", "observed_hours_used")),
              p.get("label", ""))
        expect = 336 if oid == "O3" else 672
        check(tag, f"window = {expect} h", p.get("window_hours") == expect, p.get("window_hours"))
        check(tag, "tariff applicability stated", bool(s.get("tariff_applicability")))
        if s["type"] == "reduction":
            check(tag, "time-average value = kWh x time-average spot", abs(s["value_spot_timeavg_sek"] - s["kwh"] * AVG) <= 0.011,
                  f"{s['value_spot_timeavg_sek']} vs {s['kwh'] * AVG:.3f}")
            if s["kwh"] > 0:
                g = 1000 * s["co2e_kg"] / s["kwh"]
                sek = s["value_spot_hourly_sek"] / max(s["kwh"] - s["kwh_in_unpriced_hours"], 1e-9)
                check(tag, "implied gCO2e/kWh within hourly factor range", C_MIN - 0.5 <= g <= C_MAX + 0.5, f"{g:.1f} g/kWh")
                check(tag, "implied SEK/kWh within hourly price range", P_MIN - 0.01 <= sek <= P_MAX + 0.01, f"{sek:.3f} SEK/kWh")
                lo, hi = s["ci95_kwh"]
                check(tag, "kWh point estimate inside its 95 % CI", lo - 0.01 <= s["kwh"] <= hi + 0.01, f"{s['kwh']} in [{lo}, {hi}]")
        else:
            check(tag, "load shift: 0 kWh and 0 SEK on non-hourly tariffs", s["kwh"] == 0 and s["value_spot_timeavg_sek"] == 0)
            check(tag, "load shift: moved kWh and events reported", s["kwh_moved"] > 0 and s["events"] > 0)

# F002 time period, rate reconciliation
o3 = next(o for o in J["opportunities"] if o["id"].startswith("O3"))
c3 = next(s for s in o3["scenarios"] if s["role"] == "central")
rate = o3["savings_rate_while_unrepaired"]
check("O3", "central kWh = excess rate x 332 observed post-step hours",
      abs(c3["kwh"] - rate["w"] / 1000 * c3["period"]["observed_hours_used"]) < 0.05, rate["reconciliation"])
check("O3", "28-day figure only as an explicitly labelled persistence projection",
      "kwh_per_28_days_if_persistent" in rate and "persistence" in J["rankings"]["comparability_note"])
check("O3", "EDA S3 uses the same 14-day window", EDA["scenarios"]["S3_F002_fridge_fault"].get("period_days") == 14)
lo, hi = EDA["scenarios"]["S3_F002_fridge_fault"]["ci95_kwh"]
check("O3", "EDA S3 CI is a 14-day CI (no zero padding)", hi - lo < 2, f"[{lo}, {hi}]")

# F007 occupancy denominators
den = next(o for o in J["opportunities"] if o["id"].startswith("O1"))["observed_evidence"]["occupancy_denominators"]
f7, f1 = den["F007"], den["F001"]
check("O1", "F007: known + unknown occupancy = 672", f7["occupancy_known"] + f7["occupancy_unknown"] == 672, f7)
check("O1", "F007: heater-on unoccupied (56) = cold with known outdoor (55) + outdoor unknown (1)",
      f7["unoccupied_heater_on"] == f7["unoccupied_cold_heater_reading_valid"] + f7["unoccupied_outdoor_unknown"])
check("O1", "F007: 0 of 55 cold unoccupied hours heater off", f7["unoccupied_cold_heater_off"] == 0 and f7["unoccupied_cold_heater_reading_valid"] == 55)
check("O1", "F001: 141 of 142 unoccupied hours have a valid reading, all off",
      f1["unoccupied_heater_reading_valid"] == 141 and f1["unoccupied_heater_on"] == 0)
check("O1", "F001: 123 of 123 cold unoccupied valid hours off", f1["unoccupied_cold_heater_off"] == f1["unoccupied_cold_heater_reading_valid"] == 123)
check("O1", "unknown occupancy never counted as unoccupied (hypothetical scenario only)",
      next(o for o in J["opportunities"] if o["id"].startswith("O1"))["scenarios"][-1]["role"] == "upper_hypothetical")

# Text-level consistency
opp_md = (REPORTS / "opportunity_report.md").read_text()
res_md = (REPORTS / "research_report.md").read_text()
check("text", "opportunity report no longer claims a blanket 28-day window", "over the 28 observed days" not in opp_md)
check("text", "research report: stale S3 CI removed", "23.4 (14.8–31.9)" not in res_md)
check("text", "research report: heater denominators state their base", "with a valid heater reading" in res_md)

# --------------------------------------------------------------------------- write report
ISSUES = [
    ("F002 savings were tabulated under 'over the 28 observed days'", "They cover only the 14 post-step days (2026-10-15T00Z to 2026-10-29T00Z, 336 h, 332 observed).",
     "Every scenario now carries a `period` block; O3 rows are labelled 14 days; the 28-day figure (47.29 kWh) exists only as a labelled persistence projection."),
    ("F002 95 % CI (14.9–32.0 kWh) resampled 28 days, 14 of them zero-padded pre-step days", "Inflated the interval roughly 20-fold.",
     "Bootstrap now resamples only the scenario's own window: 22.97–23.79 kWh (opportunities) / 22.96–23.76 (EDA)."),
    ("F001 '0 of 142 unoccupied hours' and the verifier treated a missing heater reading as 0 kWh", "Violated the missing-is-not-zero rule (1 missing reading).",
     "Stated as 0 kWh in 141 of 141 valid readings (142 unoccupied); verifier no longer coerces missing to 0."),
    ("F007 counts 64 / 56 / 55 and F001 142 / 123 appeared without their bases", "Readers could not reconcile them.",
     "`occupancy_denominators` block lists every base; 56 = 55 cold hours + 1 hour with unknown outdoor temperature."),
    ("Evidence quality used free text ('conditional simulation (depends on repair)')", "Not machine-checkable for the engine/coach.",
     "Added `evidence_classification` with a fixed enum plus `waste_status: unconfirmed` and `verification_status: not_verified`."),
]
md = ["# Consistency audit", "", "_Generated by `analysis/audit_consistency.py`._", "",
      f"**Result: {len(rows) - fails}/{len(rows)} checks passed.**", "",
      "## Issues found and fixed in this audit", "", "| Issue | Effect | Fix |", "|---|---|---|",
      *[f"| {a} | {b} | {c} |" for a, b, c in ISSUES], "",
      "## Labelling rules now enforced", "",
      "- **Measured:** cleaned hourly consumption and the anomaly/timing pattern itself.",
      "- **Inferred:** appliance identity (from the load signature). It must be confirmed by the student before it is named without a '-like' suffix.",
      "- **Hypothetical:** whether consumption is avoidable, and whether the student's tariff rewards the change.",
      "- **Simulated:** every savings number. It stays 'potential' until the student confirms, and is never 'verified' without post-intervention data.",
      "- Every scenario states its UTC window, its hours, the observed hours used, and which tariffs its SEK value applies to.",
      "", "## Check results", "", "| Area | Check | Result | Detail |", "|---|---|---|---|",
      *[f"| {a} | {n} | {r} | {str(d)[:160]} |" for a, n, r, d in rows], ""]
(REPORTS / "consistency_audit.md").write_text("\n".join(md))
print(f"{len(rows) - fails}/{len(rows)} checks passed")
sys.exit(1 if fails else 0)

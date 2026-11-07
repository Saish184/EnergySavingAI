"""Independent verification of reports/opportunities.json.

- Recomputes each opportunity's headline numbers through a SEPARATE code path: from the per-file cleaned
  outputs (readings_clean.csv, context_clean.csv, prices_clean.csv) with plain Python/zoneinfo time handling,
  not from analytical_table.csv or pandas tz conversion.
- Cross-checks overlapping figures against reports/eda_results.json.
- Re-runs analysis/opportunities.py and checks the JSON/Markdown are byte-identical (determinism).
- Checks structure (every opportunity has the 8 required sections and exactly one central scenario),
  DST coverage facts, and that the original dataset is unchanged.
Exit code 1 on any failure.  Run: python analysis/verify_opportunities.py
"""
import csv
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from common import ORIGINAL_FILES, PROCESSED, REPORTS, ROOT

STO = ZoneInfo("Europe/Stockholm")
T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def close(a, b, tol=0.011):
    return a is not None and b is not None and abs(a - b) <= tol


def rows(name):
    with open(PROCESSED / name, newline="") as f:
        return list(csv.DictReader(f))


def fnum(x):
    return float(x) if x not in ("", None) else None


J = json.loads((REPORTS / "opportunities.json").read_text())
EDA = json.loads((REPORTS / "eda_results.json").read_text())
OPP = {o["id"]: o for o in J["opportunities"]}


def scen(oid, role):
    return next(s for s in OPP[oid]["scenarios"] if s["role"] == role)


# ---------------------------------------------------------------- independent data load
kwh = {}  # (appliance_id, hour) -> kWh or None
for r in rows("readings_clean.csv"):
    kwh[(r["appliance_id"], int(r["hour_idx"]))] = fnum(r["energy_kwh"])
price, carbon = {}, {}
for r in rows("prices_clean.csv"):
    h = int((datetime.strptime(r["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) - T0).total_seconds() // 3600)
    price[h], carbon[h] = fnum(r["spot_sek_per_kwh"]), fnum(r["carbon_gco2e_per_kwh"])
occ, outdoor = {}, {}
for r in rows("context_clean.csv"):
    h = int((datetime.strptime(r["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) - T0).total_seconds() // 3600)
    occ[(r["flat_id"], h)] = fnum(r["occupants_home"])
    outdoor[h] = fnum(r["outdoor_temp_c"])
lh = {h: (T0 + timedelta(hours=h)).astimezone(STO).hour for h in range(672)}


def val(pairs):
    """pairs: list of (hour, kWh) -> (kWh, SEK hourly, kgCO2e)"""
    k = sum(v for _, v in pairs)
    s = sum(v * price[h] for h, v in pairs if price[h] is not None)
    c = sum(v * carbon[h] / 1000 for h, v in pairs)
    return k, s, c


# ---------------------------------------------------------------- coverage / DST
P = J["period"]
local = [(T0 + timedelta(hours=h)).astimezone(STO) for h in range(672)]
check("672 UTC intervals", P["hourly_intervals"] == 672 == len(price))
a, b = datetime(2026, 10, 1, tzinfo=STO), datetime(2026, 10, 29, tzinfo=STO)
check("local 1-28 Oct = 673 elapsed hours", (b.astimezone(timezone.utc) - a.astimezone(timezone.utc)).total_seconds() / 3600 == 673
      == P["elapsed_hours_local_calendar_1_to_28_oct"])
check("671 distinct naive wall-clock hours", len({x.replace(tzinfo=None) for x in local}) == 671 == P["unique_naive_local_wall_clock_times"])
check("25 Oct local has 25 h, 29 Oct has 1 h",
      sum(x.date().isoformat() == "2026-10-25" for x in local) == 25 and sum(x.date().isoformat() == "2026-10-29" for x in local) == 1)

# ---------------------------------------------------------------- O1
o1 = [(h, kwh[("F007-A07", h)] or 0.0) for h in range(672) if occ[("F007", h)] == 0]
k, s, c = val(o1)
u = scen("O1_F007_heating_unoccupied", "upper_measured")
check("O1 upper (all unoccupied hours) kWh/SEK/CO2e independent", close(k, u["kwh"]) and close(s, u["value_spot_hourly_sek"]) and close(c, u["co2e_kg"], 0.002), (k, s, c))
empty = sorted(h for h, _ in o1)
runs, cur = [], [empty[0]]
for h in empty[1:]:
    (cur.append(h) if h == cur[-1] + 1 else (runs.append(cur), cur := [h]))
runs.append(cur)
k2, s2, c2 = val([(h, kwh[("F007-A07", h)] or 0.0) for run in runs if len(run) >= 2 for h in run])
cc = scen("O1_F007_heating_unoccupied", "central")
check("O1 central (absences >= 2 h) independent", close(k2, cc["kwh"]) and close(s2, cc["value_spot_hourly_sek"]), (k2, s2))
check("O1 episodes = 52", len(runs) == OPP["O1_F007_heating_unoccupied"]["observed_evidence"]["unoccupied_episodes"] == 52)
f001 = [h for h in range(672) if occ[("F001", h)] == 0]
check("O1 comparator: F001 heater 0 kWh in all unoccupied hours", all((kwh[("F001-A07", h)] or 0) == 0 for h in f001) and len(f001) == 142)

# ---------------------------------------------------------------- O2
vals5 = [(h, v) for h in range(672) if (v := kwh[("F005-A06", h)]) is not None]
peer_min = sorted(min(v for hh in range(672) if (v := kwh[(f"F00{i}-A06", hh)]) is not None) for i in (1, 2, 3, 4, 6, 7, 8))[3]
f5min = min(v for _, v in vals5)
k, s, c = val([(h, max(0.0, min(v - peer_min, f5min - peer_min))) for h, v in vals5])
u = scen("O2_F005_elevated_base_load", "upper_measured")
check("O2 full-excess kWh/SEK/CO2e independent", close(k, u["kwh"]) and close(s, u["value_spot_hourly_sek"]) and close(c, u["co2e_kg"], 0.002), (k, s, c))
check("O2 central = 50 % of full excess", close(scen("O2_F005_elevated_base_load", "central")["kwh"], u["kwh"] / 2))

# ---------------------------------------------------------------- O3
cp = 336  # 2026-10-15T00:00Z
pre = [v for h in range(cp) if (v := kwh[("F002-A01", h)]) is not None]
post = [(h, v) for h in range(cp, 672) if (v := kwh[("F002-A01", h)]) is not None]
pm = sum(pre) / len(pre)
k, s, c = val([(h, max(0.0, v - pm)) for h, v in post])
cc = scen("O3_F002_refrigerator_step", "central")
check("O3 changepoint at 2026-10-15T00:00Z", OPP["O3_F002_refrigerator_step"]["observed_evidence"]["changepoint_utc"] == "2026-10-15T00:00:00Z")
check("O3 central kWh/SEK/CO2e independent", close(k, cc["kwh"]) and close(s, cc["value_spot_hourly_sek"]) and close(c, cc["co2e_kg"], 0.002), (k, s, c))

# ---------------------------------------------------------------- O4
peer_med = {}
for hr in range(24):
    vs = sorted(v for f in ("F001", "F002", "F003", "F005", "F006", "F007", "F008") for h in range(672)
                if lh[h] == hr and (v := kwh[(f"{f}-A05", h)]) is not None)
    n = len(vs); peer_med[hr] = vs[n // 2] if n % 2 else (vs[n // 2 - 1] + vs[n // 2]) / 2
k, s, c = val([(h, max(0.0, v - peer_med[lh[h]])) for h in range(672) if 9 <= lh[h] <= 16 and (v := kwh[("F004-A05", h)]) is not None])
cc = scen("O4_F004_daytime_electronics", "central")
check("O4 central kWh/SEK/CO2e independent", close(k, cc["kwh"]) and close(s, cc["value_spot_hourly_sek"]) and close(c, cc["co2e_kg"], 0.002), (k, s, c))

# ---------------------------------------------------------------- O5
events = [(f, h, v) for f in range(1, 9) for h in range(672) if (v := kwh[(f"F00{f}-A04", h)]) is not None and v > 0.1]
check("O5 108 events, all at 20:00 local", len(events) == 108 and all(lh[h] == 20 for _, h, _ in events))
sv, cv = 0.0, 0.0
for _, h, v in events:
    d = next(x for x in range(h, h + 25) if lh[x] == 21)
    if price[h] is not None and price[d] is not None:
        sv += v * (price[h] - price[d])
    cv += v * (carbon[h] - carbon[d]) / 1000
cc = scen("O5_dishwasher_price_timing", "central")
check("O5 central (21:00 start) SEK/CO2e independent", close(sv, cc["value_spot_hourly_sek"]) and close(cv, cc["co2e_kg"], 0.002), (sv, cv))
check("O5 load shift has zero kWh and zero time-average value", all(s_["kwh"] == 0 and s_["value_spot_timeavg_sek"] == 0
                                                                     for s_ in OPP["O5_dishwasher_price_timing"]["scenarios"]))

# ---------------------------------------------------------------- cross-check vs EDA results
S = EDA["scenarios"]
check("EDA S1 == O1 upper_measured", close(S["S1_F007_heater_off_when_empty"]["saving_kwh"], scen("O1_F007_heating_unoccupied", "upper_measured")["kwh"]))
check("EDA S2 == O2 full excess", close(S["S2_F005_always_on_A06"]["saving_kwh"], scen("O2_F005_elevated_base_load", "upper_measured")["kwh"]))
check("EDA S3 == O3 central", close(S["S3_F002_fridge_fault"]["saving_kwh"], scen("O3_F002_refrigerator_step", "central")["kwh"]))
check("EDA S5 == O4 central", close(S["S5_F004_daytime_electronics"]["saving_kwh"], scen("O4_F004_daytime_electronics", "central")["kwh"]))
check("EDA S6 == O5 price-optimal", close(S["S6_dishwasher_delay_start"]["saving_sek_hourly_spot"], scen("O5_dishwasher_price_timing", "upper")["value_spot_hourly_sek"]))

# ---------------------------------------------------------------- structure
REQ = ["observed_evidence", "data_quality_flags", "anomaly_vs_waste", "intervention", "counterfactual", "scenarios",
       "uncertainty", "actionability", "evidence_quality", "statistical_confidence", "action_feasibility", "recommendation_status"]
for oid, o in OPP.items():
    check(f"{oid}: required sections present", all(k in o for k in REQ), [k for k in REQ if k not in o])
    check(f"{oid}: exactly one central scenario", sum(s_["role"] == "central" for s_ in o["scenarios"]) == 1)
    check(f"{oid}: every scenario states tariff applicability", all(s_.get("tariff_applicability") for s_ in o["scenarios"]))
check("5 opportunities", len(OPP) == 5)

# ---------------------------------------------------------------- determinism + originals
h_before = {p: hashlib.sha256((REPORTS / p).read_bytes()).hexdigest() for p in ("opportunities.json", "opportunity_report.md")}
subprocess.run([sys.executable, str(ROOT / "analysis" / "opportunities.py")], check=True, capture_output=True, cwd=ROOT)
h_after = {p: hashlib.sha256((REPORTS / p).read_bytes()).hexdigest() for p in h_before}
check("opportunities.py is deterministic (byte-identical re-run)", h_before == h_after)
check("analytical table hash matches JSON", hashlib.sha256((PROCESSED / "analytical_table.csv").read_bytes()).hexdigest()
      == J["inputs_sha256"]["data/processed/analytical_table.csv"])
for f in ORIGINAL_FILES:
    check(f"original unchanged: {f}", hashlib.sha256((ROOT / f).read_bytes()).hexdigest() == J["original_dataset_sha256"][f])
check("originals identical to git HEAD", subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *ORIGINAL_FILES], cwd=ROOT).returncode == 0)

fails = [x for x in results if not x[1]]
for n, p, d in results:
    print(f"[{'PASS' if p else 'FAIL'}] {n}" + (f"  {d}" if not p else ""))
print(f"\n{len(results) - len(fails)}/{len(results)} checks passed")
sys.exit(1 if fails else 0)

"""Independent validation checks on the cleaned outputs. Exit code 1 on any failure.
Run:  python analysis/validate.py   (after clean_data.py)
"""
import hashlib
import json
import subprocess
import sys

import numpy as np
import pandas as pd

from common import ORIGINAL_FILES, PROCESSED, ROOT, SPIKE_THRESHOLD_KWH, TZ_LOCAL

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


summary = json.loads((PROCESSED / "cleaning_summary.json").read_text())
t = pd.read_csv(PROCESSED / "analytical_table.csv")
raw = pd.read_csv(ROOT / "energy_readings.csv", dtype=str, keep_default_na=False)
log = pd.read_csv(PROCESSED / "cleaning_log.csv", dtype=str, keep_default_na=False)

# 1. originals untouched
for f in ORIGINAL_FILES:
    h = hashlib.sha256((ROOT / f).read_bytes()).hexdigest()
    check(f"original unchanged (hash): {f}", h == summary["original_sha256"][f])
git = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *ORIGINAL_FILES], cwd=ROOT)
check("originals identical to git HEAD", git.returncode == 0)

# 2. grid shape & keys
check("analytical table has 37,632 rows", len(t) == 37632, len(t))
check("unique flat x appliance x hour", not t.duplicated(["appliance_id", "timestamp_utc"]).any())
check("8 flats x 7 channels", t.appliance_id.nunique() == 56 and t.flat_id.nunique() == 8)
check("appliance prefix matches flat", (t.appliance_id.str[:4] == t.flat_id).all())
check("672 hours per channel", (t.groupby("appliance_id").size() == 672).all())
check("reading_id unique where present", t.reading_id.dropna().is_unique)

# 3. values
ok = t[t.energy_status == "ok"]
check("valid kWh within [0, spike threshold]", ok.energy_kwh.between(0, SPIKE_THRESHOLD_KWH).all())
check("no zero-filling: every non-ok status has NaN energy", t.loc[t.energy_status != "ok", "energy_kwh"].isna().all())
check("every NaN energy has a non-ok status", (t.energy_kwh.isna() == (t.energy_status != "ok")).all())
raw_missing = (raw.energy_value.str.strip().isin(["", "N/A"])).sum()
check("raw empty/N/A count preserved as missing (minus duplicates)",
      (t.energy_status.isin(["missing_empty", "missing_na"])).sum() <= raw_missing, raw_missing)
check("negative spot prices retained", (t.spot_sek_per_kwh < 0).sum() == 13 * 56)
check("missing price -> missing cost (not zero)", t.loc[t.price_missing, "cost_spot_sek"].isna().all())
check("cost = kWh x price",
      np.allclose(ok.cost_spot_sek.dropna(), (ok.energy_kwh * ok.spot_sek_per_kwh).dropna()))
check("co2e = kWh x factor / 1000", np.allclose(ok.co2e_kg, ok.energy_kwh * ok.carbon_gco2e_per_kwh / 1000))
check("occupancy within 0..residents", (t.occupants_home.dropna() <= t.loc[t.occupants_home.notna(), "residents"]).all())
check("no outdoor sentinel left", (t.outdoor_temp_c.dropna() > -50).all())

# 4. time / DST
utc = pd.to_datetime(t.timestamp_utc, utc=True)
check("UTC period 2026-10-01 .. 2026-10-28 23:00", utc.min() == pd.Timestamp("2026-10-01", tz="UTC")
      and utc.max() == pd.Timestamp("2026-10-28T23:00", tz="UTC"))
check("timestamp_local == tz conversion of UTC",
      (pd.to_datetime(t.timestamp_local, format="ISO8601", utc=True) == utc).all())
loc = utc.dt.tz_convert(TZ_LOCAL)
check("local hour derived consistently", (loc.dt.hour == t.local_hour).all())
one = t[t.appliance_id == "F001-A01"]
check("local date 2026-10-25 has 25 hours", (one.local_date == "2026-10-25").sum() == 25)

# 5. reconciliation raw -> clean
st = summary["stats"]["readings"]
check("row reconciliation: raw - removed duplicates + no-record slots = grid",
      st["raw_rows"] - st["duplicate_exact_removed"] - st["duplicate_conflicts_resolved"]
      + st["status_counts"]["missing_no_record"] == 37632)
check("cleaning log covers every value correction",
      (log.rule == "decimal comma -> decimal point").sum() == st["decimal_comma_fixed"])
raw_comma = raw.energy_value.str.strip().str.match(r"^-?\d+,\d+$").sum()
check("all raw decimal-comma values handled", raw_comma == st["decimal_comma_fixed"], raw_comma)

fail = [r for r in results if not r[1]]
for name, passed, detail in results:
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f"  ({detail})" if detail != "" and not passed else ""))
print(f"\n{len(results) - len(fail)}/{len(results)} checks passed")
sys.exit(1 if fail else 0)

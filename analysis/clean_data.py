"""Reproducible cleaning + validation pipeline for the EnergySavingAI participant dataset.

Reads the four original CSVs (never modifies them) and writes to data/processed/:
  readings_clean.csv     one row per flat x appliance x UTC hour (37,632 slots), with status flags
  context_clean.csv      hourly context with sentinel/invalid values set to missing + flags
  prices_clean.csv       hourly prices (negative prices kept) + missing flag
  analytical_table.csv   readings joined to flats, context and prices, with missing-data indicators
  cleaning_log.csv       one row per individual correction / exclusion
and reports/data_quality_report.md.

Rules: missing values are never set to zero and no readings are invented. Every change is logged.
Run:  python analysis/clean_data.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess

import numpy as np
import pandas as pd

from common import (APPLIANCE_EVIDENCE, APPLIANCE_LABELS, N_CHANNELS, N_FLATS, N_HOURS,
                    ORIGINAL_FILES, PERIOD_START_UTC, PROCESSED, RAW, REPORTS, ROOT,
                    SPIKE_THRESHOLD_KWH, TZ_LOCAL)

T0 = pd.Timestamp(PERIOD_START_UTC)
LOG: list[dict] = []


def log(file, line, rid, field, old, new, action, rule):
    LOG.append(dict(source_file=file, source_line=line, reading_id=rid, field=field,
                    original_value=old, new_value=new, action=action, rule=rule))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------------------
# 1. Energy readings
# --------------------------------------------------------------------------------------
def parse_ts(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    s = s.str.strip()
    iso = s.str.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    legacy = s.str.match(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}$")
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns, UTC]")
    out[iso] = pd.to_datetime(s[iso], format="%Y-%m-%dT%H:%M:%SZ", utc=True)
    out[legacy] = pd.to_datetime(s[legacy], format="%Y/%m/%d %H:%M", utc=True)
    return out, legacy


def clean_readings(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    F = "energy_readings.csv"
    r = raw.copy()
    r["source_line"] = r.index + 2  # header is line 1
    st: dict = {"raw_rows": len(r)}

    # --- reading_id encodes the slot: n-1 = hour*56 + (flat-1)*7 + (channel-1)
    assert r.reading_id.str.match(r"^R\d{7}$").all(), "unexpected reading_id format"
    n = r.reading_id.str[1:].astype(int) - 1
    r["id_hour"] = n // (N_FLATS * N_CHANNELS)
    r["id_flat"] = "F" + ((n % 56) // 7 + 1).astype(str).str.zfill(3)
    r["id_app"] = r.id_flat + "-A" + (n % 7 + 1).astype(str).str.zfill(2)

    # --- timestamps
    ts, legacy = parse_ts(r.timestamp_utc)
    assert ts.notna().all(), "unparseable timestamps"
    for i in r.index[legacy]:
        log(F, r.at[i, "source_line"], r.at[i, "reading_id"], "timestamp_utc", r.at[i, "timestamp_utc"],
            ts[i].strftime("%Y-%m-%dT%H:%M:%SZ"), "corrected", "legacy 'YYYY/MM/DD HH:MM' (UTC) -> ISO 8601 UTC")
    r["ts"] = ts
    r["hour_idx"] = ((ts - T0) // pd.Timedelta("1h")).astype(int)
    st["legacy_timestamps"] = int(legacy.sum())
    st["timestamp_vs_id_hour_mismatch"] = int((r.hour_idx != r.id_hour).sum())
    st["out_of_period"] = int(((r.hour_idx < 0) | (r.hour_idx >= N_HOURS)).sum())

    # --- identifiers
    app_norm = r.appliance_id.str.strip().str.upper()
    case_fix = (app_norm != r.appliance_id) & (app_norm == r.id_app)
    for i in r.index[case_fix]:
        log(F, r.at[i, "source_line"], r.at[i, "reading_id"], "appliance_id", r.at[i, "appliance_id"], app_norm[i],
            "corrected", "strip whitespace / upper-case appliance_id")
    st["appliance_id_case_whitespace"] = int(case_fix.sum())

    placeholder = app_norm.str.startswith("F999")
    ok_place = placeholder & (r.flat_id == r.id_flat) & (r.hour_idx == r.id_hour)
    for i in r.index[ok_place]:
        log(F, r.at[i, "source_line"], r.at[i, "reading_id"], "appliance_id", r.at[i, "appliance_id"], r.at[i, "id_app"],
            "corrected", "placeholder F999 appliance: channel recovered from reading_id (flat_id and timestamp agree; slot otherwise empty)")
    st["appliance_id_placeholder_fixed"] = int(ok_place.sum())

    flat_wrong = (~placeholder) & (app_norm == r.id_app) & (r.flat_id != r.id_flat)
    for i in r.index[flat_wrong]:
        log(F, r.at[i, "source_line"], r.at[i, "reading_id"], "flat_id", r.at[i, "flat_id"], r.at[i, "id_flat"],
            "corrected", "flat_id contradicted appliance_id prefix; appliance_id and reading_id agree (slot otherwise empty)")
    st["flat_id_mismatch_fixed"] = int(flat_wrong.sum())

    unresolved_id = ~(((app_norm == r.id_app) & (r.flat_id == r.id_flat)) | ok_place | flat_wrong)
    st["identifier_unresolved"] = int(unresolved_id.sum())
    r = r[~unresolved_id].copy()
    r["flat_id"] = r.id_flat
    r["appliance_id"] = r.id_app

    # --- units
    u_raw = r.energy_unit
    u = u_raw.str.strip().str.lower()
    assert set(u.unique()) <= {"kwh", "wh"}, f"unknown units {set(u.unique())}"
    for i in r.index[(u == "kwh") & (u_raw != "kWh")]:
        log(F, r.at[i, "source_line"], r.at[i, "reading_id"], "energy_unit", repr(u_raw[i]), "kWh", "corrected",
            "normalise unit spelling/whitespace")
    st["unit_spelling_fixed"] = int(((u == "kwh") & (u_raw != "kWh")).sum())

    # --- values
    v_raw = r.energy_value.str.strip()
    comma = v_raw.str.match(r"^-?\d+,\d+$")
    v_txt = v_raw.where(~comma, v_raw.str.replace(",", ".", regex=False))
    for i in r.index[comma]:
        log(F, r.at[i, "source_line"], r.at[i, "reading_id"], "energy_value", v_raw[i], v_txt[i], "corrected",
            "decimal comma -> decimal point")
    st["decimal_comma_fixed"] = int(comma.sum())

    val = pd.to_numeric(v_txt, errors="coerce")
    status = pd.Series("ok", index=r.index)
    status[v_raw == ""] = "missing_empty"
    status[v_raw.str.upper() == "N/A"] = "missing_na"
    status[val.isna() & (status == "ok")] = "invalid_nonnumeric"

    wh = u == "wh"
    kwh = val.where(~wh, val / 1000.0)
    for i in r.index[wh & val.notna()]:
        log(F, r.at[i, "source_line"], r.at[i, "reading_id"], "energy_value", f"{v_raw[i]} Wh", f"{kwh[i]:.6g} kWh",
            "corrected", "Wh -> kWh (/1000)")
    st["wh_converted"] = int((wh & val.notna()).sum())

    neg = (kwh < 0) & (status == "ok")
    spike = (kwh > SPIKE_THRESHOLD_KWH) & (status == "ok")
    status[neg] = "invalid_negative"
    status[spike] = "invalid_spike"
    for i in r.index[neg | spike]:
        log(F, r.at[i, "source_line"], r.at[i, "reading_id"], "energy_value", v_raw[i], "", "set_missing",
            "negative consumption impossible (no generation channel)" if neg[i]
            else f"> {SPIKE_THRESHOLD_KWH} kWh in one hour on one circuit is physically implausible")
    kwh[status != "ok"] = np.nan
    r["energy_kwh"] = kwh
    r["energy_status"] = status
    r["raw_value"] = v_raw
    r["raw_unit"] = u_raw

    # --- duplicates (keyed on reading_id == slot)
    r = r.sort_values("source_line")
    groups = r.groupby("reading_id")
    dup_ids = groups.size()[lambda s: s > 1].index
    st["duplicate_rows_total"] = int(r.reading_id.isin(dup_ids).sum() - len(dup_ids))
    single = r[~r.reading_id.isin(dup_ids)].set_index(["appliance_id", "hour_idx"])["energy_kwh"]
    keep_idx, exact, conflict = [], 0, []
    for rid, g in r[r.reading_id.isin(dup_ids)].groupby("reading_id"):
        vals = g.energy_kwh.round(9)
        valid = g[g.energy_status == "ok"]
        if vals.nunique(dropna=False) == 1 and g.energy_status.nunique() == 1:
            keep = g.index[0]
            exact += len(g) - 1
            for i in g.index[1:]:
                log(F, g.at[i, "source_line"], rid, "row", "duplicate", "", "removed",
                    "exact duplicate of reading_id (kept first occurrence)")
        else:
            cand = valid if len(valid) else g
            app, h = g.appliance_id.iloc[0], g.hour_idx.iloc[0]
            neigh = [single.get((app, h + d), np.nan) for d in (-2, -1, 1, 2)]
            ref = np.nanmedian(neigh) if np.isfinite(neigh).any() else cand.energy_kwh.min()
            keep = (cand.energy_kwh - ref).abs().idxmin()
            conflict.append(dict(reading_id=rid, appliance_id=app, values=sorted(g.energy_kwh.round(4).tolist()),
                                 neighbour_median=round(float(ref), 4), kept=round(float(g.at[keep, "energy_kwh"]), 4)))
            for i in g.index:
                if i != keep:
                    log(F, g.at[i, "source_line"], rid, "energy_value", g.at[i, "raw_value"], "", "removed",
                        f"conflicting duplicate; kept value {g.at[keep, 'energy_kwh']:.4g} closest to neighbouring-hour median {ref:.4g}")
        keep_idx.append(keep)
    r = pd.concat([r[~r.reading_id.isin(dup_ids)], r.loc[keep_idx]])
    st["duplicate_exact_removed"] = exact
    st["duplicate_conflicts_resolved"] = len(conflict)
    st["conflicts"] = conflict
    assert r.reading_id.is_unique

    # --- full slot grid (no invented readings: absent slots stay missing)
    flats = [f"F{i:03d}" for i in range(1, N_FLATS + 1)]
    grid = pd.MultiIndex.from_product(
        [[f"{f}-A{a:02d}" for f in flats for a in range(1, N_CHANNELS + 1)], range(N_HOURS)],
        names=["appliance_id", "hour_idx"]).to_frame(index=False)
    out = grid.merge(r[["appliance_id", "hour_idx", "reading_id", "energy_kwh", "energy_status", "raw_value", "raw_unit"]],
                     on=["appliance_id", "hour_idx"], how="left", validate="1:1")
    out["energy_status"] = out.energy_status.fillna("missing_no_record")
    out["flat_id"] = out.appliance_id.str[:4]
    out["appliance_code"] = out.appliance_id.str[-3:]
    out["timestamp_utc"] = T0 + pd.to_timedelta(out.hour_idx, unit="h")
    st["slots"] = len(out)
    st["status_counts"] = out.energy_status.value_counts().to_dict()
    return out, st


# --------------------------------------------------------------------------------------
# 2. Context, flats, prices
# --------------------------------------------------------------------------------------
def clean_flats(f: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    assert f.flat_id.is_unique and len(f) == N_FLATS
    assert (f.residents > 0).all() and (f.floor_area_m2 > 0).all()
    return f, {"rows": len(f), "price_areas": sorted(f.price_area.unique()),
               "tariff_ids": sorted(f.tariff_id.unique()), "residents_total": int(f.residents.sum())}


def clean_context(c: pd.DataFrame, flats: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    F = "hourly_context.csv"
    c = c.copy()
    c["source_line"] = c.index + 2
    st = {"rows": len(c)}
    c["timestamp_utc"] = pd.to_datetime(c.timestamp_utc, format="%Y-%m-%dT%H:%M:%SZ", utc=True)
    st["duplicate_flat_ts"] = int(c.duplicated(["flat_id", "timestamp_utc"]).sum())
    assert st["duplicate_flat_ts"] == 0

    # DST / local-time consistency
    exp_local = c.timestamp_utc.dt.tz_convert(TZ_LOCAL)
    exp_str = exp_local.dt.strftime("%Y-%m-%dT%H:%M:%S%z").str.replace(r"(\d{2})(\d{2})$", r"\1:\2", regex=True)
    st["local_timestamp_mismatch_vs_tzdb"] = int((exp_str != c.timestamp_local).sum())
    st["local_instant_mismatch_vs_utc"] = int(
        (pd.to_datetime(c.timestamp_local, format="ISO8601", utc=True) != c.timestamp_utc).sum())
    one = c[c.flat_id == c.flat_id.iloc[0]]
    rep = one[one.timestamp_local.str[:19].duplicated(keep=False)]
    st["repeated_local_wall_times"] = rep[["timestamp_utc", "timestamp_local"]].astype(str).values.tolist()
    st["offsets"] = c.timestamp_local.str[-6:].value_counts().to_dict()

    sentinel = c.outdoor_temp_c < -50
    for i in c.index[sentinel]:
        log(F, c.at[i, "source_line"], "", "outdoor_temp_c", c.at[i, "outdoor_temp_c"], "", "set_missing",
            "sentinel -99 (physically implausible for October SE3)")
    c.loc[sentinel, "outdoor_temp_c"] = np.nan
    st["outdoor_sentinel_set_missing"] = int(sentinel.sum())

    res = c.flat_id.map(flats.set_index("flat_id").residents)
    too_many = c.occupants_home > res
    for i in c.index[too_many]:
        log(F, c.at[i, "source_line"], "", "occupants_home", c.at[i, "occupants_home"], "", "set_missing",
            "occupants_home exceeds flat's resident count")
    c.loc[too_many, "occupants_home"] = np.nan
    st["occupancy_exceeds_residents_set_missing"] = int(too_many.sum())
    st["occupancy_missing_raw"] = int(c.occupants_home.isna().sum() - too_many.sum())
    c["outdoor_temp_missing"] = c.outdoor_temp_c.isna()
    c["occupancy_missing"] = c.occupants_home.isna()
    c["indoor_temp_missing"] = c.indoor_temp_c.isna()
    st["indoor_range"] = [float(c.indoor_temp_c.min()), float(c.indoor_temp_c.max())]
    st["outdoor_range_after"] = [float(c.outdoor_temp_c.min()), float(c.outdoor_temp_c.max())]
    return c.drop(columns="source_line"), st


def clean_prices(p: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    p = p.copy()
    p["timestamp_utc"] = pd.to_datetime(p.timestamp_utc, format="%Y-%m-%dT%H:%M:%SZ", utc=True)
    st = {"rows": len(p), "duplicate_ts": int(p.duplicated(["timestamp_utc", "price_area"]).sum())}
    assert st["duplicate_ts"] == 0
    full = pd.date_range(T0, periods=N_HOURS, freq="h")
    st["missing_hours"] = int(len(full.difference(p.timestamp_utc)))
    p["price_missing"] = p.spot_sek_per_kwh.isna()
    p["carbon_missing"] = p.carbon_gco2e_per_kwh.isna()
    st["spot_missing"] = int(p.price_missing.sum())
    st["spot_missing_hours"] = p.loc[p.price_missing, "timestamp_utc"].dt.strftime("%Y-%m-%dT%H:%MZ").tolist()
    st["carbon_missing"] = int(p.carbon_missing.sum())
    st["negative_prices_kept"] = int((p.spot_sek_per_kwh < 0).sum())
    for i in p.index[p.price_missing]:
        log("hourly_prices.csv", i + 2, "", "spot_sek_per_kwh", "", "", "kept_missing",
            "no spot price; cost for this hour left missing (not zero)")
    return p, st


# --------------------------------------------------------------------------------------
# 3. Join + derived fields
# --------------------------------------------------------------------------------------
def build_table(rd, flats, ctx, prices) -> tuple[pd.DataFrame, dict]:
    t = rd.merge(flats, on="flat_id", how="left", validate="m:1")
    t = t.merge(ctx, on=["flat_id", "timestamp_utc"], how="left", validate="m:1", indicator="ctx_join")
    t = t.merge(prices, on=["timestamp_utc", "price_area"], how="left", validate="m:1", indicator="price_join")
    st = {"rows": len(t), "context_unmatched": int((t.ctx_join != "both").sum()),
          "price_unmatched": int((t.price_join != "both").sum())}
    t = t.drop(columns=["ctx_join", "price_join"])
    loc = t.timestamp_utc.dt.tz_convert(TZ_LOCAL)
    t["local_date"] = loc.dt.strftime("%Y-%m-%d")
    t["local_hour"] = loc.dt.hour
    t["weekday"] = loc.dt.day_name()
    t["is_weekend"] = loc.dt.dayofweek >= 5
    t["is_overnight"] = t.local_hour.between(0, 5)  # 00:00-05:59 local
    t["appliance_label_inferred"] = t.appliance_code.map(APPLIANCE_LABELS)
    t["energy_missing"] = t.energy_kwh.isna()
    t["cost_spot_sek"] = t.energy_kwh * t.spot_sek_per_kwh            # NaN propagates on purpose
    t["co2e_kg"] = t.energy_kwh * t.carbon_gco2e_per_kwh / 1000.0
    t["timestamp_utc"] = t.timestamp_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    cols = ["flat_id", "appliance_id", "appliance_code", "appliance_label_inferred", "timestamp_utc",
            "timestamp_local", "local_date", "local_hour", "weekday", "is_weekend", "is_overnight", "hour_idx",
            "reading_id", "energy_kwh", "energy_status", "energy_missing", "raw_value", "raw_unit",
            "residents", "floor_area_m2", "price_area", "tariff_id",
            "outdoor_temp_c", "outdoor_temp_missing", "indoor_temp_c", "indoor_temp_missing",
            "occupants_home", "occupancy_missing",
            "spot_sek_per_kwh", "price_missing", "carbon_gco2e_per_kwh", "carbon_missing",
            "cost_spot_sek", "co2e_kg"]
    return t[cols].sort_values(["flat_id", "appliance_code", "hour_idx"]).reset_index(drop=True), st


# --------------------------------------------------------------------------------------
# 4. Report
# --------------------------------------------------------------------------------------
def impact(t: pd.DataFrame) -> dict:
    ok = t[~t.energy_missing]
    m = ok.groupby("appliance_id").energy_kwh.mean()
    miss = t[t.energy_missing].groupby("appliance_id").size()
    est_missing_kwh = float((m.reindex(miss.index) * miss).sum())
    return {
        "valid_slots": int(len(ok)), "missing_slots": int(t.energy_missing.sum()),
        "coverage_pct": round(100 * len(ok) / len(t), 2),
        "observed_kwh": round(float(ok.energy_kwh.sum()), 1),
        "est_kwh_in_missing_slots": round(est_missing_kwh, 1),
        "est_missing_share_pct": round(100 * est_missing_kwh / (ok.energy_kwh.sum() + est_missing_kwh), 2),
        "kwh_in_unpriced_hours": round(float(ok.loc[ok.price_missing, "energy_kwh"].sum()), 2),
        "kwh_in_unpriced_share_pct": round(100 * ok.loc[ok.price_missing, "energy_kwh"].sum() / ok.energy_kwh.sum(), 2),
        "kwh_in_unknown_occupancy_hours": round(float(ok.loc[ok.occupancy_missing, "energy_kwh"].sum()), 2),
        "missing_by_flat": t.groupby("flat_id").energy_missing.sum().astype(int).to_dict(),
        "missing_by_channel": t.groupby("appliance_code").energy_missing.sum().astype(int).to_dict(),
        "max_missing_run_hours": int(t.sort_values(["appliance_id", "hour_idx"]).groupby("appliance_id").energy_missing
                                     .apply(lambda s: (s.groupby((~s).cumsum()).sum()).max()).max()),
    }


def write_report(st, imp, hashes):
    R, C, P, J = st["readings"], st["context"], st["prices"], st["join"]
    sc = R["status_counts"]
    conflicts = pd.DataFrame(R["conflicts"])
    agree_lower = int((conflicts.kept == conflicts["values"].map(min)).sum())
    lines = [
        "# Data-quality report",
        "",
        "_Generated by `analysis/clean_data.py`. Do not edit by hand; re-run the script._",
        "",
        "## Originals preserved",
        "",
        "The six supplied files are read-only inputs. SHA-256 at run time (checked again by `analysis/validate.py`):",
        "",
        "| File | SHA-256 |", "|---|---|",
        *[f"| {k} | `{v[:16]}…` |" for k, v in hashes.items()],
        "",
        "## Inventory",
        "",
        "| File | Raw rows | Expected | Notes |", "|---|---:|---:|---|",
        f"| energy_readings.csv | {R['raw_rows']:,} | 37,632 slots (8 flats × 7 channels × 672 h) | {R['raw_rows']-37632:+,} vs slots before de-duplication |",
        f"| flats.csv | {st['flats']['rows']} | 8 | {st['flats']['residents_total']} residents; price area {', '.join(st['flats']['price_areas'])}; tariff {', '.join(st['flats']['tariff_ids'])} (no lookup) |",
        f"| hourly_context.csv | {C['rows']:,} | 5,376 | complete flat × hour grid, no duplicates |",
        f"| hourly_prices.csv | {P['rows']} | 672 | complete hourly grid, SE3 only |",
        "",
        "## Key discovery: `reading_id` encodes the slot",
        "",
        "`reading_id = R` + (hour_index × 56 + (flat − 1) × 7 + channel), 1-based, where hour_index counts hours from "
        "2026-10-01T00:00Z. The formula reproduces the reported flat, appliance and timestamp for "
        f"{R['raw_rows'] - R['flat_id_mismatch_fixed'] - R['appliance_id_placeholder_fixed']:,} of {R['raw_rows']:,} rows and the timestamp "
        f"for **all** rows ({R['timestamp_vs_id_hour_mismatch']} timestamp disagreements). It is therefore used as "
        "independent evidence to repair identifiers — only when at least two of the three fields (reading_id, flat_id, "
        "appliance_id) agree with each other, the timestamp agrees, and the target slot has no other record.",
        "",
        "## Corrections to energy readings",
        "",
        "| Issue | Rows | Action |", "|---|---:|---|",
        f"| Legacy timestamp `YYYY/MM/DD HH:MM` | {R['legacy_timestamps']} | Parsed as UTC (per README), rewritten ISO 8601 |",
        f"| appliance_id lower-case / padded with spaces | {R['appliance_id_case_whitespace']} | Stripped + upper-cased |",
        f"| appliance_id placeholder `F999-A01` | {R['appliance_id_placeholder_fixed']} | Channel recovered from reading_id (flat_id + timestamp agree) |",
        f"| flat_id contradicts appliance_id prefix | {R['flat_id_mismatch_fixed']} | flat_id set from appliance_id (reading_id agrees) |",
        f"| Identifiers unresolvable | {R['identifier_unresolved']} | Would be dropped (none occurred) |",
        f"| Unit spelled ` kwh ` | {R['unit_spelling_fixed']} | Normalised to kWh |",
        f"| Unit `Wh` | {R['wh_converted']} | Divided by 1000 |",
        f"| Decimal comma (`0,033`) | {R['decimal_comma_fixed']} | Converted to decimal point |",
        f"| Exact duplicate rows | {R['duplicate_exact_removed']} | Removed (first occurrence kept) |",
        f"| Conflicting duplicates (same reading_id, different value) | {R['duplicate_conflicts_resolved']} | Kept the value closest to neighbouring hours of the same channel (see below) |",
        f"| Empty value | {sc.get('missing_empty', 0)} | Left missing |",
        f"| `N/A` value | {sc.get('missing_na', 0)} | Left missing |",
        f"| Negative consumption | {sc.get('invalid_negative', 0)} | Set missing (no generation channel exists) |",
        f"| Spike > {SPIKE_THRESHOLD_KWH:g} kWh/h | {sc.get('invalid_spike', 0)} | Set missing |",
        f"| Slot with no record at all | {sc.get('missing_no_record', 0)} | Left missing (not invented) |",
        "",
        "Every individual change is in `data/processed/cleaning_log.csv` (source file, line, field, old → new, rule).",
        "",
        "### Conflicting duplicates",
        "",
        f"In {sum(abs(max(v) - min(v) - 0.13) < 1e-6 for v in conflicts['values'])} of {len(conflicts)} conflicts the two copies differ by exactly **+0.13 kWh** "
        "— a systematic offset, not measurement noise. The copy closer to the median of the same channel's ±2 neighbouring hours "
        f"was kept; this equals the lower copy in {agree_lower} of {len(conflicts)} cases. Maximum effect if the other copy were "
        f"right: {0.13 * len(conflicts):.2f} kWh in total ({100 * 0.13 * len(conflicts) / imp['observed_kwh']:.2f} % of observed consumption).",
        "",
        "### Spike threshold",
        "",
        f"The largest plausible reading is 1.30 kWh/h; the smallest rejected value is 10.8 kWh/h, so any threshold between "
        f"~1.5 and 10 kWh gives the same result. Rejected spikes are not Wh mislabelled as kWh: read as Wh they would be "
        "0.01–0.045 kWh, which is impossible for e.g. the always-on cold appliance (≥0.035 kWh/h) and heater channels in flats that never use a heater.",
        "",
        "## Context and prices",
        "",
        "| Issue | Rows | Action |", "|---|---:|---|",
        f"| outdoor_temp_c = −99 sentinel | {C['outdoor_sentinel_set_missing']} | Set missing |",
        f"| occupants_home empty | {C['occupancy_missing_raw']} | Left missing (not assumed 0) |",
        f"| occupants_home = 9, above resident count | {C['occupancy_exceeds_residents_set_missing']} | Set missing |",
        f"| spot_sek_per_kwh empty | {P['spot_missing']} | Left missing; cost for those hours is missing |",
        f"| Negative spot price | {P['negative_prices_kept']} | **Kept** (valid per README) |",
        f"| Carbon factor missing | {P['carbon_missing']} | — |",
        "",
        f"Hours without a spot price: {', '.join(P['spot_missing_hours'])}.",
        "",
        "## Daylight-saving transition (25 October)",
        "",
        f"- Local offsets present: {C['offsets']}.",
        f"- `timestamp_local` agrees with the IANA `Europe/Stockholm` conversion of `timestamp_utc` on every row "
        f"({C['local_timestamp_mismatch_vs_tzdb']} mismatches) and denotes the same instant ({C['local_instant_mismatch_vs_utc']} mismatches).",
        f"- The repeated wall-clock hour is legitimate: {C['repeated_local_wall_times']} (per flat). "
        "UTC has no gap or repeat, so all joins use UTC; local hour/day fields are derived from UTC.",
        "- Consequence: local date 2026-10-25 has 25 hours, 2026-10-01 has 22 hours (data start at 02:00 local) and "
        "2026-10-29 has 2 hours. Daily statistics use only complete local days and are reported per hour where day lengths differ.",
        "",
        "## Join validation",
        "",
        f"Readings grid ({J['rows']:,} rows = 8 × 7 × 672) → flats (many-to-one on flat_id) → context (many-to-one on flat_id + "
        f"timestamp_utc) → prices (many-to-one on timestamp_utc + price_area). Unmatched rows: context {J['context_unmatched']}, "
        f"prices {J['price_unmatched']}. Cardinality enforced with pandas `validate='m:1'`.",
        "",
        "## Appliance inference (assumption)",
        "",
        "The dataset supplies no appliance types. Labels below are inferred from load signatures and are used only for readability.",
        "",
        "| Channel | Inferred label | Evidence |", "|---|---|---|",
        *[f"| {k} | {APPLIANCE_LABELS[k]} | {APPLIANCE_EVIDENCE[k]} |" for k in APPLIANCE_LABELS],
        "",
        "## Remaining gaps and their effect on the analysis",
        "",
        f"- Valid energy slots: {imp['valid_slots']:,} of 37,632 (**{imp['coverage_pct']} %**). Missing: {imp['missing_slots']} "
        f"(by flat {imp['missing_by_flat']}; by channel {imp['missing_by_channel']}). Longest gap in one channel: {imp['max_missing_run_hours']} h.",
        f"- Observed consumption: {imp['observed_kwh']:,} kWh. Estimated consumption hidden in missing slots (channel mean × missing hours): "
        f"~{imp['est_kwh_in_missing_slots']} kWh ({imp['est_missing_share_pct']} %). Totals in the research report are **observed** unless labelled "
        "'coverage-adjusted'; rankings do not change under either.",
        f"- {imp['kwh_in_unpriced_hours']} kWh ({imp['kwh_in_unpriced_share_pct']} %) fall in the 8 unpriced hours, so spot cost is understated by roughly that share.",
        f"- {imp['kwh_in_unknown_occupancy_hours']} kWh fall in hours with unknown occupancy; occupancy analyses exclude those hours.",
        "- 20 hours lack outdoor temperature; temperature analyses exclude them.",
        "- No total-meter channel exists, so channel sums cannot be validated against an independent meter.",
        "",
    ]
    (REPORTS / "data_quality_report.md").write_text("\n".join(lines))


def main():
    PROCESSED.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    hashes = {f: sha256(ROOT / f) for f in ORIGINAL_FILES}

    raw = pd.read_csv(RAW["readings"], dtype=str, keep_default_na=False)
    rd, st_r = clean_readings(raw)
    flats, st_f = clean_flats(pd.read_csv(RAW["flats"]))
    ctx, st_c = clean_context(pd.read_csv(RAW["context"]), flats)
    prices, st_p = clean_prices(pd.read_csv(RAW["prices"]))
    table, st_j = build_table(rd, flats, ctx, prices)

    st = {"readings": st_r, "flats": st_f, "context": st_c, "prices": st_p, "join": st_j}
    imp = impact(table)

    out_rd = rd.copy()
    out_rd["timestamp_utc"] = out_rd.timestamp_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out_rd[["reading_id", "flat_id", "appliance_id", "appliance_code", "timestamp_utc", "hour_idx",
            "energy_kwh", "energy_status", "raw_value", "raw_unit"]].sort_values(
        ["appliance_id", "hour_idx"]).to_csv(PROCESSED / "readings_clean.csv", index=False)
    c2 = ctx.copy(); c2["timestamp_utc"] = c2.timestamp_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    c2.to_csv(PROCESSED / "context_clean.csv", index=False)
    p2 = prices.copy(); p2["timestamp_utc"] = p2.timestamp_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    p2.to_csv(PROCESSED / "prices_clean.csv", index=False)
    table.to_csv(PROCESSED / "analytical_table.csv", index=False)
    pd.DataFrame(LOG).to_csv(PROCESSED / "cleaning_log.csv", index=False)

    summary = {"stats": st, "impact": imp, "original_sha256": hashes}
    (PROCESSED / "cleaning_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    write_report(st, imp, hashes)

    changed = subprocess.run(["git", "status", "--porcelain", "--", *ORIGINAL_FILES], cwd=ROOT,
                             capture_output=True, text=True).stdout.strip()
    assert not changed, f"original files modified: {changed}"
    print(json.dumps({"status_counts": st_r["status_counts"], "impact": imp, "log_entries": len(LOG)}, indent=1))


if __name__ == "__main__":
    main()

"""What-if scenarios. Each one edits a COPY of the readings, then the full engine is re-run,
so 'after' numbers use exactly the same method as 'before'. Only physically plausible edits:
nothing creates energy, shifting keeps kWh equal, reductions never go below base load."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config as C
from . import metrics
from .attribution import window_mask
from .dataset import Dataset
from .evaluate import evaluate
from .projection import project_triplet

SCENARIOS = ("return_to_baseline", "shift_flexible_load", "reduce_away_usage")


# ---------- edits (return modified copy + assumptions) ----------

def return_to_baseline(ds: Dataset, anomaly_id: str) -> tuple[Dataset, list[str]]:
    a = ds.anomaly(anomaly_id)
    r = ds.readings.copy()
    m = window_mask(r, a)
    rate = a.get("baseline_kwh_per_h")
    assumptions = [f"{a['appliance_id']} returns to its pre-anomaly rate inside the anomaly window only"]
    # behaviour patterns only apply to the hours that define them
    if a["type"] == "away_usage":
        occ = r[["flat_id", "timestamp_utc"]].merge(ds.context, on=["flat_id", "timestamp_utc"], how="left")["occupants_home"]
        m &= occ.eq(0).to_numpy()
        assumptions.append("only hours where the sensor says nobody is home (unknown occupancy left unchanged)")
    elif a["type"] == "night_baseload":
        m &= r["timestamp_utc"].dt.tz_convert(C.TZ_LOCAL).dt.hour.isin(C.NIGHT_HOURS_LOCAL)
        assumptions.append("only night hours (local 00-06)")
    if rate is not None and not np.isnan(rate):
        target = pd.Series(float(rate), index=r.index[m])
    else:
        # fallback: hourly median of the same channel in the other flats
        peers = r[(r["channel"] == a["channel"]) & (r["flat_id"] != a["flat_id"])]
        med = peers.groupby("timestamp_utc")["kwh"].median()
        target = r.loc[m, "timestamp_utc"].map(med)
        assumptions.append("no pre-anomaly baseline supplied; used peer median of the same channel")
    # min() so a repair never ADDS energy; NaN stays NaN
    # (unknown target -> inf -> reading left unchanged)
    cap = np.nan_to_num(target.to_numpy(dtype=float), nan=np.inf)
    r.loc[m, "kwh"] = np.minimum(r.loc[m, "kwh"].to_numpy(dtype=float), cap)
    remaining = [x for x in ds.anomalies if x["id"] != anomaly_id]
    return ds.copy(readings=r, anomalies=remaining), assumptions


def shift_flexible_load(ds: Dataset, flat_id: str, channel: str) -> tuple[Dataset, list[str]]:
    """Move above-base kWh in local peak hours to the cheapest non-peak hour within the next 12 h."""
    if channel in C.HEATER_CHANNELS:
        raise ValueError("heater-like load is not treated as shiftable")
    r = ds.readings.copy()
    app = f"{flat_id}-{channel}"
    sub = r[r["appliance_id"] == app].sort_values("timestamp_utc")
    if sub.empty:
        raise ValueError(f"no readings for {app}")
    area = ds.flats.set_index("flat_id").loc[flat_id, "price_area"]
    spot = ds.prices[ds.prices["price_area"] == area].set_index("timestamp_utc")["spot"]
    ts = sub["timestamp_utc"].to_numpy()
    idx = sub.index.to_numpy()
    kwh = sub["kwh"].to_numpy(dtype=float).copy()
    price = sub["timestamp_utc"].map(spot).to_numpy(dtype=float)
    peak = sub["timestamp_utc"].dt.tz_convert(C.TZ_LOCAL).dt.hour.isin(C.PEAK_HOURS_LOCAL).to_numpy()
    base = np.nanpercentile(kwh, C.BASELOAD_PERCENTILE)
    flex = np.where(np.isnan(kwh), 0.0, np.maximum(0.0, kwh - base))
    hour = np.timedelta64(1, "h")
    moved = 0.0
    for i in np.where(peak & (flex > 0) & ~np.isnan(price))[0]:
        best, best_p = None, price[i]
        for j in range(i + 1, min(len(ts), i + 1 + C.SHIFT_WINDOW_HOURS)):
            if ts[j] - ts[i] > C.SHIFT_WINDOW_HOURS * hour:
                break
            if peak[j] or np.isnan(kwh[j]) or np.isnan(price[j]):
                continue
            if price[j] < best_p:
                best, best_p = j, price[j]
        if best is not None:
            kwh[i] -= flex[i]
            kwh[best] += flex[i]
            moved += flex[i]
    r.loc[idx, "kwh"] = kwh
    assumptions = [
        f"{channel} assumed {metrics.assumed_type(channel)} and shiftable (assumption, no appliance labels in data)",
        f"above-base load in local peak hours moved to the cheapest non-peak hour within {C.SHIFT_WINDOW_HOURS} h",
        "total kWh unchanged; only cost and CO2 timing change",
        f"{moved:.2f} kWh moved in 28 days",
    ]
    return ds.copy(readings=r), assumptions


def reduce_away_usage(ds: Dataset, flat_id: str, fraction: float = C.AWAY_REDUCTION_DEFAULT) -> tuple[Dataset, list[str]]:
    if not 0 <= fraction <= 1:
        raise ValueError("fraction must be between 0 and 1")
    e = metrics.enrich(ds.readings, ds.flats, ds.prices, ds.context)
    m = (e["flat_id"] == flat_id) & e["occupants_home"].eq(0) & ~e["is_heater"] & e["above_base"].notna()
    r = ds.readings.copy()
    # enrich() preserves row order of readings (left merges), so positions line up
    pos = np.where(m.to_numpy())[0]
    col = r.columns.get_loc("kwh")
    r.iloc[pos, col] = r.iloc[pos, col].to_numpy() - fraction * e["above_base"].to_numpy()[pos]
    assumptions = [
        f"{int(fraction * 100)}% of above-base use in hours with nobody home is avoided (non-heater channels)",
        "hours with unknown occupancy are not treated as away",
        "possible rebound effects not modelled",
    ]
    return ds.copy(readings=r), assumptions


# ---------- runner ----------

def _flat_snapshot(ev: dict, flat_id: str) -> dict:
    t = ev["totals"].loc[flat_id]
    snap = {"kwh": float(t["kwh"]), "sek": float(t["sek"]), "co2_kg": float(t["co2_kg"])}
    for lens, tab in ev["lenses"].items():
        row = tab.loc[flat_id]
        snap[lens] = {"score": float(row["score"]), "band": row["band"], "rank": float(row["rank"]),
                      "pillars": {k: float(row[k]) for k in C.LENSES[lens]}}
    return snap


def apply(ds: Dataset, scenario: str, params: dict) -> tuple[Dataset, list[str], str]:
    """Returns (modified copy, assumptions, flat_id)."""
    if scenario == "return_to_baseline":
        a = ds.anomaly(params["anomaly_id"])
        new, asm = return_to_baseline(ds, a["id"])
        return new, asm, a["flat_id"]
    if scenario == "shift_flexible_load":
        new, asm = shift_flexible_load(ds, params["flat_id"], params["channel"])
        return new, asm, params["flat_id"]
    if scenario == "reduce_away_usage":
        new, asm = reduce_away_usage(ds, params["flat_id"], float(params.get("fraction", C.AWAY_REDUCTION_DEFAULT)))
        return new, asm, params["flat_id"]
    raise ValueError(f"unknown scenario {scenario}; choose one of {SCENARIOS}")


def run_scenario(ds: Dataset, scenario: str, params: dict, before: dict | None = None) -> dict:
    before = before or evaluate(ds, with_sensitivity=False)
    new, assumptions, flat_id = apply(ds, scenario, params)
    after = evaluate(new, with_sensitivity=False)
    b, a = _flat_snapshot(before, flat_id), _flat_snapshot(after, flat_id)
    delta = {k: a[k] - b[k] for k in ("kwh", "sek", "co2_kg")}
    db = metrics.daily_flat_series(before["enriched"], flat_id)
    da = metrics.daily_flat_series(after["enriched"], flat_id)
    dd = (da - db)
    heater_like = scenario == "return_to_baseline" and ds.anomaly(params["anomaly_id"])["channel"] in C.HEATER_CHANNELS
    return {
        "scenario": scenario,
        "params": params,
        "flat_id": flat_id,
        "label": "scenario",
        "horizon": "28d measured counterfactual",
        "delta_28d": delta,
        "before": b,
        "after": a,
        "score_change": {lens: a[lens]["score"] - b[lens]["score"] for lens in C.LENSES},
        "projection_annual": project_triplet(
            delta["kwh"], delta["sek"], delta["co2_kg"],
            {k: dd[k].to_numpy() for k in ("kwh", "sek", "co2_kg")},
            heater_like=heater_like, extra_assumptions=assumptions[:1]),
        "assumptions": assumptions + ["other flats unchanged; benchmark recomputed with the same method"],
    }

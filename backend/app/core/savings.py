"""Savings engine: one or several interventions on ONE flat's hourly trajectory.

For each run it returns (all over explicit windows, all deterministic):
  ladder        observed, expected baseline, unexplained excess, avoidable estimate, counterfactual consumption
                (per intervention, observed hours only - the estimand of the validated opportunity analysis)
  delta         saving kWh / spot SEK / kgCO2e of the COMBINED trajectory (load reductions and shifts separated)
  valuation     money per tariff (spot component only), carbon with hourly factors
  uncertainty   sampling: 95 % day-block bootstrap of the saving within the window (seeded)
                scenario: min-max of the saving over each intervention's documented parameter grid
                evidence: the detector's statistics and claim level (NOT a probability)
  scores        before / after for both lenses, frozen references, computed on the coverage-adjusted matrix
  overlap       sum of individual savings minus combined saving (double counting avoided)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config as C
from . import interventions as IV
from .hourly import CHANNELS, AdjustedTrajectory, Trajectory, combine, difference, totals
from .pillars import adjusted_matrix
from .projection import project_triplet
from .valuation import value

KEYS = ("kwh", "sek_spot_hourly", "sek_spot_timeavg_proxy", "co2e_kg")


def _window(anoms: list[dict]) -> tuple[int, int]:
    """Observation window of the saving: the whole period, except that a lasting step change only exists from the day
    it starts (F002: 14 days). Scattered patterns (timing, heating, blocks, base load) use all 28 observed days."""
    starts = [int(np.where(a["cells"])[0].min() // 24 * 24) if a["type"] == "fault_step_change" else 0 for a in anoms]
    return min(starts), 672


def _daily(fd, base, cf, window) -> pd.DataFrame:
    rows = []
    for d0 in range(window[0], window[1], 24):
        r = difference(fd, base, cf, window=(d0, d0 + 24))
        rows.append({"kwh": r["kwh"], "sek": r["sek_spot_hourly"], "co2_kg": r["co2e_kg"]})
    return pd.DataFrame(rows)


def _boot(v: np.ndarray, seed_offset: int = 0) -> list[float]:
    rng = np.random.default_rng(C.BOOTSTRAP_SEED + seed_offset)
    s = rng.choice(v, size=(C.BOOTSTRAP_DRAWS, v.size), replace=True).sum(axis=1)
    return [float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))]


def _snap(ev: dict, fl: str) -> dict:
    out = {}
    for lens, tab in ev["lenses"].items():
        row = tab.loc[fl]
        out[lens] = {"score": float(row["score"]), "band": row["band"], "rank": float(row["rank"]),
                     "pillars": {k: float(row[k]) for k in C.LENSES[lens]}}
    return out


def ladder(ds, a: dict, params: dict | None) -> dict:
    """Quantity ladder for ONE intervention (observed hours of the anomaly's cells)."""
    fd = ds.flats[a["flat_id"]]
    x = fd.kwh[a["channel"]].to_numpy(dtype=float)
    obs = a["cells"] & np.isfinite(x)
    ops, p = IV.ops_for(ds, a, params)
    cf, _ = combine(fd.kwh, ops)
    kind = IV.KIND.get(a["type"], "reduction")
    saving = difference(fd, fd.kwh, cf)["kwh"]
    observed = float(np.nansum(x[obs]))
    out = {
        "kind": kind, "anomaly_id": a["id"], "params": p,
        "window_hours": int(a["cells"].sum()), "observed_hours": int(obs.sum()),
        "observed_kwh": observed,
        "expected_baseline_kwh": observed - float(np.sum(np.minimum(np.maximum(x[obs] - a["ref"][obs], 0.0), a["cap"][obs])))
        if kind == "reduction" else observed,
        "unexplained_excess_kwh": float(a["excess_kwh"]) if kind == "reduction" else 0.0,
        "avoidable_estimate_kwh": float(saving) if kind == "reduction" else 0.0,
        "counterfactual_kwh": observed - float(saving) if kind == "reduction" else observed,
        "kwh_moved": float(sum(op.share * x[h0] for op in ops for h0, _ in op.moves if np.isfinite(x[h0]))) if kind == "shift" else 0.0,
        "labels": {"observed_kwh": "measured", "expected_baseline_kwh": "inferred (frozen reference)",
                   "unexplained_excess_kwh": "measured relative to the stated reference", "avoidable_estimate_kwh": "simulated (assumption)",
                   "counterfactual_kwh": "simulated"},
    }
    if a["type"] == "heater_pattern":
        out["unexplained_excess_upper_kwh"] = float(a["stats"]["kwh_any_absence"])
    return out


def run(ds, items: list[dict], before: dict | None = None, tariff: dict | None = None, with_range: bool = True) -> dict:
    """items: [{"anomaly_id": str, "params": {...}}] - all for the same flat."""
    from .evaluate import evaluate
    anoms = [ds.anomaly(i["anomaly_id"]) for i in items]
    flats = {a["flat_id"] for a in anoms}
    if len(flats) != 1:
        raise ValueError("combine interventions per flat (one flat per call)")
    fl = flats.pop()
    fd = ds.flats[fl]
    ops, resolved = [], []
    for a, it in zip(anoms, items):
        o, p = IV.ops_for(ds, a, it.get("params"))
        ops += o
        resolved.append(p)
    kinds = {IV.KIND.get(a["type"], "reduction") for a in anoms}
    cf, logs = combine(fd.kwh, ops)                                       # observed accounting
    window = _window(anoms)
    d = difference(fd, fd.kwh, cf)
    daily = _daily(fd, fd.kwh, cf, window)
    individual = [difference(fd, fd.kwh, combine(fd.kwh, IV.ops_for(ds, a, it.get("params"))[0])[0]) for a, it in zip(anoms, items)]
    overlap = {k: float(sum(i[k] for i in individual) - d[k]) for k in KEYS}

    # scenario range: each intervention over its parameter grid (others at their resolved values)
    rng = None
    if with_range:
        vals = []
        for j, a in enumerate(anoms):
            for g in IV.grid(a):
                its = [dict(i) for i in items]
                its[j] = {"anomaly_id": a["id"], "params": {**(items[j].get("params") or {}), **g}}
                o = [op for a2, it in zip(anoms, its) for op in IV.ops_for(ds, a2, it.get("params"))[0]]
                vals.append(difference(fd, fd.kwh, combine(fd.kwh, o)[0]))
        rng = {k: [float(min(v[k] for v in vals)), float(max(v[k] for v in vals))] for k in ("kwh", "sek_spot_hourly", "co2e_kg")}

    # scores on the coverage-adjusted matrix (interventions also act on frozen imputations of missing hours)
    X = pd.DataFrame(adjusted_matrix(fd, None, ds.refs), columns=CHANNELS)
    adj, _ = combine(AdjustedTrajectory.of(X), ops)
    before = before or evaluate(ds, with_sensitivity=False)
    after = evaluate(ds, {fl: adj}, with_sensitivity=False)
    b, af = _snap(before, fl), _snap(after, fl)
    projectable = kinds == {"reduction"} and all(a["type"] in C.PROJECTABLE_TYPES for a in anoms)
    kind = "shift" if kinds == {"shift"} else ("reduction" if kinds == {"reduction"} else "mixed")
    return {
        "flat_id": fl, "items": [{"anomaly_id": a["id"], "type": a["type"], "params": p} for a, p in zip(anoms, resolved)],
        "kind": kind, "window": {"start_utc": str(pd.Timestamp(C.PERIOD_START) + pd.Timedelta(hours=window[0])),
                                 "end_utc_exclusive": str(pd.Timestamp(C.PERIOD_START) + pd.Timedelta(hours=window[1])),
                                 "days": (window[1] - window[0]) / 24},
        "ladder": [ladder(ds, a, it.get("params")) for a, it in zip(anoms, items)],
        "delta": {"kwh": d["kwh"], "sek_spot_hourly": d["sek_spot_hourly"], "co2e_kg": d["co2e_kg"],
                  "sek_spot_timeavg_proxy": d["sek_spot_timeavg_proxy"]},
        "valuation": value(d, "shift" if kind == "shift" else "reduction", tariff),
        "uncertainty": {
            "sampling_ci95": {"kwh": _boot(daily.kwh.to_numpy()), "sek_spot_hourly": _boot(daily.sek.to_numpy(), 1),
                              "co2e_kg": _boot(daily.co2_kg.to_numpy(), 2),
                              "method": f"day-block bootstrap over the {len(daily)} window days ({C.BOOTSTRAP_DRAWS} draws, seed {C.BOOTSTRAP_SEED})"},
            "scenario_range": rng, "scenario_method": "min-max over each intervention's documented parameter grid",
            "evidence": {a["id"]: {"status": a["status"].name, "stats": a["stats"]} for a in anoms},
            "not_included": ["intervention adoption beyond the 'adoption' parameter", "rebound beyond the stated range",
                             "future weather and prices", "tariff (a condition, not a probability)"],
        },
        "scores": {"before": b, "after": af, "change": {lens: af[lens]["score"] - b[lens]["score"] for lens in C.LENSES}},
        "overlap": overlap, "missing_hour_moves": sum(lg["moved_into_missing_hour"] for lg in logs),
        "projection_annual": project_triplet({"kwh": daily.kwh.to_numpy(), "sek": daily.sek.to_numpy(), "co2_kg": daily.co2_kg.to_numpy()},
                                             projectable, None if projectable else
                                             "not extrapolated: heating depends on weather, timing on prices; only persistent equipment/base-load patterns are"),
    }

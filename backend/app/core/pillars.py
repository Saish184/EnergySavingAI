"""Additive energy partition and the four pillars (0-100, higher = better).

Partition of a flat's coverage-adjusted energy X over the period (frozen local imputation for cells missing at
baseline; intervention deltas included, also where a reading is missing):

    X  =  explained  +  R (resident-attributable excess)  +  F (equipment-fault excess)

  F = sum of excess of manager-responsibility anomalies with status >= PLAUSIBLE
  R = sum of excess of resident/unknown-responsibility anomalies with status >= PLAUSIBLE (one evidence rule for
      every behavioural pattern, incl. heater use with nobody home). peak_usage is NOT excess (timing).
  Excess of anomaly a in hour h:  min(max(X_h - ref_h, 0), cap_h)  on its cells, with FROZEN ref/cap from
  detection; anomalies are applied sequentially on the remainder, so overlapping cells are never counted twice.

Pillars (each kWh appears in exactly one pillar; every pillar is non-increasing in every hourly kWh value;
all scales are frozen references, so no pillar can fall when another flat changes or when energy is saved):
  USE     = 100 * min(1, B_lens / u),   u = explained / eq / days        (B = frozen P20 benchmark)
            apartment lens: explained incl. heater-like use; resident lens: excl. heater-like channels
  WASTE   = 100 * K / (K + R / eq / days)      K = frozen typical intensity (median flat)
  HEALTH  = 100 * K / (K + F / eq / days)      apartment lens only
  TIMING  = 100 * K_T / (K_T + P / eq / days)  P = flexible-appliance kWh in peak-price hours
The ratio form x0/(x0 + e) needs no threshold: 100 at e = 0, 50 when the excess equals a typical flat's level.
"""
from __future__ import annotations

import numpy as np

from .. import config as C
from .claims import Status
from .hourly import CHANNELS, FlatData, Trajectory

CIDX = {c: i for i, c in enumerate(CHANNELS)}


def adjusted_matrix(fd: FlatData, traj: Trajectory | None, R) -> np.ndarray:
    """Coverage-adjusted kWh (672 x 7): observed base + delta; baseline-missing cells = frozen imputation + delta;
    cells missing only in this (modified) input = local imputation from the current data."""
    from .hourly import AdjustedTrajectory
    from .references import local_imputation
    if isinstance(traj, AdjustedTrajectory):
        return traj.base[CHANNELS].to_numpy(dtype=float) + traj.delta[CHANNELS].to_numpy(dtype=float)
    tr = traj if traj is not None else fd.trajectory()
    base = tr.base[CHANNELS].to_numpy(dtype=float)
    delta = tr.delta[CHANNELS].to_numpy(dtype=float)
    fl = fd.flat_id
    frozen_mask, frozen_imp = R.missing[fl], R.imputation[fl]
    X = base.copy()
    X[frozen_mask] = frozen_imp[frozen_mask]
    new_missing = np.isnan(X)
    if new_missing.any():
        X[new_missing] = local_imputation(base)[new_missing]
    return np.nan_to_num(X) + delta


def counts_in(a: dict) -> str | None:
    """Which pillar an anomaly's excess belongs to (None = not counted)."""
    if a["type"] == "peak_usage":
        return None
    if a["responsibility"] == "manager":
        return "health" if a["status"] >= Status.PLAUSIBLE else None
    # every behavioural pattern (incl. heater use with nobody home) counts once it meets the evidence criterion
    # (PLAUSIBLE); counting means "possible avoidable consumption", never "confirmed waste"
    return "waste" if a["status"] >= Status.PLAUSIBLE else None


def anomaly_excess_vector(X: np.ndarray, a: dict) -> np.ndarray:
    j = CIDX[a["channel"]]
    v = np.zeros(X.shape[0])
    m = a["cells"]
    v[m] = np.minimum(np.maximum(X[m, j] - a["ref"][m], 0.0), a["cap"][m])
    return v


def partition(fd: FlatData, traj: Trajectory | None, anomalies: list[dict], R) -> dict:
    X = adjusted_matrix(fd, traj, R)
    work = X.copy()
    F = Rr = Rr_heat = 0.0
    excess = {}
    for a in sorted([a for a in anomalies if a["flat_id"] == fd.flat_id], key=lambda a: (a["responsibility"] != "manager", a["id"])):
        where = counts_in(a)
        e = anomaly_excess_vector(work, a)
        excess[a["id"]] = float(e.sum())
        if where is None:
            continue
        work[:, CIDX[a["channel"]]] -= e
        if where == "health":
            F += float(e.sum())
        else:
            Rr += float(e.sum())
            if a["channel"] in C.HEATER_CHANNELS:
                Rr_heat += float(e.sum())
    heat_j = [CIDX[c] for c in C.HEATER_CHANNELS]
    flex_j = [CIDX[c] for c in C.FLEXIBLE_CHANNELS]
    total = float(X.sum())
    heater_total = float(X[:, heat_j].sum())
    peak = np.isin(fd.local_hour.to_numpy(), sorted(R.peak_hours)) if R.peak_hours else np.zeros(X.shape[0], bool)
    return {
        "total_kwh": total, "heater_kwh": heater_total, "fault_kwh": F, "resident_excess_kwh": Rr,
        "explained_apartment": total - F - Rr,
        "explained_resident": (total - heater_total) - F - (Rr - Rr_heat),
        "flexible_kwh": float(X[:, flex_j].sum()), "peak_flexible_kwh": float(X[peak][:, flex_j].sum()),
        "excess_by_anomaly": excess,
    }


def pillars(fd: FlatData, part: dict, R) -> dict:
    eq, days = R.eq[fd.flat_id], C.PERIOD_DAYS
    out = {}
    for lens in ("apartment", "resident"):
        u = part[f"explained_{lens}"] / eq / days
        use = 100.0 if u <= 0 else 100.0 * min(1.0, R.use_bench[lens] / u)
        waste = 100.0 * R.K / (R.K + part["resident_excess_kwh"] / eq / days)
        timing = 100.0 * R.K_T / (R.K_T + part["peak_flexible_kwh"] / eq / days)
        p = {"use": use, "waste": waste, "timing": timing}
        if lens == "apartment":
            p["health"] = 100.0 * R.K / (R.K + part["fault_kwh"] / eq / days)
        out[lens] = p
    out["intensities"] = {"u_apartment": part["explained_apartment"] / eq / days, "u_resident": part["explained_resident"] / eq / days,
                          "resident_excess_per_eq_day": part["resident_excess_kwh"] / eq / days,
                          "fault_per_eq_day": part["fault_kwh"] / eq / days,
                          "peak_flexible_per_eq_day": part["peak_flexible_kwh"] / eq / days}
    return out

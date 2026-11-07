"""Measured kWh / spot SEK / kgCO2e per flat and channel. Missing kWh stay missing (reported as coverage)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config as C
from .hourly import CHANNELS, N_HOURS, FlatData, Trajectory, totals


def assumed_type(channel: str) -> str:
    return C.ASSUMED_TYPES.get(channel, C.ASSUMED_TYPE_DEFAULT)


def _traj(fd: FlatData, traj: Trajectory | None) -> Trajectory:
    return traj if traj is not None else fd.trajectory()


def flat_totals(ds, trajectories: dict | None = None, partitions: dict | None = None) -> pd.DataFrame:
    rows = {}
    for fl, fd in ds.flats.items():
        tr = _traj(fd, (trajectories or {}).get(fl))
        t = totals(fd, tr)
        peak = np.isin(fd.local_hour.to_numpy(), sorted(ds.refs.peak_hours))
        tp = totals(fd, Trajectory(tr.base.where(pd.Series(peak, index=tr.base.index), np.nan, axis=0),
                                   tr.delta.where(pd.Series(peak, index=tr.delta.index), 0.0, axis=0)))
        obs = int(np.isfinite(fd.kwh.to_numpy(dtype=float)).sum())
        rows[fl] = {
            "kwh": t["kwh"], "sek": t["sek_spot_hourly"], "co2_kg": t["co2e_kg"],
            "kwh_coverage_adjusted": (partitions or {}).get(fl, {}).get("total_kwh", np.nan),
            "hours_observed": obs, "coverage": obs / (len(CHANNELS) * N_HOURS),
            "price_coverage": (t["kwh"] - t["kwh_unpriced"]) / t["kwh"] if t["kwh"] else np.nan,
            "peak_share": tp["kwh"] / t["kwh"] if t["kwh"] else np.nan,
            "residents": fd.residents, "floor_area_m2": fd.floor_area_m2,
        }
    out = pd.DataFrame(rows).T
    out.index.name = "flat_id"
    for k in ("kwh", "sek", "co2_kg"):
        out[f"{k}_per_resident"] = out[k] / out["residents"]          # labelled average, not per person
    out["kwh_per_m2"] = out["kwh"] / out["floor_area_m2"]
    return out.astype(float)


def channel_breakdown(ds, flat_id: str, traj: Trajectory | None = None) -> pd.DataFrame:
    fd = ds.flats[flat_id]
    tr = _traj(fd, traj)
    peak = np.isin(fd.local_hour.to_numpy(), sorted(ds.refs.peak_hours))
    total = totals(fd, tr)["kwh"]
    rows = []
    for c in CHANNELS:
        t = totals(fd, tr, channels=[c])
        x = tr.base[c].to_numpy(dtype=float)
        rows.append({
            "appliance_id": f"{flat_id}-{c}", "channel": c, "kwh": t["kwh"], "sek": t["sek_spot_hourly"], "co2_kg": t["co2e_kg"],
            "hours_observed": int(np.isfinite(x).sum()), "coverage": float(np.isfinite(x).mean()),
            "share_of_flat": t["kwh"] / total if total else np.nan,
            "peak_share": (np.nansum(x[peak]) + tr.delta[c].to_numpy()[peak].sum()) / t["kwh"] if t["kwh"] else np.nan,
            "assumed_type": assumed_type(c), "assumed_type_is_assumption": True,
            "flexible": c in C.FLEXIBLE_CHANNELS, "heater_like": c in C.HEATER_CHANNELS,
        })
    return pd.DataFrame(rows).sort_values("kwh", ascending=False)


def daily_flat_series(fd: FlatData, traj: Trajectory | None = None) -> pd.DataFrame:
    """Daily kWh / spot SEK / kgCO2e (UTC days) of observed base + deltas."""
    tr = _traj(fd, traj)
    rows = []
    for d in range(N_HOURS // 24):
        t = totals(fd, tr, window=(24 * d, 24 * d + 24))
        rows.append({"day": str((pd.Timestamp(C.PERIOD_START) + pd.Timedelta(days=d)).date()),
                     "kwh": t["kwh"], "sek": t["sek_spot_hourly"], "co2_kg": t["co2e_kg"]})
    return pd.DataFrame(rows).set_index("day")

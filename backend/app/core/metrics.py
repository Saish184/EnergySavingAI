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


def local_profile(fd: FlatData, peak_hours: set, tz: str = C.TZ_LOCAL) -> dict:
    """Measured hour-of-day profile and daily totals in LOCAL time (Europe/Stockholm), observed readings only.

    hour_of_day: for each local clock hour, the mean observed kWh per channel (NaN readings excluded, never 0) and their sum,
                 the mean spot price and carbon factor of those hours, and whether the hour is a peak-price hour.
    daily:       measured kWh / spot SEK / kgCO2e per LOCAL date. The period is 2026-10-01 00:00 UTC .. 2026-10-29 00:00 UTC,
                 so the first local day has 22 hours, 25 October has 25 hours (DST ends) and 29 October 1 hour.
    No arithmetic beyond means and sums of measured values; no extrapolation."""
    from .hourly import T0
    utc = pd.date_range(T0, periods=N_HOURS, freq="h", tz="UTC")
    local = utc.tz_convert(tz)
    lh = fd.local_hour.to_numpy()
    x = fd.kwh[CHANNELS].to_numpy(dtype=float)
    price = fd.price.to_numpy(dtype=float)
    carbon = fd.carbon.to_numpy(dtype=float)
    hours = []
    for h in range(24):
        m = lh == h
        by_ch = {c: (float(np.nanmean(x[m, j])) if np.isfinite(x[m, j]).any() else None) for j, c in enumerate(CHANNELS)}
        known = [v for v in by_ch.values() if v is not None]
        p = price[m][np.isfinite(price[m])]
        g = carbon[m][np.isfinite(carbon[m])]
        hours.append({
            "local_hour": h, "hours_in_period": int(m.sum()),
            "mean_kwh": float(sum(known)) if len(known) == len(CHANNELS) else None,
            "mean_kwh_by_channel": by_ch,
            "observed_share": float(np.isfinite(x[m]).mean()) if m.any() else None,
            "mean_spot_sek_per_kwh": float(p.mean()) if p.size else None,
            "mean_carbon_g_per_kwh": float(g.mean()) if g.size else None,
            "is_peak": h in peak_hours,
        })
    dates = np.array([str(d) for d in local.date])
    daily = []
    for d in sorted(set(dates)):
        pos = np.where(dates == d)[0]
        a, b = int(pos.min()), int(pos.max()) + 1                # local dates are contiguous runs of UTC hours
        t = totals(fd, window=(a, b))                           # same accounting as every other measured total
        daily.append({
            "local_date": d, "hours_in_period": b - a, "complete_day": bool(b - a >= 23),
            "kwh": t["kwh"], "sek": t["sek_spot_hourly"], "co2_kg": t["co2e_kg"],
            "observed_share": float(np.isfinite(x[a:b]).mean()),
        })
    return {"hour_of_day": hours, "daily": daily}

"""Was the repair worth it? Compare post-repair readings with what the faulty rate would have used.

saving = pre_repair_rate * observed_post_hours - observed_post_kWh
pre_repair_rate = the anomaly's observed_kwh_per_h (the rate if the fault had continued).
Needs >= 7 days of post-repair data, else the finding stays REPAIRED.
VERIFIED only when the 90% bootstrap interval is entirely above zero."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config as C
from .claims import Status, verification_transition


def verify(pre_repair_rate_kwh_per_h: float, post: pd.DataFrame, current: Status,
           simulated: bool = False, n_boot: int = C.BOOTSTRAP_DRAWS, seed: int = C.BOOTSTRAP_SEED) -> dict:
    """post: DataFrame with timestamp_utc, kwh (NaN allowed = missing hour)."""
    p = post.dropna(subset=["kwh"]).copy()
    p["timestamp_utc"] = pd.to_datetime(p["timestamp_utc"], utc=True)
    hours = len(p)
    days_of_data = hours / 24
    out = {"simulated": bool(simulated), "post_hours": hours, "post_days": days_of_data,
           "min_days_required": C.VERIFY_MIN_DAYS, "pre_repair_rate_kwh_per_h": pre_repair_rate_kwh_per_h,
           "horizon": f"{days_of_data:.1f} days measured after repair"}
    if days_of_data < C.VERIFY_MIN_DAYS:
        out.update(status=current.name, saving_kwh=None, interval_90=None,
                   reason=f"needs >= {C.VERIFY_MIN_DAYS} days of post-repair data, has {days_of_data:.1f}")
        return out

    p["day"] = p["timestamp_utc"].dt.floor("D")
    g = p.groupby("day")["kwh"]
    daily_saving = (pre_repair_rate_kwh_per_h * g.count() - g.sum()).to_numpy()
    saving = float(daily_saving.sum())
    rng = np.random.default_rng(seed)
    boots = rng.choice(daily_saving, size=(n_boot, daily_saving.size), replace=True).sum(axis=1)
    lo, hi = (float(np.percentile(boots, q)) for q in C.VERIFY_INTERVAL)
    measured = lo > 0
    status = verification_transition(current, measured)
    out.update(status=status.name, saving_kwh=saving, interval_90=[lo, hi],
               saving_kwh_per_day=saving / daily_saving.size,
               reason="saving measured (90% interval above zero)" if measured
               else "no clear saving yet (90% interval includes zero)")
    if simulated:
        out["reason"] += " - SIMULATED post-repair data, demo only"
    return out


def simulate_post_repair(anomaly: dict, days: int = 14, noise: float = 0.10, seed: int = 0) -> pd.DataFrame:
    """DEMO ONLY: fake post-repair readings at the pre-anomaly baseline rate. Always flagged simulated."""
    rng = np.random.default_rng(seed)
    ts = pd.date_range(C.PERIOD_END, periods=days * 24, freq="h", tz="UTC")
    rate = anomaly.get("baseline_kwh_per_h") or 0.0
    kwh = np.maximum(0.0, rate * (1 + noise * rng.standard_normal(len(ts))))
    return pd.DataFrame({"timestamp_utc": ts, "kwh": kwh, "simulated": True})

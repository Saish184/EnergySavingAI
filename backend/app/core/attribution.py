"""Who can act on excess kWh: the resident, the manager (equipment), or unknown."""
from __future__ import annotations

import numpy as np
import pandas as pd

RESPONSIBILITY = {
    "fault_step_change": "manager",
    "peer_outlier": "manager",
    "away_usage": "resident",
    "night_baseload": "resident",
    "peak_usage": "resident",
    "heater_pattern": "unknown",
}

NOTES = {
    "manager": "equipment issue: the building manager can fix it; residents are not scored on it",
    "resident": "behaviour: residents can change this themselves",
    "unknown": "possible heating opportunity, needs confirmation",
}


def responsibility(anomaly_type: str) -> str:
    return RESPONSIBILITY.get(anomaly_type, "unknown")


def note(resp: str) -> str:
    return NOTES[resp]


def window_mask(readings: pd.DataFrame, a: dict) -> pd.Series:
    ts = readings["timestamp_utc"]
    return (readings["appliance_id"] == a["appliance_id"]) & (ts >= a["start"]) & (ts < a["end"])


def remove_manager_excess(readings: pd.DataFrame, anomalies: list[dict]) -> pd.DataFrame:
    """Copy of readings with manager-attributed excess removed (used by the Resident Actions lens).
    In each manager anomaly window, subtract (observed - baseline) per hour, never below 0.
    Applies at every claim level: residents are never scored on suspected equipment faults."""
    r = readings.copy()
    for a in anomalies:
        if a.get("responsibility") != "manager":
            continue
        obs, base = a.get("observed_kwh_per_h"), a.get("baseline_kwh_per_h")
        if obs is None or base is None or np.isnan(obs) or np.isnan(base):
            continue
        delta = max(0.0, obs - base)
        m = window_mask(r, a)
        r.loc[m, "kwh"] = (r.loc[m, "kwh"] - delta).clip(lower=0)
    return r

"""Who can act on excess kWh: the resident, the manager (equipment), or unknown."""
from __future__ import annotations

import numpy as np
import pandas as pd

RESPONSIBILITY = {
    "fault_step_change": "manager",      # on equipment channels; detector sets "resident" on others
    "base_load_outlier": "resident",     # student first; provider if the load is hard-wired
    "scheduled_block": "resident",
    "heater_pattern": "unknown",
    "peak_usage": "resident",
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

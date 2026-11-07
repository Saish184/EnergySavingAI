"""JSON helpers: numpy/pandas -> plain Python, NaN -> null."""
from __future__ import annotations

import datetime as dt
import math
from enum import Enum

import numpy as np
import pandas as pd


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [jsonable(v) for v in o]
    if isinstance(o, Enum):
        return o.name
    if isinstance(o, (pd.Timestamp, dt.datetime, dt.date)):
        return None if pd.isna(o) else o.isoformat().replace("+00:00", "Z")
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return jsonable(o.tolist())
    if o is pd.NA or o is pd.NaT:
        return None
    return o

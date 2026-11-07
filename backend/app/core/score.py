"""Two lenses over the pillars, combined with a weighted geometric mean.

Geometric mean = a weak pillar can't be hidden by a strong one (unlike an average).
Pillars are floored at 1 so ln() is defined; the arithmetic mean uses the same floored values
so that geometric <= arithmetic always holds (AM-GM)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config as C


def _w(weights: dict) -> dict:
    s = sum(weights.values())
    return {k: v / s for k, v in weights.items()}


def geometric(pillars: dict, weights: dict) -> float:
    w = _w(weights)
    vals = [pillars[k] for k in w]
    if any(v is None or np.isnan(v) for v in vals):
        return float("nan")
    return float(np.exp(sum(w[k] * np.log(max(1.0, pillars[k])) for k in w)))


def arithmetic(pillars: dict, weights: dict) -> float:
    w = _w(weights)
    vals = [pillars[k] for k in w]
    if any(v is None or np.isnan(v) for v in vals):
        return float("nan")
    return float(sum(w[k] * max(1.0, pillars[k]) for k in w))


def band(score: float) -> str | None:
    if score is None or np.isnan(score):
        return None
    for threshold, letter in C.BANDS:
        if score >= threshold:
            return letter
    return "G"


def score_table(pillars: pd.DataFrame, weights: dict) -> pd.DataFrame:
    """pillars: index flat_id, columns = pillar names. Returns pillars + score/arith/band/rank."""
    t = pillars[list(weights)].copy()
    t["score"] = [geometric(row, weights) for row in t.to_dict("records")]
    t["arithmetic_mean"] = [arithmetic(row, weights) for row in t[list(weights)].to_dict("records")]
    t["band"] = t["score"].map(band)
    t["rank"] = t["score"].rank(ascending=False, method="min")
    return t

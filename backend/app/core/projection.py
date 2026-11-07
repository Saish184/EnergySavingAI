"""Annual extrapolation, ONLY for persistent, weather- and price-independent patterns (config.PROJECTABLE_TYPES).

value = mean daily saving over the pattern's observed window x 365; range = day-bootstrap p5-p95 of that mean x 365.
Everything else (heating, load timing, whole-flat totals) is NOT extrapolated: it depends on weather and prices
outside the 4 observed October weeks. Every output is labelled "projection" and carries its assumptions."""
from __future__ import annotations

import numpy as np

from .. import config as C


def project(daily: np.ndarray | None, unit: str, projectable: bool, reason: str | None = None,
            extra_assumptions: list[str] | None = None) -> dict:
    base = {"label": "projection", "horizon": "annual", "unit": unit, "assumptions": list(C.PROJECTION_BASE_ASSUMPTIONS) + (extra_assumptions or [])}
    d = None if daily is None else np.asarray(daily, dtype=float)
    if not projectable or d is None or d.size == 0:
        return {**base, "value": None, "low": None, "high": None, "factor": None,
                "reason": reason or "not extrapolated: depends on weather/prices outside the observed 4 weeks"}
    rng = np.random.default_rng(C.BOOTSTRAP_SEED)
    means = rng.choice(d, size=(C.BOOTSTRAP_DRAWS, d.size), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [5, 95]) * C.ANNUAL_DAYS
    return {**base, "value": float(d.mean() * C.ANNUAL_DAYS), "low": float(min(lo, hi)), "high": float(max(lo, hi)),
            "factor": f"mean daily saving over {d.size} observed days x {C.ANNUAL_DAYS}",
            "range_method": "day-bootstrap p5-p95 of the mean daily saving"}


def project_triplet(daily: dict | None, projectable: bool, reason: str | None = None, extra_assumptions: list[str] | None = None) -> dict:
    daily = daily or {}
    return {
        "kwh": project(daily.get("kwh"), "kWh", projectable, reason, extra_assumptions),
        "sek": project(daily.get("sek"), "SEK (spot only, excl. VAT)", projectable, reason, extra_assumptions),
        "co2_kg": project(daily.get("co2_kg"), "kgCO2e", projectable, reason, extra_assumptions),
    }

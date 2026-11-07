"""Annualise 28-day numbers. Every output is labelled "projection" and carries assumptions."""
from __future__ import annotations

import numpy as np

from .. import config as C


def bootstrap_total(daily: np.ndarray, n: int = C.BOOTSTRAP_DRAWS, seed: int = C.BOOTSTRAP_SEED) -> tuple[float, float]:
    """Resample days with replacement; returns p5/p95 of the 28-day-equivalent total."""
    d = np.asarray(daily, dtype=float)
    d = d[~np.isnan(d)]
    if d.size == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    sums = rng.choice(d, size=(n, d.size), replace=True).mean(axis=1) * C.PERIOD_DAYS
    return float(np.percentile(sums, 5)), float(np.percentile(sums, 95))


def project(value_28d: float, daily: np.ndarray | None, unit: str, heater_like: bool = False,
            extra_assumptions: list[str] | None = None) -> dict:
    factor = C.ANNUAL_FACTOR_HEATER if heater_like else C.ANNUAL_FACTOR
    central = value_28d * factor
    lo, hi = central * (1 - C.PROJECTION_BAND), central * (1 + C.PROJECTION_BAND)
    if central < 0:
        lo, hi = hi, lo
    boot = (float("nan"), float("nan"))
    if daily is not None:
        b5, b95 = bootstrap_total(daily)
        boot = (b5 * factor, b95 * factor)
        if not np.isnan(boot[0]):
            lo, hi = min(lo, boot[0]), max(hi, boot[1])
    assumptions = list(C.PROJECTION_BASE_ASSUMPTIONS)
    assumptions.append("heating season only (182 days)" if heater_like else "28-day pattern assumed to repeat all year")
    assumptions += extra_assumptions or []
    return {
        "label": "projection",
        "horizon": "annual",
        "unit": unit,
        "value": central,
        "low": lo,
        "high": hi,
        "factor": factor,
        "basis_28d": value_28d,
        "bootstrap_low": boot[0],
        "bootstrap_high": boot[1],
        "range_method": "max of ±30% and day-bootstrap p5-p95",
        "assumptions": assumptions,
    }


def project_triplet(kwh: float, sek: float, co2_kg: float, daily: dict | None = None,
                    heater_like: bool = False, extra_assumptions: list[str] | None = None) -> dict:
    """daily: optional {"kwh": array, "sek": array, "co2_kg": array}"""
    daily = daily or {}
    return {
        "kwh": project(kwh, daily.get("kwh"), "kWh", heater_like, extra_assumptions),
        "sek": project(sek, daily.get("sek"), "SEK (spot only, excl. VAT)", heater_like, extra_assumptions),
        "co2_kg": project(co2_kg, daily.get("co2_kg"), "kgCO2e", heater_like, extra_assumptions),
    }

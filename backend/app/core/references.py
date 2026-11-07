"""Frozen references, fitted ONCE on the baseline and reused for every evaluation and counterfactual.

Freezing is what makes before/after comparisons valid (requirement R7): a flat's score can change only through
its own hourly trajectory, never because another flat changed or because a benchmark was re-estimated.

Contents
  missing      bool[672x7] per flat: cells missing at baseline
  imputation   float[672x7] per flat: LOCAL imputation for those cells (same channel, same UTC day; else +/-1 day;
               else channel mean). Frozen, so an intervention cannot change what is assumed for an unobserved hour.
  peak_hours   local hours with mean spot price above the time-average price (data-driven)
  eq           equivalent residents n ** EQUIVALENCE_EXPONENT
  use_bench    per lens: P20 across flats of baseline 'explained' kWh per equivalent resident per day
  K            typical consumption intensity (median across flats, apartment lens) - common scale for Waste/Health
  K_T          typical flexible-appliance intensity (median across flats) - common scale for Timing
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import numpy as np

from .. import config as C
from .hourly import CHANNELS, N_HOURS, FlatData


def local_imputation(x: np.ndarray) -> np.ndarray:
    """x: (672, k). Returns imputed values where x is NaN (NaN elsewhere)."""
    days = x.reshape(N_HOURS // 24, 24, -1)
    import warnings
    with warnings.catch_warnings():                                     # all-missing day -> NaN, handled below
        warnings.simplefilter("ignore", category=RuntimeWarning)
        dm = np.nanmean(days, axis=1)                                   # (28, k) day means
        cm = np.nanmean(x, axis=0)                                      # channel means
    out = np.full_like(x, np.nan)
    for d in range(N_HOURS // 24):
        for j in range(x.shape[1]):
            seg = slice(24 * d, 24 * d + 24)
            miss = np.isnan(x[seg, j])
            if not miss.any():
                continue
            v = dm[d, j]
            if np.isnan(v):
                nb = [dm[e, j] for e in (d - 1, d + 1) if 0 <= e < dm.shape[0] and not np.isnan(dm[e, j])]
                v = float(np.mean(nb)) if nb else cm[j]
            col = out[seg, j]
            col[miss] = v
            out[seg, j] = col
    return out


@dataclass
class References:
    missing: dict = field(default_factory=dict)
    imputation: dict = field(default_factory=dict)
    peak_hours: set = field(default_factory=set)
    eq: dict = field(default_factory=dict)
    use_bench: dict = field(default_factory=dict)
    K: float = float("nan")
    K_T: float = float("nan")
    time_avg_price: float = float("nan")
    statuses_at_fit: dict = field(default_factory=dict)

    def summary(self) -> dict:
        d = {"peak_hours_local": sorted(self.peak_hours), "equivalence_exponent": C.EQUIVALENCE_EXPONENT,
             "eq_residents": {k: round(v, 6) for k, v in self.eq.items()},
             "use_bench_kwh_per_eq_resident_day": {k: round(v, 6) for k, v in self.use_bench.items()},
             "K_kwh_per_eq_resident_day": round(self.K, 6), "K_T_kwh_per_eq_resident_day": round(self.K_T, 6),
             "use_bench_percentile": C.USE_BENCH_PERCENTILE, "time_avg_price_sek_per_kwh": round(self.time_avg_price, 6)}
        d["hash"] = hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]
        return d


def fit(flats: dict[str, FlatData], anomalies: list[dict]) -> References:
    from .detect import peak_hours
    from .pillars import partition
    R = References()
    R.peak_hours = peak_hours(flats)
    fd0 = next(iter(flats.values()))
    R.time_avg_price = float(fd0.price.mean())
    for fl, fd in flats.items():
        x = fd.kwh[CHANNELS].to_numpy(dtype=float)
        R.missing[fl] = np.isnan(x)
        R.imputation[fl] = local_imputation(x)
        R.eq[fl] = float(fd.residents) ** C.EQUIVALENCE_EXPONENT
    R.statuses_at_fit = {a["id"]: int(a["status"]) for a in anomalies}
    parts = {fl: partition(fd, None, anomalies, R) for fl, fd in flats.items()}
    days = C.PERIOD_DAYS
    u = {lens: np.array([parts[fl][f"explained_{lens}"] / R.eq[fl] / days for fl in sorted(flats)]) for lens in ("apartment", "resident")}
    R.use_bench = {lens: float(np.percentile(v, C.USE_BENCH_PERCENTILE)) for lens, v in u.items()}
    R.K = float(np.median(u["apartment"]))
    R.K_T = float(np.median([parts[fl]["flexible_kwh"] / R.eq[fl] / days for fl in sorted(flats)]))
    return R

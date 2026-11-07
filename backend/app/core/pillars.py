"""Four pillars, each 0-100 (higher = better). NaN in = NaN out; NaN is never treated as 0."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config as C
from .claims import Status


def _clip01(x):
    return np.clip(x, 0.0, 1.0)


def use_pillar(kwh: pd.Series, residents: pd.Series, days: float = C.PERIOD_DAYS,
               percentile: float = C.USE_BENCH_PERCENTILE) -> tuple[pd.Series, pd.Series, float]:
    """USE: x = kWh / sqrt(residents) / days; bench = P20 of x across flats; USE = 100*min(1, bench/x).
    sqrt(residents) = shared appliances (fridge, router) don't scale with people."""
    x = kwh / np.sqrt(residents.reindex(kwh.index)) / days
    bench = float(np.nanpercentile(x.to_numpy(dtype=float), percentile))
    with np.errstate(divide="ignore", invalid="ignore"):
        use = 100 * np.minimum(1.0, bench / x)
    use = use.where(x.notna())
    use[(x == 0)] = 100.0
    return x, use, bench


def avoidable_away_kwh(e: pd.DataFrame, heater_confirmed_flats: set[str]) -> pd.Series:
    """Above-base kWh in hours where occupants_home == 0. Unknown occupancy (NaN) is NOT away.
    Heater-like kWh only counts once a heater finding is CONFIRMED by a person."""
    counted = ~e["is_heater"] | e["flat_id"].isin(heater_confirmed_flats)
    away = e["occupants_home"].eq(0)                       # NaN -> False
    return e["above_base"].where(counted & away).groupby(e["flat_id"]).sum(min_count=0)


def waste_pillar(e: pd.DataFrame, heater_confirmed_flats: set[str]) -> tuple[pd.Series, pd.Series]:
    avoidable = avoidable_away_kwh(e, heater_confirmed_flats)
    total = e.groupby("flat_id")["kwh"].sum(min_count=1)
    share = avoidable.reindex(total.index) / total
    waste = 100 * _clip01(1 - share / C.WASTE_FULL_PENALTY_SHARE)
    return waste, avoidable.reindex(total.index)


def carbon_profile(prices: pd.DataFrame) -> tuple[float, float, float]:
    """(mean g, best hour-of-day mean g, worst hour-of-day mean g) on Europe/Stockholm clock."""
    g = prices.dropna(subset=["carbon"])
    hod = g["timestamp_utc"].dt.tz_convert(C.TZ_LOCAL).dt.hour
    by_h = g.groupby(hod)["carbon"].mean()
    return float(g["carbon"].mean()), float(by_h.min()), float(by_h.max())


def timing_pillar(e: pd.DataFrame, prices: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """CTI = carbon-weighted flexible kWh / mean carbon. 1.0 = average timing, <1 = cleaner hours.
    Scaled 0-100 between the worst and best hour-of-day profile."""
    gmean, gbest, gworst = carbon_profile(prices)
    flex = e["above_base"].where(~e["is_heater"])
    ok = flex.notna() & e["carbon"].notna()
    num = (flex * e["carbon"]).where(ok).groupby(e["flat_id"]).sum()
    den = flex.where(ok).groupby(e["flat_id"]).sum()
    cti = num / den / gmean
    best, worst = gbest / gmean, gworst / gmean
    timing = 100 * _clip01((worst - cti) / (worst - best))
    timing = timing.where(den > 0, 100.0)                  # no flexible load -> nothing to time
    return timing, cti


def fault_kwh(anomalies: list[dict], flat_ids) -> pd.Series:
    """Manager-attributed excess with status >= PLAUSIBLE."""
    s = pd.Series(0.0, index=pd.Index(flat_ids, name="flat_id"))
    for a in anomalies:
        if a.get("responsibility") == "manager" and a["status"] >= Status.PLAUSIBLE:
            v = a.get("excess_kwh")
            if v is not None and not np.isnan(v):
                s[a["flat_id"]] += max(0.0, float(v))
    return s


def health_pillar(total_kwh: pd.Series, anomalies: list[dict]) -> tuple[pd.Series, pd.Series]:
    fk = fault_kwh(anomalies, total_kwh.index)
    health = 100 * _clip01(1 - C.HEALTH_FAULT_MULTIPLIER * fk / total_kwh)
    return health, fk


def heater_confirmed_flats(anomalies: list[dict]) -> set[str]:
    return {a["flat_id"] for a in anomalies
            if a["type"] == "heater_pattern" and a["status"] >= Status.CONFIRMED}

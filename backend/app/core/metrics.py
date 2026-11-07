"""Measured 28-day kWh / spot SEK / kgCO2e. Missing kWh stays NaN and is reported as coverage."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config as C


def assumed_type(channel: str) -> str:
    return C.ASSUMED_TYPES.get(channel, C.ASSUMED_TYPE_DEFAULT)


def enrich(readings: pd.DataFrame, flats: pd.DataFrame, prices: pd.DataFrame, context: pd.DataFrame) -> pd.DataFrame:
    """Join readings to flat, price (UTC + price_area) and context (flat + UTC). Adds base load and local time."""
    r = readings.merge(flats[["flat_id", "price_area"]], on="flat_id", how="left", validate="many_to_one")
    r = r.merge(prices[["timestamp_utc", "price_area", "spot", "carbon"]],
                on=["timestamp_utc", "price_area"], how="left", validate="many_to_one")
    r = r.merge(context[["flat_id", "timestamp_utc", "occupants_home"]],
                on=["flat_id", "timestamp_utc"], how="left", validate="many_to_one")
    local = r["timestamp_utc"].dt.tz_convert(C.TZ_LOCAL)
    r["local_hour"] = local.dt.hour
    r["day"] = r["timestamp_utc"].dt.floor("D")          # UTC day, used for bootstrap
    r["is_peak"] = r["local_hour"].isin(C.PEAK_HOURS_LOCAL)
    r["is_heater"] = r["channel"].isin(C.HEATER_CHANNELS)
    # Base load = P10 of observed hourly kWh per appliance (NaN ignored, not zero)
    r["base"] = r.groupby("appliance_id")["kwh"].transform(lambda s: s.quantile(C.BASELOAD_PERCENTILE / 100))
    r["above_base"] = (r["kwh"] - r["base"]).clip(lower=0)  # NaN stays NaN
    r["sek"] = r["kwh"] * r["spot"]
    r["co2_kg"] = r["kwh"] * r["carbon"] / 1000
    return r


def coverage_adjusted_kwh(e: pd.DataFrame, expected_hours: int = C.PERIOD_HOURS) -> pd.Series:
    """Per flat: sum over appliances of mean(observed kWh) * expected hours. Missing hours are
    filled by that appliance's own average, never by zero."""
    per_app = e.groupby(["flat_id", "appliance_id"])["kwh"].mean() * expected_hours
    return per_app.groupby(level="flat_id").sum(min_count=1)


def flat_totals(e: pd.DataFrame, flats: pd.DataFrame) -> pd.DataFrame:
    g = e.groupby("flat_id")
    t = pd.DataFrame({
        "kwh": g["kwh"].sum(min_count=1),
        "sek": g["sek"].sum(min_count=1),
        "co2_kg": g["co2_kg"].sum(min_count=1),
        "hours_observed": g["kwh"].count(),
        "hours_rows": g.size(),
        "kwh_peak": e[e["is_peak"]].groupby("flat_id")["kwh"].sum(min_count=1),
        "kwh_with_price": e[e["spot"].notna()].groupby("flat_id")["kwh"].sum(min_count=1),
    })
    t["kwh_coverage_adjusted"] = coverage_adjusted_kwh(e)
    t = t.join(flats.set_index("flat_id")[["residents", "floor_area_m2"]], how="right")
    n_app = e.groupby("flat_id")["appliance_id"].nunique()
    t["coverage"] = t["hours_observed"] / (n_app * C.PERIOD_HOURS)
    t["price_coverage"] = t["kwh_with_price"] / t["kwh"]
    t["peak_share"] = t["kwh_peak"] / t["kwh"]
    t["kwh_per_resident"] = t["kwh"] / t["residents"]
    t["sek_per_resident"] = t["sek"] / t["residents"]
    t["co2_kg_per_resident"] = t["co2_kg"] / t["residents"]
    t["kwh_per_m2"] = t["kwh"] / t["floor_area_m2"]
    return t.drop(columns=["hours_rows", "kwh_with_price"])


def channel_breakdown(e: pd.DataFrame, flat_id: str) -> pd.DataFrame:
    f = e[e["flat_id"] == flat_id]
    g = f.groupby(["appliance_id", "channel"])
    b = pd.DataFrame({
        "kwh": g["kwh"].sum(min_count=1),
        "sek": g["sek"].sum(min_count=1),
        "co2_kg": g["co2_kg"].sum(min_count=1),
        "hours_observed": g["kwh"].count(),
        "base_kwh_per_h": g["base"].first(),
        "kwh_peak": f[f["is_peak"]].groupby(["appliance_id", "channel"])["kwh"].sum(min_count=1),
    }).reset_index()
    total = b["kwh"].sum()
    b["share_of_flat"] = b["kwh"] / total if total else np.nan
    b["peak_share"] = b["kwh_peak"] / b["kwh"]
    b["assumed_type"] = b["channel"].map(assumed_type)
    b["coverage"] = b["hours_observed"] / C.PERIOD_HOURS
    return b.drop(columns=["kwh_peak"]).sort_values("kwh", ascending=False)


def daily_flat_series(e: pd.DataFrame, flat_id: str) -> pd.DataFrame:
    """Daily kWh / SEK / CO2 for one flat (UTC days); used for bootstrap ranges."""
    f = e[e["flat_id"] == flat_id]
    return f.groupby("day")[["kwh", "sek", "co2_kg"]].sum(min_count=1)

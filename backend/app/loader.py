"""Read raw (organiser) + processed (teammate) or mock files into a Dataset.

This is NOT the cleaning pipeline. It only parses types and applies validity guards that turn
impossible values into NaN ("unknown") so they never silently become zeros. Every guard is
logged in `quality` and shown in /health."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .core.attribution import responsibility
from .core.claims import Status, initial_status
from .core.dataset import Dataset


def parse_utc(s: pd.Series) -> pd.Series:
    """ISO UTC, plus the legacy 'YYYY/MM/DD HH:MM' export (also UTC)."""
    out = pd.to_datetime(s, utc=True, errors="coerce", format="ISO8601")
    bad = out.isna() & s.notna()
    if bad.any():
        out[bad] = pd.to_datetime(s[bad], utc=True, errors="coerce", format="%Y/%m/%d %H:%M")
    return out


def _in_period(df: pd.DataFrame) -> pd.DataFrame:
    start, end = pd.Timestamp(C.PERIOD_START), pd.Timestamp(C.PERIOD_END)
    return df[(df["timestamp_utc"] >= start) & (df["timestamp_utc"] < end)]


def resolve_source() -> tuple[str, Path]:
    proc_ok = (C.PROCESSED_DIR / "clean_readings.csv").exists() and (C.PROCESSED_DIR / "anomalies.json").exists()
    if C.DATA_SOURCE == "processed" or (C.DATA_SOURCE == "auto" and proc_ok):
        return "processed", C.PROCESSED_DIR
    return "mock", C.MOCK_DIR


def load_flats() -> pd.DataFrame:
    f = pd.read_csv(C.RAW_DIR / "flats.csv", dtype={"flat_id": str})
    f["residents"] = pd.to_numeric(f["residents"], errors="coerce")
    f["floor_area_m2"] = pd.to_numeric(f["floor_area_m2"], errors="coerce")
    return f


def load_prices(quality: dict) -> pd.DataFrame:
    p = pd.read_csv(C.RAW_DIR / "hourly_prices.csv", dtype=str)
    p["timestamp_utc"] = parse_utc(p["timestamp_utc"])
    p["spot"] = pd.to_numeric(p["spot_sek_per_kwh"], errors="coerce")          # negative prices are valid
    p["carbon"] = pd.to_numeric(p["carbon_gco2e_per_kwh"], errors="coerce")
    p.loc[p["carbon"] < 0, "carbon"] = np.nan
    n = len(p)
    p = p.drop_duplicates(subset=["timestamp_utc", "price_area"], keep="first")
    quality["prices_missing_spot_hours"] = int(p["spot"].isna().sum())
    quality["prices_duplicates_dropped"] = n - len(p)
    return _in_period(p[["timestamp_utc", "price_area", "spot", "carbon"]])


def load_context(flats: pd.DataFrame, quality: dict) -> pd.DataFrame:
    c = pd.read_csv(C.RAW_DIR / "hourly_context.csv", dtype=str)
    c["timestamp_utc"] = parse_utc(c["timestamp_utc"])
    for col in ("occupants_home", "indoor_temp_c", "outdoor_temp_c"):
        c[col] = pd.to_numeric(c[col], errors="coerce")
    res = c["flat_id"].map(flats.set_index("flat_id")["residents"])
    impossible = (c["occupants_home"] < 0) | (c["occupants_home"] > res)
    quality["context_occupancy_missing"] = int(c["occupants_home"].isna().sum())
    quality["context_occupancy_impossible_to_unknown"] = int(impossible.sum())
    c.loc[impossible, "occupants_home"] = np.nan                              # unknown, NOT away
    sentinel = c["outdoor_temp_c"] < -60
    quality["context_outdoor_sentinel_to_unknown"] = int(sentinel.sum())
    c.loc[sentinel, "outdoor_temp_c"] = np.nan
    c = c.drop_duplicates(subset=["flat_id", "timestamp_utc"], keep="first")
    return _in_period(c[["flat_id", "timestamp_utc", "occupants_home", "indoor_temp_c", "outdoor_temp_c"]])


def load_readings(folder: Path, quality: dict) -> pd.DataFrame:
    r = pd.read_csv(folder / "clean_readings.csv", dtype={"flat_id": str, "appliance_id": str})
    r["timestamp_utc"] = parse_utc(r["timestamp_utc"].astype(str))
    r["kwh"] = pd.to_numeric(r["kwh"], errors="coerce")                        # NaN = missing, never 0
    if "channel" not in r.columns:
        r["channel"] = r["appliance_id"].str.split("-").str[-1]
    n = len(r)
    r = r.drop_duplicates(subset=["appliance_id", "timestamp_utc"], keep="first")
    quality["readings_duplicate_keys_dropped"] = n - len(r)                   # should be 0 from teammate
    quality["readings_missing_kwh"] = int(r["kwh"].isna().sum())
    r = _in_period(r)
    return r[["flat_id", "appliance_id", "channel", "timestamp_utc", "kwh"]].reset_index(drop=True)


def _num(v):
    try:
        return float(v) if v is not None else np.nan
    except (TypeError, ValueError):
        return np.nan


def _utc(v) -> pd.Timestamp:
    t = pd.Timestamp(v)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def prepare_anomalies(raw: list[dict]) -> list[dict]:
    """Attach engine-side status + responsibility. Teammate fields are kept as-is."""
    out = []
    for a in raw:
        a = dict(a)
        a["start"], a["end"] = _utc(a["start"]), _utc(a["end"])
        for k in ("excess_kwh", "baseline_kwh_per_h", "observed_kwh_per_h", "confidence"):
            a[k] = _num(a.get(k))
        a["channel"] = a["appliance_id"].split("-")[-1]
        a["status"] = initial_status(None if np.isnan(a["confidence"]) else a["confidence"], a["start"], a["end"])
        a["responsibility"] = responsibility(a["type"])
        out.append(a)
    return out


def load_anomalies(folder: Path) -> list[dict]:
    with open(folder / "anomalies.json", encoding="utf-8") as fh:
        return prepare_anomalies(json.load(fh))


def load() -> tuple[Dataset, dict]:
    source, folder = resolve_source()
    if source == "mock" and not (folder / "clean_readings.csv").exists():
        from mock_data import generate                                       # backend/mock_data.py
        generate()
    quality: dict = {"data_source": source, "folder": str(folder)}
    flats = load_flats()
    ds = Dataset(
        readings=load_readings(folder, quality),
        flats=flats,
        prices=load_prices(quality),
        context=load_context(flats, quality),
        anomalies=load_anomalies(folder),
    )
    quality["anomalies"] = len(ds.anomalies)
    quality["readings_rows"] = len(ds.readings)
    log = folder / "cleaning_log.json"
    if log.exists():
        quality["cleaning_log"] = json.loads(log.read_text(encoding="utf-8"))
    return ds, quality

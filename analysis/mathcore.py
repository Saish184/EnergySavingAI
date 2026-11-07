"""Analysis-side access to the canonical hourly accounting (backend/app/core/hourly.py).

There is ONE implementation of the accounting (FlatData, Trajectory, Op, apply_op, combine, totals). This module
re-exports it for the analysis scripts and tests, and adds:
  - load_flats(): FlatData from the validated pipeline output data/processed/analytical_table.csv
  - the five validated opportunity cases (O1-O5) as operator RECIPES with their original assumptions, used as
    golden references for the engine (tests/math). They are fixtures, not a second savings implementation.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd

from common import PROCESSED, ROOT

if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.core.hourly import (CHANNELS, N_HOURS, STAGES, FlatData, Op, Trajectory, apply_op, combine,  # noqa: E402,F401
                             difference, flats_from_frames, heating_degree_hours, per_resident_average,
                             time_average_price, totals, unoccupied_runs)

STEP_HOUR_F002 = 336  # 2026-10-15T00:00Z, validated changepoint


@lru_cache(maxsize=1)
def _table() -> pd.DataFrame:
    return pd.read_csv(PROCESSED / "analytical_table.csv")


def load_flats() -> dict[str, FlatData]:
    t = _table()
    readings = t.rename(columns={"appliance_code": "channel", "energy_kwh": "kwh"})[["flat_id", "channel", "hour_idx", "kwh"]]
    hh = t.drop_duplicates(["flat_id", "hour_idx"])
    context = hh[["flat_id", "hour_idx", "occupants_home", "outdoor_temp_c"]]
    prices = hh.drop_duplicates("hour_idx")[["hour_idx", "spot_sek_per_kwh", "carbon_gco2e_per_kwh"]].rename(
        columns={"spot_sek_per_kwh": "spot", "carbon_gco2e_per_kwh": "carbon"})
    meta = hh.drop_duplicates("flat_id")[["flat_id", "residents", "floor_area_m2"]]
    return flats_from_frames(readings, context, prices, meta)


# --------------------------------------------------------------------------- validated opportunity recipes
def op_O1_heater_off_unoccupied(fd: FlatData, min_absence_h: int = 2, rebound: float = 0.0) -> Op:
    return Op("O1 heater off when unoccupied", "fraction", "A07", unoccupied_runs(fd, min_absence_h), "reduction", phi=1.0 - rebound)


def op_O2_always_on(fd: FlatData, theta: float = 0.5, peer_floor: float = 0.033, excess: float = 0.095) -> Op:
    return Op("O2 always-on base load", "excess", "A06", list(range(N_HOURS)), "reduction", level=peer_floor, cap=excess, theta=theta)


def op_O3_fridge_repair(fd: FlatData, level: float | None = None, fix_fraction: float = 1.0, repair_after_days: int = 0) -> Op:
    pre = fd.kwh["A01"].loc[:STEP_HOUR_F002 - 1].mean() if level is None else level
    start = STEP_HOUR_F002 + 24 * repair_after_days
    return Op("O3 fridge repair", "excess", "A01", list(range(start, N_HOURS)), "repair", level=float(pre), theta=fix_fraction)


def peer_hourly_median(flats: dict[str, FlatData], channel: str, exclude: str) -> pd.Series:
    vals = pd.concat([pd.DataFrame({"v": f.kwh[channel], "lh": f.local_hour}) for k, f in flats.items() if k != exclude])
    return vals.dropna().groupby("lh").v.median()


def op_O4_daytime_electronics(fd: FlatData, flats: dict[str, FlatData], only_unoccupied: bool = False, theta: float = 1.0) -> Op:
    med = peer_hourly_median(flats, "A05", fd.flat_id)
    hours = [h for h in range(N_HOURS) if 9 <= fd.local_hour.loc[h] <= 16 and (not only_unoccupied or fd.occupants.loc[h] == 0)]
    return Op("O4 daytime electronics", "excess", "A05", hours, "reduction", level=fd.local_hour.map(med), theta=theta)


def op_O5_dishwasher_shift(fd: FlatData, start_local_hour: int = 21, share: float = 1.0) -> Op:
    ev = [h for h in range(N_HOURS) if pd.notna(fd.kwh["A04"].loc[h]) and fd.kwh["A04"].loc[h] > 0.1]
    moves = []
    for h0 in ev:
        h1 = next((h for h in range(h0, min(h0 + 25, N_HOURS)) if fd.local_hour.loc[h] == start_local_hour), None)
        if h1 is not None:
            moves.append((h0, h1))
    return Op("O5 dishwasher shift", "shift", "A04", stage="shift", moves=moves, share=share)


def op_S1b_heater_setback(fd: FlatData, delta_c: float = 1.0, slope: float = 0.12, balance: float = 12.0) -> Op:
    """Illustrative research-report scenario (unvalidated): used only to test overlap handling."""
    base = (slope * (balance - fd.outdoor)).clip(lower=0)
    cf = (slope * (balance - delta_c - fd.outdoor)).clip(lower=0)
    phi = (1 - cf / base).where(base > 0, 0.0).fillna(0.0)
    return Op("S1b heater setback (illustrative)", "fraction", "A07", list(range(N_HOURS)), "reduction", phi=phi)

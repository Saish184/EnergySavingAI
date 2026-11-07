"""Canonical hourly accounting for the whole project (engine, analysis scripts and tests).

Data model
  FlatData    one flat: hourly kWh matrix (672 UTC hours x channels A01..A07, NaN = missing, never 0)
              plus aligned price, carbon, occupancy, outdoor temperature and Europe/Stockholm local hour.
  Trajectory  counterfactual = observed base (NaN untouched) + intervention delta layer. A load shift may move
              known energy into an hour whose own reading is missing: it is carried in the delta, never lost and
              never mistaken for that hour's full reading.
  Op          one intervention on one channel: fraction | excess | shift, with a fixed combination stage
              (repair -> reduction -> shift) so combined interventions never double count.

Everything here is vectorised and deterministic. This module contains no score formula.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

CHANNELS = [f"A0{i}" for i in range(1, 8)]
N_HOURS = 672
T0 = pd.Timestamp("2026-10-01T00:00:00Z")
TZ_LOCAL = "Europe/Stockholm"
STAGES = {"repair": 0, "reduction": 1, "shift": 2}


@dataclass
class FlatData:
    flat_id: str
    residents: int
    floor_area_m2: float
    kwh: pd.DataFrame
    price: pd.Series
    carbon: pd.Series
    occupants: pd.Series
    outdoor: pd.Series
    local_hour: pd.Series
    extra: pd.DataFrame | None = None  # energy added by interventions to cells whose reading is missing

    def with_kwh(self, kwh: pd.DataFrame) -> "FlatData":
        return FlatData(self.flat_id, self.residents, self.floor_area_m2, kwh, self.price, self.carbon,
                        self.occupants, self.outdoor, self.local_hour)

    def with_trajectory(self, traj: "Trajectory") -> "FlatData":
        on_missing = traj.base.isna() & (traj.delta != 0)
        return FlatData(self.flat_id, self.residents, self.floor_area_m2, traj.base + traj.delta, self.price,
                        self.carbon, self.occupants, self.outdoor, self.local_hour,
                        traj.delta.where(on_missing, 0.0) if on_missing.to_numpy().any() else None)

    def trajectory(self) -> "Trajectory":
        """Inverse of with_trajectory: observed base + (extra energy on missing cells) as a delta layer."""
        base = self.kwh.where(self.kwh.notna())
        delta = pd.DataFrame(0.0, index=base.index, columns=base.columns)
        if self.extra is not None:
            delta = delta + self.extra.fillna(0.0)
        return Trajectory(base, delta)


def flats_from_frames(readings: pd.DataFrame, context: pd.DataFrame, prices: pd.DataFrame,
                      flats_meta: pd.DataFrame) -> dict[str, FlatData]:
    """Build FlatData from long tables.
    readings: flat_id, channel, hour_idx | timestamp_utc, kwh (NaN = missing)
    context:  flat_id, hour_idx | timestamp_utc, occupants_home, outdoor_temp_c
    prices:   hour_idx | timestamp_utc, spot, carbon (one price area)
    flats_meta: flat_id, residents, floor_area_m2"""
    def hidx(df):
        if "hour_idx" in df:
            return df.hour_idx.astype(int)
        return ((pd.to_datetime(df.timestamp_utc, utc=True) - T0) // pd.Timedelta("1h")).astype(int)

    r = readings.assign(hour_idx=hidx(readings))
    c = context.assign(hour_idx=hidx(context))
    p = prices.assign(hour_idx=hidx(prices)).drop_duplicates("hour_idx").set_index("hour_idx").sort_index().reindex(range(N_HOURS))
    hours = pd.RangeIndex(N_HOURS)
    local_hour = pd.Series((T0 + pd.to_timedelta(hours, unit="h")).tz_convert(TZ_LOCAL).hour, index=hours)
    meta = flats_meta.set_index("flat_id")
    out = {}
    for fl in sorted(meta.index):
        k = (r[r.flat_id == fl].pivot_table(index="hour_idx", columns="channel", values="kwh", aggfunc="first", dropna=False)
             .reindex(index=hours, columns=CHANNELS))
        cc = c[c.flat_id == fl].drop_duplicates("hour_idx").set_index("hour_idx").reindex(hours)
        out[fl] = FlatData(fl, int(meta.loc[fl, "residents"]), float(meta.loc[fl, "floor_area_m2"]), k.astype(float),
                           p["spot"].astype(float), p["carbon"].astype(float), cc["occupants_home"].astype(float),
                           cc["outdoor_temp_c"].astype(float), local_hour)
    return out


# --------------------------------------------------------------------------- accounting
def time_average_price(fd: FlatData) -> float:
    return float(fd.price.mean())


def totals(fd: FlatData, kwh: "pd.DataFrame | Trajectory | None" = None, window: tuple[int, int] = (0, N_HOURS),
           channels: list[str] | None = None) -> dict:
    """kWh, spot SEK (hourly), time-average SEK proxy and kgCO2e: observed base (NaN skipped) + all deltas."""
    if kwh is None:
        kwh = fd.kwh if fd.extra is None else Trajectory(fd.kwh, fd.extra.fillna(0.0))
    base, delta = (kwh.base, kwh.delta) if isinstance(kwh, Trajectory) else (kwh, None)
    cols = channels or CHANNELS
    a, b = window
    x = base[cols].to_numpy(dtype=float)[a:b]
    dx = delta[cols].to_numpy(dtype=float)[a:b] if delta is not None else np.zeros_like(x)
    p = fd.price.to_numpy(dtype=float)[a:b][:, None]
    c = fd.carbon.to_numpy(dtype=float)[a:b][:, None]
    priced = ~np.isnan(p)
    k = float(np.nansum(x) + np.nansum(dx))
    xp = np.where(priced, x, np.nan) * p
    dp = np.where(priced, dx, 0.0) * np.nan_to_num(p)
    return {
        "kwh": k,
        "sek_spot_hourly": float(np.nansum(xp) + np.nansum(dp)),
        "sek_spot_timeavg_proxy": k * time_average_price(fd),
        "co2e_kg": float(np.nansum(x * c) + np.nansum(dx * c)) / 1000.0,
        "kwh_unpriced": float(np.nansum(np.where(priced, np.nan, x)) + np.nansum(np.where(priced, 0.0, dx))),
        "observed_cells": int(np.isfinite(x).sum()),
        "window_hours": b - a,
    }


def difference(fd: FlatData, base, cf, **kw) -> dict:
    A, B = totals(fd, base, **kw), totals(fd, cf, **kw)
    return {k: A[k] - B[k] for k in ("kwh", "sek_spot_hourly", "sek_spot_timeavg_proxy", "co2e_kg")}


def per_resident_average(value: float, residents: int) -> dict:
    return {"value": value / residents, "label": "average per resident (flat total / residents), not measured per person"}


def heating_degree_hours(outdoor: pd.Series, balance: float = 12.0) -> float:
    return float((balance - outdoor).clip(lower=0).sum())


def unoccupied_runs(fd: FlatData, min_len: int) -> list[int]:
    """Hours with occupants_home == 0 (unknown is NOT unoccupied) that belong to a run of >= min_len hours."""
    occ = fd.occupants.to_numpy()
    z = occ == 0
    out, h = [], 0
    while h < N_HOURS:
        if z[h]:
            j = h
            while j < N_HOURS and z[j]:
                j += 1
            if j - h >= min_len:
                out.extend(range(h, j))
            h = j
        else:
            h += 1
    return out


# --------------------------------------------------------------------------- operators
@dataclass
class Op:
    name: str
    kind: str                                        # fraction | excess | shift
    channel: str
    hours: list[int] = field(default_factory=list)
    stage: str = "reduction"
    phi: float | pd.Series | None = None              # fraction: s = phi * x
    level: float | pd.Series | None = None            # excess:   s = theta * min(max(x - level, 0), cap)
    cap: float | pd.Series | None = None
    theta: float = 1.0
    moves: list[tuple[int, int]] = field(default_factory=list)
    share: float = 1.0


@dataclass
class Trajectory:
    base: pd.DataFrame
    delta: pd.DataFrame

    @classmethod
    def of(cls, kwh: pd.DataFrame) -> "Trajectory":
        return cls(kwh, pd.DataFrame(0.0, index=kwh.index, columns=kwh.columns))

    def effective(self) -> pd.DataFrame:
        eff = self.base + self.delta
        fill = self.base.isna() & (self.delta != 0)
        return eff.where(~fill, self.delta)

    def missing_with_delta(self) -> int:
        return int((self.base.isna() & (self.delta != 0)).to_numpy().sum())


class AdjustedTrajectory(Trajectory):
    """A trajectory whose base is the coverage-adjusted matrix (no NaN): used for scoring counterfactuals so an
    intervention also applies to hours whose reading was missing (their frozen imputation)."""


def _vec(v, hours: np.ndarray) -> np.ndarray:
    if isinstance(v, pd.Series):
        return v.reindex(range(N_HOURS)).to_numpy(dtype=float)[hours]
    return np.full(len(hours), float(v))


def apply_op(traj: "Trajectory | pd.DataFrame", op: Op) -> tuple[Trajectory, dict]:
    tr = Trajectory.of(traj) if isinstance(traj, pd.DataFrame) else traj
    delta = tr.delta.copy()
    base = tr.base[op.channel].to_numpy(dtype=float)
    d = delta[op.channel].to_numpy(dtype=float).copy()
    log = {"op": op.name, "skipped_missing": 0, "moved_into_missing_hour": 0}
    if op.kind in ("fraction", "excess"):
        hrs = np.asarray(sorted(set(op.hours)), dtype=int)
        if hrs.size:
            obs = ~np.isnan(base[hrs])
            log["skipped_missing"] = int((~obs).sum())
            h = hrs[obs]
            v = base[h] + d[h]
            if op.kind == "fraction":
                s = _vec(op.phi, h) * v
            else:
                s = np.maximum(v - _vec(op.level, h), 0.0)
                if op.cap is not None:
                    s = np.minimum(s, _vec(op.cap, h))
                s = op.theta * s
            d[h] -= s
    elif op.kind == "shift":
        for h0, h1 in op.moves:
            if np.isnan(base[h0]):
                log["skipped_missing"] += 1
                continue
            k = op.share * (base[h0] + d[h0])
            d[h0] -= k
            d[h1] += k
            log["moved_into_missing_hour"] += int(np.isnan(base[h1]))
    else:
        raise ValueError(op.kind)
    delta[op.channel] = d
    out = type(tr)(tr.base, delta)
    eff = np.where(np.isnan(base), d, base + d)
    if (np.nan_to_num(eff) < -1e-9).any():
        raise ValueError(f"{op.name} produced negative energy")
    return out, log


def combine(kwh: "pd.DataFrame | Trajectory", ops: list[Op]) -> tuple[Trajectory, list[dict]]:
    """Apply all interventions to ONE hourly trajectory: repairs, then reductions, then shifts (stable order)."""
    tr, logs = (Trajectory.of(kwh) if isinstance(kwh, pd.DataFrame) else kwh), []
    for op in sorted(ops, key=lambda o: STAGES[o.stage]):
        tr, lg = apply_op(tr, op)
        logs.append(lg)
    return tr, logs

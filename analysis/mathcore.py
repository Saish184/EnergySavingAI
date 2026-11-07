"""Reference hourly-accounting library for the quantitative engine (formula-agnostic).

Purpose: give the mathematical tests and the score-audit harness one exact, reviewable implementation of
  - per-flat hourly data with missing observations kept as NaN (never 0),
  - kWh / spot-SEK / kgCO2e accounting over an explicit window,
  - intervention operators (reductions, capped excess removal, load shifts) on the hourly trajectory,
  - deterministic combination of interventions (no double counting),
  - the validated opportunity cases (O1-O5) expressed as operators.
It contains NO sustainability-score formula. Nothing here changes existing reports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd

from common import PROCESSED

CHANNELS = [f"A0{i}" for i in range(1, 8)]
N_HOURS = 672
STEP_HOUR_F002 = 336  # 2026-10-15T00:00Z, validated changepoint


@dataclass
class FlatData:
    flat_id: str
    residents: int
    floor_area_m2: float
    kwh: pd.DataFrame          # index: hour_idx 0..671; columns A01..A07; NaN = missing observation
    price: pd.Series           # SEK/kWh spot (NaN = unpriced)
    carbon: pd.Series          # gCO2e/kWh
    occupants: pd.Series       # estimated occupants home (NaN = unknown)
    outdoor: pd.Series         # degC (NaN = unknown)
    local_hour: pd.Series      # Europe/Stockholm hour of day, derived from UTC
    extra: pd.DataFrame | None = None  # intervention energy added to cells whose own reading is MISSING (known kWh
                                       # on top of an unknown baseline); None = nothing added

    def with_kwh(self, kwh: pd.DataFrame) -> "FlatData":
        return FlatData(self.flat_id, self.residents, self.floor_area_m2, kwh, self.price, self.carbon,
                        self.occupants, self.outdoor, self.local_hour)

    def with_trajectory(self, traj: "Trajectory") -> "FlatData":
        """Counterfactual view for score models: kwh = base + delta on observed cells (NaN stays NaN);
        energy moved into missing cells is carried separately in `extra`, so it is neither lost nor mistaken
        for the cell's full reading."""
        on_missing = traj.base.isna() & (traj.delta != 0)
        return FlatData(self.flat_id, self.residents, self.floor_area_m2, traj.base + traj.delta, self.price,
                        self.carbon, self.occupants, self.outdoor, self.local_hour,
                        traj.delta.where(on_missing, 0.0) if on_missing.any().any() else None)


@lru_cache(maxsize=1)
def _table() -> pd.DataFrame:
    return pd.read_csv(PROCESSED / "analytical_table.csv")


def load_flats() -> dict[str, FlatData]:
    t = _table()
    out = {}
    for fl, d in t.groupby("flat_id"):
        kwh = d.pivot(index="hour_idx", columns="appliance_code", values="energy_kwh").reindex(range(N_HOURS))[CHANNELS]
        hh = d.drop_duplicates("hour_idx").set_index("hour_idx").sort_index()
        out[fl] = FlatData(fl, int(hh.residents.iloc[0]), float(hh.floor_area_m2.iloc[0]), kwh.astype(float),
                           hh.spot_sek_per_kwh, hh.carbon_gco2e_per_kwh, hh.occupants_home, hh.outdoor_temp_c, hh.local_hour)
    return out


def time_average_price(fd: FlatData) -> float:
    return float(fd.price.mean())


# --------------------------------------------------------------------------- accounting
def totals(fd: FlatData, kwh: "pd.DataFrame | Trajectory | None" = None, window: tuple[int, int] = (0, N_HOURS),
           channels: list[str] | None = None) -> dict:
    """kWh, spot SEK (hourly), time-average SEK proxy and kgCO2e over observed hours only."""
    if kwh is None:
        kwh = fd.kwh if fd.extra is None else Trajectory(fd.kwh, fd.extra)
    if isinstance(kwh, Trajectory):
        base, delta = kwh.base, kwh.delta
    else:
        base, delta = kwh, None
    sl = slice(window[0], window[1] - 1)
    cols = channels or CHANNELS
    x = base.loc[sl, cols]
    dx = delta.loc[sl, cols] if delta is not None else x * 0.0
    p, c = fd.price.loc[x.index], fd.carbon.loc[x.index]
    priced = p.notna()
    # energy = observed base (NaN skipped) + every intervention delta (also where the base reading is missing)
    k = float(np.nansum(x.values) + np.nansum(dx.values))
    sek = float(np.nansum(x[priced].mul(p[priced], axis=0).values) + np.nansum(dx[priced].mul(p[priced], axis=0).values))
    co2 = float(np.nansum(x.mul(c, axis=0).values) + np.nansum(dx.mul(c, axis=0).values)) / 1000.0
    return {
        "kwh": k, "sek_spot_hourly": sek, "sek_spot_timeavg_proxy": k * time_average_price(fd), "co2e_kg": co2,
        "kwh_unpriced": float(np.nansum(x[~priced].values) + np.nansum(dx[~priced].values)),
        "observed_cells": int(x.notna().sum().sum()),
        "window_hours": window[1] - window[0],
    }


def difference(fd: FlatData, base: "pd.DataFrame | Trajectory", cf: "pd.DataFrame | Trajectory", **kw) -> dict:
    a, b = totals(fd, base, **kw), totals(fd, cf, **kw)
    return {k: a[k] - b[k] for k in ("kwh", "sek_spot_hourly", "sek_spot_timeavg_proxy", "co2e_kg")}


def per_resident_average(value: float, residents: int) -> dict:
    """Labelled average only; never an individual measurement."""
    return {"value": value / residents, "label": "average per resident (flat total / residents), not measured per person"}


# --------------------------------------------------------------------------- operators
STAGES = {"repair": 0, "reduction": 1, "shift": 2}


@dataclass
class Op:
    """Intervention operator on one channel. kind in {fraction, excess, shift}. stage fixes combination order."""
    name: str
    kind: str
    channel: str
    hours: list[int] = field(default_factory=list)
    stage: str = "reduction"
    phi: float | pd.Series | None = None          # fraction: x' = (1 - phi) x
    level: float | pd.Series | None = None        # excess: s = theta * min(max(x - level, 0), cap)
    cap: float | None = None
    theta: float = 1.0
    moves: list[tuple[int, int]] = field(default_factory=list)  # shift: (from_hour, to_hour)
    share: float = 1.0


def _val(v, h):
    return float(v.loc[h]) if isinstance(v, pd.Series) else float(v)


@dataclass
class Trajectory:
    """Counterfactual = observed base (NaN = missing, untouched) + intervention delta layer.

    Keeping the delta separate lets a load shift move known energy INTO an hour whose own reading is missing
    without losing it (base unknown, delta known) and without inventing the missing baseline.
    """
    base: pd.DataFrame
    delta: pd.DataFrame

    @classmethod
    def of(cls, kwh: pd.DataFrame) -> "Trajectory":
        return cls(kwh, pd.DataFrame(0.0, index=kwh.index, columns=kwh.columns))

    def effective(self) -> pd.DataFrame:
        """Known energy per cell: base + delta where base observed; delta alone where base missing but delta != 0;
        NaN where nothing is known. Use for scoring; flagged cells are listed by missing_with_delta()."""
        eff = self.base + self.delta
        fill = self.base.isna() & (self.delta != 0)
        return eff.where(~fill, self.delta)

    def missing_with_delta(self) -> int:
        return int((self.base.isna() & (self.delta != 0)).sum().sum())


def apply_op(traj: "Trajectory | pd.DataFrame", op: Op) -> tuple[Trajectory, dict]:
    """Returns (new Trajectory, log). Missing base cells are never filled; reductions skip them."""
    tr = Trajectory.of(traj) if isinstance(traj, pd.DataFrame) else traj
    delta = tr.delta.copy()
    base, d = tr.base[op.channel], delta[op.channel]
    log = {"op": op.name, "skipped_missing": 0, "moved_into_missing_hour": 0}
    if op.kind in ("fraction", "excess"):
        for h in op.hours:
            if pd.isna(base.loc[h]):
                log["skipped_missing"] += 1
                continue
            v = base.loc[h] + d.loc[h]
            if op.kind == "fraction":
                s_ = _val(op.phi, h) * v
            else:
                s_ = max(v - _val(op.level, h), 0.0)
                if op.cap is not None:
                    s_ = min(s_, op.cap)
                s_ *= op.theta
            d.loc[h] -= s_
    elif op.kind == "shift":
        for h0, h1 in op.moves:
            if pd.isna(base.loc[h0]):
                log["skipped_missing"] += 1
                continue
            k = op.share * (base.loc[h0] + d.loc[h0])
            d.loc[h0] -= k
            d.loc[h1] += k
            log["moved_into_missing_hour"] += int(pd.isna(base.loc[h1]))
    else:
        raise ValueError(op.kind)
    delta[op.channel] = d
    out = Trajectory(tr.base, delta)
    if (out.effective().fillna(0) < -1e-12).any().any():
        raise ValueError(f"{op.name} produced negative energy")
    return out, log


def combine(kwh: "pd.DataFrame | Trajectory", ops: list[Op]) -> tuple[Trajectory, list[dict]]:
    """Apply all interventions to ONE hourly trajectory: repairs, then reductions, then shifts (stable order)."""
    tr, logs = (Trajectory.of(kwh) if isinstance(kwh, pd.DataFrame) else kwh), []
    for op in sorted(ops, key=lambda o: STAGES[o.stage]):
        tr, lg = apply_op(tr, op)
        logs.append(lg)
    return tr, logs


# --------------------------------------------------------------------------- validated opportunity cases
def unoccupied_runs(fd: FlatData, min_len: int) -> list[int]:
    occ = fd.occupants
    hrs = [h for h in range(N_HOURS) if occ.loc[h] == 0]
    runs, cur = [], []
    for h in hrs:
        if cur and h == cur[-1] + 1:
            cur.append(h)
        else:
            if cur:
                runs.append(cur)
            cur = [h]
    if cur:
        runs.append(cur)
    return [h for r in runs if len(r) >= min_len for h in r]


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


def heating_degree_hours(outdoor: pd.Series, balance: float = 12.0) -> float:
    return float((balance - outdoor).clip(lower=0).sum())

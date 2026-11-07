"""Interventions per anomaly type, as hourly operators bounded by the detector's evidence.

Every parameter has a default (the 'central' assumption) and a documented range used for the scenario range.
Load REDUCTIONS and load SHIFTS are different kinds: shifts never change kWh.

  fault_step_change  repair: s = fix_fraction * max(x - post_level, 0) from split + repair_after_days
  base_load_outlier  s = avoidable_fraction * min(max(x - peer floor, 0), excess floor)
  scheduled_block    s = avoidable_fraction * max(x - peer hourly median, 0) on the flagged hours
                       (only_when_unoccupied: just the hours with nobody home)
  heater_pattern     s = (1 - rebound) * x on unoccupied hours in absences >= min_absence_hours (never other hours)
  peak_usage         each run in a peak hour moves (share_moved) to the first later hour within max_delay_hours that is
                     not a peak hour, not a quiet hour and has a known price
`adoption` (student input, default 1) scales every reduction fraction / shift share: potential vs estimated realised.
"""
from __future__ import annotations

import numpy as np

from .. import config as C
from .detect import unoccupied_cells
from .hourly import N_HOURS, Op

PARAMS = {
    "fault_step_change": {"fix_fraction": (1.0, [0.5, 1.0]), "repair_after_days": (0, [0, 7]),
                          "post_level": ("pre_step_mean", ["pre_step_mean", "peer_mean"])},
    "base_load_outlier": {"avoidable_fraction": (1.0, [0.25, 0.5, 1.0])},
    "scheduled_block": {"avoidable_fraction": (1.0, [0.5, 1.0]), "only_when_unoccupied": (False, [True, False])},
    "heater_pattern": {"min_absence_hours": (C.MIN_ABSENCE_HOURS, [1, 2, 3]), "rebound": (0.0, [0.0, 0.25])},
    "peak_usage": {"share_moved": (1.0, [0.5, 1.0]), "max_delay_hours": (C.SHIFT_WINDOW_HOURS, [3, 12])},
}
KIND = {"peak_usage": "shift"}


def defaults(a: dict) -> dict:
    return {k: v[0] for k, v in PARAMS[a["type"]].items()}


def resolve(a: dict, params: dict | None) -> dict:
    p = defaults(a)
    for k, v in (params or {}).items():
        if k in ("quiet_hours", "adoption"):
            p[k] = v
            continue
        if k not in p:
            raise ValueError(f"unknown parameter {k!r} for {a['type']}; allowed: {sorted(p)} + adoption, quiet_hours")
        p[k] = v
    p.setdefault("adoption", 1.0)
    if not 0 <= float(p["adoption"]) <= 1:
        raise ValueError("adoption must be in [0, 1]")
    return p


def _peer_mean(ds, a) -> float:
    return float(np.nanmean([np.nanmean(f.kwh[a["channel"]].to_numpy(dtype=float)) for k, f in ds.flats.items() if k != a["flat_id"]]))


def ops_for(ds, a: dict, params: dict | None = None) -> tuple[list[Op], dict]:
    p = resolve(a, params)
    q = float(p["adoption"])
    fd = ds.flats[a["flat_id"]]
    t, ch = a["type"], a["channel"]
    hours = list(np.where(a["cells"])[0])
    if t == "fault_step_change":
        start = int(min(hours)) + 24 * int(p["repair_after_days"])
        level = a["ref"][0] if p["post_level"] == "pre_step_mean" else _peer_mean(ds, a)
        return [Op(f"repair {a['id']}", "excess", ch, [h for h in hours if h >= start], "repair",
                   level=float(level), theta=float(p["fix_fraction"]) * q)], p
    if t == "base_load_outlier":
        return [Op(f"base load {a['id']}", "excess", ch, hours, "reduction", level=float(a["ref"][0]), cap=float(a["cap"][0]),
                   theta=float(p["avoidable_fraction"]) * q)], p
    if t == "scheduled_block":
        hrs = hours
        if p["only_when_unoccupied"]:
            occ = fd.occupants.to_numpy()
            hrs = [h for h in hours if occ[h] == 0]
        import pandas as pd
        return [Op(f"block {a['id']}", "excess", ch, hrs, "reduction", level=pd.Series(a["ref"]), theta=float(p["avoidable_fraction"]) * q)], p
    if t == "heater_pattern":
        x = np.nan_to_num(fd.kwh[ch].to_numpy(dtype=float))
        cells = unoccupied_cells(fd, int(p["min_absence_hours"])) & (x > 0)
        return [Op(f"heater off when empty {a['id']}", "fraction", ch, list(np.where(cells)[0]), "reduction",
                   phi=(1.0 - float(p["rebound"])) * q)], p
    if t == "peak_usage":
        peak = ds.refs.peak_hours
        quiet = set(p.get("quiet_hours") or C.QUIET_HOURS_LOCAL)
        lh = fd.local_hour.to_numpy()
        price = fd.price.to_numpy(dtype=float)
        moves = []
        for h0 in hours:
            h1 = next((h for h in range(h0 + 1, min(h0 + 1 + int(p["max_delay_hours"]), N_HOURS))
                       if lh[h] not in peak and lh[h] not in quiet and np.isfinite(price[h])), None)
            if h1 is not None:
                moves.append((h0, h1))
        return [Op(f"shift {a['id']}", "shift", ch, stage="shift", moves=moves, share=float(p["share_moved"]) * q)], p
    raise ValueError(f"no intervention for anomaly type {t}")


def grid(a: dict) -> list[dict]:
    """Scenario range: every combination of the documented parameter values."""
    from itertools import product
    keys = list(PARAMS[a["type"]])
    return [dict(zip(keys, vals)) for vals in product(*[PARAMS[a["type"]][k][1] for k in keys])]

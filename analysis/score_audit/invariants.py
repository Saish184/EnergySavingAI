"""Property checks for any ScoreModel, driven by the validated opportunity cases.

Every result is a dict {check, requirement, cls, case, flat, passed, detail}. cls is one of:
  universal  - mathematically necessary for the stated requirement (must pass)
  policy     - depends on a product/design decision (reported; pass/fail means "consistent with the stated policy")
  heuristic  - indirect evidence (a flag to investigate, not proof)
  info       - measured behaviour, no pass/fail
Requirement IDs refer to docs/math/requirements_spec.md.
"""
from __future__ import annotations

import numpy as np

from mathcore import (CHANNELS, Op, Trajectory, combine, op_O1_heater_off_unoccupied, op_O2_always_on, op_O3_fridge_repair,
                      op_O4_daytime_electronics, op_O5_dishwasher_shift, totals)

TOL = 1e-9


def cases(flats) -> list[dict]:
    """Controlled interventions taken from the validated opportunity analysis (plus one synthetic uniform cut)."""
    cs = [
        {"case": "O4 F004 daytime electronics (pure reduction)", "type": "reduction", "flat": "F004",
         "ops": [op_O4_daytime_electronics(flats["F004"], flats)]},
        {"case": "O2 F005 always-on, full excess (pure reduction)", "type": "reduction", "flat": "F005",
         "ops": [op_O2_always_on(flats["F005"], theta=1.0)]},
        {"case": "O1 F007 heater off when unoccupied (pure reduction)", "type": "reduction", "flat": "F007",
         "ops": [op_O1_heater_off_unoccupied(flats["F007"])]},
        {"case": "O3 F002 fridge repaired at step (repair = reduction)", "type": "reduction", "flat": "F002",
         "ops": [op_O3_fridge_repair(flats["F002"])]},
        {"case": "O3+O5 F002 combined", "type": "combined", "flat": "F002",
         "ops": [op_O3_fridge_repair(flats["F002"]), op_O5_dishwasher_shift(flats["F002"])]},
    ]
    for fl, fd in flats.items():
        cs.append({"case": f"O5 {fl} dishwasher 20:00 -> 21:00 (pure shift)", "type": "shift", "flat": fl,
                   "ops": [op_O5_dishwasher_shift(fd)]})
        cs.append({"case": f"uniform 5 % cut of every channel {fl} (pure reduction)", "type": "reduction", "flat": fl,
                   "ops": [Op(f"5% {c}", "fraction", c, list(range(672)), phi=0.05) for c in CHANNELS]})
    return cs


def _with(flats, fl, traj: Trajectory):
    out = dict(flats)
    out[fl] = flats[fl].with_trajectory(traj)
    return out


def _res(check, req, cls, case, flat, passed, detail):
    return {"check": check, "requirement": req, "cls": cls, "case": case, "flat": flat,
            "passed": None if passed is None else bool(passed), "detail": detail}


def run_all(model, flats) -> list[dict]:
    R = []
    refs = model.fit_references(flats)
    base = model.score(flats, refs)

    # determinism (R11)
    again = model.score(flats, refs)
    R.append(_res("determinism", "R11", "universal", "baseline", "all", again == base, "two identical calls"))

    # bounds and weights (R12, declared promises)
    lo, hi = model.score_range
    bad = [(fl, v["score"]) for fl, v in base.items() if not (lo - 1e-9 <= v["score"] <= hi + 1e-9)]
    R.append(_res("score within declared range", "R12", "universal", "baseline", "all", not bad, bad or f"[{lo}, {hi}]"))
    if model.pillar_weights:
        w = model.pillar_weights
        R.append(_res("weights positive and sum to 1", "R12", "universal", "declared", "all",
                      abs(sum(w.values()) - 1) < 1e-9 and min(w.values()) > 0, w))

    # zero handling for geometric aggregation (policy D3)
    if model.aggregation == "geometric":
        coll = [fl for fl, v in base.items() if min(v["pillars"].values()) <= 0 and v["score"] == 0]
        R.append(_res("no zero-collapse of geometric aggregate", "R13", "policy", "baseline", ",".join(coll) or "none",
                      not coll, f"flats with a zero pillar forcing score 0: {coll}"))

    for c in cases(flats):
        fl = c["flat"]
        fd = flats[fl]
        traj, logs = combine(fd.kwh, c["ops"])
        new = model.score(_with(flats, fl, traj), refs)[fl]
        old = base[fl]
        d_kwh = totals(fd, traj)["kwh"] - totals(fd)["kwh"]
        if c["type"] == "reduction":
            R.append(_res("score non-decreasing under pure reduction", "R4", "universal", c["case"], fl,
                          new["score"] >= old["score"] - 1e-9, f"{old['score']:.3f} -> {new['score']:.3f} (dkWh {d_kwh:.2f})"))
            dec = {k: round(new["pillars"][k] - old["pillars"][k], 3) for k in old["pillars"] if new["pillars"][k] < old["pillars"][k] - 1e-9}
            R.append(_res("no pillar decreases under pure reduction", "R4", "policy", c["case"], fl, not dec, dec or "none"))
        if c["type"] == "shift":
            R.append(_res("shift conserves total kWh", "R9", "universal", c["case"], fl, abs(d_kwh) < 1e-9, f"dkWh {d_kwh:.2e}"))
            moved = {k: round(new["pillars"][k] - old["pillars"][k], 6) for k in model.energy_pillars
                     if abs(new["pillars"][k] - old["pillars"][k]) > 1e-9}
            R.append(_res("energy pillars unchanged by pure shift", "R9", "universal", c["case"], fl, not moved, moved or "unchanged"))
        if c["type"] == "combined":
            parts = [model.score(_with(flats, fl, combine(fd.kwh, [op])[0]), refs)[fl]["score"] - old["score"] for op in c["ops"]]
            R.append(_res("projected score from combined trajectory (additivity of increments)", "R6", "info", c["case"], fl, None,
                          f"combined {new['score'] - old['score']:+.3f} vs sum of separate {sum(parts):+.3f}"))

    # peer invariance with frozen references (R7)
    other = "F003"  # scale F003 to 1.5x the largest flat, so any un-frozen peer statistic (min, max, mean) must move
    fac = 1.5 * max(totals(fd)["kwh"] for fd in flats.values()) / totals(flats[other])["kwh"]
    scaled = dict(flats)
    scaled[other] = flats[other].with_kwh(flats[other].kwh * fac)
    after = model.score(scaled, refs)
    moved = {fl: round(after[fl]["score"] - base[fl]["score"], 6) for fl in flats if fl != other and abs(after[fl]["score"] - base[fl]["score"]) > 1e-9}
    R.append(_res("peer invariance under frozen references", "R7", "universal", f"scale {other} to 1.5x the largest flat ({fac:.2f}x)", "others", not moved, moved or "unchanged"))

    # missing is not zero (R3): deleting readings must not act like zero consumption
    if model.energy_pillars:
        fl = "F002"
        col = flats[fl].kwh["A01"].loc[:335].dropna()
        cells = (col - col.median()).abs().sort_values().index[:24]  # 24 typical (near-median) pre-step fridge hours
        k_nan = flats[fl].kwh.copy(); k_nan.loc[cells, "A01"] = np.nan
        k_zero = flats[fl].kwh.copy(); k_zero.loc[cells, "A01"] = 0.0
        s0 = base[fl]["score"]
        d_nan = model.score({**flats, fl: flats[fl].with_kwh(k_nan)}, refs)[fl]["score"] - s0
        d_zero = model.score({**flats, fl: flats[fl].with_kwh(k_zero)}, refs)[fl]["score"] - s0
        R.append(_res("deleting typical readings does not act like zero consumption", "R3", "universal",
                      "24 near-median F002 A01 hours: NaN vs 0", fl, abs(d_nan) < 0.5 * abs(d_zero) if d_zero else abs(d_nan) < 1e-9,
                      f"score change if deleted {d_nan:+.4f}; if set to 0 {d_zero:+.4f}"))
    return R


def summary(results: list[dict]) -> dict:
    out = {}
    for cls in ("universal", "policy", "heuristic", "info"):
        rs = [r for r in results if r["cls"] == cls]
        out[cls] = {"checks": len(rs), "failed": sum(r["passed"] is False for r in rs)}
    return out

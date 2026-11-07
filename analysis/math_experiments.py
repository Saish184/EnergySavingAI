"""Controlled experiments for the decision report (deterministic). Writes reports/math_experiments.json.

X1 size / occupancy normalisation variants      X4 combined interventions on one hourly trajectory
X2 heating under different weather              X5 missing observations and load shifting
X3 aggregation, zero pillars, floors and weights (stand-in pillars, clearly labelled)
No sustainability-score formula is proposed here.
"""
import json
import math
from itertools import combinations

import numpy as np

from common import REPORTS
from mathcore import (combine, difference, heating_degree_hours, load_flats, op_O1_heater_off_unoccupied, op_O2_always_on,
                      op_O3_fridge_repair, op_O4_daytime_electronics, op_O5_dishwasher_shift, op_S1b_heater_setback, totals)

F = load_flats()
OUT = {}
r = lambda v, n=3: round(float(v), n)
NONHEAT = ["A01", "A02", "A03", "A04", "A05", "A06"]


def kendall(a, b):
    idx = {k: i for i, k in enumerate(b)}
    pairs = list(combinations(a, 2))
    conc = sum(1 if idx[x] < idx[y] else -1 for x, y in pairs)
    return conc / len(pairs)


# X1 -------------------------------------------------------------------------------------------
nh = {fl: totals(fd, channels=NONHEAT)["kwh"] for fl, fd in F.items()}
res = {fl: fd.residents for fl, fd in F.items()}
area = {fl: fd.floor_area_m2 for fl, fd in F.items()}
ph = {fl: float(fd.occupants.sum()) for fl, fd in F.items()}
b, a = np.polyfit([res[f] for f in F], [nh[f] for f in F], 1)
variants = {
    "per_flat_kwh": nh,
    "per_resident": {f: nh[f] / res[f] for f in F},
    "per_m2": {f: nh[f] / area[f] for f in F},
    "per_equivalent_resident (OLS a+b*n)": {f: nh[f] / (a + b * res[f]) for f in F},
    "per_person_hour_home": {f: nh[f] / ph[f] for f in F},
}
ranks = {k: sorted(v, key=lambda f: -v[f]) for k, v in variants.items()}  # worst (highest) first
OUT["X1_normalisation"] = {
    "metric": "non-heater kWh (A01-A06), 28 days, observed hours",
    "ols": {"a_kwh": r(a, 1), "b_kwh_per_resident": r(b, 1)},
    "values": {k: {f: r(x) for f, x in v.items()} for k, v in variants.items()},
    "rank_highest_first": ranks,
    "kendall_tau": {f"{p} vs {q}": r(kendall(ranks[p], ranks[q])) for p, q in combinations(ranks, 2)},
    "worst_flat_by_variant": {k: v[0] for k, v in ranks.items()},
}

# X2 -------------------------------------------------------------------------------------------
x2 = {}
for fl in ("F001", "F007"):
    fd = F[fl]
    obs = totals(fd, channels=["A07"])["kwh"]
    hdh = heating_degree_hours(fd.outdoor.dropna(), 12.0)
    model = {s: float((0.12 * (12 - (fd.outdoor.dropna() + s))).clip(lower=0).sum()) for s in (-3, -1, 0, 1, 3)}
    x2[fl] = {"observed_heater_kwh": r(obs, 1), "heating_degree_hours_base12": r(hdh, 1), "kwh_per_degree_hour": r(obs / hdh, 4),
              "model_kwh_by_outdoor_shift_c": {str(k): r(v, 1) for k, v in model.items()},
              "pct_change_per_degc_colder": r(100 * (model[-1] / model[0] - 1), 1)}
OUT["X2_weather"] = {"heater_model": "kWh_h = 0.12 x max(0, 12 - T_out) (validated, both flats)", "flats": x2,
                     "note": "Raw heater kWh changes with weather at fixed behaviour; kWh per heating degree-hour does not."}

# X3 -------------------------------------------------------------------------------------------
W = {"Use": 0.40, "Waste": 0.25, "Timing": 0.20, "Health": 0.15}
mr = json.loads((REPORTS / "math_review_numbers.json").read_text())["candidate_score_ILLUSTRATIVE"]["baseline_pillars_0_100"]
names = ["I1_consumption_index", "I2_always_on_w", "I3_price_timing_ratio", "I4_carbon_timing_ratio"]
stand = {f: dict(zip(W, (v[n] for n in names))) for f, v in mr.items()}  # STAND-INS, not the teammate's pillars
geo = lambda p, w, fl=0.0: math.prod(max(p[k], fl) ** w[k] for k in w)
ari = lambda p, w: sum(w[k] * p[k] for k in w)
rank = lambda s: sorted(s, key=lambda f: -s[f])
base_geo = {f: geo(p, W) for f, p in stand.items()}
x3 = {"warning": "Pillar values are STAND-INS (illustrative candidate from the math review), mapped positionally onto the "
                 "teammate's pillar names only to exercise the aggregation; they are not the teammate's pillars.",
      "geometric_no_floor": {f: r(v, 1) for f, v in base_geo.items()},
      "geometric_floor_1": {f: r(geo(p, W, 1.0), 1) for f, p in stand.items()},
      "geometric_floor_5": {f: r(geo(p, W, 5.0), 1) for f, p in stand.items()},
      "arithmetic": {f: r(ari(p, W), 1) for f, p in stand.items()},
      "flats_with_score_0_geometric": [f for f, v in base_geo.items() if v == 0]}
x3["rank_geometric_floor_1"] = rank({f: geo(p, W, 1.0) for f, p in stand.items()})
x3["rank_arithmetic"] = rank({f: ari(p, W) for f, p in stand.items()})
pert = []
for k in W:
    for st in (-0.10, 0.10):
        w = dict(W); w[k] *= 1 + st; t = sum(w.values()); w = {a_: b_ / t for a_, b_ in w.items()}
        rk = rank({f: geo(p, w, 1.0) for f, p in stand.items()})
        pert.append({"pillar": k, "change": st, "rank_changed": rk != x3["rank_geometric_floor_1"]})
x3["weight_perturbation_pm10pct_rank_changes"] = sum(p["rank_changed"] for p in pert)
x3["weight_perturbations"] = pert
x3["single_pillar_drop_factor"] = {k: {"to_50": r(0.5 ** w, 3), "to_10": r(0.1 ** w, 3), "to_1": r(0.01 ** w, 3)} for k, w in W.items()}
OUT["X3_aggregation"] = x3

# X4 -------------------------------------------------------------------------------------------
def d(fl, ops, window=(0, 672)):
    fd = F[fl]
    return difference(fd, fd.kwh, combine(fd.kwh, ops)[0], window=window)


sets = {
    "F002": [op_O3_fridge_repair(F["F002"]), op_O5_dishwasher_shift(F["F002"])],
    "F004": [op_O4_daytime_electronics(F["F004"], F), op_O5_dishwasher_shift(F["F004"])],
    "F005": [op_O2_always_on(F["F005"], theta=0.5), op_O5_dishwasher_shift(F["F005"])],
    "F007": [op_O1_heater_off_unoccupied(F["F007"]), op_O5_dishwasher_shift(F["F007"])],
    "F007 overlap (O1 + illustrative S1b)": [op_O1_heater_off_unoccupied(F["F007"]), op_S1b_heater_setback(F["F007"])],
}
x4 = {}
for k, ops in sets.items():
    fl = k[:4]
    parts = [d(fl, [o]) for o in ops]
    both = d(fl, ops)
    x4[k] = {"individual": [{"op": o.name, **{m: r(p[m]) for m in ("kwh", "sek_spot_hourly", "co2e_kg")}} for o, p in zip(ops, parts)],
             "combined": {m: r(both[m]) for m in ("kwh", "sek_spot_hourly", "co2e_kg")},
             "sum_of_individual": {m: r(sum(p[m] for p in parts)) for m in ("kwh", "sek_spot_hourly", "co2e_kg")},
             "double_count_if_summed_kwh": r(sum(p["kwh"] for p in parts) - both["kwh"])}
OUT["X4_combined"] = x4

# X5 -------------------------------------------------------------------------------------------
fd = F["F002"]
post = fd.kwh.A01.loc[336:]
mu = fd.kwh.A01.loc[:335].mean()
moved_missing = []
for fl, f in F.items():
    op = op_O5_dishwasher_shift(f)
    for h0, h1 in op.moves:
        if np.isnan(f.kwh.A04.loc[h1]):
            k = f.kwh.A04.loc[h0]
            moved_missing.append({"flat": fl, "from_hour": h0, "to_hour": h1, "kwh": r(k),
                                  "sek": r(k * (f.price[h0] - f.price[h1])), "co2e_kg": r(k * (f.carbon[h0] - f.carbon[h1]) / 1000, 4)})
OUT["X5_missing"] = {
    "F002_O3_observed_hours_total_kwh": r((post.dropna() - mu).sum()),
    "F002_O3_window_total_at_observed_rate_kwh": r((post.dropna() - mu).mean() * 336),
    "F002_post_step_missing_hours": int(post.isna().sum()),
    "F002_baseline_understatement_if_missing_zero_filled_kwh": r(post.isna().sum() * post.mean()),
    "dishwasher_runs_moved_into_missing_hours": moved_missing,
    "value_lost_if_such_moves_are_rejected": {"sek": r(sum(m["sek"] for m in moved_missing)), "co2e_kg": r(sum(m["co2e_kg"] for m in moved_missing), 4)},
}
(REPORTS / "math_experiments.json").write_text(json.dumps(OUT, indent=2) + "\n")
print(json.dumps({k: OUT["X1_normalisation"][k] for k in ("worst_flat_by_variant", "kendall_tau", "ols")}, indent=1))
print(json.dumps(OUT["X2_weather"]["flats"], indent=1))
print(json.dumps({k: x3[k] for k in ("geometric_no_floor", "geometric_floor_1", "arithmetic", "flats_with_score_0_geometric",
                                     "rank_geometric_floor_1", "rank_arithmetic", "weight_perturbation_pm10pct_rank_changes")}, indent=1))
print(json.dumps({k: {"combined": v["combined"], "double": v["double_count_if_summed_kwh"]} for k, v in x4.items()}, indent=1))
print(json.dumps(OUT["X5_missing"], indent=1))

"""Numbers for the mathematical review (docs/math/mathematical_review.md).

Computes, from the cleaned analytical table and reports/opportunities.json:
  1. F002 interval diagnostics (assumptions of the current bootstrap vs alternatives)
  2. Uncertainty decomposition per opportunity (sampling CI vs assumption range)
  3. Overlap of savings supports between all scenarios (double-counting check) + combination rules
  4. Per-resident / household-size fairness diagnostics
  5. ILLUSTRATIVE candidate score indicators and a projected-score example (NOT an approved definition)
Writes reports/math_review_numbers.json. Deterministic (fixed seeds). Does not modify any other output.
Run: python analysis/math_review.py
"""
import json

import numpy as np
import pandas as pd

from common import PROCESSED, REPORTS

T_975_DF13 = 2.1604  # Student t 0.975 quantile, 13 df (no scipy dependency)
t = pd.read_csv(PROCESSED / "analytical_table.csv")
ok = t[~t.energy_missing].copy()
J = {o["id"]: o for o in json.loads((REPORTS / "opportunities.json").read_text())["opportunities"]}
H = t.drop_duplicates("hour_idx").set_index("hour_idx").sort_index()
P_AVG, C_AVG = float(H.spot_sek_per_kwh.mean()), float(H.carbon_gco2e_per_kwh.mean())
OUT: dict = {}
r = lambda x, n=3: None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)

# ============================================================================ 1. F002 interval
f = t[t.appliance_id == "F002-A01"].sort_values("hour_idx").set_index("hour_idx")
pre, post = f.loc[:335].energy_kwh.dropna(), f.loc[336:].energy_kwh.dropna()
mu0 = pre.mean()
s = post - mu0
daily = s.groupby(s.index // 24).sum()
hours_per_day = post.groupby(post.index // 24).size()
N = len(post)
v_post, v_mu = N * post.var(), N ** 2 * pre.var() / len(pre)
x = post.values - post.values.mean()


def newey_west(x, L):
    v = (x * x).mean()
    for k in range(1, L + 1):
        v += 2 * (1 - k / (L + 1)) * (x[:-k] * x[k:]).mean()
    return v


rng = np.random.default_rng(20261107)
dmeans = s.groupby(s.index // 24).mean().values
boot_rate = np.percentile(rng.choice(dmeans, size=(2000, 14)).mean(1) * N, [2.5, 97.5])
OUT["F002_interval"] = {
    "estimand_reported": "sum over the 332 observed post-step hours of (x_h - mean_pre)",
    "point_kwh": r(s.sum()), "mean_pre_kwh_h": r(mu0, 5), "sd_pre": r(pre.std(), 5), "sd_post": r(post.std(), 5),
    "n_pre_hours": int(len(pre)), "n_post_hours": int(N),
    "clip_at_zero_binds_hours": int((post < mu0).sum()),
    "acf_post_lag1_lag2_lag24": [r(f.loc[336:].energy_kwh.autocorr(k)) for k in (1, 2, 24)],
    "acf_daily_sums_lag1": r(daily.autocorr(1)),
    "newey_west_24_variance_ratio_vs_iid": r(newey_west(x, 24) / x.var()),
    "daily_sums_kwh": [r(v) for v in daily], "hours_per_day": hours_per_day.astype(int).tolist(),
    "intervals_kwh": {
        "current_day_bootstrap_percentile (opportunities.json)": J["O3_F002_refrigerator_step"]["scenarios"][0]["ci95_kwh"],
        "t_interval_on_14_daily_sums": [r(daily.sum() - T_975_DF13 * daily.std() * np.sqrt(14)), r(daily.sum() + T_975_DF13 * daily.std() * np.sqrt(14))],
        "normal_iid_hourly_post_only": [r(s.sum() - 1.96 * np.sqrt(v_post)), r(s.sum() + 1.96 * np.sqrt(v_post))],
        "normal_iid_hourly_incl_mean_pre_uncertainty": [r(s.sum() - 1.96 * np.sqrt(v_post + v_mu)), r(s.sum() + 1.96 * np.sqrt(v_post + v_mu))],
        "day_bootstrap_on_daily_means_x332 (missing-hour neutral)": [r(boot_rate[0]), r(boot_rate[1])],
    },
    "half_width_increase_from_mean_pre_uncertainty_pct": r(100 * (np.sqrt(v_post + v_mu) / np.sqrt(v_post) - 1), 1),
    "definition_sensitivity_kwh": {
        "reference_pre_mean": r(s.sum()),
        "reference_peer_mean_0.0526": r((post - 0.0526).clip(lower=0).sum()),
        "window_total_336h_at_observed_rate": r(s.mean() * 336),
    },
}

# ============================================================================ 2. uncertainty decomposition
dec = {}
for oid, o in J.items():
    c = next(s_ for s_ in o["scenarios"] if s_["role"] == "central")
    rng_vals = [s_["kwh"] for s_ in o["scenarios"] if s_["role"] != "upper_hypothetical"]
    rng_sek = [s_["value_spot_hourly_sek"] for s_ in o["scenarios"] if s_["role"] != "upper_hypothetical"]
    ci_k = c.get("ci95_kwh"); ci_s = c.get("ci95_value_spot_hourly_sek")
    dec[oid] = {
        "central_kwh": c["kwh"], "central_sek_hourly": c["value_spot_hourly_sek"],
        "sampling_ci_width_kwh": r(ci_k[1] - ci_k[0], 2) if ci_k else None,
        "assumption_range_width_kwh": r(max(rng_vals) - min(rng_vals), 2),
        "sampling_ci_width_sek": r(ci_s[1] - ci_s[0], 2) if ci_s else None,
        "assumption_range_width_sek": r(max(rng_sek) - min(rng_sek), 2),
        "uncertainty_sources_not_in_ci": {
            "O1_F007_heating_unoccupied": ["occupancy-sensor accuracy", "which absences are acted on (min absence length)", "rebound", "weather/season"],
            "O2_F005_elevated_base_load": ["avoidable fraction f (no data)", "device identity"],
            "O3_F002_refrigerator_step": ["post-repair level L", "repair timing", "fix effectiveness", "uncertainty of mean_pre"],
            "O4_F004_daytime_electronics": ["whether the device's work is needed", "hours acted on"],
            "O5_dishwasher_price_timing": ["tariff (decisive)", "share of runs moved", "cycle length / hours spanned", "future prices"],
        }[oid],
    }
OUT["uncertainty_decomposition"] = dec

# ============================================================================ 3. overlap / double counting
emp7 = t[(t.flat_id == "F007") & (t.appliance_code == "A07") & (t.occupants_home == 0)].sort_values("hour_idx").copy()
emp7["run"] = (emp7.hour_idx.diff() != 1).cumsum()
emp7["len"] = emp7.run.map(emp7.groupby("run").size())
h7 = ok[(ok.flat_id == "F007") & (ok.appliance_code == "A07")].copy()
# per-hour savings vectors s[(appliance_id, hour)] for each scenario (reductions) / touched cells for shifts
vec = {}
vec["O1_central (F007 heater off, absences >= 2 h)"] = {("F007-A07", h): v for h, v in emp7.loc[emp7.len >= 2, ["hour_idx", "energy_kwh"]].values}
f5 = ok[(ok.flat_id == "F005") & (ok.appliance_code == "A06")]
vec["O2_central (F005 base, f = 0.5)"] = {("F005-A06", h): 0.5 * min(max(v - 0.033, 0), 0.095) for h, v in f5[["hour_idx", "energy_kwh"]].values}
vec["O3_central (F002 fridge repair)"] = {("F002-A01", h): max(v - mu0, 0) for h, v in post.items()}
a5 = ok[ok.appliance_code == "A05"]
peer = a5[a5.flat_id != "F004"].groupby("local_hour").energy_kwh.median()
f4 = a5[(a5.flat_id == "F004") & a5.local_hour.between(9, 16)]
vec["O4_central (F004 daytime)"] = {("F004-A05", h): max(v - peer[lh], 0) for h, v, lh in f4[["hour_idx", "energy_kwh", "local_hour"]].values}
# research-report scenarios that could be combined by mistake
m = 0.12  # kWh/h per degC, balance point 12 C (both heater flats, opportunities.json heater_model)
for fl in ("F007",):
    d = ok[(ok.flat_id == fl) & (ok.appliance_code == "A07")]
    base_m = np.clip(m * (12 - d.outdoor_temp_c), 0, None); cf_m = np.clip(m * (11 - d.outdoor_temp_c), 0, None)
    ratio = (cf_m / base_m).where(base_m > 0, 0).fillna(1.0)
    vec["S1b_F007 part (heater thermostat -1 C, all hours)"] = {(f"{fl}-A07", h): v * (1 - q) for h, v, q in zip(d.hour_idx, d.energy_kwh, ratio)}
a5n = ok[(ok.appliance_code == "A05") & ok.is_overnight]
vec["S4 (electronics off 00-06 h, all flats, 50 %)"] = {(a, h): 0.5 * max(v - 0.010, 0) for a, h, v in a5n[["appliance_id", "hour_idx", "energy_kwh"]].values}
ev = ok[(ok.appliance_code == "A04") & (ok.energy_kwh > 0.1)]
shift_cells = set((a, h) for a, h in ev[["appliance_id", "hour_idx"]].values) | set((a, h + 1) for a, h in ev[["appliance_id", "hour_idx"]].values)
names = list(vec)
overlap = []
for i, a in enumerate(names):
    for b in names[i + 1:]:
        cells = set(k for k in vec[a] if vec[a][k] > 0) & set(k for k in vec[b] if vec[b][k] > 0)
        if cells:
            naive = sum(vec[a][k] + vec[b][k] for k in cells)
            # correct sequential combination on shared cells: second acts on remainder x - s_a (multiplicative form)
            xk = {k: ok.set_index(["appliance_id", "hour_idx"]).energy_kwh.get(k) for k in cells}
            combined = sum(vec[a][k] + vec[b][k] * (xk[k] - vec[a][k]) / xk[k] for k in cells if xk[k])
            overlap.append({"a": a, "b": b, "shared_cells": len(cells), "naive_sum_on_shared_kwh": r(naive, 2),
                            "combined_on_shared_kwh": r(combined, 2), "double_count_kwh": r(naive - combined, 2)})
OUT["overlap"] = {
    "scenarios": {n_: {"cells": sum(v > 0 for v in vec[n_].values()), "kwh": r(sum(vec[n_].values()), 2)} for n_ in names},
    "pairs_with_shared_cells": overlap,
    "O5_shift_touches": "A04 cells only (origin 20:00 + destination 21:00); no reduction scenario touches A04",
    "O5_shift_cells_shared_with_reductions": int(sum(len(shift_cells & set(vec[n_])) for n_ in names)),
    "opportunity_records_pairwise_disjoint": not any(p for p in overlap if p["a"].startswith("O") and p["b"].startswith("O")),
}

# ============================================================================ 4. per-student fairness
hh = t.drop_duplicates(["flat_id", "hour_idx"])
flat = pd.DataFrame({
    "residents": hh.groupby("flat_id").residents.first(),
    "floor_area_m2": hh.groupby("flat_id").floor_area_m2.first(),
    "person_hours_home": hh.groupby("flat_id").occupants_home.sum(),
    "occupancy_unknown_hours": hh.groupby("flat_id").occupancy_missing.sum(),
    "kwh_total": ok.groupby("flat_id").energy_kwh.sum(),
    "kwh_excl_heater": ok[ok.appliance_code != "A07"].groupby("flat_id").energy_kwh.sum(),
    "kwh_shared_A01_A04_A06": ok[ok.appliance_code.isin(["A01", "A04", "A06"])].groupby("flat_id").energy_kwh.sum(),
})
flat["kwh_per_resident_excl_heater"] = flat.kwh_excl_heater / flat.residents
flat["kwh_per_person_hour_home_excl_heater"] = flat.kwh_excl_heater / flat.person_hours_home
b, a = np.polyfit(flat.residents, flat.kwh_excl_heater, 1)
pred = a + b * flat.residents
ss_res = ((flat.kwh_excl_heater - pred) ** 2).sum(); ss_tot = ((flat.kwh_excl_heater - flat.kwh_excl_heater.mean()) ** 2).sum()
flat["expected_excl_heater_given_residents"] = pred
flat["index_vs_expected"] = flat.kwh_excl_heater / pred
# leave-one-out sensitivity of the fixed part
loo = {fl: list(np.polyfit(flat.drop(fl).residents, flat.drop(fl).kwh_excl_heater, 1)) for fl in flat.index}
recs = {"O1_F007_heating_unoccupied": "F007", "O2_F005_elevated_base_load": "F005", "O3_F002_refrigerator_step": "F002",
        "O4_F004_daytime_electronics": "F004"}
per_res = {oid: {"flat": fl, "residents": int(flat.loc[fl, "residents"]),
                 "flat_kwh": next(s_ for s_ in J[oid]["scenarios"] if s_["role"] == "central")["kwh"],
                 "equal_split_kwh_per_resident": r(next(s_ for s_ in J[oid]["scenarios"] if s_["role"] == "central")["kwh"] / flat.loc[fl, "residents"], 2)}
           for oid, fl in recs.items()}
OUT["per_student"] = {
    "flat_table": {fl: {k: r(v, 3) for k, v in row.items()} for fl, row in flat.iterrows()},
    "ols_kwh_excl_heater_on_residents": {"intercept_kwh": r(a, 1), "slope_kwh_per_resident": r(b, 1), "r2": r(1 - ss_res / ss_tot),
                                         "n_flats": 8, "loo_intercept_range": [r(min(v[1] for v in loo.values()), 1), r(max(v[1] for v in loo.values()), 1)],
                                         "loo_slope_range": [r(min(v[0] for v in loo.values()), 1), r(max(v[0] for v in loo.values()), 1)]},
    "equal_split_examples": per_res,
}

# ============================================================================ 5. ILLUSTRATIVE candidate score + projection
def indicators(xf: pd.DataFrame, n_res: int, ab=(a, b)) -> dict:
    """xf: one flat's rows (appliance_code, hour_idx, energy_kwh, spot, carbon, local_hour). Missing kWh excluded."""
    xf = xf.dropna(subset=["energy_kwh"])
    nh = xf[xf.appliance_code != "A07"]
    tot_h = nh.groupby("hour_idx").energy_kwh.sum()
    ctrl_h = xf[~xf.appliance_code.isin(["A01", "A07"])].groupby("hour_idx").energy_kwh.sum()
    pr = xf.dropna(subset=["spot_sek_per_kwh"])
    return {
        "I1_consumption_index": nh.energy_kwh.sum() / (ab[0] + ab[1] * n_res),                       # lower better
        "I2_always_on_w": 1000 * ctrl_h.quantile(0.05),                                                # lower better
        "I3_price_timing_ratio": (pr.energy_kwh * pr.spot_sek_per_kwh).sum() / pr.energy_kwh.sum() / P_AVG,  # lower better
        "I4_carbon_timing_ratio": (xf.energy_kwh * xf.carbon_gco2e_per_kwh).sum() / xf.energy_kwh.sum() / C_AVG,  # lower better
    }


cols = ["flat_id", "appliance_code", "appliance_id", "hour_idx", "energy_kwh", "spot_sek_per_kwh", "carbon_gco2e_per_kwh", "local_hour"]
base_ind = {fl: indicators(t[t.flat_id == fl][cols], int(flat.loc[fl, "residents"])) for fl in flat.index}
bi = pd.DataFrame(base_ind).T
anchors = {k: [float(bi[k].min()), float(bi[k].max())] for k in bi.columns}  # frozen at baseline


def normalise(ind: dict) -> dict:
    return {k: 100 * float(np.clip((anchors[k][1] - v) / (anchors[k][1] - anchors[k][0]), 0, 1)) for k, v in ind.items()}


W = {"equal": dict.fromkeys(bi.columns, 0.25), "energy_heavy": {"I1_consumption_index": 0.4, "I2_always_on_w": 0.3,
                                                                  "I3_price_timing_ratio": 0.15, "I4_carbon_timing_ratio": 0.15}}
score = lambda nrm, w: sum(w[k] * nrm[k] for k in w)
base_scores = {fl: {wn: r(score(normalise(base_ind[fl]), w), 1) for wn, w in W.items()} for fl in flat.index}


def apply(fl, reductions: dict, shifts: list) -> pd.DataFrame:
    xf = t[t.flat_id == fl][cols].copy().set_index(["appliance_id", "hour_idx"])
    for k, v in reductions.items():
        if k in xf.index:
            xf.loc[k, "energy_kwh"] = xf.loc[k, "energy_kwh"] - v
    for app, h0, h1, kwh in shifts:
        xf.loc[(app, h0), "energy_kwh"] -= kwh
        xf.loc[(app, h1), "energy_kwh"] = (0 if pd.isna(xf.loc[(app, h1), "energy_kwh"]) else xf.loc[(app, h1), "energy_kwh"]) + kwh
    return xf.reset_index()


def first_local(h0, target):
    return next(x_ for x_ in range(h0, h0 + 25) if H.local_hour[x_] == target)


proj = {}
for label, fl, red, shf in [
    ("F002 + O3 central (fridge repaired at step)", "F002", vec["O3_central (F002 fridge repair)"], []),
    ("F002 + O5 start 21:00", "F002", {}, [(a_, h, first_local(h, 21), k) for a_, h, k in ev[ev.flat_id == "F002"][["appliance_id", "hour_idx", "energy_kwh"]].values]),
    ("F002 + O3 + O5 (combined on one hourly vector)", "F002", vec["O3_central (F002 fridge repair)"],
     [(a_, h, first_local(h, 21), k) for a_, h, k in ev[ev.flat_id == "F002"][["appliance_id", "hour_idx", "energy_kwh"]].values]),
    ("F004 + O4 central", "F004", vec["O4_central (F004 daytime)"], []),
]:
    ind = indicators(apply(fl, red, shf), int(flat.loc[fl, "residents"]))
    nrm = normalise(ind)
    proj[label] = {"indicators": {k: r(v, 4) for k, v in ind.items()}, "pillars_0_100": {k: r(v, 1) for k, v in nrm.items()},
                   "score_equal": r(score(nrm, W["equal"]), 1), "score_energy_heavy": r(score(nrm, W["energy_heavy"]), 1),
                   "baseline_score_equal": base_scores[fl]["equal"], "baseline_score_energy_heavy": base_scores[fl]["energy_heavy"]}
OUT["candidate_score_ILLUSTRATIVE"] = {
    "status": "Illustrative candidate only. No sustainability score is defined in the repository or on teammate branches.",
    "baseline_indicators": {fl: {k: r(v, 4) for k, v in row.items()} for fl, row in bi.iterrows()},
    "frozen_anchors_min_max": {k: [r(v[0], 4), r(v[1], 4)] for k, v in anchors.items()},
    "baseline_pillars_0_100": {fl: {k: r(v, 1) for k, v in normalise(base_ind[fl]).items()} for fl in flat.index},
    "baseline_scores": base_scores,
    "rank_equal_vs_energy_heavy": {wn: [fl for fl, _ in sorted(base_scores.items(), key=lambda kv: -kv[1][wn])] for wn in W},
    "indicator_spearman": {k: {k2: r(v2) for k2, v2 in row.items()} for k, row in bi.corr("spearman").iterrows()},
    "projection_examples": proj,
}
(REPORTS / "math_review_numbers.json").write_text(json.dumps(OUT, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)) + "\n")
_d = lambda o: o.item() if hasattr(o, "item") else str(o)
print(json.dumps(OUT["overlap"], indent=1, default=_d))
print(json.dumps(OUT["per_student"]["ols_kwh_excl_heater_on_residents"], default=_d), json.dumps(OUT["per_student"]["equal_split_examples"], default=_d))
print(json.dumps(OUT["candidate_score_ILLUSTRATIVE"]["baseline_scores"], default=_d), json.dumps(OUT["candidate_score_ILLUSTRATIVE"]["rank_equal_vs_energy_heavy"], default=_d))
print(json.dumps(OUT["candidate_score_ILLUSTRATIVE"]["projection_examples"], indent=1, default=_d))
print(json.dumps(OUT["candidate_score_ILLUSTRATIVE"]["baseline_indicators"], default=_d))
print(json.dumps(OUT["candidate_score_ILLUSTRATIVE"]["indicator_spearman"], default=_d))

"""Exploratory data analysis + savings scenarios on the cleaned analytical table.

Inputs : data/processed/analytical_table.csv  (from clean_data.py)
Outputs: reports/figures/*.png, reports/eda_results.json, reports/eda_tables.md
Run    : python analysis/eda.py
All totals are OBSERVED (valid slots only) unless a field name says 'adj' (coverage-adjusted).
"""
from __future__ import annotations

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import APPLIANCE_LABELS, FIGURES, PROCESSED, REPORTS, SHIFTABLE

RNG = np.random.default_rng(20261107)
N_BOOT = 2000
DAYS = 28
CAT_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"]
CODES = list(APPLIANCE_LABELS)
COLOR = dict(zip(CODES, CAT_COLORS))
LBL = {k: f"{k} {v}" for k, v in APPLIANCE_LABELS.items()}
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": INK2, "axes.labelcolor": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 10, "axes.titlesize": 12,
    "axes.titleweight": "bold", "axes.axisbelow": True, "legend.frameon": False, "savefig.dpi": 150, "savefig.bbox": "tight",
})

R: dict = {}          # numeric results -> eda_results.json
TABLES: list[str] = []  # markdown tables -> eda_tables.md


def md(title: str, df: pd.DataFrame, floatfmt=2):
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_float_dtype(df[c]):
            df[c] = df[c].map(lambda v: "" if pd.isna(v) else f"{v:,.{floatfmt}f}")
    head = "| " + " | ".join([df.index.name or ""] + [str(c) for c in df.columns]) + " |"
    sep = "|" + "---|" * (len(df.columns) + 1)
    rows = ["| " + " | ".join([str(i)] + [str(v) for v in r]) + " |" for i, r in zip(df.index, df.values)]
    TABLES.append(f"### {title}\n\n" + "\n".join([head, sep, *rows]) + "\n")


def save(fig, name):
    fig.savefig(FIGURES / name)
    plt.close(fig)


def boot_total(daily: pd.Series, days=None) -> list[float]:
    """95% CI of a window total by resampling the window's days (block = 1 day) with replacement.
    days: the scenario's window (default all 28 days); days outside the window are NOT padded in."""
    days = list(range(DAYS)) if days is None else list(days)
    v = daily.reindex(days, fill_value=0.0).to_numpy()
    sims = RNG.choice(v, size=(N_BOOT, len(days)), replace=True).sum(axis=1)
    return [round(float(np.percentile(sims, 2.5)), 2), round(float(np.percentile(sims, 97.5)), 2)]


# ======================================================================================
t = pd.read_csv(PROCESSED / "analytical_table.csv")
t["day"] = t.hour_idx // 24
ok = t[~t.energy_missing].copy()
flats = t.groupby("flat_id")[["residents", "floor_area_m2"]].first()
R["observed_kwh_total"] = round(ok.energy_kwh.sum(), 1)
R["coverage_pct"] = round(100 * len(ok) / len(t), 2)
priced = ok[~ok.price_missing]
mean_spot = float(t.drop_duplicates("timestamp_utc").spot_sek_per_kwh.mean())
R["time_avg_spot_sek_per_kwh"] = round(mean_spot, 4)
R["time_avg_carbon_g_per_kwh"] = round(float(t.drop_duplicates("timestamp_utc").carbon_gco2e_per_kwh.mean()), 2)

# Coverage-adjusted channel totals: valid mean x 672 per flat-channel (estimate, not imputed rows)
adj = ok.groupby("appliance_id").energy_kwh.mean() * 672
adj_flat_cat = adj.rename("kwh_adj").reset_index().assign(flat_id=lambda d: d.appliance_id.str[:4],
                                                          code=lambda d: d.appliance_id.str[-3:])

# ---------------------------------------------------------------- Q1 consumption ranking
cat = ok.groupby("appliance_code").agg(kwh=("energy_kwh", "sum"), cost=("cost_spot_sek", "sum"),
                                       co2=("co2e_kg", "sum"))
cat["kwh_adj"] = adj_flat_cat.groupby("code").kwh_adj.sum()
cat["kwh_share_pct"] = 100 * cat.kwh / cat.kwh.sum()
cat["cost_share_pct"] = 100 * cat.cost / cat.cost.sum()
cat["co2_share_pct"] = 100 * cat.co2 / cat.co2.sum()
pk = priced.groupby("appliance_code").energy_kwh.sum()
cat["eff_price_sek_per_kwh"] = cat.cost / pk
cat["eff_carbon_g_per_kwh"] = 1000 * cat.co2 / cat.kwh
cat["flats_using"] = ok[ok.energy_kwh > 0].groupby("appliance_code").flat_id.nunique()
cat.index = [LBL[c] for c in cat.index]
cat.index.name = "Channel (inferred label)"
cat = cat.sort_values("kwh", ascending=False)
R["by_channel"] = cat.round(3).to_dict(orient="index")
md("Consumption, spot cost and CO2e by channel (28 days, all flats, observed)",
   cat[["kwh", "kwh_adj", "kwh_share_pct", "cost", "cost_share_pct", "co2", "co2_share_pct",
        "eff_price_sek_per_kwh", "eff_carbon_g_per_kwh", "flats_using"]]
   .rename(columns={"kwh": "kWh", "kwh_adj": "kWh (cov.-adj.)", "kwh_share_pct": "kWh %", "cost": "Spot SEK",
                    "cost_share_pct": "SEK %", "co2": "kgCO2e", "co2_share_pct": "CO2e %",
                    "eff_price_sek_per_kwh": "Eff. SEK/kWh", "eff_carbon_g_per_kwh": "Eff. g/kWh",
                    "flats_using": "Flats using"}))

fc = ok.pivot_table(index="flat_id", columns="appliance_code", values="energy_kwh", aggfunc="sum")
fc["Total"] = fc.sum(axis=1)
R["flat_by_channel_kwh"] = fc.round(2).to_dict(orient="index")
md("kWh by flat and channel (observed, 28 days)", fc, 1)
share = fc[CODES].div(fc.Total, axis=0) * 100
R["flat_top_channel"] = {f: [share.loc[f].idxmax(), round(share.loc[f].max(), 1)] for f in share.index}
md("Channel share of each flat's consumption (%)", share, 1)
non_heat = fc.drop(columns=["A07", "Total"])
R["flat_top_channel_excl_heater"] = {f: non_heat.loc[f].idxmax() for f in non_heat.index}

# Fig 1: channel ranking, three panels (kWh, SEK, kgCO2e) - same order, one axis each
fig, axes = plt.subplots(1, 3, figsize=(13, 3.8), sharey=True)
order = [c for c in cat.index][::-1]
codes_order = [c.split()[0] for c in order]
for ax, col, title in zip(axes, ["kwh", "cost", "co2"], ["Electricity (kWh)", "Spot cost (SEK, excl. VAT)", "Emissions (kgCO2e)"]):
    vals = cat.loc[order, col]
    ax.barh(order, vals, color=[COLOR[c] for c in codes_order], height=0.62, edgecolor=SURF, linewidth=2)
    for y, v in enumerate(vals):
        ax.text(v, y, f" {v:,.0f}" if col != "co2" else f" {v:,.1f}", va="center", fontsize=9, color=INK)
    ax.set_title(title, loc="left"); ax.grid(axis="y", visible=False)
    ax.set_xlim(0, vals.max() * 1.22)
fig.suptitle("Which channels use the most electricity, cost the most and emit the most - 8 flats, 1-28 Oct 2026",
             x=0.01, ha="left", fontsize=12, fontweight="bold", y=1.04)
save(fig, "01_channel_ranking.png")

# ---------------------------------------------------------------- Q5 flats
fl = fc[["Total"]].rename(columns={"Total": "kwh"}).join(flats)
fl["kwh_adj"] = adj_flat_cat.groupby("flat_id").kwh_adj.sum()
fl["kwh_excl_heater"] = fc.Total - fc.A07
fl["cost"] = ok.groupby("flat_id").cost_spot_sek.sum()
fl["co2"] = ok.groupby("flat_id").co2e_kg.sum()
fl["kwh_per_resident"] = fl.kwh / fl.residents
fl["kwh_excl_heater_per_resident"] = fl.kwh_excl_heater / fl.residents
fl["kwh_per_m2"] = fl.kwh / fl.floor_area_m2
occ_h = t.drop_duplicates(["flat_id", "hour_idx"]).groupby("flat_id").occupants_home.sum()
fl["kwh_per_occupant_hour"] = fl.kwh_excl_heater / occ_h
fl["sek_per_resident"] = fl.cost / fl.residents
fl["indoor_mean_c"] = t.drop_duplicates(["flat_id", "hour_idx"]).groupby("flat_id").indoor_temp_c.mean()
fl["occupancy_rate"] = occ_h / (fl.residents * 672)
R["by_flat"] = fl.round(3).to_dict(orient="index")
md("Flat comparison (observed, 28 days)", fl[["residents", "floor_area_m2", "kwh", "kwh_adj", "kwh_excl_heater",
   "kwh_per_resident", "kwh_excl_heater_per_resident", "kwh_per_m2", "kwh_per_occupant_hour", "cost",
   "sek_per_resident", "co2", "indoor_mean_c", "occupancy_rate"]].rename(columns={
   "floor_area_m2": "m2", "kwh": "kWh", "kwh_adj": "kWh adj", "kwh_excl_heater": "kWh excl. A07",
   "kwh_per_resident": "kWh/res", "kwh_excl_heater_per_resident": "kWh/res excl. A07", "kwh_per_m2": "kWh/m2",
   "kwh_per_occupant_hour": "kWh/occupant-h excl. A07", "cost": "SEK", "sek_per_resident": "SEK/res",
   "co2": "kgCO2e", "indoor_mean_c": "Indoor °C", "occupancy_rate": "Occ. rate"}))
# correlation of non-heater use with residents
R["corr_residents_vs_kwh_excl_heater"] = round(float(np.corrcoef(fl.residents, fl.kwh_excl_heater)[0, 1]), 3)

# Fig 2: stacked per resident by flat
fig, axes = plt.subplots(1, 2, figsize=(13, 4.2))
pr = fc[CODES].div(flats.residents, axis=0)
for ax, data, title in [(axes[0], fc[CODES], "kWh per flat"), (axes[1], pr, "kWh per resident")]:
    left = np.zeros(len(data))
    for c in CODES:
        ax.barh(data.index, data[c], left=left, color=COLOR[c], label=LBL[c], height=0.62, edgecolor=SURF, linewidth=2)
        left += data[c].to_numpy()
    for y, v in enumerate(left):
        ax.text(v, y, f" {v:,.0f}", va="center", fontsize=9, color=INK)
    ax.invert_yaxis(); ax.set_title(title, loc="left"); ax.grid(axis="y", visible=False)
    ax.set_xlim(0, left.max() * 1.15)
    ax.set_yticks(range(len(data)), [f"{f} ({flats.residents[f]} res.)" for f in data.index])
fig.legend(*axes[1].get_legend_handles_labels(), loc="lower center", ncol=4, fontsize=8, bbox_to_anchor=(0.5, -0.1))
fig.suptitle("Two flats with portable heaters (F001, F007) dominate; per resident F001 is ~3.5x the median",
             x=0.01, ha="left", fontweight="bold", y=1.03)
save(fig, "02_flat_by_channel.png")

# ---------------------------------------------------------------- Q3 temporal patterns
# hourly profile (local hour), mean kWh per flat-hour per channel
prof = ok.groupby(["local_hour", "appliance_code"]).energy_kwh.mean().unstack() * 1  # per flat
R["hourly_profile_mean_kwh_per_flat"] = prof.round(4).to_dict()
tot_prof = ok.groupby(["flat_id", "hour_idx", "local_hour"]).energy_kwh.sum().groupby("local_hour").mean()
R["peak_local_hour"] = int(tot_prof.idxmax()); R["trough_local_hour"] = int(tot_prof.idxmin())
hp = t.drop_duplicates("timestamp_utc").groupby("local_hour")[["spot_sek_per_kwh", "carbon_gco2e_per_kwh"]].mean()
R["price_by_local_hour"] = hp.spot_sek_per_kwh.round(4).to_dict()
R["carbon_by_local_hour"] = hp.carbon_gco2e_per_kwh.round(2).to_dict()
R["most_expensive_local_hours"] = hp.spot_sek_per_kwh.nlargest(4).index.tolist()
R["cheapest_local_hours"] = hp.spot_sek_per_kwh.nsmallest(4).index.tolist()

fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
bottom = np.zeros(24)
for c in CODES:
    axes[0].bar(prof.index, prof[c], bottom=bottom, color=COLOR[c], label=LBL[c], width=0.86, edgecolor=SURF, linewidth=1)
    bottom += prof[c].to_numpy()
axes[0].set_ylabel("Mean kWh per flat-hour"); axes[0].legend(ncol=2, fontsize=8, loc="upper center")
axes[0].set_title("Average load by local hour of day (all flats, stacked by channel)", loc="left")
axes[1].plot(hp.index, hp.spot_sek_per_kwh, color=INK, lw=2, marker="o", ms=4)
axes[1].axhline(0, color=INK2, lw=0.8)
axes[1].set_ylabel("Spot SEK/kWh"); axes[1].set_xlabel("Local hour (Europe/Stockholm)")
axes[1].set_title("Mean spot price by local hour", loc="left"); axes[1].set_xticks(range(0, 24, 2))
save(fig, "03_hourly_profile_vs_price.png")

# daily totals, complete local days (2-28 Oct); per-hour normalised x24 for the 25 h DST day
fh = ok.groupby(["flat_id", "local_date", "hour_idx"]).energy_kwh.sum().reset_index()
hours_per_day = t.drop_duplicates(["flat_id", "hour_idx"]).groupby(["flat_id", "local_date"]).size()
full_days = [d for d in sorted(t.local_date.unique()) if "2026-10-02" <= d <= "2026-10-28"]
dd = fh.groupby(["flat_id", "local_date"]).agg(kwh=("energy_kwh", "sum"), n=("hour_idx", "nunique")).reset_index()
dd = dd[dd.local_date.isin(full_days)]
dd["kwh_24h"] = dd.kwh / dd.n * 24   # normalise for DST day and for flat-hours with no valid channel
daily = dd.pivot(index="local_date", columns="flat_id", values="kwh_24h")
R["daily_kwh_24h_mean_by_flat"] = daily.mean().round(2).to_dict()
R["daily_kwh_24h_cv_by_flat"] = (daily.std() / daily.mean()).round(3).to_dict()
wk = pd.to_datetime(pd.Series(daily.index)).dt.dayofweek.ge(5).to_numpy()
wkd = pd.DataFrame({"weekday": daily[~wk].mean(), "weekend": daily[wk].mean()})
wkd["weekend_minus_weekday_pct"] = 100 * (wkd.weekend / wkd.weekday - 1)
R["weekday_weekend"] = wkd.round(3).to_dict(orient="index")
wkc = ok.assign(we=ok.is_weekend).groupby(["appliance_code", "we"]).energy_kwh.mean().unstack()
wkc["weekend_vs_weekday_pct"] = 100 * (wkc[True] / wkc[False] - 1)
R["weekday_weekend_by_channel_pct"] = wkc.weekend_vs_weekday_pct.round(1).to_dict()
md("Weekday vs weekend mean daily kWh (complete local days 2-28 Oct, normalised to 24 h)", wkd)

fig, ax = plt.subplots(figsize=(11, 4.2))
flat_cols = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
for i, f in enumerate(daily.columns):
    ax.plot(pd.to_datetime(daily.index), daily[f], color=flat_cols[i], lw=2, label=f)
for d in pd.to_datetime(daily.index)[wk]:
    ax.axvspan(d, d + pd.Timedelta("1D"), color=GRID, alpha=0.5, lw=0)
outd = t.drop_duplicates("hour_idx").groupby("local_date").outdoor_temp_c.mean().reindex(daily.index)
ax.set_ylabel("kWh per day"); ax.legend(ncol=8, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12))
ax.set_title("Daily electricity per flat (complete local days, shaded = weekend). Heater flats track the weather.", loc="left")
save(fig, "04_daily_by_flat.png")

# overnight (00:00-05:59 local)
on = ok[ok.is_overnight]
night = on.groupby(["flat_id", "appliance_code"]).energy_kwh.mean().unstack() * 6  # kWh per night
night["Total"] = night.sum(axis=1)
night["excl_fridge_heater"] = night.Total - night.A01 - night.A07
R["overnight_kwh_per_night"] = night.round(3).to_dict(orient="index")
R["overnight_share_of_total_pct"] = round(100 * on.energy_kwh.sum() / ok.energy_kwh.sum(), 1)
R["overnight_share_by_flat_pct"] = (100 * on.groupby("flat_id").energy_kwh.sum() / ok.groupby("flat_id").energy_kwh.sum()).round(1).to_dict()
md("Overnight (00:00-05:59 local) mean kWh per night by flat and channel", night, 3)

# Fig: overnight discretionary load
fig, ax = plt.subplots(figsize=(10, 3.8))
oc = ["A05", "A06", "A02", "A03", "A04"]
left = np.zeros(8)
for c in oc:
    ax.barh(night.index, night[c], left=left, color=COLOR[c], label=LBL[c], height=0.62, edgecolor=SURF, linewidth=2)
    left += night[c].to_numpy()
for y, v in enumerate(left):
    ax.text(v, y, f" {v:.2f}", va="center", fontsize=9)
ax.invert_yaxis(); ax.grid(axis="y", visible=False); ax.legend(fontsize=8, loc="lower right")
ax.set_xlabel("kWh per night (00:00-05:59 local)"); ax.set_xlim(0, left.max() * 1.15)
ax.set_title("Overnight discretionary load (excludes cold appliance and heater): F005 highest", loc="left")
save(fig, "05_overnight_discretionary.png")

# ---------------------------------------------------------------- Q4 relationships
hh = ok.groupby(["flat_id", "hour_idx"]).agg(kwh=("energy_kwh", "sum"), n=("energy_kwh", "size"),
                                             occ=("occupants_home", "first"), out=("outdoor_temp_c", "first"),
                                             ind=("indoor_temp_c", "first"), price=("spot_sek_per_kwh", "first"),
                                             carbon=("carbon_gco2e_per_kwh", "first")).reset_index()
nh = ok[ok.appliance_code != "A07"].groupby(["flat_id", "hour_idx"]).energy_kwh.sum().rename("kwh_nh")
hh = hh.join(nh, on=["flat_id", "hour_idx"])
hh = hh[hh.n == 7]  # complete flat-hours only
heater_flats = ["F001", "F007"]
corr = {}
for name, d in [("all_flats", hh), ("heater_flats", hh[hh.flat_id.isin(heater_flats)]),
                ("non_heater_flats", hh[~hh.flat_id.isin(heater_flats)])]:
    corr[name] = d[["kwh", "kwh_nh", "occ", "out", "ind", "price", "carbon"]].corr(method="spearman").loc[
        ["kwh", "kwh_nh"], ["occ", "out", "ind", "price", "carbon"]].round(3).to_dict(orient="index")
# within-flat occupancy effect (non-heater kWh per extra occupant)
slopes = {}
for f, d in hh.dropna(subset=["occ"]).groupby("flat_id"):
    slopes[f] = round(float(np.polyfit(d.occ, d.kwh_nh, 1)[0]), 4)
corr["within_flat_kwh_nh_per_extra_occupant"] = slopes
pr_ = t.drop_duplicates("timestamp_utc")
corr["price_vs_carbon_spearman"] = round(float(pr_[["spot_sek_per_kwh", "carbon_gco2e_per_kwh"]].corr("spearman").iloc[0, 1]), 3)
agg_h = hh.groupby("hour_idx").agg(kwh=("kwh", "sum"), price=("price", "first"))
corr["fleet_load_vs_price_spearman"] = round(float(agg_h.corr("spearman").iloc[0, 1]), 3)
R["correlations"] = corr
R["load_weighted_price_sek_per_kwh"] = round(float(priced.cost_spot_sek.sum() / priced.energy_kwh.sum()), 4)
R["load_weighted_carbon_g_per_kwh"] = round(float(1000 * ok.co2e_kg.sum() / ok.energy_kwh.sum()), 2)
occ_tbl = hh.dropna(subset=["occ"]).groupby("occ").agg(kwh_nh=("kwh_nh", "mean"), n=("kwh_nh", "size"))
R["non_heater_kwh_by_occupants"] = occ_tbl.round(4).to_dict(orient="index")

# Heater model: degree-hour fit per heater flat, heat = b * max(0, T0 - Tout)
hm = ok[(ok.appliance_code == "A07") & ok.flat_id.isin(heater_flats)].dropna(subset=["outdoor_temp_c"])
heat_model = {}
for f, d in hm.groupby("flat_id"):
    on_ = d[d.energy_kwh > 0]
    b, a = np.polyfit(on_.outdoor_temp_c, on_.energy_kwh, 1)  # heat = a + b*T, b<0
    heat_model[f] = {"slope_kwh_per_h_per_degC": round(-b, 4), "balance_point_c": round(-a / b, 2),
                     "r_all_hours": round(float(np.corrcoef(d.outdoor_temp_c, d.energy_kwh)[0, 1]), 3),
                     "kwh": round(d.energy_kwh.sum(), 1), "hours_on": int((d.energy_kwh > 0).sum()),
                     "indoor_mean_c": round(float(d.indoor_temp_c.mean()), 2),
                     "indoor_std_c": round(float(d.indoor_temp_c.std()), 2),
                     "corr_indoor_vs_heater": round(float(np.corrcoef(d.indoor_temp_c, d.energy_kwh)[0, 1]), 3)}
R["heater_model"] = heat_model

fig, ax = plt.subplots(figsize=(8.5, 4.6))
for f, c in zip(heater_flats, ["#2a78d6", "#6250d6"]):
    d = hm[hm.flat_id == f]
    ax.scatter(d.outdoor_temp_c, d.energy_kwh, s=10, alpha=0.35, color=c, edgecolor="none", label=f"{f} hourly")
    m = heat_model[f]; xs = np.linspace(d.outdoor_temp_c.min(), d.outdoor_temp_c.max(), 50)
    ax.plot(xs, np.clip(m["slope_kwh_per_h_per_degC"] * (m["balance_point_c"] - xs), 0, None), color=c, lw=2.5,
            label=f"{f} fit: {m['slope_kwh_per_h_per_degC']:.3f} kWh/h per °C, off above {m['balance_point_c']:.1f} °C")
ax.set_xlabel("Outdoor temperature (°C)"); ax.set_ylabel("Heater kWh in hour")
ax.set_title("Portable heater use rises ~linearly as it gets colder", loc="left"); ax.legend(fontsize=8)
save(fig, "06_heater_vs_outdoor.png")

# ---------------------------------------------------------------- Q6 anomalies
anom = {}
# F002 cold-appliance step change
f2 = t[t.appliance_id == "F002-A01"].set_index("hour_idx").energy_kwh
cp = max(range(48, 624), key=lambda k: abs(f2.loc[k:].mean() - f2.loc[:k - 1].mean()))
pre, post = f2.loc[:cp - 1].mean(), f2.loc[cp:].mean()
peers = ok[(ok.appliance_code == "A01") & (ok.flat_id != "F002")].energy_kwh
anom["F002_fridge_step"] = {
    "changepoint_local": t[(t.appliance_id == "F002-A01") & (t.hour_idx == cp)].timestamp_local.iloc[0],
    "pre_mean_kwh_h": round(pre, 4), "post_mean_kwh_h": round(post, 4), "ratio": round(post / pre, 2),
    "peer_mean_kwh_h": round(peers.mean(), 4), "post_min_kwh_h": round(f2.loc[cp:].min(), 4),
    "pre_max_kwh_h": round(f2.loc[:cp - 1].max(), 4), "post_hours_valid": int(f2.loc[cp:].notna().sum()),
    "excess_kwh_observed": round(float((f2.loc[cp:] - pre).sum()), 2)}
# F005 A06 always-on floor
a6 = ok[ok.appliance_code == "A06"]
floor = a6.groupby("flat_id").energy_kwh.quantile(0.05)
anom["A06_floor_kwh_h_by_flat"] = floor.round(4).to_dict()
anom["F005_A06_excess_floor_kwh_h"] = round(float(floor["F005"] - floor.drop("F005").median()), 4)
# F004 A05 daytime
a5 = ok[ok.appliance_code == "A05"]
day5 = a5[a5.local_hour.between(9, 16)].groupby("flat_id").energy_kwh.mean()
emp5 = a5[a5.occupants_home == 0].groupby("flat_id").energy_kwh.mean()
anom["A05_daytime_09_16_mean_by_flat"] = day5.round(4).to_dict()
anom["A05_mean_when_flat_empty_by_flat"] = emp5.round(4).to_dict()
# heater while nobody home
hz = ok[(ok.appliance_code == "A07") & (ok.energy_kwh > 0)]
anom["heater_on_empty_flat"] = {f: {"hours": int(((d.occupants_home == 0)).sum()),
                                    "kwh": round(float(d.loc[d.occupants_home == 0, "energy_kwh"].sum()), 2)}
                                for f, d in hz.groupby("flat_id")}
anom["heater_overnight_share_pct"] = {f: round(100 * d[d.is_overnight].energy_kwh.sum() / d.energy_kwh.sum(), 1)
                                      for f, d in hz.groupby("flat_id")}
# dishwasher at fixed time
a4 = ok[(ok.appliance_code == "A04") & (ok.energy_kwh > 0.1)]
anom["dishwasher_events"] = int(len(a4)); anom["dishwasher_share_at_20_local_pct"] = round(100 * (a4.local_hour == 20).mean(), 1)
# event-channel standby: zero-share
zero = ok.groupby("appliance_code").energy_kwh.apply(lambda s: (s == 0).mean())
anom["zero_share_by_channel"] = zero.round(3).to_dict()
# heater switching behaviour in cold (<12 C) empty hours: F001 vs F007
cold = ok[(ok.appliance_code == "A07") & ok.flat_id.isin(heater_flats) & (ok.outdoor_temp_c < 12)]
anom["heater_cold_empty_hours"] = {f: {"empty_hours": int((d.occupants_home == 0).sum()),
                                       "heater_off_in_empty_hours": int(((d.occupants_home == 0) & (d.energy_kwh == 0)).sum())}
                                   for f, d in cold.groupby("flat_id")}
# vacancy baseload: F003 empty for whole local days 13-15 Oct
vac = ok[(ok.flat_id == "F003") & ok.local_date.isin(["2026-10-13", "2026-10-14", "2026-10-15"])]
anom["F003_vacancy"] = {"days": ["2026-10-13", "2026-10-15"],
                        "max_occupants": float(vac.occupants_home.max()),
                        "kwh_per_day_by_channel": (vac.groupby("appliance_code").energy_kwh.mean() * 24).round(3).to_dict(),
                        "kwh_per_day_total": round(float(vac.groupby("appliance_code").energy_kwh.mean().sum() * 24), 2)}
anom["fleet_A06_33W_floor_kwh_28d"] = round(float(floor.drop("F005").median() * 672 * 8), 1)
R["anomalies"] = anom

fig, axes = plt.subplots(1, 2, figsize=(13, 3.8), gridspec_kw={"width_ratios": [1.6, 1]})
ts = pd.to_datetime(t[t.appliance_id == "F002-A01"].sort_values("hour_idx").timestamp_utc)
axes[0].plot(ts, f2.values, color="#2a78d6", lw=1, label="F002 cold appliance (A01)")
pm = ok[(ok.appliance_code == "A01") & (ok.flat_id != "F002")].groupby("hour_idx").energy_kwh.median()
axes[0].plot(pd.to_datetime(t.drop_duplicates("hour_idx").set_index("hour_idx").loc[pm.index, "timestamp_utc"]), pm.values,
             color=INK2, lw=1, label="Median of other 7 flats")
axes[0].axvline(ts.iloc[cp], color=INK, ls="--", lw=1)
axes[0].text(ts.iloc[cp], post * 1.18, f"  step on {anom['F002_fridge_step']['changepoint_local'][:10]}: {pre:.3f} → {post:.3f} kWh/h (x{post/pre:.1f})", fontsize=9)
axes[0].set_ylim(0, post * 1.4); axes[0].set_ylabel("kWh per hour"); axes[0].legend(fontsize=8, loc="lower left")
axes[0].set_title("F002 cold appliance: sustained step change (suspected fault)", loc="left")
import matplotlib.dates as mdates
axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
axes[1].barh(floor.index, floor.values, color=["#eb6834" if f == "F005" else "#2a78d6" for f in floor.index],
             height=0.62, edgecolor=SURF, linewidth=2)
for y, v in enumerate(floor.values):
    axes[1].text(v, y, f" {v*1000:.0f} W", va="center", fontsize=9)
axes[1].invert_yaxis(); axes[1].grid(axis="y", visible=False); axes[1].set_xlim(0, floor.max() * 1.3)
axes[1].set_xlabel("A06 always-on floor (5th percentile, kWh/h)")
axes[1].set_title("F005 lighting/entertainment never drops below ~128 W", loc="left")
save(fig, "07_anomalies.png")

# ---------------------------------------------------------------- Q7 load shifting (hourly tariff only)
price = t.drop_duplicates("hour_idx").set_index("hour_idx")[["spot_sek_per_kwh", "carbon_gco2e_per_kwh", "local_hour"]]


def shift_events(code: str, max_delay: int, allowed_hours: set[int] | None):
    ev = ok[(ok.appliance_code == code) & (ok.energy_kwh > 0.1)]
    rows = []
    for _, e in ev.iterrows():
        h0 = int(e.hour_idx)
        if pd.isna(price.at[h0, "spot_sek_per_kwh"]):
            continue
        cands = [h for h in range(h0, min(h0 + max_delay + 1, 672))
                 if pd.notna(price.at[h, "spot_sek_per_kwh"]) and (allowed_hours is None or price.at[h, "local_hour"] in allowed_hours or h == h0)]
        best = min(cands, key=lambda h: price.at[h, "spot_sek_per_kwh"])
        rows.append(dict(flat_id=e.flat_id, day=h0 // 24, kwh=e.energy_kwh, h0=h0, best=best, delay=best - h0,
                         cost0=e.energy_kwh * price.at[h0, "spot_sek_per_kwh"],
                         cost1=e.energy_kwh * price.at[best, "spot_sek_per_kwh"],
                         co2_0=e.energy_kwh * price.at[h0, "carbon_gco2e_per_kwh"] / 1000,
                         co2_1=e.energy_kwh * price.at[best, "carbon_gco2e_per_kwh"] / 1000))
    return pd.DataFrame(rows)


shift = {}
dish = shift_events("A04", 11, None)  # delay-start up to 11 h (20:00 -> 07:00), any hour
wash = shift_events("A03", 12, set(range(7, 22)))  # delay up to 12 h but only start 07:00-21:59 local
for name, d in [("dishwasher_A04_delay_to_07", dish), ("washing_A03_delay_12h_daytime", wash)]:
    d["save_sek"] = d.cost0 - d.cost1; d["dco2"] = d.co2_1 - d.co2_0
    shift[name] = {"events": len(d), "kwh": round(d.kwh.sum(), 2), "baseline_sek": round(d.cost0.sum(), 2),
                   "counterfactual_sek": round(d.cost1.sum(), 2), "saving_sek_hourly_tariff": round(d.save_sek.sum(), 2),
                   "saving_pct": round(100 * d.save_sek.sum() / d.cost0.sum(), 1),
                   "saving_sek_per_event": round(d.save_sek.mean(), 3),
                   "ci95_sek": boot_total(d.groupby("day").save_sek.sum()),
                   "co2_change_kg": round(d.dco2.sum(), 3), "kwh_change": 0.0,
                   "median_delay_h": float(d.delay.median()),
                   "saving_sek_monthly_avg_or_fixed_tariff": 0.0}
R["load_shifting"] = shift
# how much of all consumption is plausibly shiftable
R["shiftable_share_pct"] = round(100 * ok[ok.appliance_code.isin(SHIFTABLE)].energy_kwh.sum() / ok.energy_kwh.sum(), 2)
# upper bound: if ALL kWh were bought at the cheapest hour of each local day
dmin = t.drop_duplicates("hour_idx").groupby("day").spot_sek_per_kwh.min()
R["theoretical_max_all_load_to_daily_min_sek"] = round(float(priced.cost_spot_sek.sum() - (priced.energy_kwh * priced.day.map(dmin)).sum()), 2)

# ---------------------------------------------------------------- Q8 / Phase 3 savings scenarios
def scen(name, base: pd.DataFrame, saved_kwh: pd.Series, desc, evidence, assumptions, verifiable, days=None):
    """base: rows of ok (index-aligned with saved_kwh) - observed baseline; saved_kwh: kWh removed per row."""
    s = pd.DataFrame({"day": base.day, "kwh": saved_kwh, "price": base.spot_sek_per_kwh,
                      "carbon": base.carbon_gco2e_per_kwh})
    s["sek"] = s.kwh * s.price
    s["co2"] = s.kwh * s.carbon / 1000
    b_kwh = base.energy_kwh.sum()
    out = {"description": desc, "evidence": evidence, "assumptions": assumptions, "verifiable_from_data": verifiable,
           "baseline_kwh": round(b_kwh, 2), "baseline_sek_spot": round(base.cost_spot_sek.sum(), 2),
           "baseline_co2_kg": round(base.co2e_kg.sum(), 3),
           "counterfactual_kwh": round(b_kwh - s.kwh.sum(), 2),
           "saving_kwh": round(s.kwh.sum(), 2), "saving_pct_of_baseline": round(100 * s.kwh.sum() / b_kwh, 1),
           "saving_sek_hourly_spot": round(s.sek.sum(), 2),
           "saving_sek_monthly_avg_spot": round(s.kwh.sum() * mean_spot, 2),
           "saving_co2_kg": round(s.co2.sum(), 3),
           "period_days": DAYS if days is None else len(list(days)),
           "ci95_kwh": boot_total(s.groupby("day").kwh.sum(), days),
           "ci95_sek_hourly": boot_total(s.groupby("day").sek.sum(), days),
           "ci95_co2_kg": boot_total(s.groupby("day").co2.sum(), days)}
    R.setdefault("scenarios", {})[name] = out


# S1 F007 heater running while nobody is home (observed)
h7 = ok[(ok.flat_id == "F007") & (ok.appliance_code == "A07")].copy()
scen("S1_F007_heater_off_when_empty", h7, h7.energy_kwh.where(h7.occupants_home == 0, 0.0),
     "F007: switch the portable heater off (or use a timer/presence plug) when nobody is home.",
     f"Heater drew {anom['heater_on_empty_flat']['F007']['kwh']} kWh in {anom['heater_on_empty_flat']['F007']['hours']} hours with 0 occupants; "
     "F001 never ran its heater in an empty flat. Main heating (district heat) keeps the flat warm meanwhile.",
     "Heater energy in hours with occupants_home == 0 is avoidable; hours with unknown occupancy are not counted; no pre-heat rebound modelled.",
     "Yes for the baseline (observed kWh in empty hours); counterfactual assumes the heater is simply off.")

# S1c F007 setpoint to peer level (22.5 -> 20.5 C) - model-based, low confidence
m7 = heat_model["F007"]; dT = round(m7["indoor_mean_c"] - fl.drop(index=heater_flats).indoor_mean_c.mean(), 2)
mb = np.clip(m7["slope_kwh_per_h_per_degC"] * (m7["balance_point_c"] - h7.outdoor_temp_c), 0, None)
mc = np.clip(m7["slope_kwh_per_h_per_degC"] * (m7["balance_point_c"] - dT - h7.outdoor_temp_c), 0, None)
ratio7 = (mc / mb).where(mb > 0, 0).fillna(1.0)
occ_mask = h7.occupants_home != 0  # do not double count S1
scen("S1c_F007_setpoint_to_20_5C", h7, (h7.energy_kwh * (1 - ratio7)).where(occ_mask, 0.0),
     f"F007: lower the heater thermostat by {dT} °C so the flat sits at the 20.5 °C every other flat has (occupied hours only).",
     f"F007 indoor mean {m7['indoor_mean_c']} °C (std {m7['indoor_std_c']}) vs 20.50 °C in the six non-heater flats and F001.",
     f"Degree-hour model (slope {m7['slope_kwh_per_h_per_degC']} kWh/h/°C, balance point {m7['balance_point_c']} °C); the setpoint change shifts the balance point 1:1. "
     "CAUTION: F001 has an identical heater curve while held at 20.5 °C, so the dataset does not show the heater causing F007's extra 2 °C.",
     "No - simulated, low confidence.")
# S1b sensitivity: both heater flats 1 C lower setpoint (lower-confidence, generic)
hb = ok[ok.flat_id.isin(heater_flats) & (ok.appliance_code == "A07")].copy()
cfb = []
for f, d in hb.groupby("flat_id"):
    m = heat_model[f]
    base_m = np.clip(m["slope_kwh_per_h_per_degC"] * (m["balance_point_c"] - d.outdoor_temp_c), 0, None)
    cf_m = np.clip(m["slope_kwh_per_h_per_degC"] * (m["balance_point_c"] - 1 - d.outdoor_temp_c), 0, None)
    cfb.append(d.energy_kwh * (cf_m / base_m).where(base_m > 0, 0).fillna(1.0))
hb["cf"] = pd.concat(cfb)
scen("S1b_heater_flats_minus_1C", hb, hb.energy_kwh - hb.cf,
     "Sensitivity: both heater flats (F001, F007) lower the heater thermostat by 1 °C.",
     "Heater kWh vs outdoor temperature r = -0.93; heater holds indoor temperature constant (indoor std ~0.36 °C).",
     "Same degree-hour model, 1 °C balance-point shift. Comfort impact not measured.",
     "No - simulated.")

# S2 F005 always-on lighting/entertainment floor
a6f = ok[(ok.flat_id == "F005") & (ok.appliance_code == "A06")].copy()
ex = anom["F005_A06_excess_floor_kwh_h"]
scen("S2_F005_always_on_A06", a6f, np.minimum(a6f.energy_kwh - floor.drop("F005").median(), ex).clip(lower=0),
     "F005: find and switch off the ~95 W of lighting/entertainment that never turns off (e.g. a left-on light, TV/console standby, decorative lighting).",
     f"F005 A06 5th-percentile floor {floor['F005']*1000:.0f} W vs median {floor.drop('F005').median()*1000:.0f} W in the other 7 flats, constant all 4 weeks.",
     "Excess floor removed every hour (capped so no hour drops below the peer floor); evening use above the floor unchanged.",
     "Baseline observed; counterfactual simulated (cause of the floor is not identifiable from hourly data).")

# S3 F002 fridge fault
a1 = ok[(ok.flat_id == "F002") & (ok.appliance_code == "A01") & (ok.hour_idx >= cp)].copy()
scen("S3_F002_fridge_fault", a1, (a1.energy_kwh - pre).clip(lower=0),
     "F002: report the cold appliance to the landlord / check door seal, thermostat and defrost - consumption jumped x2.4 overnight on 15 Oct and stayed there.",
     f"Mean {pre:.3f} kWh/h before vs {post:.3f} after the step; every post-step hour exceeds the pre-step maximum ({anom['F002_fridge_step']['pre_max_kwh_h']}).",
     "Repair restores the pre-step level; only the 14 post-step days are counted (no extrapolation).",
     "Baseline observed; post-repair level is an assumption (pre-fault level).", days=range(cp // 24, DAYS))

# S4 overnight personal electronics: off overnight (keep small charging allowance)
a5n = ok[(ok.appliance_code == "A05") & ok.is_overnight].copy()
allow = 0.010
scen("S4_A05_overnight_off_all_flats", a5n, (a5n.energy_kwh - allow).clip(lower=0) * 0.5,
     "All flats: shut down PCs/consoles/monitors at night instead of leaving them on (00:00-05:59), keeping a 10 W charging allowance; 50 % adoption.",
     f"A05 averages ~65 W from 21:00 to 07:59 local but 4 W from 08:00 to 16:59 in 7 of 8 flats; its night level scales with occupants home.",
     "Night load above 10 W/h is discretionary; half of it is avoided (adoption/compliance 50 %). Device identity unknown.",
     "No - simulated; device type is inferred.")

# S5 F004 electronics on all day
a5d = ok[(ok.flat_id == "F004") & (ok.appliance_code == "A05") & ok.local_hour.between(8, 16)].copy()
peer_day = day5.drop("F004").median()
scen("S5_F004_daytime_electronics", a5d, (a5d.energy_kwh - peer_day).clip(lower=0),
     "F004: switch off electronics during the day (08:00-16:59) - its A05 channel stays at night-time level all day.",
     f"F004 A05 09-16 mean {day5['F004']*1000:.0f} W vs peer median {peer_day*1000:.0f} W; when the flat is empty it still draws {emp5.get('F004', np.nan)*1000:.0f} W.",
     "Daytime A05 reduced to the peer median level.",
     "Baseline observed; counterfactual simulated.")

# Shifting scenarios in same structure
for key, d, code in [("S6_dishwasher_delay_start", dish, "A04"), ("S7_washing_delay_daytime", wash, "A03")]:
    s = shift["dishwasher_A04_delay_to_07" if code == "A04" else "washing_A03_delay_12h_daytime"]
    R["scenarios"][key] = {
        "description": ("Use delay-start so the dishwasher (always started at 20:00) runs in the cheapest hour before 07:00."
                        if code == "A04" else "Start the washing machine in the cheapest hour within the next 12 h, 07:00-21:59 only."),
        "evidence": f"{s['events']} events, {s['kwh']} kWh over 28 days.",
        "assumptions": "Hourly spot tariff with day-ahead prices known; same kWh per cycle; only delays, never earlier.",
        "verifiable_from_data": "Simulated; zero SEK effect for fixed-price, monthly-average or rent-included electricity.",
        "baseline_kwh": s["kwh"], "baseline_sek_spot": s["baseline_sek"], "counterfactual_kwh": s["kwh"],
        "saving_kwh": 0.0, "saving_pct_of_baseline": 0.0,
        "saving_sek_hourly_spot": s["saving_sek_hourly_tariff"], "saving_sek_monthly_avg_spot": 0.0,
        "saving_co2_kg": round(-s["co2_change_kg"], 3), "ci95_kwh": [0.0, 0.0], "ci95_sek_hourly": s["ci95_sek"],
        "ci95_co2_kg": None}

sc = pd.DataFrame(R["scenarios"]).T
tbl = sc[["saving_kwh", "saving_pct_of_baseline", "saving_sek_hourly_spot", "saving_sek_monthly_avg_spot",
          "saving_co2_kg"]].astype(float)
tbl["kWh 95% CI"] = sc.ci95_kwh.map(lambda v: f"{v[0]:.1f}-{v[1]:.1f}")
tbl["SEK 95% CI (hourly)"] = sc.ci95_sek_hourly.map(lambda v: f"{v[0]:.1f}-{v[1]:.1f}")
tbl.index.name = "Scenario (28 days)"
md("Savings scenarios over the 28 observed days (spot energy component only, excl. VAT)", tbl.rename(columns={
    "saving_kwh": "kWh saved", "saving_pct_of_baseline": "% of baseline", "saving_sek_hourly_spot": "SEK (hourly spot)",
    "saving_sek_monthly_avg_spot": "SEK (monthly-avg spot)", "saving_co2_kg": "kgCO2e saved"}))

fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)
names = list(R["scenarios"])
short = {"S1_F007_heater_off_when_empty": "S1 F007 heater off when empty", "S1c_F007_setpoint_to_20_5C": "S1c F007 thermostat -2 °C (model)",
         "S1b_heater_flats_minus_1C": "S1b Both heaters -1 °C (model)",
         "S2_F005_always_on_A06": "S2 F005 always-on ~95 W", "S3_F002_fridge_fault": "S3 F002 fridge fault (14 d)",
         "S4_A05_overnight_off_all_flats": "S4 Electronics off overnight (50 %)",
         "S5_F004_daytime_electronics": "S5 F004 daytime electronics",
         "S6_dishwasher_delay_start": "S6 Dishwasher delay-start", "S7_washing_delay_daytime": "S7 Washing delay"}
yl = [short[n] for n in names][::-1]
for ax, key, ci, title in [(axes[0], "saving_kwh", "ci95_kwh", "kWh saved"),
                           (axes[1], "saving_sek_hourly_spot", "ci95_sek_hourly", "SEK saved (hourly spot)"),
                           (axes[2], "saving_co2_kg", "ci95_co2_kg", "kgCO2e saved")]:
    vals = [R["scenarios"][n][key] for n in names][::-1]
    cis = [R["scenarios"][n][ci] for n in names][::-1]
    ax.barh(yl, vals, color="#2a78d6", height=0.6, edgecolor=SURF, linewidth=2)
    for y, (v, c) in enumerate(zip(vals, cis)):
        if c is not None and c != [0.0, 0.0]:
            ax.plot(c, [y, y], color=INK, lw=1.2)
        ax.text(max(v, c[1] if c else v), y, f"  {v:.1f}", va="center", fontsize=9)
    ax.axvline(0, color=INK2, lw=0.8); ax.set_title(title, loc="left"); ax.grid(axis="y", visible=False)
    ax.set_xlim(min(0, min(vals)) * 1.3, max(max(vals), max((c[1] for c in cis if c), default=0)) * 1.3)
fig.suptitle("Savings over the 28 observed days per scenario (bars = point estimate, lines = 95% day-bootstrap CI)",
             x=0.01, ha="left", fontweight="bold", y=1.03)
save(fig, "08_savings_scenarios.png")

# price/carbon by hour figure (single axis each)
fig, axes = plt.subplots(1, 2, figsize=(12, 3.6))
axes[0].bar(hp.index, hp.spot_sek_per_kwh, color="#2a78d6", width=0.8, edgecolor=SURF)
axes[0].set_title("Mean spot price by local hour (SEK/kWh)", loc="left"); axes[0].set_xticks(range(0, 24, 3))
axes[1].bar(hp.index, hp.carbon_gco2e_per_kwh, color="#1baf7a", width=0.8, edgecolor=SURF)
axes[1].set_title("Mean carbon factor by local hour (gCO2e/kWh)", loc="left"); axes[1].set_xticks(range(0, 24, 3))
for ax in axes:
    ax.set_xlabel("Local hour"); ax.grid(axis="x", visible=False)
save(fig, "09_price_carbon_by_hour.png")

# weekday/weekend hourly profile
wp = ok.groupby(["is_weekend", "flat_id", "hour_idx", "local_hour"]).energy_kwh.sum().groupby(["is_weekend", "local_hour"]).mean().unstack(0)
fig, ax = plt.subplots(figsize=(9, 3.6))
ax.plot(wp.index, wp[False], color="#2a78d6", lw=2, marker="o", ms=4, label="Weekday")
ax.plot(wp.index, wp[True], color="#eb6834", lw=2, marker="s", ms=4, label="Weekend")
ax.set_xlabel("Local hour"); ax.set_ylabel("Mean kWh per flat-hour"); ax.legend(); ax.set_xticks(range(0, 24, 2))
ax.set_title("Weekday vs weekend load shape (all channels, all flats)", loc="left")
save(fig, "10_weekday_weekend_profile.png")

(REPORTS / "eda_results.json").write_text(json.dumps(R, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
(REPORTS / "eda_tables.md").write_text("# EDA tables\n\n_Generated by `analysis/eda.py`; all figures in kWh over 1-28 Oct 2026 unless stated._\n\n" + "\n".join(TABLES))
print(json.dumps({k: R[k] for k in ["observed_kwh_total", "load_weighted_price_sek_per_kwh", "time_avg_spot_sek_per_kwh",
                                     "peak_local_hour", "most_expensive_local_hours", "cheapest_local_hours",
                                     "shiftable_share_pct", "corr_residents_vs_kwh_excl_heater"]}, indent=1))

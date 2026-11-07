"""Opportunity validation + intervention scenarios (stage 3).

Inputs : data/processed/analytical_table.csv, data/processed/cleaning_summary.json (both from clean_data.py)
Outputs: reports/opportunities.json      structured, machine-readable (chatbot / calculator input)
         reports/opportunity_report.md   human-readable report generated from the same numbers
Run    : python analysis/opportunities.py      (then python analysis/verify_opportunities.py)

Conventions
- "measured"     : read directly from cleaned observations.
- "inferred"     : derived from measured patterns with an explicit rule (e.g. appliance identity).
- "hypothetical" : depends on an assumption the data cannot test (e.g. that a load is avoidable).
- All money values are the SPOT-ENERGY COMPONENT ONLY (SEK, excl. VAT). They are not bill savings.
  value_spot_hourly_sek   = sum(kWh_h x spot_h)       -> meaningful only on an hourly spot-price contract
  value_spot_timeavg_sek  = kWh x time-average spot   -> rough proxy for a monthly-average spot contract
  fixed-price contract    = kWh x (user's price)      -> calculator input; load shifting is worth 0
  electricity in rent     = 0 SEK to the student      -> kWh and CO2e still change
- kgCO2e uses the hour-specific synthetic operational (average, not marginal) factor.
- Uncertainty intervals are 95 % day-block bootstrap (2,000 draws, fixed seed) and capture day-to-day
  variability only; assumption risk is expressed through named sensitivity scenarios.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from common import APPLIANCE_LABELS, PROCESSED, REPORTS, ROOT, TZ_LOCAL

SEED = 20261107
N_BOOT = 2000
SRC_FILES = ["analysis/common.py", "analysis/clean_data.py", "analysis/opportunities.py"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def r(x, n=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


t = pd.read_csv(PROCESSED / "analytical_table.csv")
t["day"] = t.hour_idx // 24
ok = t[~t.energy_missing]
hours = t.drop_duplicates("hour_idx").set_index("hour_idx").sort_index()
SPOT_AVG = float(hours.spot_sek_per_kwh.mean())
CARBON_AVG = float(hours.carbon_gco2e_per_kwh.mean())
clean_summary = json.loads((PROCESSED / "cleaning_summary.json").read_text())


# ---------------------------------------------------------------------------- valuation helpers
FULL = (0, 672)


def period(window: tuple[int, int], observed_hours: int | None = None) -> dict:
    """Explicit time label for a scenario: UTC window [start, end) in hour indices."""
    a, b = window
    t0 = pd.Timestamp("2026-10-01T00:00:00Z")
    return {"window_start_utc": (t0 + pd.Timedelta(hours=a)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window_end_utc_exclusive": (t0 + pd.Timedelta(hours=b)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window_hours": b - a, "window_days": round((b - a) / 24, 2),
            "observed_hours_used": observed_hours,
            "label": f"{(b - a) / 24:g} days observed ({(t0 + pd.Timedelta(hours=a)).strftime('%d %b')}"
                     f"-{(t0 + pd.Timedelta(hours=b - 1)).strftime('%d %b %Y')}, UTC)"}


def boot(daily: pd.Series, seed_offset: int = 0, window: tuple[int, int] = FULL) -> list[float]:
    """95 % CI of the window total: resample the window's days only (no zero-padding outside it)."""
    rng = np.random.default_rng(SEED + seed_offset)
    days = list(range(window[0] // 24, -(-window[1] // 24)))
    v = daily.reindex(days, fill_value=0.0).to_numpy()
    sims = rng.choice(v, size=(N_BOOT, len(days)), replace=True).sum(axis=1)
    return [r(np.percentile(sims, 2.5)), r(np.percentile(sims, 97.5))]


def value_reduction(hour_idx: pd.Series, kwh: pd.Series, label: str, role: str, tariff_note: str | None = None,
                    seed_offset: int = 0, window: tuple[int, int] = FULL, observed_hours: int | None = None) -> dict:
    """kWh avoided in the given hours. Missing prices -> that hour's SEK is excluded (reported)."""
    d = pd.DataFrame({"h": hour_idx.to_numpy(), "kwh": kwh.to_numpy()})
    d["spot"] = d.h.map(hours.spot_sek_per_kwh)
    d["carbon"] = d.h.map(hours.carbon_gco2e_per_kwh)
    d["day"] = d.h // 24
    d["sek"] = d.kwh * d.spot
    d["co2"] = d.kwh * d.carbon / 1000
    return {
        "label": label, "role": role, "type": "reduction",
        "period": period(window, observed_hours if observed_hours is not None else int(len(d))),
        "kwh": r(d.kwh.sum()), "co2e_kg": r(d.co2.sum(), 3),
        "value_spot_hourly_sek": r(d.sek.sum()),
        "value_spot_timeavg_sek": r(d.kwh.sum() * SPOT_AVG),
        "kwh_in_unpriced_hours": r(d.loc[d.spot.isna(), "kwh"].sum(), 3),
        "ci95_kwh": boot(d.groupby("day").kwh.sum(), seed_offset, window),
        "ci95_value_spot_hourly_sek": boot(d.groupby("day").sek.sum(), seed_offset + 1, window),
        "tariff_applicability": tariff_note or (
            "kWh and CO2e change on any tariff. SEK: hourly spot contract -> value_spot_hourly_sek; "
            "monthly-average spot -> approx. value_spot_timeavg_sek; fixed price -> kWh x own price; "
            "electricity included in rent -> 0 SEK to the student."),
    }


def value_shift(ev: pd.DataFrame, dest: pd.Series, label: str, role: str, seed_offset: int = 0) -> dict:
    """Move each event's kWh from ev.hour_idx to dest (same index). kWh unchanged."""
    d = pd.DataFrame({"h0": ev.hour_idx.to_numpy(), "h1": dest.to_numpy(), "kwh": ev.energy_kwh.to_numpy()})
    p0, p1 = d.h0.map(hours.spot_sek_per_kwh), d.h1.map(hours.spot_sek_per_kwh)
    c0, c1 = d.h0.map(hours.carbon_gco2e_per_kwh), d.h1.map(hours.carbon_gco2e_per_kwh)
    valid = p0.notna() & p1.notna()
    d["save"] = (d.kwh * (p0 - p1)).where(valid, 0.0)
    d["co2"] = d.kwh * (c0 - c1) / 1000
    d["day"] = d.h0 // 24
    return {
        "label": label, "role": role, "type": "load_shift", "period": period(FULL, int(len(d))),
        "kwh": 0.0, "kwh_moved": r(d.kwh.sum()), "events": int(len(d)),
        "events_not_valued_missing_price": int((~valid).sum()),
        "co2e_kg": r(d.co2.sum(), 3),
        "value_spot_hourly_sek": r(d.save.sum()),
        "value_spot_timeavg_sek": 0.0,
        "baseline_spot_hourly_sek": r((d.kwh * p0).where(valid, 0).sum()),
        "median_delay_h": r((d.h1 - d.h0).median(), 1),
        "ci95_value_spot_hourly_sek": boot(d.groupby("day").save.sum(), seed_offset),
        "tariff_applicability": ("SEK only on an hourly spot-price contract. Fixed-price, monthly-average or "
                                 "rent-included electricity: 0 SEK (kWh identical). CO2e change uses average "
                                 "hourly factors, not marginal emissions."),
    }


# ============================================================================ 1. coverage & DST
utc = pd.date_range("2026-10-01", periods=672, freq="h", tz="UTC")
loc = utc.tz_convert(TZ_LOCAL)
a_loc, b_loc = pd.Timestamp("2026-10-01", tz=TZ_LOCAL), pd.Timestamp("2026-10-29", tz=TZ_LOCAL)
inside = (loc >= a_loc) & (loc < b_loc)
per_date = pd.Series(loc.strftime("%Y-%m-%d")).value_counts().sort_index()
coverage = {
    "utc_first_interval_start": "2026-10-01T00:00:00Z", "utc_last_interval_start": "2026-10-28T23:00:00Z",
    "utc_end_exclusive": "2026-10-29T00:00:00Z", "hourly_intervals": 672,
    "local_first_interval_start": loc[0].isoformat(), "local_last_interval_start": loc[-1].isoformat(),
    "elapsed_hours_local_calendar_1_to_28_oct": int((b_loc - a_loc) / pd.Timedelta("1h")),
    "naive_wall_clock_hours_1_to_28_oct": 672,
    "dataset_hours_inside_local_1_to_28_oct": int(inside.sum()),
    "local_hours_1_to_28_oct_not_in_dataset": [(a_loc + pd.Timedelta(hours=i)).isoformat() for i in range(673)
                                               if (a_loc + pd.Timedelta(hours=i)) not in set(loc)],
    "dataset_hours_outside_local_1_to_28_oct": [x.isoformat() for x in loc[~inside]],
    "unique_naive_local_wall_clock_times": int(loc.tz_localize(None).nunique()),
    "repeated_wall_clock_hour": ["2026-10-25T02:00:00+02:00 (=00:00Z)", "2026-10-25T02:00:00+01:00 (=01:00Z)"],
    "hours_per_local_date": {"2026-10-01": int(per_date["2026-10-01"]), "2026-10-25": int(per_date["2026-10-25"]),
                             "2026-10-29": int(per_date["2026-10-29"]), "other_dates": 24},
    "interpretation": ("The dataset is exactly 672 UTC hours. The local calendar month-slice 1-28 Oct is 673 elapsed "
                       "hours because 25 Oct has 25 hours; the dataset covers 671 of them plus 00:00 on 29 Oct local, "
                       "and lacks 00:00-01:59 on 1 Oct local. Anything keyed on naive local time sees only 671 distinct "
                       "wall-clock hours and silently merges the two 02:00 hours. Rule: compute elapsed time, joins and "
                       "totals in UTC; use local time only for labels and hour-of-day patterns; per-day comparisons "
                       "must normalise by hours present (25 Oct = 25 h)."),
}

# ============================================================================ 2. missing observation vs energy
ch = t.groupby("appliance_code")
chan_mean_by_hour = ok.groupby(["appliance_id", "local_hour"]).energy_kwh.mean()
miss = t[t.energy_missing].copy()
miss["est_central"] = [chan_mean_by_hour.get((a, h), np.nan) for a, h in zip(miss.appliance_id, miss.local_hour)]
chan_max = ok.groupby("appliance_id").energy_kwh.max()
miss["est_upper"] = miss.appliance_id.map(chan_max)
mv = pd.DataFrame({
    "slots": ch.size(), "missing_slots": ch.energy_missing.sum(),
    "observed_zero_slots": ok.groupby("appliance_code").energy_kwh.apply(lambda s: int((s == 0).sum())),
    "observed_kwh": ok.groupby("appliance_code").energy_kwh.sum(),
    "missing_kwh_lower": 0.0,
    "missing_kwh_central": miss.groupby("appliance_code").est_central.sum(),
    "missing_kwh_upper": miss.groupby("appliance_code").est_upper.sum(),
})
# dishwasher: expected-but-unobserved events (strict 2-day cadence)
a4 = t[t.appliance_code == "A04"]
hidden = a4[(a4.local_hour == 20) & a4.energy_missing]
hidden_rows = []
for _, h in hidden.iterrows():
    ev_h = a4[(a4.flat_id == h.flat_id) & (a4.energy_kwh > 0.1)].hour_idx
    gap_before = (h.hour_idx - ev_h[ev_h < h.hour_idx].max()) / 24
    gap_after = (ev_h[ev_h > h.hour_idx].min() - h.hour_idx) / 24
    hidden_rows.append({"flat_id": h.flat_id, "timestamp_local": h.timestamp_local, "status": h.energy_status,
                        "days_since_previous_event": r(gap_before, 1), "days_to_next_event": r(gap_after, 1),
                        "likely_unobserved_event": bool(gap_before == 2 and gap_after == 2)})
missing_vs_energy = {
    "principle": ("A missing observation (empty, N/A, negative, spike or absent record) means the energy is UNKNOWN, "
                  "not zero. A measured 0.0 means the channel was observed off. The analytical table keeps both "
                  "apart: energy_status/energy_missing flags; cost and CO2e stay missing when kWh or price is missing."),
    "by_channel": {k: {c: (int(v) if c in ("slots", "missing_slots", "observed_zero_slots") else r(v)) for c, v in row.items()}
                   for k, row in mv.iterrows()},
    "total_missing_slots": int(t.energy_missing.sum()),
    "total_missing_kwh_central": r(mv.missing_kwh_central.sum()),
    "total_missing_kwh_upper": r(mv.missing_kwh_upper.sum()),
    "central_method": "same channel's mean at the same local hour of day (estimate only; no rows are imputed)",
    "upper_method": "same channel's maximum observed hourly value",
    "example_dishwasher_hidden_events": hidden_rows,
    "example_vacancy_is_measured_low_energy": "F003 13-15 Oct: occupants 0, observed 2.18 kWh/day - real low use, not missing data",
}

# ============================================================================ 3. appliance identity evidence
ident = {}
occ_known = ok.dropna(subset=["occupants_home"])
for c, d in ok.groupby("appliance_code"):
    nz = d[d.energy_kwh > 0]
    intermittent = (d.energy_kwh == 0).mean() > 0.5
    events = d[d.energy_kwh > 0.1] if intermittent else d.iloc[0:0]
    users = sorted(nz.flat_id.unique())
    users_sub = d[d.flat_id.isin(users)]
    m = {
        "flats_with_nonzero_use": len(users),
        "share_hours_zero": r((d.energy_kwh == 0).mean(), 3),
        "min_kwh_h": r(d.energy_kwh.min(), 4), "median_kwh_h": r(d.energy_kwh.median(), 4),
        "p99_kwh_h": r(d.energy_kwh.quantile(0.99), 3),
        "channel_type": "intermittent (on/off events)" if intermittent else "continuous (never/rarely zero)",
        "events_gt_0_1kwh": int(len(events)) if intermittent else None,
        "mean_event_kwh": r(events.energy_kwh.mean(), 3) if len(events) else None,
        "top_event_local_hours": events.local_hour.value_counts().head(4).to_dict() if len(events) else {},
        "share_events_in_top_hour": r(events.local_hour.value_counts(normalize=True).max(), 3) if len(events) else None,
        "spearman_vs_outdoor_temp_in_using_flats": r(users_sub[["energy_kwh", "outdoor_temp_c"]].corr("spearman").iloc[0, 1], 3),
        "spearman_vs_occupants_home_in_using_flats": r(occ_known[occ_known.appliance_code.eq(c) & occ_known.flat_id.isin(users)]
                                                       [["energy_kwh", "occupants_home"]].corr("spearman").iloc[0, 1], 3),
        "weekend_vs_weekday_mean_ratio": r(d[d.is_weekend].energy_kwh.mean() / d[~d.is_weekend].energy_kwh.mean(), 3),
        "overnight_share_of_energy": r(d[d.is_overnight].energy_kwh.sum() / d.energy_kwh.sum(), 3),
    }
    ident[c] = {"label_inferred": APPLIANCE_LABELS[c], "metrics": m}
IDENT_JUDGEMENT = {
    "A01": ("medium-high", "Continuous, never-zero ~50 W load with no daily or weather cycle in 7 flats is the classic "
            "cold-appliance signature; hourly data cannot show compressor cycling, so a different always-on device "
            "cannot be excluded.", ["any always-on device of ~50 W"]),
    "A02": ("medium", "Large (~0.8 kWh) one-hour events at breakfast, lunch and dinner, more at weekends; matches "
            "cooking. Kettle/microwave clusters would be smaller.", ["kettle + microwave combined", "oven only"]),
    "A03": ("low-medium", "Isolated ~0.67 kWh one-hour events every ~2-3 days at varied daytime hours. Consistent with a "
            "washing machine but also with a tumble dryer on eco or other occasional appliance.", ["tumble dryer", "vacuum/other"]),
    "A04": ("medium", "~0.9 kWh events every 2 days at exactly 20:00 in all flats: a cycle-type appliance on a fixed "
            "habit/timer. Size fits a dishwasher eco cycle; a dryer would usually use more.", ["washer-dryer", "other timed appliance"]),
    "A05": ("low", "4 W standby 08-17 h, a flat-specific constant 53-89 W 21-08 h scaling with resident count, ~30-50 W "
            "17-21 h. Plausibly personal electronics/chargers, but the night level is too high for phone charging alone.",
            ["PCs/consoles left on", "electric bed warmers", "aquarium/terrarium equipment"]),
    "A06": ("low-medium", "33 W constant floor plus an evening (17-23 h) increase of 27-55 W; evening shape fits lighting/"
            "TV. The floor could be a router or standby loads.", ["router/network + standby", "ventilation fan"]),
    "A07": ("high", "Used by 2 flats only; hourly energy = 0.12 kWh/h per degC below 12 degC (residual sd 0.003 kWh); "
            "README states portable heaters are the supplementary electric heat in scope.", ["other weather-driven load (unlikely)"]),
}
for c, (conf, why, alts) in IDENT_JUDGEMENT.items():
    ident[c].update({"identity_confidence": conf, "reasoning": why, "plausible_alternatives": alts})

# ============================================================================ 4. opportunities
OPP: list[dict] = []
flats = t.groupby("flat_id")[["residents", "floor_area_m2"]].first()

# ---------------------------------------------------------------- O1 F007 heater while unoccupied
h7 = t[(t.flat_id == "F007") & (t.appliance_code == "A07")].sort_values("hour_idx").copy()
h1 = t[(t.flat_id == "F001") & (t.appliance_code == "A07")]
emp = h7[h7.occupants_home == 0].copy()
emp["run"] = (emp.hour_idx.diff() != 1).cumsum()
runs = emp.groupby("run").agg(start=("timestamp_local", "first"), end=("timestamp_local", "last"),
                              hours=("hour_idx", "size"), kwh=("energy_kwh", "sum"),
                              outdoor_mean=("outdoor_temp_c", "mean"))
emp["run_len"] = emp.run.map(runs.hours)
unk = h7[h7.occupancy_missing]
heated_empty = emp[emp.energy_kwh > 0]
o1_scen = [
    value_reduction(emp.loc[emp.run_len >= 2, "hour_idx"], emp.loc[emp.run_len >= 2, "energy_kwh"],
                    "Manual habit: heater off for absences of 2 h or more", "central", seed_offset=10, observed_hours=int((emp.run_len >= 2).sum())),
    value_reduction(emp.hour_idx, emp.energy_kwh.fillna(0),
                    "Automated presence/occupancy control: off in every unoccupied hour", "upper_measured", seed_offset=12, observed_hours=int(emp.energy_kwh.notna().sum())),
    value_reduction(emp.loc[emp.run_len >= 3, "hour_idx"], emp.loc[emp.run_len >= 3, "energy_kwh"],
                    "Conservative: only absences of 3 h or more", "lower", seed_offset=14),
    value_reduction(pd.concat([emp.hour_idx, unk.hour_idx]), pd.concat([emp.energy_kwh, unk.energy_kwh]).fillna(0),
                    "Hypothetical upper bound: automated control AND all unknown-occupancy hours were in fact empty",
                    "upper_hypothetical", seed_offset=16),
]
reb = {f"rebound_{int(p*100)}pct": r(o1_scen[0]["kwh"] * (1 - p)) for p in (0.1, 0.25)}
OPP.append({
    "id": "O1_F007_heating_unoccupied", "title": "F007: portable heater runs while the flat is unoccupied",
    "flat_id": "F007", "appliance_code": "A07", "appliance_label_inferred": APPLIANCE_LABELS["A07"],
    "identity_confidence": ident["A07"]["identity_confidence"], "finding_type": "behavioural waste (consumption during absence)",
    "observed_evidence": {
        "heater_kwh_28d": r(h7.energy_kwh.sum()), "heater_hours_on": int((h7.energy_kwh > 0).sum()),
        "unoccupied_hours": int(len(emp)), "unoccupied_hours_heater_on": int(len(heated_empty)),
        "heater_kwh_in_unoccupied_hours": r(emp.energy_kwh.sum()),
        "unoccupied_episodes": int(len(runs)),
        "episode_length_distribution_h": {int(k): int(v) for k, v in runs.hours.value_counts().sort_index().items()},
        "kwh_by_episode_length_h": {int(k): r(v) for k, v in runs.groupby("hours").kwh.sum().items()},
        "largest_episodes": runs.sort_values("kwh", ascending=False).head(5)[["start", "end", "hours", "kwh"]]
            .assign(kwh=lambda d: d.kwh.round(3)).to_dict(orient="records"),
        "first_and_last_unoccupied_heating": [heated_empty.timestamp_local.iloc[0], heated_empty.timestamp_local.iloc[-1]],
        "heater_model_check": "hourly kWh = 0.12 x (12.0 - outdoor degC), residual sd 0.003 kWh - heater output depends on weather only, not on presence",
        "indoor_temp_mean_unoccupied_vs_occupied_c": [r(emp.indoor_temp_c.mean()), r(h7[h7.occupants_home > 0].indoor_temp_c.mean())],
        "occupancy_denominators": {fl: {
            "hours_total": int(len(d)), "occupancy_known": int(d.occupants_home.notna().sum()),
            "occupancy_unknown": int(d.occupancy_missing.sum()), "unoccupied": int((d.occupants_home == 0).sum()),
            "unoccupied_heater_reading_valid": int(((d.occupants_home == 0) & d.energy_kwh.notna()).sum()),
            "unoccupied_heater_on": int(((d.occupants_home == 0) & (d.energy_kwh > 0)).sum()),
            "unoccupied_outdoor_below_12c": int(((d.occupants_home == 0) & (d.outdoor_temp_c < 12)).sum()),
            "unoccupied_outdoor_unknown": int(((d.occupants_home == 0) & d.outdoor_temp_missing).sum()),
            "unoccupied_cold_heater_reading_valid": int(((d.occupants_home == 0) & (d.outdoor_temp_c < 12) & d.energy_kwh.notna()).sum()),
            "unoccupied_cold_heater_off": int(((d.occupants_home == 0) & (d.outdoor_temp_c < 12) & (d.energy_kwh == 0)).sum()),
        } for fl, d in (("F007", h7), ("F001", h1))},
        "denominator_note": ("Each count names its base. 'Unoccupied' = occupants_home == 0 among hours with known occupancy; "
                             "hours with unknown occupancy are never counted as unoccupied; a missing heater reading is never counted as 'off'. "
                             "F007: 64 unoccupied, 56 with heater on (= 55 cold hours with known outdoor temperature + 1 hour with unknown outdoor temperature); "
                             "the 8 others were >= 12 degC so the weather-driven heater was off anyway. "
                             "F001: 142 unoccupied, 141 with a valid heater reading, all 0 kWh; of the 124 cold ones, 123 have a valid reading."),
        "comparator_F001": {"unoccupied_hours": int((h1.occupants_home == 0).sum()),
                            "unoccupied_hours_valid_heater_reading": int(((h1.occupants_home == 0) & h1.energy_kwh.notna()).sum()),
                            "heater_on_in_unoccupied_hours": int(((h1.occupants_home == 0) & (h1.energy_kwh > 0)).sum()),
                            "occupied_cold_hours_heater_off": int(((h1.occupants_home > 0) & (h1.energy_kwh == 0) & (h1.outdoor_temp_c < 12)).sum()),
                            "note": "F001's heater is off in every unoccupied hour and on whenever occupied and <12 degC"},
    },
    "data_quality_flags": {
        "heater_readings_missing_in_unoccupied_hours": int(emp.energy_missing.sum()),
        "heater_readings_missing_total": int(h7.energy_missing.sum()),
        "occupancy_unknown_hours": int(len(unk)), "heater_kwh_in_occupancy_unknown_hours": r(unk.energy_kwh.sum()),
        "occupancy_is_simulated_sensor_estimate": True,
        "outdoor_temp_missing_hours": int(h7.outdoor_temp_missing.sum()),
    },
    "anomaly_vs_waste": {
        "demonstrated": [
            f"The heater delivered {r(emp.energy_kwh.sum())} kWh in {len(heated_empty)} hours that the occupancy estimate marks as empty.",
            "F001 never heats an empty flat: 0 kWh in all 141 unoccupied hours with a valid heater reading (142 unoccupied, 1 reading missing).",
            "Heater output follows outdoor temperature only (r = -1.00), so it is not switched by anyone in F007.",
        ],
        "hypotheses": [
            "That the occupancy estimate is correct for every hour (it is a simulated sensor; 42 of 52 episodes last only 1 h, which could partly be sensor noise).",
            "That heating during absence is not needed for comfort on return (indoor temperature stays 22.5 degC either way in the data, so no comfort effect is measurable).",
            "That no re-heating rebound occurs after the heater is switched back on (not observable: heater output is weather-determined).",
        ],
    },
    "intervention": {
        "action": "Switch the portable heater off when leaving for 2 h or more; optionally automate with a timer/presence control.",
        "who": "student",
        "constraints": {
            "safety": ["Portable heaters should not be left running unattended; switching off when leaving also reduces fire risk.",
                       "Peak observed draw 1.23 kWh in an hour (>=1.2 kW): any smart/timer plug must be rated for the heater's nameplate load, and the heater's manual must permit use with timers."],
            "comfort": ["F007's indoor temperature is 22.5 degC whether the heater is on or off (other flats 20.5 degC with district heating only), so the data give no sign that switching off during absences makes the flat cold - but the heater's effect on indoor temperature cannot be measured here."],
            "equipment_control": ["Manual switching is realistic only for longer absences; 1-h gaps need automation."],
        },
    },
    "counterfactual": {
        "measured_inputs": ["hourly A07 kWh (F007)", "occupants_home (simulated estimate)", "hourly spot price and carbon factor"],
        "assumptions": ["heater is off (0 kWh) in the selected unoccupied hours", "no re-heating rebound in the central case",
                        "consumption in occupied hours is unchanged", "same weather and prices as observed"],
        "formula": "savings_kWh = sum over selected unoccupied hours h of A07_kWh(h); SEK_hourly = sum A07_kWh(h) x spot(h); CO2e = sum A07_kWh(h) x carbon(h)/1000",
    },
    "scenarios": o1_scen,
    "uncertainty": {
        "key_unknowns": ["accuracy of the occupancy estimate (14 h unknown; frequent 1-h flips)",
                         "which absences the student can realistically act on", "rebound when re-heating",
                         "season: October averaged 7.8 degC outdoors; colder months raise heater energy by 0.12 kWh/h per degC below 12 degC"],
        "sensitivity_rebound_on_central_kwh": reb,
        "do_not_extrapolate": "Do not annualise: savings scale with outdoor temperature and absence patterns outside the observed range.",
    },
    "actionability": {"level": "student_independent", "actor": "student",
                      "steps": ["switch off on leaving", "optional timer/presence plug rated for the heater"]},
    "evidence_quality": {"consumption": "measured", "occupancy_coincidence": "measured (simulated sensor)",
                         "appliance_identity": "inferred (high)", "avoidability": "hypothetical", "savings": "conditional simulation"},
    "statistical_confidence": "high that heating coincides with recorded absences; medium that the absences are real",
    "action_feasibility": "high for absences >= 2 h; low for 1-h gaps without automation",
    "recommendation_status": "requires_student_confirmation",
    "chatbot_guidance": {
        "can_say": ["Your heater ran during hours when the flat appeared empty (about 9-23 kWh over 4 weeks depending on how many absences you can act on)."],
        "must_confirm": ["Were you actually out at these times?", "Can the heater be switched off safely when you leave?"],
        "must_not_say": ["That this saves a specific amount on the bill without knowing the tariff.", "Annual savings."],
    },
})

# ---------------------------------------------------------------- O2 F005 elevated base load
a6 = ok[ok.appliance_code == "A06"]
floor = a6.groupby("flat_id").energy_kwh.min()
peer_floor = float(floor.drop("F005").median())
f5 = t[(t.flat_id == "F005") & (t.appliance_code == "A06")]
f5o = f5[~f5.energy_missing]
excess = float(floor["F005"] - peer_floor)
ev_inc = a6[a6.local_hour.between(17, 22)].groupby("flat_id").energy_kwh.mean() - floor
o2_save = np.minimum(f5o.energy_kwh - peer_floor, excess).clip(lower=0)
o2_scen = [
    value_reduction(f5o.hour_idx, o2_save, "Excess base load fully eliminated (device found and switched off)", "upper_measured", seed_offset=20),
    value_reduction(f5o.hour_idx, o2_save * 0.5, "Half of the excess avoidable (e.g. device needed part-time or replaced by a lower-power one)", "central", seed_offset=22),
    value_reduction(f5o.hour_idx, o2_save * 0.25, "Quarter of the excess avoidable", "lower", seed_offset=24),
]
OPP.append({
    "id": "O2_F005_elevated_base_load", "title": "F005: persistent ~95 W elevated base consumption",
    "flat_id": "F005", "appliance_code": "A06", "appliance_label_inferred": APPLIANCE_LABELS["A06"],
    "identity_confidence": ident["A06"]["identity_confidence"], "finding_type": "persistent anomaly (always-on load)",
    "observed_evidence": {
        "f005_min_kwh_h": r(floor["F005"], 4), "peer_min_kwh_h_by_flat": {k: r(v, 4) for k, v in floor.drop("F005").items()},
        "excess_constant_w": r(excess * 1000, 1),
        "valid_hours": int(len(f5o)), "hours_below_f005_floor": int((f5o.energy_kwh < floor["F005"] - 1e-9).sum()),
        "weekly_minimum_kwh_h": {int(k): r(v, 4) for k, v in f5o.groupby(f5o.hour_idx // 168).energy_kwh.min().items()},
        "mean_when_flat_unoccupied_kwh_h": r(f5o[f5o.occupants_home == 0].energy_kwh.mean(), 4),
        "overnight_mean_kwh_h": r(f5o[f5o.is_overnight].energy_kwh.mean(), 4),
        "evening_increment_above_floor_kwh_h": {k: r(v, 4) for k, v in ev_inc.items()},
        "excess_kwh_28d_observed_hours": r(o2_save.sum()),
        "context": {"residents": int(flats.loc["F005", "residents"]), "floor_area_m2": int(flats.loc["F005", "floor_area_m2"]),
                    "note": "Peers with 2-4 residents and 56-82 m2 all share an identical 33 W floor, so size does not explain a constant +95 W."},
    },
    "data_quality_flags": {"missing_slots": int(f5.energy_missing.sum()),
                           "missing_status": f5[f5.energy_missing].energy_status.value_counts().to_dict(),
                           "excess_in_missing_slots_estimate_kwh": r(f5.energy_missing.sum() * excess)},
    "anomaly_vs_waste": {
        "demonstrated": ["A constant additive +95 W on A06 in every one of 661 valid hours for 4 weeks, including unoccupied and overnight hours.",
                         "Evening use above the floor (+70 W) is in the normal range of other flats, so the anomaly is a fixed always-on device, not more active use."],
        "hypotheses": ["Which device it is (light left on, TV/console standby, aquarium/terrarium, network storage, or a building load wired to the flat's circuit).",
                       "Whether it is avoidable - some always-on devices are needed."],
    },
    "intervention": {
        "action": "Locate the always-on device (check lights/LED strips, TV/console/speaker standby, chargers, aquariums) and switch it off or put it on a switched power strip/timer.",
        "who": "student first; housing provider if the load turns out to be fixed installation",
        "constraints": {"safety": ["Do not switch off devices that must run continuously (e.g. medical equipment, aquarium life support)."],
                        "comfort": ["None expected if it is an unused light or standby load."],
                        "equipment_control": ["Hourly data cannot identify the device; finding it needs a walk-round or a plug-in power meter."]},
    },
    "counterfactual": {
        "measured_inputs": ["hourly A06 kWh (F005)", "A06 minimum of the 7 other flats (33 W)"],
        "assumptions": ["a fraction f of the 95 W excess is removed in every hour (f = 1, 0.5, 0.25)",
                        "evening use above the floor unchanged", "no hour falls below the peer floor"],
        "formula": "savings_kWh = f x sum_h min(A06(h) - 0.033, 0.095)",
    },
    "scenarios": o2_scen,
    "uncertainty": {"key_unknowns": ["device identity", "fraction avoidable"],
                    "note": "Measurement uncertainty is negligible (constant load); savings range is driven by f. f = 0.5 is a neutral midpoint chosen because nothing in the data indicates how much of the load is avoidable - it is not an estimate. Because the load is flat across all hours, hourly-spot and time-average values are nearly equal.",
                    "rate_if_persistent": {"kwh_per_day_full_excess": r(excess * 24, 3),
                                           "note": "A constant load would continue at this rate; any longer-period figure is an extrapolation and depends on that period's prices."}},
    "actionability": {"level": "student_first_then_provider", "actor": "student (investigate), housing provider (if hard-wired)",
                      "steps": ["walk-round at night with lights/devices", "switch off one candidate at a time and check next-day data"]},
    "evidence_quality": {"consumption": "measured", "anomaly": "measured", "appliance_identity": "inferred (low-medium)",
                         "avoidability": "hypothetical", "savings": "conditional simulation"},
    "statistical_confidence": "very high that the +95 W always-on load exists",
    "action_feasibility": "medium: depends on finding the device",
    "recommendation_status": "requires_student_confirmation",
    "chatbot_guidance": {
        "can_say": ["Something in your flat draws about 95 W more than in other flats, all day and night, including when nobody is home."],
        "must_confirm": ["What is always on in the flat?", "Does it need to run continuously?"],
        "must_not_say": ["That a specific device is to blame.", "That the full 63 kWh is guaranteed savings."],
    },
})

# ---------------------------------------------------------------- O3 F002 refrigerator step
f2 = t[t.appliance_id == "F002-A01"].sort_values("hour_idx").set_index("hour_idx")
s = f2.energy_kwh
cand = {k: abs(s.loc[k:].mean() - s.loc[:k - 1].mean()) for k in range(48, 624)}
cp = max(cand, key=cand.get)
pre, post = s.loc[:cp - 1].dropna(), s.loc[cp:].dropna()
se = np.sqrt(pre.var() / len(pre) + post.var() / len(post))
peer_a01 = ok[(ok.appliance_code == "A01") & (ok.flat_id != "F002")]
other_f2 = ok[(ok.flat_id == "F002") & (ok.appliance_code != "A01")]
post_rows = f2.loc[cp:].dropna(subset=["energy_kwh"]).reset_index()
excess_rate = float(post.mean() - pre.mean())
daily_post = post_rows.assign(day=post_rows.hour_idx // 24).groupby("day").energy_kwh.mean()
o3_scen = [
    value_reduction(post_rows.hour_idx, (post_rows.energy_kwh - pre.mean()).clip(lower=0),
                    "Repaired at the step: excess over the pre-step mean avoided for the 14 observed post-step days (retrospective)", "central", seed_offset=30, window=(cp, 672), observed_hours=len(post_rows)),
    value_reduction(post_rows.hour_idx, (post_rows.energy_kwh - peer_a01.energy_kwh.mean()).clip(lower=0),
                    "Repaired to the peer-fridge mean (0.0526 kWh/h) instead of F002's own pre-step mean", "sensitivity", seed_offset=32, window=(cp, 672), observed_hours=len(post_rows)),
    value_reduction(post_rows.hour_idx, (post_rows.energy_kwh - pre.mean()).clip(lower=0) * 0.5,
                    "Partial fix (e.g. door/seal adjusted, compressor still degraded): half the excess avoided", "lower", seed_offset=34, window=(cp, 672), observed_hours=len(post_rows)),
]
rate_value = value_reduction(post_rows.hour_idx, pd.Series(np.full(len(post_rows), excess_rate)), "rate", "rate", window=(cp, 672))
OPP.append({
    "id": "O3_F002_refrigerator_step", "title": "F002: sudden, sustained x2.4 increase in refrigerator-like consumption",
    "flat_id": "F002", "appliance_code": "A01", "appliance_label_inferred": APPLIANCE_LABELS["A01"],
    "identity_confidence": ident["A01"]["identity_confidence"], "finding_type": "equipment anomaly (suspected fault)",
    "observed_evidence": {
        "changepoint_utc": f2.loc[cp, "timestamp_utc"], "changepoint_local": f2.loc[cp, "timestamp_local"],
        "last_normal_hour_local": f2.loc[cp - 1, "timestamp_local"],
        "last_pre_values_kwh": [r(v, 4) for v in s.loc[cp - 3:cp - 1]], "first_post_values_kwh": [r(v, 4) for v in s.loc[cp:cp + 2]],
        "pre": {"hours": int(len(pre)), "mean": r(pre.mean(), 4), "sd": r(pre.std(), 4), "min": r(pre.min(), 4), "max": r(pre.max(), 4)},
        "post": {"hours": int(len(post)), "mean": r(post.mean(), 4), "sd": r(post.std(), 4), "min": r(post.min(), 4), "max": r(post.max(), 4)},
        "ratio_post_to_pre": r(post.mean() / pre.mean(), 2), "excess_w": r(excess_rate * 1000, 1),
        "welch_t": r((post.mean() - pre.mean()) / se, 1),
        "post_hours_above_pre_max": f"{int((post > pre.max()).sum())} of {len(post)}",
        "post_step_daily_means_kwh_h": {int(k): r(v, 4) for k, v in daily_post.items()},
        "post_step_trend_kwh_h_per_day": r(np.polyfit(daily_post.index, daily_post.values, 1)[0], 5),
        "peer_A01_mean_pre_post": [r(peer_a01[peer_a01.hour_idx < cp].energy_kwh.mean(), 4), r(peer_a01[peer_a01.hour_idx >= cp].energy_kwh.mean(), 4)],
        "other_F002_channels_mean_pre_post": {c: [r(d[d.hour_idx < cp].energy_kwh.mean(), 4), r(d[d.hour_idx >= cp].energy_kwh.mean(), 4)]
                                              for c, d in other_f2.groupby("appliance_code")},
        "F002_occupancy_indoor_pre_post": {"occupants_mean": [r(f2.loc[:cp - 1].occupants_home.mean()), r(f2.loc[cp:].occupants_home.mean())],
                                           "indoor_c": [r(f2.loc[:cp - 1].indoor_temp_c.mean()), r(f2.loc[cp:].indoor_temp_c.mean())]},
        "excess_kwh_observed_post_step": r((post - pre.mean()).sum()),
    },
    "data_quality_flags": {"missing_slots_pre_post": [int(f2.loc[:cp - 1].energy_missing.sum()), int(f2.loc[cp:].energy_missing.sum())],
                           "missing_status": f2[f2.energy_missing].energy_status.value_counts().to_dict(),
                           "post_step_rows_from_Wh_conversion": int(((f2.loc[cp:].raw_unit.str.strip().str.lower() == "wh")).sum()),
                           "artefact_checks": "step is abrupt (one hour), confined to this channel; other F002 channels, occupancy, indoor temperature and the other 7 fridges show no change; values after the step are realistic noise, not a constant or unit artefact"},
    "anomaly_vs_waste": {
        "demonstrated": [f"Mean consumption rose from {r(pre.mean(),4)} to {r(post.mean(),4)} kWh/h (x{r(post.mean()/pre.mean(),2)}) between {f2.loc[cp-1,'timestamp_local']} and {f2.loc[cp,'timestamp_local']}, and stayed there for all 14 remaining days with no recovery trend.",
                         "No simultaneous change in occupancy, indoor temperature, other F002 channels or other flats' fridges."],
        "hypotheses": ["Cause: fault (door seal, thermostat, defrost, fan, compressor) vs a user setting (fast-freeze/super-cool left on, door not closing, fridge overfilled after shopping) vs a second appliance added to the circuit.",
                       "That a repair returns consumption to the pre-step level."],
    },
    "intervention": {
        "action": "Student checks first: door closes and seals, fast-freeze/super-cool mode off, thermostat at normal setting (about 4 degC fridge / -18 degC freezer), vents not blocked, no heavy frost. If unchanged, report to the housing provider.",
        "who": "student (checks + report); housing provider (repair/replacement)",
        "constraints": {"safety": ["Never switch the fridge off to 'save' energy: food safety comes first."],
                        "comfort": ["None."],
                        "equipment_control": ["Appliances in student housing are often provider-owned; repairs typically need the provider (assumption: ownership not in data)."]},
    },
    "counterfactual": {
        "measured_inputs": ["hourly A01 kWh (F002) before and after the step", "peer A01 mean"],
        "assumptions": ["after repair, consumption returns to the pre-step mean (central) or peer mean (sensitivity)",
                        "repair at the moment of the step (retrospective) - real savings start only when it is actually fixed"],
        "formula": "savings_kWh = sum over post-step hours h of max(0, A01(h) - pre_mean); savings rate = (post_mean - pre_mean) per hour",
    },
    "scenarios": o3_scen,
    "savings_rate_while_unrepaired": {"kwh_per_day": r(excess_rate * 24, 3), "w": r(excess_rate * 1000, 1),
                                      "kwh_per_28_days_if_persistent": r(excess_rate * 672, 2),
                                      "reconciliation": f"central kWh = excess rate x observed post-step hours = {excess_rate:.5f} x {len(post_rows)} = {excess_rate * len(post_rows):.2f}; window has 336 h, 4 missing",
                                      "co2e_kg_per_day_at_observed_post_step_factors": r(rate_value["co2e_kg"] / (len(post_rows) / 24), 4),
                                      "value_spot_hourly_sek_per_day_at_observed_post_step_prices": r(rate_value["value_spot_hourly_sek"] / (len(post_rows) / 24), 3),
                                      "note": "Each day of delay costs this much energy. Future prices differ; this is a rate, not a forecast."},
    "uncertainty": {"key_unknowns": ["cause of the step", "post-repair level", "repair date"],
                    "statistical": "the excess rate itself is very precisely measured (Welch t ~ 90)"},
    "actionability": {"level": "shared_student_then_provider", "actor": "student checks settings/door; housing provider repairs",
                      "steps": ["check door/seal/settings", "if no change in 24-48 h, report fault with the step date as evidence"]},
    "evidence_quality": {"consumption": "measured", "anomaly": "measured", "appliance_identity": "inferred (medium-high)",
                         "cause": "hypothetical", "savings": "conditional simulation (depends on repair)"},
    "statistical_confidence": "very high that the step is real",
    "action_feasibility": "medium: student can check settings; repair depends on the provider",
    "recommendation_status": "supported_by_data_as_alert",
    "chatbot_guidance": {
        "can_say": [f"Your fridge-like circuit has used about {r(post.mean()/pre.mean(),1)}x its normal energy since {f2.loc[cp,'timestamp_local'][:10]}; that pattern usually indicates a setting or fault."],
        "must_confirm": ["Did anything change on 15 October (new appliance, fast-freeze, door problem)?"],
        "must_not_say": ["That the fridge is definitely broken.", "To turn the fridge off."],
    },
})

# ---------------------------------------------------------------- O4 F004 electronics
a5 = ok[ok.appliance_code == "A05"]
f4 = t[(t.flat_id == "F004") & (t.appliance_code == "A05")]
f4o = f4[~f4.energy_missing]
peer_hour = a5[a5.flat_id != "F004"].groupby("local_hour").energy_kwh.median()
peer2_hour = a5[a5.flat_id.isin(["F001", "F008"])].groupby("local_hour").energy_kwh.mean()
day_block = f4o[f4o.local_hour.between(9, 16)]
prof4 = f4o.groupby("local_hour").energy_kwh.mean()
excess_all = (f4o.energy_kwh - f4o.local_hour.map(peer_hour)).clip(lower=0)
blk = f4o.local_hour.between(9, 16)
o4_scen = [
    value_reduction(f4o.loc[blk, "hour_idx"], excess_all[blk], "Daytime (09-17 h) block reduced to the peer level (4 W)", "central", seed_offset=40),
    value_reduction(f4o.loc[blk & (f4o.occupants_home == 0), "hour_idx"], excess_all[blk & (f4o.occupants_home == 0)],
                    "Only when nobody is home during 09-17 h", "lower", seed_offset=42),
    value_reduction(f4o.hour_idx, excess_all, "Every hour reduced to the peer hourly median (includes small evening/night differences)", "upper_measured", seed_offset=44),
]
OPP.append({
    "id": "O4_F004_daytime_electronics", "title": "F004: electronics-like load stays on during the day",
    "flat_id": "F004", "appliance_code": "A05", "appliance_label_inferred": APPLIANCE_LABELS["A05"],
    "identity_confidence": ident["A05"]["identity_confidence"], "finding_type": "persistent anomaly (scheduled daytime load)",
    "observed_evidence": {
        "daytime_09_16_mean_kwh_h": r(day_block.energy_kwh.mean(), 4),
        "daytime_09_16_min_max": [r(day_block.energy_kwh.min(), 4), r(day_block.energy_kwh.max(), 4)],
        "days_with_daytime_block": f"{int((day_block.groupby('local_date').energy_kwh.mean() > 0.05).sum())} of {day_block.local_date.nunique()}",
        "peer_daytime_09_16_mean_by_flat": {k: r(v, 4) for k, v in a5[a5.local_hour.between(9, 16) & (a5.flat_id != 'F004')].groupby('flat_id').energy_kwh.mean().items()},
        "daytime_mean_when_unoccupied_vs_occupied": [r(day_block[day_block.occupants_home == 0].energy_kwh.mean(), 4),
                                                     r(day_block[day_block.occupants_home > 0].energy_kwh.mean(), 4)],
        "f004_profile_by_local_hour": {int(k): r(v, 4) for k, v in prof4.items()},
        "matched_peers_2_residents_profile": {int(k): r(v, 4) for k, v in peer2_hour.items()},
        "other_hours_vs_2_resident_peers": "21-08 h identical to F001/F008 (0.053 kWh/h); 17-20 h within 0.01 kWh/h; only 09-16 h differs",
        "excess_kwh_28d_daytime": r(excess_all[blk].sum()),
    },
    "data_quality_flags": {"missing_slots": int(f4.energy_missing.sum()),
                           "missing_slots_in_09_16": int(f4[f4.local_hour.between(9, 16)].energy_missing.sum()),
                           "missing_status": f4[f4.energy_missing].energy_status.value_counts().to_dict()},
    "anomaly_vs_waste": {
        "demonstrated": ["A 69 W load runs from 09:00 to 16:59 local on every day, independent of whether anyone is home; every other flat is at 4 W in those hours.",
                         "Outside 09-17 h F004 matches the other 2-resident flats exactly."],
        "hypotheses": ["The rigid 09:00-17:00 block suggests a timer/schedule (e.g. a PC, console or display on a schedule, or a device on a timer plug) rather than forgetfulness.",
                       "Whether the device is doing useful work (e.g. a computation/download) - if so it is not waste."],
    },
    "intervention": {"action": "Identify what runs 09:00-17:00 (check device schedules, timer plugs, PC sleep settings) and switch it off or enable sleep when not in use.",
                     "who": "student",
                     "constraints": {"safety": ["None specific."], "comfort": ["None."],
                                     "equipment_control": ["If the device performs needed work, shift or shorten rather than remove."]}},
    "counterfactual": {"measured_inputs": ["hourly A05 kWh (F004)", "median A05 of the other 7 flats by local hour"],
                       "assumptions": ["daytime consumption falls to the peer median for the same hour (4 W)", "other hours unchanged"],
                       "formula": "savings_kWh = sum over 09-16 h of max(0, A05_F004(h) - peer_median(local_hour(h)))"},
    "scenarios": o4_scen,
    "uncertainty": {"key_unknowns": ["device identity", "whether its work is needed"],
                    "note": "Measurement uncertainty is negligible (identical block every day); the range reflects how many hours the student actually acts on."},
    "actionability": {"level": "student_independent", "actor": "student", "steps": ["find the scheduled device", "change schedule / sleep settings"]},
    "evidence_quality": {"consumption": "measured", "anomaly": "measured", "appliance_identity": "inferred (low)",
                         "avoidability": "hypothetical", "savings": "conditional simulation"},
    "statistical_confidence": "very high that the daytime block exists",
    "action_feasibility": "high once the device is identified",
    "recommendation_status": "requires_student_confirmation",
    "chatbot_guidance": {"can_say": ["Something on your electronics circuit runs at about 69 W every day from 09:00 to 17:00, even when you are out."],
                         "must_confirm": ["Is something scheduled to run during the day?"],
                         "must_not_say": ["That it is definitely a computer."]},
})

# ---------------------------------------------------------------- O5 dishwasher scheduling
ev = ok[(ok.appliance_code == "A04") & (ok.energy_kwh > 0.1)].sort_values("hour_idx").copy()
loc_hour = hours.local_hour


def to_local_hour(h0: int, target: int) -> int:
    """first hour at or after h0 whose local hour == target (handles DST)."""
    for h in range(h0, min(h0 + 25, 672)):
        if loc_hour[h] == target:
            return h
    return h0


def optimal(h0: int, max_delay: int) -> int:
    c = [h for h in range(h0, min(h0 + max_delay + 1, 672)) if pd.notna(hours.spot_sek_per_kwh[h])]
    return min(c, key=lambda h: hours.spot_sek_per_kwh[h]) if c else h0


o5_scen = [
    value_shift(ev, ev.hour_idx.map(lambda h: to_local_hour(h, 21)), "Start at 21:00 instead of 20:00 (1-h delay, before typical quiet hours)", "central", 50),
    value_shift(ev, ev.hour_idx.map(lambda h: to_local_hour(h, 22)), "Start at 22:00 (2-h delay)", "sensitivity", 52),
    value_shift(ev, ev.hour_idx.map(lambda h: to_local_hour(h, 1)), "Delay-start timer to 01:00 (overnight run)", "sensitivity", 54),
    value_shift(ev, ev.hour_idx.map(lambda h: optimal(h, 11)), "Price-optimal hour before 07:00 using day-ahead prices", "upper", 56),
]
per_flat = ev.groupby("flat_id").agg(events=("energy_kwh", "size"), kwh=("energy_kwh", "sum"))
central_ev = ev.assign(dest=ev.hour_idx.map(lambda h: to_local_hour(h, 21)))
central_ev["save"] = central_ev.energy_kwh * (central_ev.hour_idx.map(hours.spot_sek_per_kwh) - central_ev.dest.map(hours.spot_sek_per_kwh))
OPP.append({
    "id": "O5_dishwasher_price_timing", "title": "Dishwasher always starts at 20:00, inside the evening price peak (all flats)",
    "flat_id": "ALL", "appliance_code": "A04", "appliance_label_inferred": APPLIANCE_LABELS["A04"],
    "identity_confidence": ident["A04"]["identity_confidence"], "finding_type": "timing opportunity (no kWh reduction)",
    "observed_evidence": {
        "events": int(len(ev)), "events_at_20_local": int((ev.local_hour == 20).sum()),
        "kwh_per_event_mean_min_max": [r(ev.energy_kwh.mean(), 3), r(ev.energy_kwh.min(), 3), r(ev.energy_kwh.max(), 3)],
        "cadence": "every 2 days in each flat (gaps of 4-6 days coincide with missing readings or F003's vacancy)",
        "events_per_flat": {k: int(v) for k, v in per_flat.events.items()},
        "mean_spot_by_local_hour_sek": {h: r(hours[hours.local_hour == h].spot_sek_per_kwh.mean(), 4) for h in (16, 19, 20, 21, 22, 1, 3)},
        "mean_carbon_by_local_hour_g": {h: r(hours[hours.local_hour == h].carbon_gco2e_per_kwh.mean(), 2) for h in (20, 21, 22, 1)},
        "baseline_spot_sek_28d": o5_scen[0]["baseline_spot_hourly_sek"],
        "central_saving_per_flat_spot_sek_28d": {k: r(v) for k, v in central_ev.groupby("flat_id").save.sum().items()},
        "central_saving_per_event_spot_sek": r(central_ev.save.mean(), 3),
    },
    "data_quality_flags": {"likely_unobserved_events": hidden_rows,
                           "events_with_missing_price_at_20": int(ev.hour_idx.map(hours.spot_sek_per_kwh).isna().sum()),
                           "note": "Two expected runs fall in missing 20:00 readings; they are not counted (savings slightly understated, ~2 x 0.9 kWh)."},
    "anomaly_vs_waste": {
        "demonstrated": ["All 108 observed runs start at exactly 20:00 local, the most expensive hour block of the day (0.92 vs 0.31 SEK/kWh at 21:00).",
                         "Moving the same kWh changes cost and CO2e, not consumption."],
        "hypotheses": ["That the 20:00 start is a habit/timer the student controls.", "That the household has an hourly-price contract (otherwise no SEK effect).",
                       "That the appliance is a dishwasher (inferred)."],
    },
    "intervention": {"action": "Start the dishwasher at 21:00 or later (manually or with delay-start).",
                     "who": "student",
                     "constraints": {"safety": ["Running appliances unattended or overnight is commonly discouraged for fire and water-leak safety; the 21:00 option avoids overnight running."],
                                     "comfort": ["Shared-housing quiet hours (often 22:00-07:00) may restrict later starts. The data show each run's energy within one hour; a real cycle started at 21:00 may continue past 22:00."],
                                     "equipment_control": ["Overnight options need a delay-start function; price-optimal timing needs day-ahead prices (published the previous afternoon) or an app."]}},
    "counterfactual": {"measured_inputs": ["observed event hours and kWh", "hourly spot price and carbon factor"],
                       "assumptions": ["same kWh per cycle", "whole cycle falls in the destination hour", "events only delayed, never advanced",
                                       "if a destination price is missing the event is not valued"],
                       "formula": "value_SEK = sum_events kWh_e x (spot(h_e) - spot(h_e')); CO2e = sum kWh_e x (carbon(h_e) - carbon(h_e'))/1000; kWh change = 0"},
    "scenarios": o5_scen,
    "uncertainty": {"key_unknowns": ["tariff type (decisive)", "quiet-hour rules", "whether cycles span two hours"],
                    "note": "On fixed, monthly-average or rent-included contracts the SEK value is 0; CO2e uses average factors and may overstate marginal benefit."},
    "actionability": {"level": "student_independent", "actor": "student", "steps": ["start one hour later", "or use delay-start"]},
    "evidence_quality": {"timing": "measured", "appliance_identity": "inferred (medium)", "tariff": "unknown", "savings": "conditional simulation"},
    "statistical_confidence": "very high that runs coincide with the price peak",
    "action_feasibility": "high (1-h delay); medium for overnight options",
    "recommendation_status": "supported_by_data_conditional_on_tariff",
    "chatbot_guidance": {"can_say": ["Your dishwasher-like appliance always starts at 20:00, when prices and emissions peak; starting at 21:00 avoids the peak."],
                         "must_confirm": ["Do you pay hourly (spot) electricity prices?", "Are there quiet hours in your building?"],
                         "must_not_say": ["That this lowers your bill if you are on a fixed or monthly price, or if electricity is included in rent."]},
})

# ---------------------------------------------------------------- normalised evidence vocabulary (engine contract)
EVIDENCE_ENUM = {"measured", "inferred", "hypothetical", "simulated", "unknown"}
for o in OPP:
    o["evidence_classification"] = {
        "consumption": "measured",          # cleaned hourly kWh
        "pattern": "measured",              # the anomaly / timing pattern itself
        "appliance_identity": "inferred",   # label from load signature, needs student confirmation
        "avoidability": "hypothetical",     # whether the kWh (or the price exposure) is avoidable
        "savings": "simulated",             # counterfactual scenario outputs
        "tariff": "unknown",                # no tariff data for any student
    }
    o["waste_status"] = "unconfirmed"       # becomes 'student_confirmed' only via the coach; never set by the engine
    o["verification_status"] = "not_verified"  # requires post-intervention measurements
    assert set(o["evidence_classification"].values()) <= EVIDENCE_ENUM

# ============================================================================ 5. rankings (separate, no composite)
def central(o):
    return next(s for s in o["scenarios"] if s["role"] == "central")


EVIDENCE_ORDER = {"O3_F002_refrigerator_step": 1, "O5_dishwasher_price_timing": 2, "O4_F004_daytime_electronics": 3,
                  "O2_F005_elevated_base_load": 4, "O1_F007_heating_unoccupied": 5}
EVIDENCE_WHY = {
    "O3_F002_refrigerator_step": "abrupt sustained step, Welch t ~ 90, artefact checks clean; cause unknown",
    "O5_dishwasher_price_timing": "timing and prices fully measured; only identity and tariff unknown",
    "O4_F004_daytime_electronics": "identical 69 W block on 28/28 days; device unknown",
    "O2_F005_elevated_base_load": "constant +95 W in 661/661 hours; device and avoidability unknown",
    "O1_F007_heating_unoccupied": "relies on a simulated occupancy estimate with frequent 1-h flips",
}
ACTION_ORDER = {"O5_dishwasher_price_timing": 1, "O1_F007_heating_unoccupied": 2, "O4_F004_daytime_electronics": 3,
                "O2_F005_elevated_base_load": 4, "O3_F002_refrigerator_step": 5}
ACTION_WHY = {
    "O5_dishwasher_price_timing": "student alone, one-step habit change",
    "O1_F007_heating_unoccupied": "student alone; needs routine or a rated timer",
    "O4_F004_daytime_electronics": "student alone once the device is found",
    "O2_F005_elevated_base_load": "student must first find the device; provider if hard-wired",
    "O3_F002_refrigerator_step": "student can only check settings; repair needs the housing provider",
}
def rng(o, key):
    v = [s_[key] for s_ in o["scenarios"] if s_["role"] != "upper_hypothetical"]
    return [min(v), max(v)]


rank_kwh = sorted(OPP, key=lambda o: -central(o)["kwh"])
rank_co2 = sorted(OPP, key=lambda o: -central(o)["co2e_kg"])
rank_sek = sorted(OPP, key=lambda o: -central(o)["value_spot_hourly_sek"])
rankings = {
    "note": "Three separate orderings; no composite score. Impact uses each opportunity's CENTRAL scenario over its own stated period (28 days for all except O3: 14 post-step days).",
    "by_realistic_impact_kwh": [{"id": o["id"], "kwh": central(o)["kwh"], "scenario_range_kwh": rng(o, "kwh")} for o in rank_kwh],
    "comparability_note": ("O3's observed saving covers only the 14 post-step days; at the measured excess rate an unrepaired "
                           f"fault adds {r(excess_rate * 672)} kWh per 28 days (persistence assumption), which would rank it first on kWh. "
                           "O2's central value rests on the arbitrary f = 0.5 (range 25-100 %). O5 saves no kWh by design."),
    "by_realistic_impact_co2e_kg": [{"id": o["id"], "co2e_kg": central(o)["co2e_kg"], "scenario_range_co2e_kg": rng(o, "co2e_kg")} for o in rank_co2],
    "by_conditional_spot_value_hourly_tariff_sek": [{"id": o["id"], "value_spot_hourly_sek": central(o)["value_spot_hourly_sek"],
                                                     "scenario_range_sek": rng(o, "value_spot_hourly_sek")} for o in rank_sek],
    "by_strength_of_evidence": [{"id": k, "rank": v, "why": EVIDENCE_WHY[k]} for k, v in sorted(EVIDENCE_ORDER.items(), key=lambda x: x[1])],
    "by_student_actionability": [{"id": k, "rank": v, "why": ACTION_WHY[k]} for k, v in sorted(ACTION_ORDER.items(), key=lambda x: x[1])],
}
status = {
    "supported_by_data": [
        "O3: F002's fridge-like circuit has a real, sustained x2.36 step (alert + check/report).",
        "O5: dishwasher-like runs sit in the 20:00 price/carbon peak; a 1-h delay avoids it (SEK only on hourly tariffs; CO2e reduction is the tariff-independent message).",
    ],
    "requires_student_confirmation": [
        "O1: whether F007 was really out in the flagged hours and can switch the heater off safely.",
        "O2: what F005's always-on 95 W device is and whether it can be switched off.",
        "O4: what F004 runs 09:00-17:00 and whether that work is needed.",
        "O3: whether a setting/door issue explains the step before a fault is reported.",
    ],
    "illustrative_simulations_only": [
        "Any SEK figure presented as a bill saving (spot component only; tariff unknown).",
        "F007/F001 thermostat-setpoint scenarios from the research report (S1b/S1c): not supported because both heaters have identical weather curves at different indoor temperatures.",
        "Overnight-electronics switch-off for all flats (S4) and price-optimal overnight dishwasher runs (safety/quiet hours).",
        "Any annualised or seasonal extrapolation.",
    ],
}

# ============================================================================ 6. write outputs
out = {
    "schema_version": "1.0",
    "generated_by": "analysis/opportunities.py",
    "inputs_sha256": {"data/processed/analytical_table.csv": sha(PROCESSED / "analytical_table.csv"),
                      **{f: sha(ROOT / f) for f in SRC_FILES}},
    "original_dataset_sha256": clean_summary["original_sha256"],
    "period": coverage,
    "valuation": {
        "currency": "SEK", "price_component": "synthetic spot energy only, excl. VAT, network fees, energy tax, markup and fixed fees",
        "time_average_spot_sek_per_kwh": r(SPOT_AVG, 4), "time_average_carbon_g_per_kwh": r(CARBON_AVG, 2),
        "carbon_factor_type": "synthetic operational average factor (not marginal, not lifecycle)",
        "tariff_rules": {
            "hourly_spot": "use value_spot_hourly_sek (spot component only)",
            "monthly_average_spot": "reductions approx. value_spot_timeavg_sek; load shifting 0 SEK",
            "fixed_price": "reductions = kWh x user's contract price; load shifting 0 SEK",
            "included_in_rent": "0 SEK to the student; kWh and CO2e still change",
            "unknown": "report kWh and CO2e; give SEK only as 'if you pay hourly spot prices'"},
        "bootstrap": {"method": "day-block resampling of the 28 days", "draws": N_BOOT, "seed": SEED},
    },
    "data_caveats": {"missing_vs_zero": missing_vs_energy, "appliance_identity": ident},
    "opportunities": OPP,
    "rankings": rankings,
    "recommendation_status": status,
}
(REPORTS / "opportunities.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)) + "\n")


# ---------------------------------------------------------------------------- markdown report
def fmt_ci(ci):
    return "-" if not ci else f"{ci[0]:,.1f}–{ci[1]:,.1f}"


def scen_table(o):
    rows = ["| Scenario | Role | Period | kWh | kgCO2e | Spot value, hourly tariff (SEK) | 95 % CI (SEK) | Spot value, time-avg proxy (SEK) |",
            "|---|---|---|---:|---:|---:|---:|---:|"]
    for s_ in o["scenarios"]:
        rows.append(f"| {s_['label']} | {s_['role']} | {s_['period']['label']} | {s_['kwh']:,.2f} | {s_['co2e_kg']:,.3f} | {s_['value_spot_hourly_sek']:,.2f} | "
                    f"{fmt_ci(s_.get('ci95_value_spot_hourly_sek'))} | {s_['value_spot_timeavg_sek']:,.2f} |")
    return "\n".join(rows)


def dash(x):
    return "–" if x is None else x


def bullets(xs):
    return "\n".join(f"- {x}" for x in xs)


def kv(d, skip=()):
    return "\n".join(f"- **{k}**: `{json.dumps(v, ensure_ascii=False, default=str)}`" for k, v in d.items() if k not in skip)


md = [
    "# Energy-saving opportunity validation",
    "",
    "_Generated by `analysis/opportunities.py` from `data/processed/analytical_table.csv`. Machine-readable twin: "
    "[`opportunities.json`](opportunities.json). Do not edit by hand; re-run the script._",
    "",
    "**How to read money values:** every SEK value is the **synthetic spot-energy component only** (excl. VAT, network fees, "
    "energy tax, markup and fixed fees). *Spot value, hourly tariff* applies only to students on an hourly spot-price contract. "
    "*Time-average proxy* (kWh × " + f"{SPOT_AVG:.4f}" + " SEK/kWh) roughly represents a monthly-average spot contract. On a fixed price, "
    "multiply kWh by the student's own price; if electricity is included in rent, the student saves 0 SEK. Load shifting "
    "is worth 0 SEK on anything except an hourly tariff. None of these is a bill saving.",
    "",
    "**Evidence vocabulary:** *measured* = read from cleaned observations; *inferred* = derived from measured patterns by an "
    "explicit rule; *hypothetical* = depends on an untestable assumption. Statistical confidence (is the pattern real?) "
    "is reported separately from action feasibility (can the student act?).",
    "",
    "## 1. Timestamp coverage and the 672 vs 673-hour issue",
    "",
    f"- Dataset: **{coverage['hourly_intervals']} hourly intervals**, {coverage['utc_first_interval_start']} to "
    f"{coverage['utc_last_interval_start']} (end exclusive {coverage['utc_end_exclusive']}).",
    f"- Local (Europe/Stockholm): {coverage['local_first_interval_start']} to {coverage['local_last_interval_start']}.",
    f"- The local calendar slice 1–28 Oct is **{coverage['elapsed_hours_local_calendar_1_to_28_oct']} elapsed hours** "
    f"(naive wall-clock count: {coverage['naive_wall_clock_hours_1_to_28_oct']}), because 25 Oct has "
    f"{coverage['hours_per_local_date']['2026-10-25']} hours. The dataset covers {coverage['dataset_hours_inside_local_1_to_28_oct']} "
    f"of them, lacks {', '.join(coverage['local_hours_1_to_28_oct_not_in_dataset'])}, and adds "
    f"{', '.join(coverage['dataset_hours_outside_local_1_to_28_oct'])}.",
    f"- Keyed on naive local time the data have only **{coverage['unique_naive_local_wall_clock_times']} distinct wall-clock hours**: "
    f"{' and '.join(coverage['repeated_wall_clock_hour'])} collapse into one.",
    f"- Hours per local date: 1 Oct = {coverage['hours_per_local_date']['2026-10-01']}, 25 Oct = "
    f"{coverage['hours_per_local_date']['2026-10-25']}, 29 Oct = {coverage['hours_per_local_date']['2026-10-29']}, all others 24.",
    f"- {coverage['interpretation']}",
    "",
    "## 2. Missing observations are not missing energy",
    "",
    missing_vs_energy["principle"],
    "",
    "| Channel | Slots | Missing slots | Observed 0.0 slots | Observed kWh | Missing kWh: lower / central / upper |",
    "|---|---:|---:|---:|---:|---|",
    *[f"| {k} {APPLIANCE_LABELS[k]} | {v['slots']} | {v['missing_slots']} | {v['observed_zero_slots']} | {v['observed_kwh']:,.1f} | "
      f"0 / {v['missing_kwh_central']:,.1f} / {v['missing_kwh_upper']:,.1f} |" for k, v in missing_vs_energy["by_channel"].items()],
    "",
    f"Central = {missing_vs_energy['central_method']}; upper = {missing_vs_energy['upper_method']}. Total: central "
    f"{missing_vs_energy['total_missing_kwh_central']} kWh, upper {missing_vs_energy['total_missing_kwh_upper']} kWh. The "
    "upper bound is deliberately extreme for event channels.",
    "",
    "**Concrete examples:**",
    *[f"- {h['flat_id']} dishwasher reading at {h['timestamp_local']} is `{h['status']}`; previous run {h['days_since_previous_event']} d "
      f"earlier, next {h['days_to_next_event']} d later on a strict 2-day cadence, so a run (~0.9 kWh) probably happened but was not observed."
      for h in hidden_rows],
    f"- Conversely, {missing_vs_energy['example_vacancy_is_measured_low_energy']}.",
    "",
    "## 3. Evidence for inferred appliance identities",
    "",
    "| Ch. | Inferred label | Confidence | Key measured signature | Plausible alternatives |",
    "|---|---|---|---|---|",
    *[f"| {c} | {v['label_inferred']} | {v['identity_confidence']} | {v['reasoning']} | {', '.join(v['plausible_alternatives'])} |"
      for c, v in ident.items()],
    "",
    "| Ch. | Flats using | Share of hours at 0 | Median kWh/h | Events > 0.1 kWh | Mean event kWh | Share of events in top hour | ρ vs outdoor | ρ vs occupants | Weekend/weekday | Overnight share |",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    *[f"| {c} | {m['flats_with_nonzero_use']} | {m['share_hours_zero']} | {m['median_kwh_h']} | {dash(m['events_gt_0_1kwh'])} | "
      f"{dash(m['mean_event_kwh'])} | {dash(m['share_events_in_top_hour'])} | {m['spearman_vs_outdoor_temp_in_using_flats']} | "
      f"{m['spearman_vs_occupants_home_in_using_flats']} | {m['weekend_vs_weekday_mean_ratio']} | {m['overnight_share_of_energy']} |"
      for c, m in ((c, v["metrics"]) for c, v in ident.items())],
    "",
    "Event columns are only computed for intermittent channels. For continuous channels (A01, A05, A06) the correlations "
    "with outdoor temperature and occupancy are confounded by time of day (nights are colder and more people are home), "
    "so they are not evidence of a causal link.",
    "",
    "Identities are used as **labels only**. No recommendation depends on an identity being exactly right; the chatbot must "
    "phrase them as \"heating-like\", \"refrigerator-like\" and so on.",
    "",
    "## 4. Opportunities",
]
for o in OPP:
    c_ = central(o)
    md += [
        "",
        f"### {o['id']}: {o['title']}",
        "",
        f"*Channel {o['appliance_code']} ({o['appliance_label_inferred']}, identity confidence {o['identity_confidence']}) · "
        f"{o['finding_type']} · status: **{o['recommendation_status']}***",
        "",
        "**1. Observed evidence (measured)**",
        "",
        kv(o["observed_evidence"]),
        "",
        "Data-quality flags:",
        "",
        kv(o["data_quality_flags"]),
        "",
        "**2. Anomaly versus waste**",
        "",
        "Demonstrated:",
        "",
        bullets(o["anomaly_vs_waste"]["demonstrated"]),
        "",
        "Hypotheses (not testable with this dataset):",
        "",
        bullets(o["anomaly_vs_waste"]["hypotheses"]),
        "",
        f"**3. Proposed intervention ({o['intervention']['who']})**: {o['intervention']['action']}",
        "",
        *[f"- *{k.replace('_', ' ')}*: " + " ".join(v) for k, v in o["intervention"]["constraints"].items()],
        "",
        "**4. Counterfactual model**",
        "",
        "- Measured inputs: " + "; ".join(o["counterfactual"]["measured_inputs"]),
        "- Scenario assumptions: " + "; ".join(o["counterfactual"]["assumptions"]),
        f"- Formula: `{o['counterfactual']['formula']}`",
        "",
        "**5. Conditional savings (each row states its time period)**",
        "",
        scen_table(o),
        "",
    ]
    if "savings_rate_while_unrepaired" in o:
        md += ["Rate while unrepaired: " + ", ".join(f"{k} = {v}" for k, v in o["savings_rate_while_unrepaired"].items() if k != "note")
               + f". {o['savings_rate_while_unrepaired']['note']}", ""]
    md += [
        "**6. Uncertainty**",
        "",
        kv(o["uncertainty"]),
        "",
        f"**7. Actionability**: `{o['actionability']['level']}` ({o['actionability']['actor']}). Steps: " + "; ".join(o["actionability"]["steps"]) + ".",
        "",
        "**8. Evidence quality**: " + "; ".join(f"{k} = *{v}*" for k, v in o["evidence_classification"].items())
        + f" (waste: {o['waste_status']}, verification: {o['verification_status']}). Detail: "
        + "; ".join(f"{k} = {v}" for k, v in o["evidence_quality"].items())
        + f". Statistical confidence: {o['statistical_confidence']}. Action feasibility: {o['action_feasibility']}.",
        "",
        "Chatbot: may say: " + " / ".join(o["chatbot_guidance"]["can_say"]) + " Must confirm: " + " / ".join(o["chatbot_guidance"]["must_confirm"])
        + " Must not say: " + " / ".join(o["chatbot_guidance"]["must_not_say"]),
    ]
md += [
    "",
    "## 5. Rankings (separate dimensions, no composite score)",
    "",
    rankings["note"],
    "",
    "| Rank | Realistic impact (kWh, central) | CO2e (kg, central) | Spot value if hourly tariff (SEK, central) | Strength of evidence | Student actionability |",
    "|---:|---|---|---|---|---|",
    *[f"| {i+1} | {a['id']} {a['kwh']:.1f} ({a['scenario_range_kwh'][0]:.1f}–{a['scenario_range_kwh'][1]:.1f}) | "
      f"{b['id']} {b['co2e_kg']:.2f} ({b['scenario_range_co2e_kg'][0]:.2f}–{b['scenario_range_co2e_kg'][1]:.2f}) | "
      f"{c['id']} {c['value_spot_hourly_sek']:.2f} ({c['scenario_range_sek'][0]:.2f}–{c['scenario_range_sek'][1]:.2f}) | {d['id']} | {e['id']} |"
      for i, (a, b, c, d, e) in enumerate(zip(rankings["by_realistic_impact_kwh"], rankings["by_realistic_impact_co2e_kg"],
                                              rankings["by_conditional_spot_value_hourly_tariff_sek"], rankings["by_strength_of_evidence"],
                                              rankings["by_student_actionability"]))],
    "",
    "Values are central (range across the opportunity's scenarios, excluding the hypothetical upper bound).",
    "",
    "**Comparability:** " + rankings["comparability_note"],
    "",
    "Why each evidence and actionability position:",
    "",
    *[f"- Evidence #{e['rank']} {e['id']}: {e['why']}" for e in rankings["by_strength_of_evidence"]],
    *[f"- Actionability #{a['rank']} {a['id']}: {a['why']}" for a in rankings["by_student_actionability"]],
    "",
    "## 6. What the data supports",
    "",
    "**Supported by the data:**", "", bullets(status["supported_by_data"]), "",
    "**Requires student confirmation before it becomes advice:**", "", bullets(status["requires_student_confirmation"]), "",
    "**Illustrative simulations only (not to be presented as findings):**", "", bullets(status["illustrative_simulations_only"]), "",
    "## 7. Reproducibility",
    "",
    "```bash",
    "python analysis/clean_data.py && python analysis/validate.py",
    "python analysis/eda.py",
    "python analysis/opportunities.py",
    "python analysis/verify_opportunities.py   # independent recomputation + cross-checks",
    "```",
    "",
    "Every number above is written to `reports/opportunities.json` by the same run. Input and source SHA-256 hashes are stored "
    "in its `inputs_sha256` field; bootstrap intervals use seed " + str(SEED) + ". `verify_opportunities.py` recomputes the central "
    "savings through a separate code path from the cleaned per-file outputs (not the joined table), cross-checks them against the EDA "
    "results, and confirms that two consecutive runs give byte-identical JSON.",
    "",
]
(REPORTS / "opportunity_report.md").write_text("\n".join(md))
print(json.dumps({o["id"]: {s_["role"]: [s_["kwh"], s_["value_spot_hourly_sek"], s_["co2e_kg"]] for s_ in o["scenarios"]} for o in OPP}, indent=1))

# Score method

All parameters are in `backend/app/config.py`.

## Pillars (0–100, higher = better)

**USE.** First, x = coverage-adjusted kWh / √residents / 28 days. A missing hour is filled with that appliance's own mean, never with 0. Then bench = the 20th percentile of x across the flats, and USE = 100 · min(1, bench / x).

**WASTE.** base = the 10th percentile of hourly kWh per appliance. avoidable = Σ max(0, kWh − base) over hours where `occupants_home == 0` (NaN occupancy counts as unknown, not away). Heater-like channels are excluded unless a heater finding is CONFIRMED. WASTE = 100 · clip(1 − (avoidable / total) / 0.5, 0, 1).

**TIMING.** flex = max(0, kWh − base), heater excluded. CTI = Σ(flex · g) / Σflex / mean(g). CTI is min-max scaled between the best and worst Europe/Stockholm hour-of-day mean carbon (best → 100). A flat with no flexible load gets 100.

**HEALTH** (Apartment lens only). fault = Σ `excess_kwh` of manager-attributed anomalies with status ≥ PLAUSIBLE. HEALTH = 100 · clip(1 − 2 · fault / total, 0, 1).

## Lenses

| | use | waste | timing | health |
|---|---|---|---|---|
| Apartment Performance | .40 | .25 | .20 | .15 |
| Resident Actions | .50 | .30 | .20 | – |

Resident Actions is computed with the same method on readings where every manager-attributed anomaly window has (observed − baseline) kWh/h removed, at every claim level. Tested property: adding manager-attributed excess lowers the Apartment score and leaves the Resident score unchanged.

score = exp(Σ w · ln(max(1, p))), the weighted geometric mean. The arithmetic mean is also returned, using the same floored pillars, so geometric ≤ arithmetic always holds.

Bands: A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 55, E ≥ 40, F ≥ 20, G < 20.

## Sensitivity
2000 weight vectors are drawn from Dirichlet(α = w · 20), seed 0, separately for each lens. The engine reports the p5/p95 of each flat's score and rank (rank 1 = best).

## Counterfactuals
Each counterfactual edits a copy of the data, then re-runs `evaluate()`.
- `return_to_baseline`: kWh = min(kWh, baseline) in the window. The anomaly is removed afterwards. If there is no baseline, the peer median is used.
- `shift_flexible_load`: above-base kWh in local peak hours (07–09, 17–20) moves to the cheapest non-peak hour within 12 h. Σ kWh is unchanged.
- `reduce_away_usage`: kWh −= fraction · above-base, in away hours, non-heater channels only.

## Projection
annual = 28-day value × 365/28 (heater-like: × 182/28). The range is the wider of ±30% and a 1000-draw day-bootstrap p5–p95. It is always labelled `"projection"`, and the assumptions always include "October data only" and "spot price only, excludes network fee, energy tax, VAT".

## Verification
saving = pre-repair rate × post hours − post kWh, where the pre-repair rate is the anomaly's `observed_kwh_per_h`. The 90% interval is a bootstrap over days. Verification needs ≥ 7 days (168 observed hours). VERIFIED is set only when the lower bound is above 0; otherwise the status stays REPAIRED. The demo can simulate post-repair data, and that output is flagged `simulated: true`.

# Audit of the teammate's quantitative engine (branch `saish`, commit `ddc02ce`)

**Scope:** locate, reproduce and audit the four-pillar scoring implementation on our validated data. Nothing on that branch was modified, merged or overwritten. It was inspected and run from a **detached, read-only worktree** of `origin/saish`.
**Reproduce:**
```bash
git worktree add --detach /tmp/saish_wt origin/saish
export SAISH_BACKEND=/tmp/saish_wt/backend
python analysis/score_audit/compare_saish.py          # -> reports/saish_engine_comparison.json
python analysis/score_audit/audit_score.py --teammate # -> reports/score_audit.{json,md}
python -m pytest                                       # 38 passed, 8 xfailed (pinned defects)
```

## 1. Why earlier inspections didn't find it

| Ref | Hash | Content |
|---|---|---|
| `origin/main` | `237d0cc` | dataset only |
| `origin/Pouyan` | `237d0cc` | = main |
| `origin/Hugo` | `59644a1` | static frontend mock-up (`wattwise-site/`) |
| `origin/mina` | `df99cb6` (local `ba0068c` unpushed) | our work |
| **`origin/saish`** | **`ddc02ce`** | **"Add quantitative engine + FastAPI backend for Flat Energy Coach"** (Saish Sandip Bhaskar) |

**Timeline (UTC):**
- 13:38:17 — our previous fetch recorded `origin/saish` at `237d0cc` (no engine).
- 13:49:31 — the engine commit `ddc02ce` was authored.
- 13:56:14 — the fetch for this audit first received it.

So the code didn't exist on the remote when we last looked. It is also a **package** (`backend/app/core/`), not a single `score.py`, which our candidate-path search assumed. The adapter now loads packages via `$SAISH_BACKEND`.

## 2. What the engine computes (as implemented, `backend/app/core/`, `config.py`)

- **Use:** x = coverage-adjusted kWh / √residents / 28. Missing hours are filled with the appliance's 28-day mean. bench = P20 of x across flats; Use = 100·min(1, bench/x). Heaters are included.
- **Waste:** base = P10 of hourly kWh per appliance. avoidable = Σ max(0, kWh − base) over hours with occupants = 0 (unknown occupancy ≠ away). Heaters are excluded unless a heater finding is CONFIRMED. Waste = 100·clip(1 − (avoidable/total)/0.5).
- **Timing:** flex = above-base kWh of every non-heater channel. CTI = Σ flex·g / Σ flex / ḡ, min–max scaled between the best and worst hour-of-day mean carbon. Carbon only, not price.
- **Health** (Apartment lens only): fault = Σ `excess_kwh` of manager-attributed anomalies at PLAUSIBLE or above; Health = 100·clip(1 − 2·fault/total).
- **Aggregation:** weighted geometric mean with pillars floored at 1.
  - Apartment lens (.40/.25/.20/.15).
  - Resident lens (.50/.30/.20), computed on readings with manager-attributed excess removed.
  - Bands A–G.
- **Sensitivity:** Dirichlet(α = 20·w), 2000 draws.
- **Counterfactuals:** `return_to_baseline`, `shift_flexible_load` (peak hours {7, 8, 17, 18, 19} local), `reduce_away_usage`. Each re-runs the whole engine.
- **Projection:** ×365/28 (heater ×182/28), range = max(±30 %, bootstrap).
- **Verification:** at least 7 days post-repair, VERIFIED only if the 90 % lower bound is above 0.

**Data used for this audit:**
- Our validated readings (`readings_clean.csv`).
- The organiser files, byte-identical to ours, through the engine's own loader guards.
- Our five validated findings, translated into its anomaly schema. The translation needs choices the schema forces: a numeric confidence (assumed: O3 0.95, O2/O4 0.90, O1 0.60), and a type per finding. F005 was run both as `night_baseload` (resident) and `peer_outlier` (manager), because the schema has no "always-on" category.

## 3. Verified results

**What is correct:**
- All 47 of the teammate's own tests pass.
- The engine is deterministic, and geometric ≤ arithmetic holds.
- Missing kWh stay NaN, and impossible occupancy becomes "unknown", not "away".
- **The F002 repair counterfactual reproduces our validated saving exactly:** 23.35 kWh / 11.54 SEK / 0.771 kg against 23.36 / 11.54 / 0.771.
- Shifting conserves total kWh.
- The claim ladder (DETECTED → … → VERIFIED) and the "verification needs 7 days" rule match our R6.
- The **two-lens design** (Resident lens excludes equipment faults) matches our responsibility proposal.

**Baseline scores on our data** (variant A):

| Flat | Apartment (band, rank) | Use | Waste | Timing | Health | Resident (rank) | Apartment rank p5–p95 (weights) |
|---|---|---|---|---|---|---|---|
| F001 | 50.5 (E, 8) | 29.0 | 97.1 | 40.5 | 100 | 43.8 (8) | 8–8 |
| F002 | 77.2 (C, 5) | 89.0 | 88.3 | 51.2 | **73.1** | 81.8 (3) | 3–6 |
| F003 | 83.2 (B, 2) | 100 | 90.5 | 45.3 | 100 | 82.8 (2) | 2–2 |
| F004 | 77.2 (C, 6) | 84.9 | **78.3** | 51.7 | 100 | 73.8 (6) | 3–6 |
| F005 | 78.9 (C, 4) | 85.5 | **97.0** | 43.3 | 100 | 76.2 (5) | 3–6 |
| F006 | 85.7 (B, 1) | 100 | 94.7 | 49.4 | 100 | 85.5 (1) | 1–1 |
| F007 | 58.3 (D, 7) | 36.2 | 97.6 | 53.2 | 100 | 51.7 (7) | 7–7 |
| F008 | 79.9 (C, 3) | 94.8 | 93.0 | 39.7 | 100 | 77.8 (4) | 3–6 |

Under weight uncertainty, the middle four flats (F002, F004, F005, F008) cannot be told apart: each has a rank range of 3–6.

## 4. Mathematical errors (verified by execution; pinned in `tests/math/test_saish_engine.py`)

| ID | Error | Evidence on our data | Requirement |
|---|---|---|---|
| **D1** | **Benchmarks are not frozen.** The Use bench (P20 across flats) is recomputed in every evaluation, including counterfactuals ("benchmark recomputed with the same method"). | Scaling F003 shifts *other* flats' Apartment scores by 1.6–2.5 points. Reclassifying F005's anomaly changes F006's Resident Use from 100 to 93.2 and F008's from 94.8 to 85.1. | R7 (universal) |
| **D2** | **Global imputation across a regime change.** A missing hour gets the appliance's 28-day mean; for F002 that mean mixes 0.052 and 0.122 kWh/h. | Deleting 24 typical F002 readings changes the score by −0.196, against +0.189 if they were zero (opposite sign, similar size). | R3 (universal) |
| **D3** | **The Resident lens falls when F002's fridge is repaired.** The lens subtracts a constant (observed − baseline) from post-repair readings. That over-corrects once readings are already back at baseline, and differs hour by hour from `min(kWh, base)`. | Our audit: Resident 81.82 → 80.76 after the repair. The engine's own scenario: −0.08. | R4 (universal) |
| **D4** | **The peak-hour set excludes 09:00 and 20:00.** `PEAK_HOURS_LOCAL = {7, 8, 17, 18, 19}`, but the hours averaging above 0.8 SEK/kWh are {7, 8, 9, 17, 18, 19, 20}. 20:00 is 0.918, and every one of the 108 dishwasher runs starts at 20:00. | `shift_flexible_load` on A04 moves **0 kWh in every flat**. The validated opportunity is 59.22 SEK and 1.656 kg. | Data consistency |
| **D5** | **The `heater_pattern` scenario has no hour restriction.** `return_to_baseline` caps all heater hours in the window. | Removes **336.16 kWh** in F007 (projected 2,185 kWh/year). Validated: 9.19 realistic, at most 23.27. | Evidence bound |
| **D6** | **Waste and Health are shares of total kWh**, so saving energy elsewhere lowers them. | F005 night-load removal: Waste 97.0 → 92.6. F007 heater removal: Waste 97.6 → 92.4. Uniform 5 % cut in F002: Health −1.4 (reported fault kWh fixed, total smaller). | R4 (pillar) |
| **D7** | **The one-value-per-cell data contract** cannot represent energy shifted into a missing hour (known energy on an unknown baseline). | A pure dishwasher shift changes F007's Use (+0.003). | R9 (universal) |
| D8 | **Timing is a ratio over mostly inflexible loads.** | Timing falls after reductions: F002 repair −9.1, F004 −5.2 (O4), −1.9 (away scenario). | R4 (pillar) |

## 5. Unsupported or hard-coded assumptions

| Item | Value | Finding |
|---|---|---|
| Household-size exponent | √residents (elasticity 0.5) | The data show **0.33** (excluding heater) and **0.24** (including heater), from log-log fits over 8 flats (themselves uncertain) |
| Heater in Use | Included raw | F001 ranks **last** although its heating behaviour is better than F007's (0.102 vs 0.118 kWh per degree-hour; F001 switches off when empty). Use doesn't adjust for weather. |
| "Flexible" load in Timing | All non-heater above P10 | Only **19.6 %** of it is A03/A04. The rest is cooking (33–43 %), electronics, fridge and lighting. |
| Waste = above-P10 use while away | — | Counts the dishwasher (up to 6.0 kWh), washing machine and fridge cycles as avoidable. **F005's constant +95 W is invisible** (P10 includes it; Waste 97.0). Our validated dishwasher advice (start later, possibly with nobody home) would *lower* Waste. |
| Fault counted three times (Apartment lens) | — | F002's 23.36 kWh sits in Use (89.0 vs 99.4 without it), Waste (88.3 vs 91.7) and Health (73.1). Repair raises the Apartment score by 4.92, while Timing *falls* 9.1. |
| Thresholds | Waste full-penalty share 0.5; Health multiplier 2.0 | **Rankings change**: share 1.0 swaps F004/F005; multiplier 1.0 or 4.0 moves F002 up or down. P20/P10 percentiles don't change the ranking. |
| Weight uncertainty | Dirichlet concentration 20 | Arbitrary; it determines how wide the reported rank intervals are |
| Annualisation | ×365/28, heater ×182/28, ±30 % | Extrapolates 4 October weeks outside the observed weather (1.8–13.8 °C). It is labelled "projection", but conflicts with our earlier no-annualisation rule. **This is a policy decision for you.** |
| Anomaly inputs | `confidence`, `excess_kwh`, `type` from upstream | Health and the claim level depend entirely on the detector's numbers. The type taxonomy forces "manager" or "resident" for an always-on load (F005: Apartment 78.9 or 70.2; Resident 76.2 or 83.6). |

## 6. Comparison with the validated opportunity analysis

| Opportunity | Validated (28 days, spot) | Engine counterfactual | Assessment |
|---|---|---|---|
| F002 fridge step | 23.36 kWh / 11.54 SEK / 0.771 kg | 23.35 / 11.54 / 0.771 | **Agrees** |
| F004 daytime electronics | 14.30 (central); 5.72 when unoccupied | `away_usage`: 5.72; `reduce_away_usage` (f = 1): 16.04 (includes fridge, washer and dishwasher cycles) | Misses the occupied part of the 09–17 block; the away scenario over-includes appliance cycles |
| F005 always-on 95 W | 62.79 full; 31.40 at θ = 0.5 | `night_baseload`: 15.58 (00–06 only); Waste pillar blind (97.0) | Under-detected |
| F007 heating while empty | 9.19 realistic; ≤ 23.27 | `heater_pattern`: 336.16 (all heater use) | **14–37× overstated** (D5) |
| Dishwasher timing | 59.22 SEK, 1.656 kg, 0 kWh | 0 moved (D4) | **Missed entirely** |

## 7. Integration requirements

1. **Data contract mapping:** the engine reads `data/processed/clean_readings.csv` (`kwh`) and `anomalies.json`. We produce `readings_clean.csv` (`energy_kwh`, `energy_status`) and `opportunities.json`. A small exporter is needed. Our `saish_engine.py` already does the mapping in memory.
2. **Anomaly translation:** numeric confidence values must be agreed; ours are assumptions. The type set needs an "always-on / base load" type, and a "daytime scheduled" type for F004.
3. **Missing + shift:** the readings contract needs an "added energy" channel, or shifts into missing hours must be rejected and reported (D7).
4. **Frozen references:** the engine needs a `references` object (bench, P10 bases, imputations) computed once and passed to counterfactual evaluations (D1, D2).
5. **Spot-only labelling** already matches decision 3. The live SE3 price service and LLM tips are outside the mathematical scope.

## 8. Recommended changes (for your decision; not implemented, teammate's code untouched)

| Priority | Change | Fixes |
|---|---|---|
| 1 | Peak hours from the data: {7, 8, 9, 17, 18, 19, 20}, or price-ranked hours computed from the prices | D4; dishwasher opportunity restored |
| 2 | Restrict `heater_pattern` counterfactuals to unoccupied hours (as `away_usage` already does), bounded by the validated evidence | D5 |
| 3 | Freeze the Use bench, P10 bases and imputations at baseline; reuse them in counterfactuals | D1, D2 |
| 4 | Impute locally (same day or same regime), or use a coverage-adjusted rate per observed hour | D2 |
| 5 | Remove the F002 fault from Use and Waste in the Apartment lens, or from Health; count it once | Triple counting |
| 6 | Make Waste and Health absolute (kWh per equivalent resident) rather than shares of the flat total; restrict Timing's "flex" to A03/A04 | D6, D8 |
| 7 | Resident lens: after a repair, stop subtracting the constant excess (check repair state, or use the same `min(kWh, base)` rule) | D3 |
| 8 | Size exponent and heater: replace √n with a declared, sensitivity-tested choice; weather-normalise heating in Use | §5 |
| 9 | Publish threshold sensitivity (Waste share, Health multiplier) next to the Dirichlet weight sensitivity | §5 |

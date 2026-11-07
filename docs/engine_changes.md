# Engine changes: original (`saish@ddc02ce`) → improved (`mina`)

The original engine was copied from `origin/saish` into `backend/` and developed further on `mina`. Saish's branch and `main` are unchanged. The audit that motivated the changes is in [math/saish_engine_audit.md](math/saish_engine_audit.md). The resulting method is in [score_method.md](score_method.md). Numbers are from `reports/engine_comparison.md`, which `python analysis/score_audit/compare_engines.py` regenerates.

## 1. Defects fixed (each pinned by a test in `backend/tests/test_regressions.py`)

| ID | Original | Improved | Test |
|---|---|---|---|
| D1 | Use benchmark re-estimated in every evaluation, so one flat's change moved other flats' scores | Benchmarks, K, K_T, peak hours, imputations and anomaly references are fitted once (`core/references.py`) and reused in every counterfactual | `test_D1_frozen_references_peer_invariance` |
| D2 | A missing hour got the 28-day channel mean, which mixes regimes for F002 | Local imputation: same channel, same day; else ±1 day; else channel mean. It is frozen, so deleting readings is neither "zero use" nor a mix of regimes | `test_D2_…` |
| D3 | The resident lens subtracted a constant fault excess, so F002's repair lowered it (−0.08) | Single partition: each kWh is explained, R or F, and is computed on the trajectory. F002 repair: apartment +1.74, resident +0.00 | `test_D3_…` (every intervention, both lenses) |
| D4 | Peak hours hard-coded {7, 8, 17, 18, 19}, so the dishwasher shift moved 0 kWh | Peak hours = local hours with mean spot above the time-average: {7, 8, 9, 17, 18, 19, 20}. Dishwasher fleet value 59.22 SEK / 1.656 kg, matching the validated result | `test_D4_…` |
| D5 | The heater counterfactual removed all heater use in the window (336.16 kWh in F007) | Removes heater-like use only in absences ≥ 2 h: 9.19 kWh, matching the validated result | `test_D5_…` |
| D6 | Waste and Health were shares of total kWh, so saving elsewhere lowered them | Ratio form K / (K + excess / eq / 28) on absolute excess: non-increasing in every hourly kWh | `test_D6_…` |
| D7 | One value per cell could not represent energy shifted into a missing hour | Trajectory = observed base + delta layer. A shift into a missing hour is kept in the delta and conserved | `test_D7_…` |
| D8 | Timing was a ratio over mostly inflexible load | Timing = K_T / (K_T + flexible kWh in peak hours); flexible = A03/A04 only. Reductions never lower it | covered by `test_D3` / `test_D6` |
| — | α = 0.001 with 999 permutations is unattainable and silently removed every detection | `check_test_resolution` refuses α ≤ 1/(B+1) | `test_detection_alpha_must_be_attainable` |

The independent invariant suite (`analysis/score_audit/audit_score.py`) finds 0/33 universal failures in both lenses of the improved engine, against 3/33 for the original.

## 2. Broader methodological changes

| Area | Original | Improved | Why |
|---|---|---|---|
| Anomalies | Read from an upstream `anomalies.json`, with a numeric `confidence` | Detected by the engine (`core/detect.py`), each with a stated statistical criterion and statistics; `confidence = null` | A probability had no basis; status should follow a criterion that can be checked |
| PLAUSIBLE | confidence ≥ 0.7 and ≥ 3 days | The detector's criterion holds (e.g. permutation p < α; above every peer in every week) and the pattern lasts ≥ 3 days | No unfounded threshold on an invented number |
| Step change | Given | Max one-sided Welch t over day splits, day-permutation p (999, seeded), days with nobody home excluded | Exact level of the test under exchangeable days; no distributional assumption on hours |
| Always-on load | Night base load 00–06 only (15.58 kWh in F005) | P5 floor above every other flat's floor in every week; excess capped at own − peer-median floor (62.79 kWh) | The +95 W is present at all hours |
| Fixed-hour block | `away_usage` with appliance cycles included | Hour-of-day above every peer in every week, and persists with nobody home | Captures F004's 09–17 block without counting dishwasher or fridge cycles |
| Counting | The F002 fault appeared in Use, Waste and Health | Partition X = explained + R + F; each kWh counts once | No triple counting |
| Waste threshold | Full-penalty share 0.5 | No threshold: the ratio is 50 when excess equals a typical flat's intensity K | The threshold changed the ranking |
| Health multiplier | 2.0 | Same ratio form as Waste | The multiplier changed the ranking |
| Heater in the resident lens | Raw heater use in Use | Excluded from resident Use (weather-driven); heating with nobody home stays in Waste | F001 was ranked last for weather |
| Savings | One number per scenario | Ladder (observed, expected baseline, unexplained excess, avoidable, counterfactual), tariff valuation, bootstrap CI and scenario range kept separate, before/after scores, overlap | Requirement 4 of the task |
| Combination | Scenarios evaluated separately | Operators combined in a fixed order (repair → reduction → shift); proportional cuts compound | Combined savings are never double-counted |
| Window | 28 days for everything | 28 days, except a step change, which counts from its split (F002: 14 days) | A saving cannot exist before the fault |
| Annual projection | ×365/28 for all types (heater ×182/28), ±30 % | Only persistent fault, base-load and fixed-block patterns; mean daily × 365 with a day-bootstrap p5–p95. Heating and timing are not extrapolated | October weather and behaviour don't extrapolate; ±30 % had no basis |
| Money | Spot SEK | Spot SEK by tariff (hourly, monthly average, fixed, included in rent, unknown); a shift is worth 0 SEK on non-hourly tariffs | Decision 3: spot only and distinguished from bills |
| Wording | "possible fault" for every PLAUSIBLE | "possible fault" only for manager/equipment; behaviour is "consistent pattern"; heater is "needs confirmation" | A timing habit is not a fault |
| LLM tips | Server-side automatic model fallback (beta) | Removed; template fallback on any error | Decision 5 |
| Data source | `clean_readings.csv` | `analytical_table.csv` (validated pipeline) first, then the old contract, then mock | One validated dataset |
| Accounting | Separate in `analysis/mathcore.py` and the backend | One implementation (`backend/app/core/hourly.py`); `mathcore.py` is a thin shim | No competing implementations |

Removed constants: `WASTE_FULL_PENALTY_SHARE`, `HEALTH_FAULT_MULTIPLIER`, `BASELOAD_PERCENTILE`, `PEAK_HOURS_LOCAL` (now `PEAK_HOURS_FALLBACK` for data without prices) and `PROJECTION_BAND`.

## 3. Effect on the results

| Flat | Original apartment | Improved apartment | Original resident | Improved resident |
|---|---:|---:|---:|---:|
| F001 | 50.5 | 49.6 | 43.8 | 74.1 |
| F002 | 77.2 | 82.7 | 81.8 | 82.0 |
| F003 | 83.2 | 88.4 | 82.8 | 88.4 |
| F004 | 77.2 | 81.1 | 73.8 | 77.6 |
| F005 | 78.9 | 82.6 | 76.2 | 81.5 |
| F006 | 85.7 | 88.5 | 85.5 | 86.0 |
| F007 | 58.3 | 58.2 | 51.8 | 89.8 |
| F008 | 79.9 | 80.1 | 77.8 | 77.2 |

- Most apartment scores rise because the fault is no longer counted three times and the Waste/Health thresholds are gone. This is a consequence of correct counting, not a goal. F007 and F001 stay at the bottom.
- The resident lens rises most for F007 and F001: their high use is weather-driven heating, which this lens excludes. F007's heating with nobody home (9.19 kWh) still counts in Waste.
- Validated savings are reproduced exactly: F002 23.36 kWh / 11.54 SEK / 0.771 kg; F004 14.30 / 5.29 / 0.492; F005 62.79 (31.40 at θ = 0.5); F007 9.19 / 5.65 / 0.375; dishwasher fleet 59.22 SEK / 1.656 kg.

## 4. Remaining assumptions and limitations

**Statistical:**
- 28 days and 8 flats. Peer comparisons ("above every other flat in every week") have little power and treat the 7 other flats as the reference population.
- The permutation test assumes exchangeable days under the null. Weekly patterns and weather trends weaken this; the vacant-day exclusion only partly controls it.
- The bootstrap CI resamples days inside the pattern's window (14 days for F002), so the intervals are wide and only approximate.
- Detection is tested once per channel, with no multiple-testing correction across 8 flats × 3 continuous channels. At α = 0.01, about 0.24 false step detections are expected under the null.

**Physical and modelling:**
- Channel types (fridge, heater, dishwasher…) are assumptions, because the channels are unlabelled.
- Occupancy is a simulated sensor estimate.
- Heater rebound is 0 in the central case (scenario range 0–0.25).
- A step change is assumed to be repairable to its pre-step level.
- Peak hours are derived from the 4 October weeks of spot prices.

**Policy (these change the middle of the ranking; the top and bottom are stable):**
- Equivalence exponent 0.5: the data suggest 0.24–0.33.
- Use benchmark P20.
- Lens weights.
- Dirichlet concentration 20 for the weight sensitivity.

**Money:** spot energy only. This is not a bill saving: VAT, network fee, energy tax, markup and fixed fees are excluded.

**Carbon:** the synthetic hourly average factor, not a marginal factor.

**Data:** the dataset is synthetic. The numbers demonstrate the method; they are not evidence of real-world savings.

**Verification:** simulated post-repair data is always flagged `simulated: true`.

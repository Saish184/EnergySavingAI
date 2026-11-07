# Decision report: mathematical validation and implementation readiness

**For:** the team mathematician. **Branch:** `mina` (local commits only; nothing pushed or merged; no teammate code modified).
**Evidence:**
- `python -m pytest`: 35 pass, 1 skipped (the teammate model, unavailable).
- `analysis/score_audit/audit_score.py` → `reports/score_audit.{json,md}`.
- `analysis/math_experiments.py` → `reports/math_experiments.json`.
- Previous: `reports/opportunities.json`, `reports/consistency_audit.md`, `reports/math_review_numbers.json`.

> **Update:** the implementation has since been found on branch `saish` (commit `ddc02ce`, pushed after the inspection below). It was audited on our validated data in [`saish_engine_audit.md`](saish_engine_audit.md). Its 7 confirmed defects (D1–D7) are pinned in `tests/math/test_saish_engine.py`. The section below is kept as the historical record of that earlier inspection.

## 0. Status of the teammate's four-pillar model

**Unavailable. Nothing was verified.**
- **Branches:** the remote has `main`, `mina`, `Hugo`, `Pouyan` and `saish`.
  - `Pouyan` and `saish` are identical to `main`.
  - `Hugo` adds only a static frontend mock-up with placeholder numbers and no score.
- **Search:** GitHub code search for "geometric", "pillar", "Health", "weight" and "score" returns 0 results, and there are no pull requests.

Everything said here about Use 40 % / Waste 25 % / Timing 20 % / Health 15 % with weighted geometric aggregation is a **methodology review**, not code verification. The audit harness is ready to verify the code the moment `score.py` exists (§6).

---

## 1. Validated results (reproduced and tested)

| Result | Evidence |
|---|---|
| All five validated opportunities reproduce exactly through an independent hourly-trajectory implementation | O1 9.19 kWh / 5.65 SEK / 0.375 kg; O2 31.40 / 14.73 / 1.169; O3 23.36 / 11.54 / 0.771 (14-day window); O4 14.30 / 5.29 / 0.492; O5 59.23 SEK / 1.657 kg fleet, per flat as recorded |
| kWh, SEK and CO₂e are dimensionally and arithmetically consistent | R1 tests (cell-by-cell recomputation) |
| Load shifts conserve energy per channel and in total; SEK = Σ k·Δp; worth 0 SEK on non-hourly tariffs | R9 tests, all 8 flats |
| The five records never overlap; combining them within a flat is exact | X4: F002 23.36 kWh / 18.02 SEK / 0.983 kg combined = sum; same for F004, F005, F007 |
| Overlap is detected and not double-counted | O1 + illustrative S1b: 2.545 kWh overlap removed by sequential combination |
| E ≥ A ≥ S holds for the defined ladders | F007: 23.27 ≥ 9.19 ≥ 6.89 (25 % rebound) |
| Statuses never claim confirmed waste or verified savings | R6 tests on `opportunities.json` |

## 2. Mathematical errors and inconsistencies found

All of these are in **candidate or prototype approaches**. None of the five validated savings figures is wrong.

| # | Finding | Severity | Status |
|---|---|---|---|
| E1 | **A plain sum over observed hours rewards missing data.** Deleting 24 typical F002 fridge readings raises a sum-based energy score exactly as much as setting them to 0 (+0.353 points), so missing data looks like saving. Also affects the illustrative pillars in `math_review.py`. | High for any score | Requirement R3 added; harness flags it |
| E2 | **Global imputation fails at regime changes.** Filling missing hours with a channel's 28-day mean mixes F002's pre-step (0.052) and post-step (0.122) levels, so deleting typical pre-step readings *worsens* the score (−0.26). | Medium | Local (same-day) imputation is required (R3.4) |
| E3 | **Imputation must be frozen at baseline.** With local imputation recomputed after an intervention, a pure dishwasher shift changed the energy pillar in F003 and F007. The run's origin hour dropped to 0, which changed the same-day mean used to fill a missing destination hour. | Medium | R3.5 / R7 |
| E4 | **Shifting into a missing hour needs a delta layer.** My first trajectory implementation rejected 3 dishwasher runs (F003, F007) moving into hours with missing A04 readings, understating the fleet total by 1.843 SEK and 0.057 kg. `opportunities.py` valued them correctly. The fix keeps the base (with gaps) and the intervention delta separately; score models receive moved energy as "extra" on an unknown base. | Medium | Fixed in `mathcore.py`; R9 test |
| E5 | **Whole-flat ratio timing pillars aren't monotone.** A pure reduction lowers the score (F004 + O4: 42.3 → 23.6 on the pillar; F002 + O3: 8.6 → 0). In an aggregate, a monotone energy pillar cannot compensate (arithmetic composite 46.9 → 42.3). | High if Timing is defined this way | R4; the harness detects it |
| E6 | **Un-frozen peer normalisation violates before/after comparisons.** Another flat's change moves your score. | High if used | R7; the harness detects it |
| E7 | **The frontend what-if** (`origin/Hugo`, placeholder) moves *all* load, including inflexible loads, and values it with averaged prices in UTC hours. | Medium (demo credibility) | Documented in `integration_readiness.md` §1; not modified |

## 3. Unsupported assumptions (methodology review of the four-pillar model)

| Assumption | Why it isn't supported by our data |
|---|---|
| **Weights 40/25/20/15** | No data or stakeholder basis. Under geometric aggregation they are elasticities: a 1 % change in Use moves the score 0.4 %. With stand-in pillars, ±10 % weight changes altered the ranking in 1 of 8 perturbations. |
| **Weighted geometric aggregation without a declared zero rule** | A zero pillar gives a zero score. With stand-in pillars, F005 and F008 score exactly 0. A floor is a new arbitrary constant: floor 10 vs floor 1 multiplies affected scores by 10^0.15 ≈ 1.41. |
| **Heater use as "Waste"** | Heater kWh is weather-driven (0.12 kWh/h per °C below 12 °C, identical in both flats; +22 % per °C colder). Only **unoccupied** heating is evidenced: 9.19 kWh realistic, 23.27 at most, relying on a simulated occupancy sensor. Classifying all or night heater use as waste contradicts the validated analysis. |
| **Equipment health from hourly data** | Only F002's step is evidenced (×2.36, Welch t ≈ 90). The cause is unknown and the student can't repair it. If Health penalises it while Waste and Use also count the same 23.36 kWh, it is counted three times. |
| **Timing over all loads** | Only 8.3 % of kWh is plausibly flexible (A03, A04). Night heating makes F001 and F007 look best on timing. Price and carbon timing correlate (ρ = 0.79). |
| **A single occupancy or size normaliser** | Five reasonable normalisers disagree. The worst flat is F005 (per flat, per equivalent resident) or F004 (per resident, per m², per person-hour at home). Kendall τ ranges from −0.21 to 0.93. |
| **Peer benchmarking with n = 8** | The OLS household-size scale (95.9 + 20.4·n kWh) is unstable: leaving out one flat moves the slope anywhere from 4.8 to 24.6. Min–max anchors are degenerate under ties (7 flats share 37 W always-on). |

## 4. Configurable design choices (decide and declare)

- Aggregation (arithmetic or geometric) and the zero floor.
- Weights, and the published sensitivity of rankings to them.
- Normaliser for Use: per flat, per resident, per m², per equivalent resident, per person-hour.
- Heating treatment: exclude, weather-normalise (kWh per heating degree-hour), or a separate pillar.
- Definition of "flexible load" (default: A03/A04, confirmable by the student).
- Whether Health contains equipment faults, or whether faults go to manager alerts only.
- Estimand for windows with missing hours: observed-hours vs coverage-adjusted.
- Waste reference per opportunity: pre-step mean, peer median, or "should be off".

## 5. Data limitations

- 8 synthetic flats, 28 autumn days, outdoor 1.8–13.8 °C. No seasonal coverage and no real-world validity.
- Occupancy is a simulated estimate; appliance identity is inferred.
- No post-intervention data, so nothing can be verified.
- Carbon factors are averages, not marginal. Spot prices are synthetic, and no tariff data exists.
- 592 missing energy cells (1.57 %); 8 unpriced hours.

## 6. Auditing `score.py` when it arrives (no code invented)

1. `export SCORE_PY=/path/to/score.py`. Do not edit their file.
2. Write `wrap()` in `analysis/score_audit/teammate_adapter.py`, about 10–20 lines. It calls their function on `interface.flats_to_table(flats)` and maps the output to `{"score", "pillars": {"Use", "Waste", "Timing", "Health"}}`. Declare `energy_pillars` (likely `("Use",)`) and the weights.
3. Run `python analysis/score_audit/audit_score.py --teammate` (reproduces all 8 scores and runs every check) and `python -m pytest`. The skipped test then becomes a real test.
4. Read the failures by class: **universal** = mathematical error; **policy** = an inconsistency with a declared choice.

## 7. Minimum changes for a working hackathon demo (priority order)

1. **Show savings from the validated engine only.** Use the `calculatorResult` and `savingsRecord` numbers and the mathcore accounting semantics (delta layer, fixed combination order). This is already reproducible.
2. **Gate the composite score.** Display it only if `audit_score.py --teammate` passes all universal checks. Otherwise show pillars separately, labelled "provisional", with no composite.
3. **Freeze references and imputations** at the baseline in the score implementation (R7, R3.5).
4. **Never use plain observed-hour sums for cross-flat comparison.** Use coverage-adjusted totals with local, frozen imputation (R3).
5. **Heating:** don't count weather-driven heater use as Waste. Count only unoccupied heating, and weather-normalise any heating in Use (kWh per heating degree-hour).
6. **Health:** move suspected equipment faults (F002) to a manager **alert** rather than a student score penalty, or at minimum make sure the same kWh are not also counted in Waste and Use.
7. **Geometric aggregation:** declare the floor, or switch to arithmetic for the demo, and publish a ±10 % weight-sensitivity line.
8. **Contracts:** add `flatSummary`, the `responsibility` field and `scoreResult` (draft in `docs/design/proposed_additions.schema.json`) only after your approval. The existing contracts stay unchanged.
9. **Frontend wiring:** feed the what-if from per-flat O5 results (dishwasher runs only, hourly prices, local-time labels) instead of shifting all load.

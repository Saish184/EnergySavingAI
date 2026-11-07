# Mathematical requirements specification: quantitative engine and scores

**Owner:** team mathematician. **Status:** v1 for review. **Branch:** `mina`.
**Tests:** `python -m pytest`. Requirement IDs appear in test names and in the audit results. **Reference library:** `analysis/mathcore.py`, which contains no score formula.

Each requirement is classified as:
- **U (universal):** mathematically necessary for the stated property. Any engine or score that claims the property must pass.
- **P (policy):** a product or design choice. Tests demonstrate its consequences but don't impose one answer.
- **C (contract):** concerns the machine-readable outputs.

## Notation

- **Data:** flat f; channel c ∈ {A01…A07}; UTC hour h ∈ H = {0, …, 671}.
  - Observed energy x_{f,c,h} ∈ ℝ≥0 ∪ {⊥}. ⊥ means *missing*, never 0. O_f is the set of observed (c, h).
  - Spot price p_h [SEK/kWh] ∪ {⊥}; carbon factor g_h [gCO₂e/kWh]; time-average p̄ = mean_h p_h.
- **Intervention:** an operator I acting on a **trajectory** T = (x, δ). δ is a delta layer on all cells, including missing ones.
  - Counterfactual energy in a cell: x + δ where x is observed; "⊥ + δ" where it is missing (known δ on an unknown base).
- **Window:** a scenario's window W ⊆ H is always stated explicitly.

---

## R1 Dimensional consistency (U)

Every reported quantity has a unit, and every formula is dimensionally homogeneous:
- E [kWh] = Σ x.
- C [SEK] = Σ x·p over priced cells.
- M [kgCO₂e] = Σ x·g / 1000.
- The time-average proxy = E·p̄.

Ratios carry their numerator and denominator units (e.g. kWh per heating degree-hour). A score is dimensionless; each pillar must document the raw indicator and unit it maps.
*Tests:* `test_R1_units_*`, plus the validated-case reproductions.

## R2 Separation of quantity types (U)

| Symbol | Quantity | Class |
|---|---|---|
| O | Observed consumption Σ_{O∩W} x | measured |
| B | Expected baseline (reference r_h: pre-step mean, peer median, 0, or a model) | inferred (the reference is a modelling choice) |
| E | Unexplained excess Σ max(x − r, 0) | measured relative to the stated reference |
| A | Avoidable consumption Σ θ_h · max(x − r, 0), with θ ∈ [0, 1] | hypothetical |
| S | Simulated counterfactual saving O − O(I(T)), including adoption and rebound | simulated |
| V | Verified saving: requires post-intervention observations and a pre-registered method | measured (v1: always ⊥) |

Required ordering when the definitions nest: **E ≥ A ≥ S ≥ 0** (θ ≤ 1, adoption ≤ 1, rebound ≥ 0).
*Tests:* `test_R2_*` (F007: 23.27 ≥ 9.19 ≥ 6.89; F005: θ = 1 ≥ θ = 0.5).

## R3 Missing observations (U)

1. ⊥ is never replaced by 0, and reductions never act on ⊥ cells.
2. Totals over a window report observed cells and window hours separately. An estimand must say whether it is an observed-hours total or a window total.
3. **Deletion neutrality:** for any score claiming to measure energy performance, deleting typical readings must not change the score as if they had become zero: |ΔS_delete| < ½ |ΔS_zero|. A plain sum over observed hours fails this, because missing data then looks like saving.
4. **Local imputation:** if missing cells are imputed, the imputation is local in time (e.g. same channel, same day). A channel-wide mean is invalid across regime changes such as F002's step.
5. **Frozen imputation:** imputations for cells missing at baseline are frozen with the references (R7), so an intervention cannot change the assumed value of an unobserved hour.

*Tests:* `test_R3_*`, harness check "deleting typical readings …", fixtures `EnergyTotalFixture` (fails) and `CoverageAdjustedEnergyFixture` (passes).

## R4 Monotonicity of energy-performance scores (U for the composite energy-performance score; P per pillar)

For any pure reduction (x' ≤ x elementwise, other conditions fixed: weather, occupancy, prices, residents, references): S(x') ≥ S(x).
- The **composite** must satisfy this.
- Whether **every pillar** must is a policy choice. A timing pillar defined as a ratio over all loads violates it (F004 + O4; F002 + O3), and a monotone pillar cannot compensate for it in an arithmetic or geometric aggregate.

*Tests:* harness check "score non-decreasing under pure reduction". Cases: O1, O2, O3, O4, and a uniform 5 % cut in all 8 flats.

## R5 No double-counting (U)

1. Every intervention is an operator on the flat's hourly trajectory. All totals (flat, portfolio, "if you do everything", projected scores) are computed from **one combined trajectory**, never as a sum of separate savings.
2. Fixed stage order: repairs → behavioural reductions → shifts (stable within a stage).
3. Proportional reductions on shared cells combine multiplicatively, 1 − Π(1 − φ_i), and commute.
4. The counterfactual is never negative; the saving never exceeds the observed energy.
5. Alternatives of one opportunity are mutually exclusive.
6. The overlap (sum of individual savings minus the combined saving) is reported. It is 0 for the five validated records and 2.54 kWh for O1 + the illustrative S1b.

*Tests:* `test_R5_*`.

## R6 No unsupported claims (U / C)

An anomaly status is `measured`; waste is `unconfirmed` until the student confirms; verification is `not_verified` until post-period data exist. Appliance identity is `inferred`. The engine never upgrades these statuses. Faults are "suspected" until confirmed by the provider.
*Tests:* `test_R6_*`.

## R7 Fixed references in before/after comparisons (U)

Everything that depends on peers or the baseline is computed once on the baseline and frozen:
- normalisation anchors;
- peer statistics;
- equivalence-scale parameters;
- imputations;
- thresholds.

Under frozen references, a flat's score must not change when another flat's data change.
*Tests:* harness check "peer invariance under frozen references" (fixture `PeerRelativeUnfrozenFixture` fails).

## R8 Per-flat and per-resident figures (U)

All measurements and savings are per flat. "Average per resident" = flat value ÷ residents. It is always labelled as an average, never as an individual measurement, and it multiplies back to the flat total. Individual attribution needs self-reported ownership (a policy decision).
*Tests:* `test_R8_*`.

## R9 Load shifting (U)

A shift moves k = share × (x + δ) from h₀ to h₁ on the same channel:
- **Energy:** Σδ = 0 per channel and in total.
- **Cost:** ΔC = Σ k (p_{h₀} − p_{h₁}) on an hourly tariff; ΔC = 0 on time-average, fixed-price or rent-included tariffs.
- **Carbon:** ΔM = Σ k (g_{h₀} − g_{h₁}) / 1000.
- **Missing destination:** moving into a destination with a missing reading is allowed. The known energy is carried in δ ("extra") and is neither lost nor treated as the cell's full reading.
- **Scores:** energy-only pillars must be unchanged by a pure shift.

*Tests:* `test_R9_*`; harness checks "shift conserves total kWh" and "energy pillars unchanged by pure shift".

## R10 Explicit periods (U / C)

Every number carries its UTC window, window hours and observed hours used. Local time is used only for labels and hour-of-day patterns: local 1–28 Oct is 673 elapsed hours, not 672.

## R11 Determinism (U)

The same inputs produce identical outputs; any randomness uses a fixed, documented seed.

## R12 Declared bounds and weights (U if declared)

If a score promises [0, 100], every output is inside it. Weights are positive and sum to 1.

## R13 Aggregation and zero pillars (P)

**Weighted geometric mean:**
- A zero pillar gives a zero score.
- The elasticity of the score to a pillar equals that pillar's weight.
- Rankings don't change when a pillar is multiplied by a constant.
- A floor ε is an extra arbitrary constant: changing it from 1 to 10 multiplies affected scores by 10^w.

**Arithmetic mean:** fully compensatory, and the scale of a pillar acts as a hidden weight (rankings can flip when one pillar is rescaled).

The method and any floor must be declared and justified.
*Tests:* `test_UNIVERSAL_*geometric*` (identities), `test_POLICY_floor_*`.

## R14 Uncertainty separation (U)

Sampling (statistical) uncertainty and intervention-scenario uncertainty are reported in separate fields and never merged without explicit, approved priors. The tariff is a condition, not a probability.
*Tests:* `test_R14_*`.

## R15 Weather (U for any metric claimed to be weather-normalised; P whether Use is normalised)

With behaviour fixed, a weather-normalised heating metric (e.g. kWh per heating degree-hour, base 12 °C from the validated curve) must be invariant to outdoor temperature. Raw heater kWh changes about 22 % per °C. Observed: F001 0.1019 vs F007 0.1175 kWh per degree-hour. The difference is behaviour: F001 switches off when unoccupied.
*Tests:* `test_UNIVERSAL_weather_*`.

## R16 Occupancy and size normalisation (P, must be declared)

Per flat, per resident, per m², per equivalent resident and per person-hour at home produce different rankings. The worst flat is F005 under some and F004 under others; Kendall τ ranges from −0.21 to 0.93. The chosen normaliser and its sensitivity must be published.
*Tests:* `test_POLICY_size_normalisation_*`; `reports/math_experiments.json` X1.

## R17 Appliance characteristics (C)

Appliance identity is inferred and must not be a precondition for any score or saving. Appliance-specific rules (e.g. "flexible load" = A03/A04) are declared policy inputs and must be confirmable by the student.

---

## Universal invariants vs product-policy decisions

| Universal (must pass) | Policy (decide and declare) |
|---|---|
| R1, R2, R3, R4 (composite), R5, R6, R7, R8, R9, R10, R11, R12 (if declared), R14, R15 (for normalised metrics) | R4 per pillar; R13 aggregation and floor; R15 whether to normalise; R16 normaliser; weights; thresholds; which loads are "flexible"; whether Health includes equipment faults |

## Audit interface for the teammate's score

`analysis/score_audit/`:
- `interface.py` defines the `ScoreModel` protocol.
- `teammate_adapter.py` locates `score.py` (or `$SCORE_PY`) and calls a reviewer-written `wrap()`.
- `audit_score.py --teammate` reproduces scores for all 8 flats and runs every check. Results go to `reports/score_audit.{json,md}`.

**The teammate's code is not in the repository. No verification of it has been performed**, and the pytest case for it is *skipped* until it exists.

# Mathematical review dossier: savings engine and sustainability score

**For:** the team mathematician (reviewer and approver of the quantitative engine).
**Status:** documentation for review only. No engine changes are approved, no product is implemented, and the agreed JSON contracts (`docs/design/contracts.schema.json`, `reports/opportunities.json` v1.0) are unchanged.
**Reproduce every number:** `python analysis/math_review.py` writes `reports/math_review_numbers.json`. The script is deterministic.
**Branch:** `mina`. Not pushed or merged.

## 0. Scope, roles and recorded decisions

**Roles:**
- **Mathematician:** owns all definitions below, approves engine changes, and decides the register in §9.
- **Engine implementer (teammate):** builds the initial engine against the agreed contracts.
- **Chatbot and frontend teammates:** out of scope here. Nothing below redesigns their components.

**Product decisions recorded from review round 2:**

| # | Decision |
|---|---|
| 1 | The demo uses a **flat selector**. |
| 2 | **English first**; Swedish only if time allows. |
| 3 | **Spot-price calculations only** for the initial demo. They are always labelled as the synthetic spot-energy component and never presented as a student's bill. The contract keeps the other tariff types (`tariffType` enum) for later. |
| 4 | **Parallel team development.** No assumption that one person builds everything. |
| 5 | **No automatic model fallback after refusals.** During API outages, show a **predefined, safe tips fallback**: static, reviewed text with no flat-specific numbers unless they come from the engine. |

### Notation used throughout

- **f**: flat. **c**: channel (A01–A07). **h**: UTC hour index, 0–671.
- **x_{f,c,h}**: observed kWh. **Missing observations are excluded, never treated as 0.** O_{f,c} is the set of observed hours.
- **p_h**: synthetic spot price (SEK/kWh, excl. VAT). p̄ = 0.4777 SEK/kWh, the mean over the 672 hours.
- **g_h**: synthetic average carbon factor (gCO₂e/kWh). ḡ = 37.30.
- **W**: a scenario's window. Every scenario now carries an explicit `period` block.
- **n_f**: residents of flat f. **o_{f,h}**: estimated occupants home (simulated sensor).

---

## 1. Sustainability score: four pillars, normalisation and weights

### 1.1 Status

**No sustainability score is defined anywhere in the project.** I checked:
- every file on `mina`;
- `origin/main`;
- the teammate branches `origin/Hugo` and `origin/Pouyan`. Both are currently identical to `main` (the dataset commit only).

Every earlier deliverable explicitly deferred the score. There are therefore **no existing pillar definitions, normalisations or weights to document**. This section supplies:
- the mathematical requirements a score should meet;
- an **illustrative candidate** (computed, to expose the pitfalls);
- the open decisions.

If a teammate already has pillar definitions, they should replace §1.3, and the same tests (§1.4) should be applied to them.

### 1.2 Requirements a score should satisfy (proposed axioms for review)

| ID | Property | Formal statement |
|---|---|---|
| A1 | Monotone in genuine savings | If x̃ ≤ x elementwise (a pure reduction), then S(x̃) ≥ S(x). |
| A2 | Projection consistency | The projected score for any set of interventions is S(x̃), where x̃ is the **combined** hourly counterfactual vector, never S(x) + Σ ΔS_i. |
| A3 | Peer invariance | A flat's projected score changes only through its own x̃. Normalisation references are frozen; they are not recomputed with the intervention. |
| A4 | Size fairness | Pillars that scale with household size are adjusted for n_f (§8). |
| A5 | No hidden double weight | Pillars are not near-duplicates. Rank correlation between pillars is reported, and highly collinear pillars are merged. |
| A6 | Bounded and interpretable | Each pillar is in [0, 100]; the composite is a convex combination; the weights are published. |
| A7 | Missing-data neutral | Missing hours are excluded identically from x and x̃. |

### 1.3 Illustrative candidate (not approved), exact definitions

**Indicators** (lower is better), each over the 28-day window and the observed hours:

- **I1, consumption index:** I1_f = Σ_{c ≠ A07} Σ_h x / (a + b·n_f), with a = 95.9 kWh and b = 20.4 kWh per resident. This is the OLS fit of non-heater kWh on resident count across the 8 flats (§8). Supplementary heating is **excluded**.
- **I2, always-on power:** I2_f = 1000 × Q_{0.05}( Σ_{c ∉ {A01, A07}} x_{f,c,h} ) in W. Q_{0.05} is the 5th percentile over hours of the controllable channels.
- **I3, price-timing ratio:** I3_f = (Σ x p / Σ x) / p̄, over all channels and priced hours.
- **I4, carbon-timing ratio:** I4_f = (Σ x g / Σ x) / ḡ, over all channels.

**Normalisation:** P_k = 100 · clip((U_k − I_k) / (U_k − L_k), 0, 1). L_k and U_k are the baseline minimum and maximum across the 8 flats, **frozen**:

| Indicator | L_k | U_k |
|---|---|---|
| I1 | 0.807 | 1.178 |
| I2 | 37 W | 132 W |
| I3 | 1.025 | 1.228 |
| I4 | 0.977 | 1.101 |

**Weights:** w = (0.25, 0.25, 0.25, 0.25) ("equal"), or the alternative (0.40, 0.30, 0.15, 0.15) ("energy-heavy"). **Score:** S_f = Σ_k w_k P_k.

### 1.4 What the candidate reveals (all values from `math_review_numbers.json`)

| Finding | Evidence | Violates |
|---|---|---|
| **The two heater flats score best.** F007 is the largest consumer (491 kWh) and scores 91.7; F001 (435 kWh) scores 83.8. | I1 excludes A07, while I3/I4 include it. The heaters run at night (cheap, low-carbon), which improves the timing ratios. | Face validity; consistency across pillars |
| **I2 is degenerate.** 7 of 8 flats have exactly 37 W, so they all get P = 100 and F005 gets 0. | Min–max on 8 flats with ties | A6 (discrimination) |
| **The score falls when consumption falls.** F004 + O4 (−14.30 kWh): equal-weight score drops from 49.5 to 48.9. | Removing daytime load at off-peak prices raises the *share* of peak-hour load. I3 rises from 1.142 to 1.180, and P3 drops from 42.3 to 23.6. | **A1** |
| The same mechanism hits F002 + O3 (−23.36 kWh). | I3 rises from 1.211 to 1.238 and P3 is clipped at 0. The total still rises (38.7 → 40.9) only because P1 improves. | A1 (per pillar) |
| **The score is not additive.** F002 baseline 38.7; +O3 alone = 40.9; +O5 alone = 55.0; combined = **58.6**, not 38.7 + 2.2 + 16.3 = 57.2. | Ratio pillars are non-linear in x | A2 makes S(x̃_combined) mandatory |
| **I3 and I4 are near-duplicates.** Spearman ρ = 0.79. | Price and carbon share the same daily peak shape | A5: timing effectively gets 2 × 0.25 weight |
| **Rankings depend on the weights.** F004 and F008 swap places between "equal" and "energy-heavy". | `rank_equal_vs_energy_heavy` | Needs a weight-sensitivity disclosure |

### 1.5 Directions for the mathematician (options, not decisions)

- **Fix A1:**
  - Express pillars in **absolute, size-adjusted units**: kWh, spot SEK and kgCO₂e per equivalent resident. These are monotone under reductions.
  - Or restrict timing pillars to **shiftable channels only** (A03, A04), so reductions elsewhere cannot move them.
  - Or define timing as "kWh in the peak block (07–10 and 17–21 local) per equivalent resident".
- **Fix A5:** merge price and carbon timing into a single pillar, or replace carbon timing with total kgCO₂e per equivalent resident.
- **Normalisation:** use external fixed anchors (e.g. defined target levels) instead of peer min–max with n = 8, which is unstable and degenerate under ties. Whichever is chosen, it stays frozen for projections (A3).
- **Heating:** decide whether supplementary heating counts. If it does, weather-normalise it (heater use is 0.12 kWh/h per °C below 12 °C in both heater flats).

---

## 2. F002 interval: statistical assumptions

### 2.1 What is estimated and how

**Estimand reported:** T = Σ_{h ∈ O_post} (x_h − μ̂_pre), summed over the 332 observed post-step hours (2026-10-15T00Z to 2026-10-29T00Z; 336 h in the window, 4 missing).
- μ̂_pre = 0.05167 kWh/h (332 pre-step hours).
- T = 23.36 kWh. The clip max(·, 0) never binds: the minimum post-step value, 0.105, is above μ̂_pre.

**Current method:**
1. Form 14 daily sums D_d = Σ_{h ∈ day d} (x_h − μ̂_pre).
2. Resample 14 days with replacement, 2,000 draws, seed 20261107.
3. Take the 2.5 and 97.5 percentiles of Σ D*.

Result: **[22.97, 23.79] kWh**.

### 2.2 Assumptions and diagnostics

| # | Assumption | Diagnostic | Verdict |
|---|---|---|---|
| B1 | Days are exchangeable / i.i.d. | Lag-1 autocorrelation of daily sums −0.05; hourly post-step ACF lags 1, 2 and 24 = −0.08, 0.09, 0.03; Newey–West (24 lags) variance / i.i.d. variance = 0.96 | Reasonable for this series |
| B2 | Post-step process is stationary (no trend, no recovery) | Daily means 0.117–0.126 kWh/h, trend ≈ 0 | Reasonable *within* the 14 days. Says nothing about the future. |
| B3 | **μ_pre is known exactly** | It is estimated: SD 0.0100, n = 332. Including its sampling variance widens the normal interval's half-width by **40.7 %** (±0.36 → ±0.51 kWh). | **Not satisfied.** The current interval is too narrow. |
| B4 | Missing hours don't distort the daily sums | 4 days have 23 h, the rest 24 h. Resampling *sums* mixes day lengths; resampling daily *means* × 332 gives [23.02, 23.69]. | Minor effect |
| B5 | A percentile bootstrap with n = 14 has nominal coverage | Small n tends to under-cover. The t-interval on daily sums (13 df) gives [22.90, 23.83]. | Minor; consider t or BCa |
| B6 | The reference level μ_pre is the right counterfactual | Using the peer mean (0.0526) gives 23.05 kWh. The shift of −0.31 kWh is about **75 % of the interval's half-width**. | **Model choice, not sampling.** Excluded from the CI. |
| B7 | The estimand is the observed-hours total, not the window total | Window total at the observed rate (× 336 h) = 23.64 kWh, a shift of +0.28 | **Definition choice.** Must be stated. |

**Interpretation caveat:** T is a sum over hours that have already happened. Its only genuine sampling uncertainty comes from μ̂_pre and measurement error. The day bootstrap therefore estimates uncertainty in the **underlying excess rate** (what a similar 14-day period would produce under stationarity), not in the realised past total.

### 2.3 Alternative intervals (kWh)

| Method | Interval |
|---|---|
| Current: day bootstrap of sums (percentile) | 22.97–23.79 |
| t-interval on 14 daily sums | 22.90–23.83 |
| Normal, i.i.d. hours, post only | 23.00–23.72 |
| **Normal, i.i.d. hours, incl. μ̂_pre uncertainty** | **22.85–23.87** |
| Day bootstrap of daily means × 332 | 23.02–23.69 |

**For decision (D4):** pick one estimand (observed-hours total or window total), and propagate μ̂_pre uncertainty, e.g. a two-sample bootstrap resampling pre and post days jointly, or the analytic variance N·s²_post + N²·s²_pre / n_pre. **This interval will never cover B6** (the counterfactual level) **or the repair assumptions**. See §4.

---

## 3. Measured excess, realistically avoidable consumption and counterfactual savings

### 3.1 Definitions (proposed canonical vocabulary)

Let r_h be a **reference level** for the affected channel and hours (pre-step mean, peer level, or 0 for "should be off").

| Quantity | Definition | Evidence class |
|---|---|---|
| **Measured excess** E | E = Σ_{h ∈ W ∩ O} max(x_h − r_h, 0). x_h is measured; r_h is a *modelling choice*, so E is "measured relative to a stated reference". | x: measured; r: inferred |
| **Realistically avoidable** A | A = θ·E with θ ∈ [0, 1], the share the student could realistically stop. More generally A = Σ θ_h max(x_h − r_h, 0). | **Hypothetical.** θ is not identifiable from these data. |
| **Counterfactual savings** S | S = Σ_h (x_h − x̃_h), where x̃ is consumption *if the intervention is followed*. It includes adoption q, timing, rebound ρ and post-intervention level: S = q·(A − R). | **Simulated** |

Ordering: **E ≥ A ≥ S ≥ 0** (if rebound is non-negative and adoption ≤ 1). Only E has an empirical anchor.

### 3.2 How the current scenarios map onto E, A and S

| Record | E (measured excess, reference) | A (avoidable) | S (counterfactual) | Note |
|---|---|---|---|---|
| O1 F007 | 23.27 kWh (r = 0 in all 64 unoccupied hours) | 9.19 (θ_h = 1 only in absences ≥ 2 h) | 9.19 (q = 1, ρ = 0); with ρ = 10–25 %: 8.27–6.89 | The "central" scenario is an **A**, not an S |
| O2 F005 | 62.79 (r = 33 W peer floor) | 31.40 (θ = 0.5, **arbitrary**) | = A | The "central" scenario is an **A** with no data basis |
| O3 F002 | 23.36 (r = μ̂_pre, observed hours) | Unknown (cause unknown) | 23.36 (repair at the step, full fix) | The "central" scenario is a retrospective **S** assuming A = E |
| O4 F004 | 14.30 (r = peer hourly median) | 14.30 (θ = 1) | = A | The "central" scenario is an **E** |
| O5 all | 0 kWh. "Excess cost" vs the 21:00 start: 59.22 SEK; vs the optimal hour: 74.15 SEK | — | 59.22 SEK, 1.656 kg (q = 1) | Price/carbon exposure, not energy |

**Finding:** the contract role `central` currently denotes **different quantity types** in different records (A, S or E), and `upper_measured` is in fact E. This is not a numerical error, but it is a semantic inconsistency for the engine and the coach.

**Proposed backward-compatible fix (decision D6):** add an *optional* field `quantity_type ∈ {measured_excess, avoidable_estimate, counterfactual_saving}` to each scenario. No existing field changes.

---

## 4. How savings uncertainty is calculated, and what it misses

### 4.1 Current method

For each scenario, the 95 % interval comes from a day-block bootstrap of daily savings within the scenario's window (fixed in the audit: no zero padding outside the window). It captures **only day-to-day variability of the observed series under fixed assumptions**.

### 4.2 Sampling interval width vs assumption range (central scenario)

| Record | Central | Sampling CI width | Assumption-range width | Ratio |
|---|---|---|---|---|
| O1 F007 (kWh) | 9.19 | 11.83 | 20.06 | 1.7 |
| O2 F005 (kWh) | 31.40 | 0.48 | 47.09 | **98** |
| O3 F002 (kWh) | 23.36 | 0.82 | 11.68 | 14 |
| O4 F004 (kWh) | 14.30 | 0.59 | 8.86 | 15 |
| O5 (SEK, hourly tariff) | 59.22 | 23.84 | 16.07 | 0.7 |

### 4.3 Does it capture uncertainty about the intervention itself? **No.**

Not captured:
- **Avoidability θ:** O2, O3 cause, O4 need.
- **Adoption q** and **rebound ρ.**
- **Post-intervention level:** O3 L.
- **Timing of the intervention:** O3 repair date.
- **Occupancy-sensor error:** O1.
- **Appliance identity.**
- **Tariff:** O5's SEK value is 59.22 or 0, a discrete state, not noise.
- **Non-stationarity of future weather and prices.**
- **Uncertainty of the reference level:** O3 μ̂_pre, §2.

For O2–O4 the intervention assumptions dominate by one to two orders of magnitude.

**Options for decision (D5):**
1. **Keep the two reported separately** (current practice): a sampling CI plus a named scenario range. This is transparent and needs no priors.
2. Report a **bounds interval** [min over scenarios of the CI lower bound, max of the CI upper bound].
3. **Monte Carlo over assumption distributions** (θ ~ Beta, q ~ Beta, ρ ~ U[0, 0.25], …). This yields one interval, but the priors are subjective and must be documented and owned.

Recommendation: never merge the two into a single "confidence interval" without explicit, approved priors. Tariff stays a categorical condition, never a probability.

---

## 5. Calculating a projected new score from an intervention scenario

This assumes a score S(·) defined over the hourly matrix x_f (§1). The rule is:

1. **Same window and hours:** compute S on the score's window (28 days) with the same observed-hour mask as the baseline (A7).
2. **Hourly counterfactual:** build x̃_f by applying the scenario's hourly rule.
   - **Reductions:** x̃_h = x_h − s_h, with s_h ≥ 0 and x̃_h ≥ 0.
   - **Shifts:** subtract k_e at h_e and add it at h'_e.
   - **Scenario windows shorter than the score's** (O3: 14 days): s_h = 0 outside the scenario window. Never rescale.
3. **Combined interventions:** apply them all to one vector (§6), then compute S(x̃) (A2). Never add score increments.
4. **Frozen normalisation:** use the baseline anchors and peer statistics. Do not recompute them with x̃ (A3).
5. **Tier:** a projected score is **simulated potential**. It may use estimated-realised parameters (q from the student) only when that tier is unlocked. A *verified* score needs post-period data.
6. **Monotonicity check:** before publishing, assert S(x̃) ≥ S(x) for every pure-reduction scenario. The candidate in §1.3 **fails** this check (F004 + O4), and this must be resolved (D2) before any projected score is shown.

Worked numbers for the candidate are in `math_review_numbers.json → candidate_score_ILLUSTRATIVE.projection_examples` (F002 + O3, F002 + O5, F002 combined, F004 + O4).

---

## 6. Preventing double-counting across overlapping recommendations

### 6.1 Support sets and current status

The support of a scenario is the set of (appliance, hour) cells with s > 0:

| Scenario | Cells | kWh |
|---|---|---|
| O1 central (F007 heater, absences ≥ 2 h) | 22 | 9.19 |
| O2 central (F005 A06, f = 0.5) | 661 | 31.40 |
| O3 central (F002 A01 post-step) | 332 | 23.36 |
| O4 central (F004 A05, 09–16 h) | 220 | 14.30 |
| O5 (A04 shift: origin 20:00, destination 21:00) | A04 cells only | 0 kWh |
| S1b F007 part (heater thermostat −1 °C), research report | 616 | 72.39 |
| S4 electronics off 00–06 h, all flats, research report | 1,296 | 36.47 |

**The five opportunity records are pairwise disjoint.** No two share a cell, and the O5 shift touches no reduction cell. Adding them within a flat is therefore currently exact. **Overlap does exist with the illustrative research-report scenarios.** O1 and S1b share 22 cells: the naive sum on those cells is 11.73 kWh, the correct combination 9.19, so **2.54 kWh would be double-counted**.

### 6.2 Combination rule (proposed for the engine; needs approval, D7)

1. Represent every intervention as an operator on the flat's hourly vector, never as a scalar saving.
2. **Order:**
   1. Repairs and faults (restore reference levels).
   2. Behavioural reductions.
   3. Shifts, applied to whatever remains of the shifted events.
3. **On a shared cell, each later reduction acts on the remainder.**
   - Proportional rules (s = φ·x): combined = x·(1 − Π_i(1 − φ_i)). This is order-invariant.
   - "Reduce to level r" rules: x̃ = min over i of r_i (also order-invariant).
   - Mixed rules: apply the fixed order above.
4. Constraints: x̃ ≥ 0, and x̃ ≥ physical floor where defined.
5. **Any total** (flat total, coach "if you do all of these", projected score) is Σ_h (x_h − x̃_h) of the combined vector.
6. **Mutually exclusive alternatives** of one opportunity (e.g. O1 central vs O1 upper; S1b vs S1c) can never be combined. Only one scenario per opportunity may be active.
7. An engine test asserts: (sum of the individual savings) − (combined saving) = the overlap reported, and the overlap is 0 for the current five records.

---

## 7. (Reserved: tariff extension)

Spot-only is agreed for the demo (§0). The valuation formulas for the other tariffs are already in the design (§4.1 there) and are unchanged.

---

## 8. Expressing per-student savings fairly from apartment-level data

### 8.1 What the data can and cannot support

- Measurements are **per flat × channel**. Nothing identifies which resident used a device.
- Occupancy is an estimated *count* per hour, not identities. Person-hours at home over the 28 days: 872 (F004) to 2,217 (F005); 9–16 hours per flat have unknown occupancy.
- Use is **sub-proportional in household size**. OLS of non-heater kWh on residents over the 8 flats gives 95.9 kWh fixed + 20.4 kWh per resident (R² = 0.52). Per resident, that is 66–74 kWh in 2-resident flats against 36–47 kWh in 4–5-resident flats.
- The fit is **unstable** (n = 8). Leave-one-out slopes range 4.8–24.6 kWh/resident and intercepts 87.7–135.3 kWh.

### 8.2 Options

| Method | Per-student value | Pros | Cons |
|---|---|---|---|
| **Flat total (primary)** | S_f | Exactly what is measured | Not per student |
| Equal split | S_f / n_f | Simple and neutral. F002 O3: 7.79 kWh per resident; F004 O4: 7.15 | Wrong for personal devices (O4, possibly O1) |
| Occupancy-weighted | Needs individual presence | — | **Not possible**: no individual identities |
| Responsibility-based | Assigned to the confirming student | Fair for personal devices | Needs self-report; can't be verified |
| Equivalence-scale normalisation (for comparisons, not savings) | kWh_f / (a + b·n_f) | Removes the size effect | a and b unstable with 8 flats; a size-adjusted score inherits that instability |

**Recommendation for review (D8):**
- Report savings at **flat level**.
- Offer "**average per resident** = flat ÷ residents" as a clearly labelled average, not a measured individual saving.
- Never attribute waste to an individual from data.
- Allow responsibility-based attribution only when a student self-reports ownership, and label it as such.
- For cross-flat comparisons and scores, use a size adjustment. Treat its parameters as uncertain, with a fixed external scale or a pooled prior, rather than the unstable 8-flat fit.

---

## 9. Register of unresolved decisions (owner: mathematician)

| ID | Decision | Options | Non-binding suggestion |
|---|---|---|---|
| D1 | Score pillars and their definitions | §1.3 candidate, teammate spec, or absolute per-equivalent-resident pillars | Absolute, size-adjusted pillars |
| D2 | Monotonicity (A1) of timing pillars | Shiftable-only timing, peak-block kWh, or drop ratios | Shiftable-only or peak-block kWh |
| D3 | Normalisation and weights | Peer min–max (frozen), external anchors, z-scores; equal vs expert weights | External anchors + weight-sensitivity table |
| D4 | F002 estimand and interval | Observed-hours vs window total; propagate μ̂_pre; t / BCa / analytic | Window total + analytic or two-sample bootstrap |
| D5 | Combining sampling and assumption uncertainty | Separate (current), bounds, Monte Carlo with priors | Keep separate |
| D6 | Scenario quantity labelling | Add optional `quantity_type` (E / A / S) | Add (backward compatible) |
| D7 | Combination operator and order | §6.2 | Adopt, with an overlap test |
| D8 | Per-student expression | §8.2 | Flat-level + labelled average |
| D9 | Supplementary heating in scores | Exclude, include, or weather-normalise | Weather-normalise, or keep as a separate pillar |
| D10 | Arbitrary central parameters (O2 θ = 0.5; O1 absence ≥ 2 h) | Keep, replace with student input, or show only ranges | Student input for θ / q, with the range shown when absent |

## 10. Limitations

- 8 synthetic flats over 4 autumn weeks. No real-world validity, no seasonal coverage, and no post-intervention data, so nothing can be verified.
- Occupancy comes from a simulated sensor; appliance identities are inferred.
- Carbon factors are averages, not marginal.
- Cohort statistics with n = 8 are unstable (§8.1).
- All SEK values are synthetic spot energy only.

## 11. Contract compatibility

- **No schema or contract has been changed.**
- The audit added fields to `opportunities.json` (`period`, `evidence_classification`, `waste_status`, `verification_status`, `occupancy_denominators`). These are additions, and all existing fields are preserved.
- Proposed future changes are additive and optional: D6 `quantity_type`, and a `combination` block for D7. They need your approval before the engine implementer adopts them.

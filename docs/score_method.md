# Score and savings method

All parameters are in `backend/app/config.py`, each with its justification. The code is in `backend/app/core/`. Changes from the original engine are in [engine_changes.md](engine_changes.md); the requirements the method must satisfy are in [math/requirements_spec.md](math/requirements_spec.md).

## 1. Data and hourly accounting (`hourly.py`)

Each flat is a matrix x[h, c]: 672 UTC hours × 7 channels.
- A missing reading is NaN, never 0.
- Price p_h (spot SEK/kWh, excl. VAT) and carbon g_h (gCO₂e/kWh) are hourly.
- The local hour comes from Europe/Stockholm, so 25 October has 25 local hours.

**Accounting rules:**
- Measured kWh = Σ observed x.
- SEK = Σ x·p over priced hours.
- kgCO₂e = Σ x·g / 1000.

**Interventions** are operators on a **trajectory** (observed base + delta layer):

| Kind | Rule |
|---|---|
| fraction | s = φ·x |
| capped excess | s = θ·min(max(x − r, 0), cap) |
| shift | moves k = share·x from h₀ to h₁ on the same channel; Σ kWh unchanged |

- **Fixed combination order:** repair → reduction → shift. Proportional cuts on the same cell combine as 1 − Π(1 − φᵢ).
- **Missing hours:** reductions never touch missing cells. A shift into a missing hour is kept in the delta layer, so it is never lost and never treated as that hour's full reading.

## 2. Detection (`detect.py`)

Detection runs on the baseline. A channel is *continuous* if it is non-zero in most hours across the fleet (A01, A05, A06). The other channels are *event-like*.

| Type | Criterion (→ PLAUSIBLE) | Excess per hour | Responsibility |
|---|---|---|---|
| `fault_step_change` | Continuous channel. Day means (≥ 12 observed h; days with nobody home all day excluded); statistic = max one-sided Welch t over every split with ≥ 3 days each side; **day-permutation p-value** (999 permutations, seeded) < α = 0.01. The split hour is refined within ±24 h. | x − r, r = pre-split mean | manager on equipment channels (A01), else resident |
| `base_load_outlier` | Always-on floor (P5 of hourly kWh) above every other flat's floor in **every** week | min(max(x − m, 0), F − m); m = median of the other flats' floors, F = own floor | resident (student first; provider if hard-wired) |
| `scheduled_block` | Local hours where the weekly median exceeds every other flat's weekly median in every week, **and** the level persists with nobody home (on ≥ 3 days) | x − peer median at that local hour | resident |
| `heater_pattern` | Heater-like use with nobody home in absences ≥ 2 h, on ≥ 3 days | x (only those hours) | unknown (needs confirmation) |
| `peak_usage` | Flexible runs (A03, A04) in peak-price hours on ≥ 3 days | none (timing, not excess) | resident |

**Peak hours** are the local hours whose mean spot price exceeds the time-average price. On this dataset that is {7, 8, 9, 17, 18, 19, 20}.

The engine never assigns a probability (`confidence = null`). It can assign only DETECTED or PLAUSIBLE; people confirm.

On the validated data the detectors find exactly the five validated opportunities:
- F002 fridge step (p = 0.001);
- F004 09–17 block;
- F005 +95 W floor;
- F007 heating with nobody home;
- peak-hour dishwasher runs in all 8 flats.

They also flag peak-hour washing-machine runs in 5 flats. There are no other detections.

## 3. Frozen references (`references.py`)

These are fitted once on the baseline and reused unchanged in every evaluation and counterfactual:
- the missing mask, with **local imputation** (same channel, same UTC day; else ±1 day; else channel mean);
- peak hours;
- equivalent residents eq = n^0.5 (OECD square-root scale);
- the Use benchmark B per lens (P20 of the flats);
- the typical intensity K and typical flexible intensity K_T (medians of the flats);
- every anomaly's reference level, cap and cells.

Values on this dataset: B = 2.901 (apartment lens) and 2.779 (resident lens) kWh per equivalent resident per day; K = 3.273; K_T = 0.402.

## 4. Partition and pillars (`pillars.py`)

Coverage-adjusted energy X = observed + frozen imputation + deltas. It is partitioned so that **each kWh counts in exactly one pillar**:

  X = explained + R (possible avoidable use) + F (possible equipment fault)

- **F:** excess of manager-responsibility anomalies at PLAUSIBLE or above.
- **R:** excess of resident/unknown-responsibility anomalies at PLAUSIBLE or above.
- Anomalies are applied sequentially on the remainder, so they never overlap.
- `peak_usage` is timing, not excess.

With u = explained / eq / 28, the pillars (0–100, higher is better) are:

| Pillar | Formula | Lenses |
|---|---|---|
| USE | 100·min(1, B / u). Apartment: explained use incl. heater-like use. Resident: excl. heater-like channels (weather-driven). | both |
| WASTE | 100·K / (K + R/eq/28) | both |
| HEALTH | 100·K / (K + F/eq/28) | apartment |
| TIMING | 100·K_T / (K_T + P/eq/28), P = flexible kWh in peak hours | both |

The ratio form x₀ / (x₀ + e) needs no threshold: it is 100 at e = 0 and 50 when the excess equals a typical flat's intensity.

**Properties (tested):**
- Every pillar is non-increasing in every hourly kWh.
- A pure shift changes only Timing.
- Another flat's data never changes a flat's score.
- Deleting readings is neither "zero use" nor regime-mixed.

**Lenses:**
- **Apartment Performance:** Use .40, Waste .25, Timing .20, Health .15.
- **Resident Actions:** Use .50, Waste .30, Timing .20; excludes possible faults and weather-driven heating.

The score is the weighted geometric mean (pillars floored at 1; pillars are strictly positive by construction). The arithmetic mean is also returned. Bands are A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 55, E ≥ 40, F ≥ 20, G < 20.

## 5. Savings (`interventions.py`, `savings.py`, `valuation.py`)

Each anomaly type has an intervention with documented parameters. The default is the central assumption; the list gives the scenario range.

| Type | Parameters (default; range) |
|---|---|
| step change (repair) | fix_fraction (1; 0.5–1), repair_after_days (0; 0–7), post_level (pre-step mean; peer mean) |
| base load | avoidable_fraction (1; 0.25–1) |
| scheduled block | avoidable_fraction (1; 0.5–1), only_when_unoccupied (no; yes) |
| heater | min_absence_hours (2; 1–3), rebound (0; 0–0.25) |
| peak timing | share_moved (1; 0.5–1), max_delay_hours (12; 3–12); quiet_hours is a student preference |

`adoption` (student input, default 1) scales every fraction or share. Potential (adoption 1) and estimated realised (student's adoption) are therefore distinct. Verified savings come only from post-change data.

**Per run the engine reports:**
- **Ladder** (observed hours of the pattern):
  - observed kWh;
  - expected baseline = observed − excess;
  - unexplained excess (measured relative to the stated reference);
  - avoidable estimate (simulated, at the parameters);
  - counterfactual kWh;
  - kWh moved, for shifts.
- **Δ of the combined trajectory:** kWh, spot SEK at hourly prices, kgCO₂e at hourly factors. Load reductions and shifts are separate kinds.
- **Valuation by tariff:**
  - hourly spot: exact;
  - monthly average: time-average price, reductions only;
  - fixed: the student's own price, reductions only;
  - included in rent: 0 SEK to the student;
  - unknown: SEK not stated, with an "if hourly spot" value alongside.
- **Uncertainty, never merged:**
  - **sampling:** 95 % day-block bootstrap within the pattern's window (2000 draws, seeded);
  - **scenario:** min–max over the parameter grid;
  - **evidence:** the detector statistics.
- **Before/after scores** for both lenses, frozen references, on the coverage-adjusted matrix.
- **Overlap** = Σ individual − combined (0 for disjoint patterns).

**Window:** 28 days, except a step change, which only counts from its start (F002: 14 days).

**Annual projection:** given only for persistent equipment and base-load patterns: mean daily saving × 365, with a day-bootstrap p5–p95 range. Heating and timing are not extrapolated.

## 6. Verification (`verification.py`, unchanged)

saving = pre-repair rate × post hours − post kWh. VERIFIED needs at least 7 days of post-change data with the 90 % bootstrap interval above 0. Simulated post-repair data is always flagged.

## 7. Sensitivity (reports/engine_comparison.md)

**Weights:** Dirichlet(α = 20·w), 2000 draws; score and rank p5–p95 are reported per flat.

**Modelling choices:**
- **Stable** (ranking unchanged): detection α ∈ {0.05, 0.01, 0.001}, the continuous-channel cut-off (0.1–0.75) and the minimum absence (1–3 h).
- **Policy:** the equivalence exponent (0.33 / 0.5 / 1) and the Use benchmark percentile (10 / 20 / 30) reorder the middle of the ranking. The top (F006, F003) and bottom (F007, F001) are stable.
- **Resolution guard:** α must exceed 1/(permutations + 1), and the engine refuses otherwise.

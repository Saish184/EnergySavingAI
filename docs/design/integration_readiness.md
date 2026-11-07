# Integration readiness: student app and apartment-manager dashboard

**Scope:** the numerical outputs both interfaces need from the shared quantitative engine, whether the existing contracts provide them, and **backward-compatible proposals** (draft in [`proposed_additions.schema.json`](proposed_additions.schema.json)).
**Constraint:** `contracts.schema.json` v1.0 is **not modified**. Proposals are additive: new objects, or new optional fields.

## 1. What the current frontend expects (read-only inspection of `origin/Hugo`, commit `59644a1`)

The `wattwise-site` mock-up uses placeholder arrays and computes these figures in the browser:
- kWh, kWh per person, spot cost (labelled "energy part only, not the full bill") and kg CO₂e;
- a 24-hour profile;
- overnight kWh per hour;
- a "what-if" shift.

It contains **no score**. Points to resolve when it is wired to the engine (I modified nothing on that branch):

| Frontend behaviour | Mathematical issue | Engine output that fixes it |
|---|---|---|
| What-if moves *all* load in 15–18 UTC to 22–04 UTC | Moves inflexible loads (fridge, cooking, lighting); violates R9's flexible-load assumption (R17) | `calculatorResult` for O5 per flat (exact hourly shifts of dishwasher runs only) |
| Saving = moved kWh × (average peak price − average night price) | Uses averaged prices, not the realised hourly ones | ΔC = Σ k (p_{h₀} − p_{h₁}) from the engine |
| Hours labelled in UTC ("after 19:00 UTC", "22:00 UTC") | Students live in local time; the UTC↔local offset changes on 25 Oct | `flatSummary.hourly_profile.clock = local` for display |
| "Overnight 00–04 UTC" baseline | Different window from the engine's 00–06 local; overnight use includes legitimate heating and fridge | Use the engine's declared window and exclude A01/A07 when discussing discretionary load |
| "kWh per person" | Must be labelled as an average (R8) | `flatSummary.per_resident_average` with its fixed label |
| Destination window 22–04 UTC for dishwashers | Quiet-hour and unattended-appliance concerns (design §5.4) | Default to the validated 21:00-local scenario |
| "Confidence: medium/low" text labels | Acceptable as categorical, but must come from the record, not be hard-coded | `statistical_confidence`, `action_feasibility` |

## 2. Minimum numerical outputs per interface

| Need | Student app | Manager dashboard | Available now? | Proposal |
|---|---|---|---|---|
| **Current consumption** (kWh, spot SEK, kg CO₂e; by channel; period) | Own flat | All flats | Partly (EDA tables; the coach tool has no schema) | `flatSummary` |
| 24-hour profile (local clock), price and carbon by hour | Yes | Optional | No contract | `flatSummary.hourly_profile` |
| Data quality (coverage, missing, unpriced, unknown occupancy) | Short note | Full table | Inside records only | `flatSummary.data_quality` |
| Average per resident (labelled) | Yes | For comparison | No | `flatSummary.per_resident_average` |
| Weather-normalised heating (kWh per heating degree-hour) | Heater flats | Yes | No | `flatSummary.weather_normalised_heating` |
| **Evidence-backed opportunities** with statuses | Own flat | All flats | Yes (`savingsRecord`) | — |
| Quantity type (excess / avoidable / saving) | Yes | Yes | No (D6) | Optional `scenario.quantity_type` |
| **Counterfactual savings**, single record | Yes | Yes | Yes (`calculatorResult`) | — |
| Counterfactual savings, several records combined | "If I do all of these" | Portfolio potential | No | `combinedCalculation` |
| **Scores** (pillars, aggregate, references, invariant status) | Yes | Distribution | No | `scoreResult` |
| Projected score after interventions | Yes | Optional | No | `projectedScore` (one combined trajectory, frozen references) |
| **Responsible party** (who acts, who pays, who sees) | Yes | Yes | No. `included_in_rent` is fixed at 0 SEK (student view), but the **provider pays** in that case. | Optional `savingsRecord.responsibility` |
| Equipment alerts with lifecycle (F002) | Notification only | Yes | Finding only, no lifecycle | `alert` |
| Verified savings | Later | Later | No (v1 always null) | `verificationResult` |
| Portfolio totals and normaliser | — | Yes | No | `portfolioSummary` |

## 3. Responsibility per validated record (proposed defaults)

| Record | action_owner | cost_bearer | Visible to the manager? |
|---|---|---|---|
| O3 F002 suspected fridge fault | shared (student checks, provider repairs) | unknown (tariff) | Yes, as an alert |
| O2 F005 always-on base load | student first, provider if hard-wired | unknown | Yes, aggregated |
| O4 F004 daytime electronics | student | unknown | Aggregated only |
| O1 F007 heating while unoccupied | student | unknown | Aggregated only (behavioural; privacy) |
| O5 dishwasher timing | student | student only on hourly tariffs | Aggregated only |

## 4. Readiness verdict

- **Ready:**
  - single-record savings (`savingsRecord`, `calculatorResult`);
  - accounting semantics (`analysis/mathcore.py`; 35 tests pass);
  - the audit harness for any score.
- **Not ready:**
  - the score itself (no implementation to audit);
  - flat summaries, combined calculations, the responsibility field, alerts, the portfolio view — all proposed additively here.
- **Blocking for a demo that shows a score:** the score must pass the universal checks (R3, R4, R5, R7, R9, R11) in `audit_score.py --teammate`. Otherwise, show pillars separately, labelled "provisional", and no composite.

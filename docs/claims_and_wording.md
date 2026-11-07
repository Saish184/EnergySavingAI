# Claims and wording (for UI and LLM)

| status | wording: equipment (manager) | wording: behaviour (resident) | set by |
|---|---|---|---|
| DETECTED | unusual pattern | unusual pattern | engine |
| PLAUSIBLE | possible fault | consistent pattern | engine, only when the detector's stated criterion holds and the pattern lasts ≥ 3 days |
| CONFIRMED | confirmed | confirmed | a person (the manager opens a work order) |
| REPAIRED | repaired, awaiting data | repaired, awaiting data | a person (work order → repaired) |
| VERIFIED | saving measured | saving measured | verification only (≥ 7 days post-change data, 90 % interval > 0) |

- Findings with responsibility `unknown` (heater_pattern) say "possible heating opportunity, needs confirmation" until a person confirms them.
- The UI must show `finding.wording` as it is and must not upgrade it. "Fault", "broken" and "saving" are only allowed at the levels shown in the table.
- **No probabilities.** `evidence.confidence` is always `null`. The UI may show `evidence.statistics` (e.g. the permutation p-value, the weeks above peers), but it must not turn them into "x % sure".

## Detector criteria behind PLAUSIBLE

| type | criterion |
|---|---|
| fault_step_change | day-permutation p < 0.01 (999 permutations, seeded) on a continuous channel |
| base_load_outlier | always-on floor above every other flat's floor in every week |
| scheduled_block | hour-of-day level above every other flat in every week, and persists with nobody home on ≥ 3 days |
| heater_pattern | heater-like use with nobody home (absences ≥ 2 h) on ≥ 3 days |
| peak_usage | flexible runs in peak-price hours on ≥ 3 days (timing, not waste) |

## Responsibility
- `manager`: "equipment issue: the building manager can fix it; residents are not scored on it"
- `resident`: "behaviour: residents can change this themselves"
- `unknown` (heater_pattern): "possible heating opportunity, needs confirmation"

`finding.counts_as` states the pillar the excess counts in:
- "possible equipment fault (apartment lens only)";
- "possible avoidable use";
- "timing opportunity (not waste)".

## Rules for the numbers
- Figures over the observed window are "measured counterfactual over N observed days". N is 28, except for a step change, which counts from its start (F002: 14).
- Savings are a "potential (if followed fully)". "Estimated realised" needs the student's adoption estimate. "Verified" needs post-change data.
- Annual figures are always "projection", with their range. They exist only for persistent equipment, base-load and fixed-block patterns; otherwise `value` is null and a reason is given.
- SEK always means "spot-energy component only (excl. VAT, network fee, energy tax, markup, fixed fees); not a bill saving". It depends on the tariff (`valuation.sek_by_tariff`). A shift is worth 0 SEK on a non-hourly tariff.
- Appliance types are always "-like" (e.g. "fridge-like") and must be marked as assumptions.
- Anything that comes from simulated post-repair data must show "simulated".
- Per-resident values are labelled averages, never individual consumption.

## LLM tips (`backend/app/services/tips.py`)
- The LLM receives only the finding JSON. It may use only the numbers given and must keep the status wording.
- It writes at most 2 sentences plus one "Action:" line.
- If the output contains any number that isn't in the input, or the API call fails or is refused, the app uses the template text. There is no automatic model fallback.

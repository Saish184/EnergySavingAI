# Claims and wording (for UI and LLM)

| status | exact wording | set by |
|---|---|---|
| DETECTED | unusual pattern | engine |
| PLAUSIBLE | possible fault | engine (confidence ≥ 0.7 and ≥ 3 days) |
| CONFIRMED | confirmed | human (manager opens work order) |
| REPAIRED | repaired, awaiting data | human (work order → repaired) |
| VERIFIED | saving measured | verification only (≥ 7 days post data, 90% interval > 0) |

The UI must show `finding.wording` as it is and must not upgrade it. "Fault", "broken" and "saving" are only allowed at the levels shown in the table.

## Responsibility
- `manager`: "equipment issue: the building manager can fix it; residents are not scored on it"
- `resident`: "behaviour: residents can change this themselves"
- `unknown` (heater_pattern): "possible heating opportunity, needs confirmation"

## Rules for the numbers
- 28-day figures are "measured". Annual figures are always "projected", with their range.
- SEK always means "spot price only (excl. VAT, network fee, energy tax)".
- Appliance types are always "-like" (e.g. "fridge-like") and must be marked as assumptions.
- Anything that comes from simulated post-repair data must show "simulated".

## LLM tips (`backend/app/services/tips.py`)
The LLM receives only the finding JSON. It may use only the numbers given and must keep the status wording. It writes at most 2 sentences plus one "Action:" line. If the output contains any number that isn't in the input, the app falls back to the template text.

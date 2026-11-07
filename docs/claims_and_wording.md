# Claims and wording (for UI and LLM)

| status | exact wording | set by |
|---|---|---|
| DETECTED | unusual pattern | engine |
| PLAUSIBLE | possible fault | engine (confidence ≥ 0.7 and ≥ 3 days) |
| CONFIRMED | confirmed | human (technician: `fault_found: true`) |
| REPAIRED | repaired, awaiting data | human (work order → repaired) |
| DISMISSED | checked, no fault found | human (technician: `fault_found: false`); excluded from HEALTH |
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

## LLM texts (`backend/app/llm/`)
The prompts are in `prompts.py` (`PROMPT_VERSION`). The LLM sees only payloads built from engine output, and these are rounded beforehand.

`validator.py` rejects any reply with:
- a number, date or time that isn't in the payload (rounding to 0, 1 or 2 decimals is accepted)
- a missing status phrase
- "broken", "faulty", "definitely", "certainly" or "confirmed" for DETECTED or PLAUSIBLE findings
- a yearly value without "projected"
- a claim that a load shift saves energy
- blame phrases on manager or unknown findings
- "your fridge" instead of "fridge-like appliance"
- text over the length limits
- a priority, pillar or CTA that doesn't match the engine

A rejected reply is retried once with the list of failures. If it fails again, the template from `templates.py` is used instead.

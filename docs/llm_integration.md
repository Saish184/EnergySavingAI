# LLM layer on Mina's engine: integration and handoff

**Branch:** `saish-llm-integration`, based on `origin/mina@2ee36f8`.

**Principle:** Mina's engine owns every number. The LLM only explains the numbers; it never calculates kWh, SEK, CO₂e, scores, projections or savings.

## 1. What changed

The LLM layer was rebuilt on Mina's data contract. Her engine, data pipeline, detection, scoring, interventions and numeric API fields are unchanged.

| | v1 (`saish@f7eeda8`) | v2 (this branch) |
|---|---|---|
| Input | Saish's own payload: re-derived cheapest hour, weekly sums | `facts.py` copies Mina's finding, score and portfolio fields into a **FactSheet**. Each fact has value, unit, display, category, period, tariff and source field |
| Numbers in text | The model wrote digits; the validator checked them against an allow-list of input numbers and small integers | The model writes **no digits**, only `{PLACEHOLDERS}`. The renderer inserts the engine's display string, which already carries the unit, period and tariff condition |
| Categories | Not distinguished | observed · unusual · possible_waste · avoidable_estimate · simulated_saving · estimated_realized · verified · projection. Each has its own language rule |
| Validator | 9 checks | 21 checks (`validator.py`): placeholders, raw numbers/number words, units, periods, projection, categories, tariff/bill, wording, overclaim, fault language, blame, appliance-as-fact, "all avoidable", shift-as-energy, unsafe advice, confidence, synthetic generalisation, required facts, length, logic |
| Fallback | Template (not always validated) | Cached LLM text (re-validated) → provider (one repair retry) → our wording (`phrases.json` v2, validated) → safe response (validated) → `unavailable`. **Nothing unvalidated is served** |
| Latency | Synchronous provider calls inside GET requests | GETs never wait for a provider. A cache miss returns our wording and schedules background generation. `export`, `/llm/warm` and `evaluate` run synchronously |
| Claude | Automatic model fallback after a refusal | Removed (team decision 5). A refusal counts as a failure and falls back to our wording |
| Prompt | v1 | **v2** (placeholder-based). Old caches are invalid by key |
| `services/tips.py` | Separate generation path | Thin wrapper over `app/llm/service.py` (one integration layer) |

### Per-finding rules (validated, from real engine values)

| Finding | Values and rules |
|---|---|
| **F002 fridge-like** (`FS-F002-A01`) | 14-day window (`P_WINDOW`); 23.36 kWh potential; "possible fault"; SEK only "if you have an hourly spot-price contract"; no blame |
| **F004 electronics-like** (`SB-F004-A05`) | 14.30 kWh, conditional; must say "potentially unnecessary"; student `question` asks what the device is and whether it can be switched off (`cta: confirm`) |
| **F005 always-on** (`BL-F005-A06`) | Measured excess 62.79 kWh (`EXCESS_KWH`, possible_waste) is kept separate from the avoidable scenario range 15.70–62.79 kWh (`RANGE_KWH`). Both are required; "all of it is avoidable" is rejected |
| **F007 heating** (`HU-F007-A07`) | 9.19 kWh behavioural scenario; no projection fact, so any yearly claim is rejected; unsafe heating advice is rejected; must say it needs confirmation |
| **Dishwasher/washer** (`PK-*`) | kWh moved and SEK on the hourly-spot contract; no `SAVE_KWH` fact exists; energy-saving claims are rejected; peak hours come from the engine's `evidence.statistics.peak_hours_local`; "overnight"/"unattended" are rejected |

## 2. Files

| File | Role |
|---|---|
| `backend/app/llm/facts.py` | Engine output → FactSheet: `finding_sheet`, `score_sheet`, `overview_sheet`, `portfolio_sheet`. Occupancy is minimised: heater facts send only the day count |
| `backend/app/llm/schemas.py` | Output models per use case: `finding_student`, `finding_manager`, `weekly_digest` (28-day overview), `score_explainer`, `portfolio_manager` |
| `backend/app/llm/prompts.py` | System prompts, `PROMPT_VERSION = "v2"` |
| `backend/app/llm/validator.py` | `validate()`, `render()`, `quantity_facts_used()` (structured claims with source fields) |
| `backend/app/llm/templates.py` + `phrases.json` | Our wording, using the same placeholders |
| `backend/app/llm/safe.py` | Last-resort responses with no quantities |
| `backend/app/llm/generate.py` | `produce()` / `produce_many()`, background generation, cache |
| `backend/app/llm/service.py` | **The only integration point with AppState**, plus deterministic manager `triage` |
| `backend/app/llm/providers/` | `gonka` (plain HTTP), `anthropic` (no auto-switch), `template` |
| `backend/app/llm/evaluate.py` | Pass-rate table → `out/llm_eval.json` |
| `backend/app/api/llm.py` | `/llm/status`, admin `/llm/regenerate` and `/llm/warm` |
| Engine-side changes | `core/claims.py` (DISMISSED), `state.py` (work orders), `services/workorders.py`, `services/findings.py` (wording when dismissed), `models.py` |

## 3. API (additive; all of Mina's fields unchanged)

| Endpoint | Added |
|---|---|
| `GET /flats/{id}/findings` | `student_text` on each finding. `?texts=false` skips it |
| `GET /flats/{id}/scores` | `explainer` |
| `GET /flats/{id}/tips` | Same fields as before, plus `title`, `question`, `cta`, `text_status`, `provider`, `model`, `prompt_version`, `claims`, `disclaimer` |
| `GET /flats/{id}/digest` | **New**: 28-day overview (3 bullets) |
| `GET /portfolio/findings` | `manager_text` and `triage` {maintenance, priority: inspect/monitor/verify/none, action_owner, reason}. Behavioural findings are never maintenance |
| `GET /portfolio/summary` | **New**: manager overview |
| `GET /llm/status` | Provider, model, `key_present` (never the key), cache size, last error, background stats |
| `POST /llm/regenerate`, `POST /llm/warm` | Admin only: `X-Admin-Token` must equal `FEC_ADMIN_TOKEN` (unset = disabled); 5 calls per minute per IP |
| `PATCH /workorders/{id}` | `{"status"?, "fault_found"?}` |
| `GET /health` | `demo_notice` |

**Every text object has these fields:**
- `use_case`, `audience`;
- `status`: ok / safe_fallback / unavailable;
- `source`: llm / template / safe;
- `provider`, `model`, `prompt_version`, `validator_version`, `phrases_version`;
- `output`: rendered fields;
- `claims`: placeholder → value, unit, category, period, tariff, source;
- `validation`, `llm_status`: cached / generated / pending / disabled / failed;
- `disclaimer`.

Examples are in `docs/api_examples/` (generated with our wording, so they are deterministic): `GET_flats_F002_digest.json`, `GET_flats_F00{4,5,7}_findings.json`, `GET_portfolio_summary.json`, `GET_llm_status.json`. Hugo's frontend shows `output` as it is and never recalculates.

## 4. Provider configuration (`.env`, gitignored)

```
FEC_LLM_PROVIDER=template          # template (default) | gonka | anthropic
GONKA_BROKER_URL=https://api.gonkarouter.io/v1
GONKA_BROKER_API_KEY=...
GONKA_MODEL=deepseek-ai/DeepSeek-V4-Flash-0731
ANTHROPIC_API_KEY=...              # only for provider=anthropic
FEC_ADMIN_TOKEN=...                # enables /llm/warm and /llm/regenerate
```

A missing key or unknown provider falls back to `template` and logs one warning. Keys are redacted from logs, errors and `repr`.

## 5. Work orders (behaviour change, reviewed separately)

- Opening a work order **no longer** sets CONFIRMED.
- The technician's outcome decides:
  - `fault_found: true` → CONFIRMED;
  - `fault_found: false` → DISMISSED. It is no longer counted in any pillar (`counts_in` needs ≥ PLAUSIBLE), and the work order becomes `closed_no_fault`;
  - `status: repaired` → REPAIRED. A saving still needs ≥ 7 days of post-change data (VERIFIED).
- `tests/test_api.py::test_manager_workflow_to_verified` was updated to this flow.

## 6. Security and privacy (hackathon scope)

- **No authentication.** `X-Flat-Id` is a demo filter, not access control. `/health` and every text carry the synthetic-data notice. Do not use with real residents' data.
- Admin LLM operations need a token and are rate-limited. Dashboard GETs cannot trigger synchronous provider calls; the background queue is capped at 200.
- Data sent to a third-party provider: engine facts and labels only. There are no timestamps of absences, and heater evidence is reduced to a day count.

## 7. Tests and compatibility

**Backend: 91 passed.**
- Mina's 63 tests: 62 unchanged, 1 updated (`test_manager_workflow_to_verified`, work-order flow).
- 28 new tests in `tests/test_llm_v2.py`:
  - all five opportunity types with real values (F002 14 d / 23.36 kWh, F004 14.30, F005 62.79 vs range, F007 9.19 and no projection, dishwasher shift);
  - 12 fabricated or misleading claims (invented number, wrong unit, wrong period, unsupported year, bill, guarantee, "proves", "broken", number words, probability, synthetic generalisation, blame);
  - missing confidence, appliance uncertainty;
  - cache plus re-validation;
  - invalid reply and outage → template; template failure → safe response;
  - non-blocking GETs;
  - Gonka 401/timeout over mocked HTTP with key redaction;
  - no automatic model switch;
  - roles (student gets no manager text and no other flats' ids), disclaimers, admin 403;
  - DISMISSED leaves HEALTH.

**Root math suite (`tests/math`):** passes. 11 tests are skipped by design because they need a checkout of the old engine (`SAISH_BACKEND`).

**v1 tests not carried over** (written for the old engine and v1 payloads):
- `test_llm.py` → replaced by `test_llm_v2.py`;
- `test_providers.py` → its mocked-HTTP and redaction cases are folded into `test_llm_v2.py`.

**Not run:** a real Gonka evaluation for prompt v2 (skipped on request). To run it, set `FEC_LLM_PROVIDER=gonka` with the key, then `cd backend && python -m app.llm.evaluate`. `python -m app.export` then fills `out/llm_cache.json`, which is committed (`.gitignore` keeps only that file in `out/`).

## 8. Remaining limitations

- The validator is pattern-based. It blocks the listed failure modes but cannot judge tone or every unsafe idea. A human should review new phrasings.
- The prompt v2 pass rate with Gonka is unmeasured. v1 had length failures, and v2 adds stricter rules.
- `estimated_realized` texts appear only once the engine receives a student's adoption estimate. The facts support it already.
- There are no weekly totals (the engine provides none), so `/digest` is a 28-day overview.

## 9. Merging into `mina`

1. Mina reviews this branch, in particular §5 (work-order behaviour) and the regenerated `docs/api_examples/`.
2. `git checkout mina && git merge --no-ff saish-llm-integration`. It merges cleanly because the branch is based on `mina@2ee36f8`.
3. `make test`, then `make examples` if the data changed.
4. Optionally, with a key: `python -m app.llm.evaluate` and `make engine` to commit fresh AI texts.

## 10. Future: interactive energy coach (not built)

- **Questions** go through read-only, authorised tools that call the same AppState views (`/flats/{id}/findings`, `/scores`, `/scenarios`). The model never gets free database access.
- **Answers** use the same FactSheet, placeholder and validator path.
- **Follow-up questions** (appliance identity, tariff confirmation, adoption) are stored as student inputs and passed to the engine. The engine recomputes the tiers (e.g. `estimated_realized`); the LLM never does.
- **Scenario comparison** calls `POST /scenarios`, and the answer cites `claims`.
- **Escalation** creates a report (`POST /findings/{fid}/report`), never a work order directly.
- **Needs first:** real authentication, per-user rate limits, conversation logging with redaction, and an evaluation set for multi-turn answers.

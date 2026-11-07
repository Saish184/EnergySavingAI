# Flat Energy Coach

An energy coach for shared student flats with two views:

- **Student**: sees only their own flat. Gets scores, findings, tips and what-if scenarios.
- **Manager**: sees all flats. Gets the portfolio, findings and work orders, and can verify repairs.

The data is the hackathon's synthetic dataset: 8 flats, SE3 price area, hourly UTC readings from 1 to 28 October 2026. The organisers' original README and data dictionary are in [data/raw/](data/raw/).

The engine produces every number in the app. No demo result is hard-coded. Every output says:

- its claim **status**
- who is **responsible** for acting on it
- its **horizon**: 28 days measured, or an annual projection
- its **assumptions**
- its **uncertainty**

## Run it

```bash
pip install -r requirements.txt
cd backend
python mock_data.py                              # only needed until the teammate's files exist
uvicorn app.api.main:app --reload --port 8000    # interactive docs: http://localhost:8000/docs
python -m pytest -q                              # tests
python -m app.export                             # writes out/*.json as a static fallback for the frontend
```

You can use `make api | test | export | mock` instead if `make` is installed. Copy `.env.example` to `.env` and add `ANTHROPIC_API_KEY` to get LLM-worded tips. Without a key the app uses template text, which contains the same numbers.

## Switching from mock data to the teammate's real files

1. The teammate writes `data/processed/clean_readings.csv` and `data/processed/anomalies.json`. The schemas are in [docs/data_contract.md](docs/data_contract.md).
2. Nothing else needs to change. With the default `FEC_DATA_SOURCE=auto`, the engine uses `processed/` as soon as **both** files exist, and falls back to `data/mock/` otherwise.
3. If the API is already running, call `POST /recompute` to reload. Check `GET /health` → `data_source` to see which data is in use.
4. You can force a source with `FEC_DATA_SOURCE=mock` or `FEC_DATA_SOURCE=processed`.

The engine does **not** clean data or detect anomalies. The loader only parses types, and turns impossible values into *unknown* (NaN) so they never quietly become zero. These are:

- occupancy higher than the resident count
- an outdoor temperature of −99
- missing prices

Each of these guards is counted in `/health` → `data_quality`.

## The two scores, in plain words

Each flat gets two scores from 0 to 100, both banded A (≥90), B (≥80), C (≥70), D (≥55), E (≥40), F (≥20) and G (below 20).

| | **Apartment Performance** (for the manager) | **Resident Actions** (for students) |
|---|---|---|
| Question it answers | How well does this flat perform overall, including its equipment? | How well are the residents doing with the things *they* control? |
| Pillars (weights) | Use 40%, Waste 25%, Timing 20%, Health 15% | Use 50%, Waste 30%, Timing 20% |
| Equipment faults | Included | **Removed**: residents are never scored on a broken fridge |

The pillars, each 0 to 100 where higher is better:

- **Use**: how much electricity the flat uses compared with the most efficient flats. The measure is kWh per day divided by √residents, because a shared fridge doesn't double when there are twice as many people. The benchmark is the 20th percentile of the flats, so being as good as the best fifth of flats gives 100.
- **Waste**: electricity used above the flat's normal base load while the occupancy sensor says nobody is home. Hours with unknown occupancy are not counted as "away". Heater-like use only counts once a person has confirmed it.
- **Timing**: whether flexible use, meaning anything above base load, runs in low-carbon hours. 100 means it runs in the cleanest hour of the day, and 0 means the dirtiest.
- **Health** (apartment score only): the share of electricity going to equipment faults that are at least *possible faults*.

The pillars are combined with a **weighted geometric mean**, so a very weak pillar can't be hidden by strong ones. The arithmetic mean is returned as well.

The score also comes with its **sensitivity**. The engine redraws the weights 2000 times, and the p5–p95 range shows how much the score and rank depend on the choice of weights.

## Claim levels: what we are allowed to say

| Status | Wording in the app | Who sets it |
|---|---|---|
| DETECTED | "unusual pattern" | Engine (default) |
| PLAUSIBLE | "possible fault" | Engine, when the detector's confidence is ≥ 0.7 **and** the pattern lasts ≥ 3 days |
| CONFIRMED | "confirmed" | A person: the technician reports `fault_found: true` |
| REPAIRED | "repaired, awaiting data" | A person: the work order is marked repaired |
| VERIFIED | "saving measured" | Only the verification step, after ≥ 7 days of post-repair data that shows a saving (90% interval above zero) |

Heating findings say "possible heating opportunity, needs confirmation" until a person confirms them.

Opening a work order does **not** change a finding's status. If the technician reports `fault_found: false`, the finding becomes DISMISSED ("checked, no fault found") and no longer counts in HEALTH. Residents are still not scored on it.

Every finding is assigned to someone:

- **manager**: equipment problems (`fault_step_change`, `peer_outlier`)
- **resident**: behaviour (`away_usage`, `night_baseload`, `peak_usage`)
- **unknown**: `heater_pattern`

## Numbers: measured vs projected

- **Measured over 28 days**: kWh, SEK and kgCO2e from the data.
  - SEK = kWh × spot price. This is the spot price only, excluding VAT, network fee and energy tax.
  - kgCO2e = kWh × the dataset's synthetic carbon factor ÷ 1000.
- **Savings**: the engine changes a *copy* of the data in a physically plausible way, re-runs itself with the same method, and reports the difference.
  - A fault returns to its baseline.
  - Peak load is moved to the cheapest hour within the next 12 hours, so kWh stays the same.
  - Use while nobody is home is reduced.
- **Annual**: always labelled **projection**. It is the 28-day value × 365/28 (× 182/28 for heater-like channels). The range is the wider of ±30% and a day-bootstrap. Its assumptions always include "October data only" and "spot price only".

Channel types such as "fridge-like" (A01), "dishwasher-like" (A04) and "heater-like" (A07) are **assumptions**. The dataset has no appliance labels.

## AI texts (wording only)

The AI never calculates anything. It only rewrites engine output as plain language, in four use cases:

- `finding_student`
- `finding_manager`
- `weekly_digest`
- `score_explainer`

**Choosing a provider:** set `FEC_LLM_PROVIDER` in `.env`.

| provider | what it does | needs |
|---|---|---|
| `template` (default) | our own wording from [phrases.json](backend/app/llm/phrases.json), with no network calls | nothing |
| `gonka` | Gonka broker, OpenAI-compatible, over plain HTTP | `GONKA_BROKER_API_KEY`, `GONKA_BROKER_URL`, `GONKA_MODEL` |
| `anthropic` | Claude | `ANTHROPIC_API_KEY` |

If the key is missing or the provider name is unknown, the app uses `template` and logs one warning. Keys belong **only in `.env`**, which is gitignored. Don't put them in `.env.example`, which is committed. API keys are never logged or returned. `GET /llm/status` shows `key_present: true/false`.

**How each text is made:**
1. The provider replies.
2. [validator.py](backend/app/llm/validator.py) checks the reply:
   - every number appears in the engine input
   - the wording matches the claim status
   - yearly values say "projected"
   - a load shift doesn't claim to save energy
   - there is no blame
   - appliance types are written as "-like"
   - the length limits hold
   - the priority and pillars match the engine
3. If the check fails, the provider gets one retry with the list of failures.
4. If it still fails, the app uses the `phrases.json` wording.

Every text carries:
- `source`: "llm" or "template"
- `provider`, `model` and `prompt_version`
- its validation report

**Commands:**
- `python -m app.llm.evaluate` writes the pass-rate table to `out/llm_eval.json`.
- `python -m app.export` fills `out/llm_cache.json`. That file is committed, so the demo shows the AI texts offline.
- `POST /llm/regenerate` clears cached texts.

## Layout

```
backend/app/core/       pure math: metrics, claims, attribution, pillars, score, sensitivity,
                        counterfactual, projection, verification (+ evaluate, dataset)
backend/app/services/   findings, workorders, reports, tips, live_prices, business_case, notifications
backend/app/llm/        prompts, schemas, validator, templates + phrases.json, generate, cache, evaluate,
                        providers/ (gonka, anthropic, template)
backend/app/api/        FastAPI routers (student, manager, prices)
backend/app/state.py    loaded data + views shared by the API and the export
backend/mock_data.py    mock data/processed files (same schema)
data/raw/               organiser files (never edited)
data/processed/         teammate output (the contract)
```

More detail: [docs/score_method.md](docs/score_method.md), [docs/claims_and_wording.md](docs/claims_and_wording.md), [docs/data_contract.md](docs/data_contract.md).

The entire dataset is synthetic. The numbers are fine for a demo, but they are not evidence of real-world savings.

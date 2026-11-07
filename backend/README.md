# Flat Energy Coach: backend and quantitative engine

One engine serves two interfaces:

- **Student:** sees only their own flat: scores, findings, savings, uncertainty, what-if scenarios.
- **Manager:** sees all flats: comparisons, possible equipment faults, maintenance, portfolio savings, evidence and data quality.

Both use **the same calculations**. Every number in the app comes from the engine; no demo result is hard-coded.

The data is the hackathon's synthetic dataset: 8 flats, SE3, hourly UTC readings 1–28 October 2026. The organisers' README and data dictionary are in the repository root ([README.md](../README.md), [DATA_DICTIONARY.md](../DATA_DICTIONARY.md)). Those files are never edited and are hash-checked.

## Run it

```bash
pip install -r requirements.txt
make pipeline        # raw -> cleaned + validated data (data/processed/analytical_table.csv) + research outputs
make api             # http://localhost:8000/docs
make test            # mathematical suite + backend suite
make engine          # out/*.json static fallback for the frontend
```

Without `make`:

```bash
python analysis/clean_data.py
cd backend && uvicorn app.api.main:app --port 8000
```

**Data source (`FEC_DATA_SOURCE=auto`):**
1. `data/processed/analytical_table.csv`, the validated pipeline output.
2. `data/processed/clean_readings.csv`, the original long-format contract.
3. `data/mock/`, as a fallback.

`GET /health` shows which source is in use.

## How the engine works

Full method: [docs/score_method.md](../docs/score_method.md). Changes from the original engine and why: [docs/engine_changes.md](../docs/engine_changes.md).

1. **Hourly accounting** (`core/hourly.py`). Each flat is a 672 h × 7-channel matrix, where a missing reading stays missing and is never 0.
   - Interventions are operators on that hourly trajectory, combined in a fixed order (repair → reduction → shift), so savings are never double-counted.
   - Energy shifted into an hour with a missing reading is carried separately, so it is never lost.
2. **Detection** (`core/detect.py`). The engine finds patterns itself, each with a stated statistical criterion:
   - lasting step changes (day-permutation test);
   - an always-on load above every other flat in every week;
   - fixed-hour device blocks that persist with nobody home;
   - heater-like use with nobody home;
   - flexible runs in peak-price hours.
3. **Frozen references** (`core/references.py`). Benchmarks, local imputations of missing hours, peak hours (data-driven) and anomaly reference levels are fitted once on the baseline. Before/after comparisons therefore change only because the flat's own energy changed.
4. **Partition and pillars** (`core/pillars.py`). Each flat's energy splits into explained use + possible avoidable use + possible equipment fault, and each kWh counts in exactly one pillar:
   - Use: explained use;
   - Waste: possible avoidable use;
   - Health: possible equipment fault;
   - Timing: flexible kWh in peak hours.

   Saving energy can never lower any pillar, and another flat's data can never move your score.
5. **Savings** (`core/savings.py`). For each intervention the engine reports:
   - observed, expected baseline, unexplained excess, avoidable estimate and counterfactual kWh;
   - SEK by tariff, spot only;
   - kgCO₂e with hourly factors;
   - a 95 % day-bootstrap interval and a scenario range (kept separate);
   - before/after scores.

## Scores

| | **Apartment Performance** (manager) | **Resident Actions** (students) |
|---|---|---|
| Pillars (weights) | Use 40 %, Waste 25 %, Timing 20 %, Health 15 % | Use 50 %, Waste 30 %, Timing 20 % |
| Possible equipment faults | Health pillar | Excluded |
| Weather-driven heater use | In Use | Excluded (only heating with nobody home counts, in Waste) |

The pillars are combined with a weighted geometric mean. The arithmetic mean and a 2000-draw weight-sensitivity range (score and rank p5–p95) are also returned.

## Claim levels

| Status | Wording | Set by |
|---|---|---|
| DETECTED | "unusual pattern" | Engine |
| PLAUSIBLE | "possible fault" | Engine, only when the detector's stated criterion holds and the pattern lasts at least 3 days (no probability is claimed) |
| CONFIRMED | "confirmed" | A person (manager opens a work order) |
| REPAIRED | "repaired, awaiting data" | A person |
| VERIFIED | "saving measured" | Verification only: at least 7 days of post-change data, 90 % interval above zero |

## Numbers

- **Measured:** kWh, SEK (spot only: excl. VAT, network fee, energy tax) and kgCO₂e (synthetic operational factor).
- **Savings:** each comes with its observed window. It is 28 days, except a fault, which only counts from its start (F002: 14 days).
- **SEK depends on the tariff:**
  - hourly spot: exact;
  - monthly average: time-average price, reductions only;
  - fixed: the student's own price;
  - included in rent: 0 SEK to the student.
  - Load shifting is worth 0 SEK on anything but an hourly tariff.
- **Annual:** a labelled projection, given only for persistent equipment and base-load patterns (mean daily saving × 365, day-bootstrap range). Heating and timing are not extrapolated.

## Layout

```
backend/app/core/       hourly, detect, references, pillars, score, evaluate, interventions, savings, valuation,
                        counterfactual, projection, metrics, verification, claims, attribution, sensitivity
backend/app/services/   findings, workorders, reports, tips (LLM rewording only; template fallback), live_prices, business_case
backend/app/api/        FastAPI routers (student, manager, prices) - see docs/api_for_frontend.md
backend/app/state.py    loaded data + views shared by the API and the export
analysis/               cleaning pipeline, research, independent audit suite (score_audit/), shared accounting shim
tests/math/             independent mathematical invariants + reproduction of validated results
backend/tests/          backend behaviour, API, and regression tests for every audited defect
```

The entire dataset is synthetic. The numbers are fine for a demo, but they are not evidence of real-world savings.

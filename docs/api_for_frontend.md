# Backend API for the frontend

Run it with `make api`, or `cd backend && uvicorn app.api.main:app --port 8000`. The OpenAPI docs are at `http://localhost:8000/docs`.

Real responses, generated from the validated data, are in [`docs/api_examples/`](api_examples/). `make examples` regenerates them; they are reproducible byte for byte.

**Offline fallback:** `make engine` writes `out/*.json` in the same shapes.

**General rules:**
- Everything is JSON, and NaN is sent as `null`.
- All timestamps are UTC, `[start, end)`. Convert to Europe/Stockholm for display. 25 October has 25 local hours.
- Both interfaces use the same calculations. The student view is a filter of the same numbers the manager sees.

## Student interface (one flat)

Send `X-Flat-Id: F00x`. If it doesn't match the path you get 403; this is a demo guard, not auth.

| Method | Path | Use it for | Example |
|---|---|---|---|
| GET | `/flats` | flat selector (id, residents, area) | `GET_flats.json` |
| GET | `/flats/{id}/scores` | the two lenses, pillars, band, rank, sensitivity, benchmark, partition | `GET_flats_F002_scores.json` |
| GET | `/flats/{id}/breakdown` | kWh / SEK / kgCO₂e per channel, daily series | `GET_flats_F002_breakdown.json` |
| GET | `/flats/{id}/findings` | finding cards (see below) | `GET_flats_F002_findings.json` |
| POST | `/flats/{id}/findings/{fid}/report` | "report to manager", body `{"message": "..."}` | |
| POST | `/flats/{id}/scenarios` | what-if calculator | `POST_flats_*_scenarios_*.json` |
| GET | `/flats/{id}/tips` | short tips (LLM rewording; template fallback) | `GET_flats_F002_tips.json` |
| GET | `/flats/{id}/notifications` | | |
| GET | `/prices/today?hourly_contract=true` | live SE3 prices (only shown for hourly contracts) | |

### Scores (`lenses.apartment`, `lenses.resident`)
Each lens has:
- `score` (weighted geometric mean, 0–100), `band` (A–G), `rank` and `of`;
- `pillars` {use, waste, timing, health (apartment only)} and `weights`;
- `arithmetic_mean`;
- `sensitivity` {score_p5, score_p95, rank_p5, rank_p95};
- `excludes`.

Show the resident lens to students. The apartment lens is "how the flat performs" and includes possible equipment faults that students are not scored on.

### Finding card (main unit)
| Field | Show as |
|---|---|
| `title`, `wording` | Show both verbatim. Never upgrade the wording; see [claims_and_wording.md](claims_and_wording.md) |
| `assumed_type` | Display with "-like" (e.g. "fridge-like") and mark it as an assumption |
| `responsibility_note`, `counts_as` | Who can act on it; which pillar it counts in |
| `evidence.text`, `evidence.statistics` | Evidence. `confidence` is always `null`: show no percentages |
| `quantities` | Ladder: `observed_kwh`, `expected_baseline_kwh`, `unexplained_excess_kwh`, `avoidable_estimate_kwh`, `counterfactual_kwh`, `kwh_moved` (shifts), `labels` |
| `avoidable_28d` | {kwh, sek, co2_kg, window_days, label "potential (if followed fully)", kind: `reduction` or `shift`}. `sek` is "if hourly spot" |
| `valuation` | `sek_by_tariff` for each tariff, plus `label` (spot only, not a bill saving). Let the student pick their tariff |
| `uncertainty` | `sampling_ci95` (day bootstrap) and `scenario_range` (parameter grid). Show them separately, never merged |
| `score_if_fixed` | before → after for each lens |
| `projection_annual` | Only when `value` is not null. Always labelled "projection", with low–high. Otherwise show the `reason` |
| `tiers` | potential / estimated_realized / verified |
| `simulated` | If true, show "simulated" |

### Scenario calculator: `POST /flats/{id}/scenarios`
```json
{"scenario": "return_to_baseline", "params": {"anomaly_id": "BL-F005-A06", "params": {"avoidable_fraction": 0.5}}}
{"scenario": "shift_flexible_load", "params": {"channel": "A04", "params": {"share_moved": 0.5, "quiet_hours": [22, 23, 0, 1, 2, 3, 4, 5, 6]}}}
{"scenario": "reduce_away_usage", "params": {"fraction": 0.5}}
{"scenario": "apply_interventions", "params": {"items": [{"anomaly_id": "FS-F002-A01"}, {"anomaly_id": "PK-F002-A04"}],
                                              "tariff": {"type": "fixed_price", "fixed_price_sek_per_kwh": 1.2}}}
```
- **Parameters per type:** see `PARAMS` in `backend/app/core/interventions.py` and the table in [score_method.md §5](score_method.md). `adoption` (0–1) is accepted by every type. Unknown parameters return 400.
- **Tariff `type` values:** `hourly_spot`, `monthly_average_spot`, `fixed_price` (needs `fixed_price_sek_per_kwh`), `included_in_rent`, `unknown`.
- **Response:**
  - `delta_28d` (negative = saving) and `before`, `after`, `score_change`;
  - `ladder`, `valuation`, `uncertainty`, `window`, `kind`, `projection_annual`, `assumptions`;
  - `overlap`: {kwh, sek_spot_hourly, co2e_kg} = sum of individual items − combined; 0 when they are disjoint;
  - `missing_hour_moves`: kWh shifted into hours with no reading. It is kept and is never lost.

## Manager interface (all flats)

| Method | Path | Use it for | Example |
|---|---|---|---|
| GET | `/portfolio` | comparison table, per-flat combined potential, totals, maintenance list, data and evidence quality, references | `GET_portfolio.json` |
| GET | `/portfolio/findings?status=&responsibility=` | all findings, sorted by 28-day potential SEK | `GET_portfolio_findings_manager.json` |
| GET | `/references` | frozen benchmarks (with hash) and what each detector found and why | `GET_references.json` |
| GET | `/reports`, `/notifications`, `/workorders` | inbox lists | |
| POST | `/workorders` | `{"finding_id": "FS-F002-A01"}` → the finding becomes CONFIRMED | |
| PATCH | `/workorders/{id}` | `{"status": "sent" \| "repaired"}` | |
| POST | `/workorders/{id}/verify` | `{"post_readings": [...]}` or `{"simulate": true}` (flagged `simulated`) | |
| GET/POST | `/business-case/reference`, `/business-case` | business-case inputs (all explicit) | |
| GET | `/health`, POST `/recompute` | data source and quality; reload | `GET_health.json` |

**`portfolio.flats[]`** contains:
- `flat_id`, `residents`, `floor_area_m2`;
- `apartment_score`, `apartment_band`, `apartment_rank`, `resident_score`, `resident_band`, `health`;
- `open_findings`, `open_manager_findings`;
- `kwh_28d`, `sek_28d`, `co2_kg_28d`, `coverage`, `comparison`, `combined_potential`.

**`portfolio.potential`** is the sum of each flat's combined potential. Flats are disjoint, so there is no double counting. It is simulated, not verified.

## Anomaly IDs
Detected anomalies are stable across runs. IDs are `{type prefix}-{flat}-{channel}`:

| Prefix | Type |
|---|---|
| `FS` | step change |
| `BL` | base load |
| `SB` | scheduled block |
| `HU` | heater use while away |
| `PK` | peak timing |

On the current data: `FS-F002-A01`, `SB-F004-A05`, `BL-F005-A06`, `HU-F007-A07`, `PK-F00x-A04` (all 8 flats) and `PK-F00x-A03` (F001, F002, F003, F005, F008).

## Display notes
- **SEK:** always "spot-energy component only, not a bill saving". With tariff `unknown`, show `sek_if_hourly_spot` labelled "if you have an hourly spot contract".
- **Per-resident numbers:** averages for the flat, labelled as such.
- **Peak hours** are local hours {7, 8, 9, 17, 18, 19, 20}; see `/references`.
- **Do not show:** "% confidence", or annual numbers without the "projection" label.

# Data contract

## data/processed/ (written by the pipeline, read by the engine)

### clean_readings.csv
| column | type | rule |
|---|---|---|
| flat_id | str | `F001`..`F008` |
| appliance_id | str | `F001-A01` .. `F008-A07` |
| channel | str | `A01`..`A07` (derived from appliance_id if absent) |
| timestamp_utc | ISO 8601 UTC | interval start, `2026-10-01T00:00:00Z` ≤ t < `2026-10-29T00:00:00Z` |
| kwh | float | energy in that hour, **empty/NaN = missing, never 0** |

One row per (appliance_id, timestamp_utc). The engine drops duplicate keys (keeps first) and counts them in `/health`.

### anomalies.json
```json
[{"id": "AN001", "flat_id": "F003", "appliance_id": "F003-A01",
  "type": "fault_step_change",
  "start": "2026-10-12T00:00:00Z", "end": "2026-10-29T00:00:00Z",
  "excess_kwh": 44.99, "baseline_kwh_per_h": 0.070, "observed_kwh_per_h": 0.181,
  "confidence": 0.92, "evidence": "free text shown to users"}]
```
- `type` ∈ `fault_step_change | peer_outlier | heater_pattern | away_usage | night_baseload | peak_usage`
- window is **[start, end)**: end is exclusive (UTC)
- `baseline_kwh_per_h` = pre-anomaly normal rate (or peer median); `observed_kwh_per_h` = mean rate inside the window
- `confidence` ∈ [0, 1]; the engine turns it into a claim level (≥ 0.7 and ≥ 3 days → PLAUSIBLE)
- for `away_usage` the engine applies the baseline cap only to hours with `occupants_home == 0`; for `night_baseload` only to local 00–06

### cleaning_log.json (optional)
Any JSON; passed through to `/health` → `data_quality.cleaning_log`.

## API (all JSON; NaN → null)

| method | path | notes |
|---|---|---|
| GET | /health | data source, data-quality counters |
| GET | /flats | |
| POST | /recompute | reload files + recompute |
| GET | /flats/{id}/scores | both lenses, pillars, sensitivity, benchmark |
| GET | /flats/{id}/breakdown | per channel kWh/SEK/CO2 + `assumed_type`, daily series, annual projection |
| GET | /flats/{id}/findings | findings for this flat |
| POST | /flats/{id}/findings/{fid}/report | `{"message": "..."}` → manager inbox |
| POST | /flats/{id}/scenarios | `{"scenario": "return_to_baseline", "params": {"anomaly_id": "AN001"}}`, `shift_flexible_load` `{"channel": "A04"}`, `reduce_away_usage` `{"fraction": 0.5}` |
| GET | /flats/{id}/tips | |
| GET | /flats/{id}/notifications | |
| GET | /prices/today?hourly_contract=true | live SE3 (15-min intervals); `shown: false` otherwise |
| GET | /portfolio | all flats |
| GET | /portfolio/findings?status=&responsibility= | sorted by projected SEK |
| GET | /reports, /notifications, /workorders | manager lists |
| POST | /workorders | `{"finding_id": "AN001"}` → finding becomes CONFIRMED |
| PATCH | /workorders/{id} | `{"status": "sent" \| "repaired"}` (open → sent → repaired) |
| POST | /workorders/{id}/verify | `{"post_readings": [{"timestamp_utc", "kwh"}]}` or `{"simulate": true}` (flagged `simulated: true`) |
| GET | /business-case/reference | engine-measured reference values |
| POST | /business-case | all inputs explicit, see `BusinessCaseInput` in `backend/app/models.py` |

Student routes accept an optional `X-Flat-Id` header; if it doesn't match the path → 403 (demo guard, not auth).

## Finding object (main frontend unit)
`id, flat_id, appliance_id, channel, assumed_type (+ assumed_type_is_assumption), type, title,
status, status_level, wording, responsibility, responsibility_note, window{start,end,days},
evidence{text, confidence, baseline_kwh_per_h, observed_kwh_per_h, reported_excess_kwh},
avoidable_28d{kwh, sek, co2_kg, horizon, scenario, method},
score_if_fixed{apartment{before,after}, resident{before,after}},
projection_annual{kwh|sek|co2_kg: {label:"projection", value, low, high, factor, assumptions[]}},
assumptions[], uncertainty{}, verification, simulated`

## out/ (static fallback, `python -m app.export`)
`scores.json` and `breakdown.json` (keyed by flat), `findings.json` (list), `portfolio.json`, `tips.json` (keyed by flat). Same shapes as the API.

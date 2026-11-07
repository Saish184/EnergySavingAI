# Frontend integration handoff (Watt Wise → mina engine)

## Launch

| What | Command | Then open |
|---|---|---|
| **Demo, offline** (default; no backend needed) | `cd watt-wise-ts && npm install && npm run serve` (or `make web`) | http://localhost:5173 |
| Live engine | Terminal 1: `make api` (FastAPI on :8000). Terminal 2: `make web` | http://localhost:5173/?mode=live |
| Rebuild only | `cd watt-wise-ts && npm run build` | |
| Smoke test | with `make web` running: `cd watt-wise-ts && npm run smoke` (24 checks) | |
| Re-record offline data | `make fixtures` (after any engine change) | |

**Signing in:**
- **Student:** flat number, e.g. `2` → F002.
- **Manager:** any well-formed email and an 8+ character password.

The app must be served over http. Opening `index.html` as a file cannot load the fixtures.

## What was copied from Hugo

`origin/Hugo` `89158cc`, directory `watt-wise-ts/` only. It was copied verbatim in commit `f317045`; there was no merge.

- **Safety ref:** branch `mina-pre-frontend-backup` = `2ee36f8` (the state before the import).
- **Kept:** layout, visual identity, panels, cards, badges, login flow, accessible markup, esbuild + strict TypeScript.

## What changed

| Hugo's original | Now |
|---|---|
| `calc.ts`: own consumption profile, evening-shift and night-trim maths, adherence band, portfolio estimate (defects H1–H7) | **Deleted.** All numbers come from the engine through the API |
| `data.ts`: invented profile, prices, carbon, channel shares, alerts, data-source table | Text only (limitations). Numbers come from `/breakdown`, `/profile`, `/findings`, `/portfolio` |
| "Confidence: medium/low" | Removed. Finding `wording` is shown verbatim, plus evidence statistics |
| UTC hour labels; fixed UTC peak window | Europe/Stockholm display. Peak hours come from the engine (`peak_hours_local`) |
| Alert status kept in JS memory | Work orders through `POST/PATCH /workorders` and `/verify` (stored by the backend) |
| "No annual claims" vs engine projections | Projection shown only when the engine gives a value; otherwise the engine's reason |
| Google Fonts | System fonts (works offline) |
| `dist/` not committed | `dist/app.js` is committed so a fresh checkout runs |

**New frontend structure (`watt-wise-ts/src/`):**

| Path | Role |
|---|---|
| `config.ts`, `config.js` | `mode` (`mock` default, `live`) and `apiBase`. URL override: `?mode=live&api=http://host:8000`. There is no automatic live→mock fallback |
| `api/contracts.ts` | Response types taken from real responses |
| `api/client.ts` | The `Api` interface; `LiveApi` (timeout, `X-Flat-Id`, typed `ApiError`) |
| `api/mock.ts` | Same interface, serving recorded real responses. Unrecorded requests and state-changing actions fail clearly; nothing is approximated |
| `api/scenarioRequest.ts` | Builds scenario requests, plus the canonical key shared with the fixture recorder |
| `api/workorders.ts` | Work-order adapter: backend status → label and actions. Unknown statuses are shown verbatim |
| `api/texts.ts` | LLM seam (below) |
| `format.ts` | Units, rounding, Stockholm time, null → "not available" |
| `components/` | charts, findings, score, simulator, tariff, textCard |
| `student.ts`, `manager.ts` | The two views |

**Backend additions (additive and tested in `backend/tests/test_frontend_endpoints.py`; no existing number changed):**
- `GET /flats/{id}/profile`: measured hour-of-day profile (local clock hours, peak flag from the frozen references) and daily totals per local date. 25 Oct has 25 h; the first and last dates are partial. Daily sums use the engine's own `totals()`.
- `GET /interventions`: supported scenarios, tariffs and each intervention's documented parameter grid, so the UI offers only accepted values.
- `backend/scripts/frontend_fixtures.py`: records 500 real responses (2.4 MB, deterministic).

`docs/api_examples` regenerated with zero diff, so the engine numbers are unchanged.

## Endpoints used

**Student:** `/flats`, `/flats/{id}/breakdown`, `/profile`, `/scores`, `/findings`, `/tips`, `/notifications`, `POST /flats/{id}/scenarios`, `POST /flats/{id}/findings/{fid}/report`, `/interventions`.

**Manager:** `/portfolio`, `/portfolio/findings?responsibility=manager|resident|unknown`, `/workorders` (GET, POST, PATCH, verify), `/reports`, `/notifications`.

## Demo scenarios (checked by `npm run smoke` against the recorded engine output)

| Case | Shown |
|---|---|
| F002 overview | 173.4 kWh · 99.64 SEK spot · 6.91 kg CO₂e · resident score 82.0 |
| F002 fridge-like (`FS-F002-A01`) | 23.4 kWh avoidable over 14 days · 11.54 SEK *if hourly spot* · "possible fault" |
| F002 dishwasher (`PK-F002-A04`) | 0.00 kWh change (shift) · 6.48 SEK hourly spot · 0.00 SEK on monthly average |
| F007 heater | 9.19 kWh · no yearly figure (engine reason) · needs confirmation |
| Portfolio | 1,904.5 kWh · 1,010.71 SEK · 73.06 kg · combined potential 109.6 kWh |

**Also checked live:**
- fixed price 1.5 SEK/kWh on F002 fridge = 35.04 SEK, computed by the backend;
- work order open → sent → repaired → simulated verification, still there after a reload;
- backend down → error state with no numbers.

## Tariffs
- Money uses the engine's `valuation`: `sek` for the requested tariff, or `sek_by_tariff`. The frontend only selects among these.
- A fixed price is valued by the backend when the simulation runs with the student's price.
- A shift is worth 0 SEK on any non-hourly tariff (engine rule).

## Limitations
- **Security:** sign-in is browser-side, and `X-Flat-Id` is a demo guard. This is **not authentication or authorization**. Manager routes and `/llm/*` (when added) have no access control. CORS is `*` for local development.
- **Storage:** work orders and reports live in backend memory and are lost on restart.
- **Offline mode:**
  - only recorded scenario combinations: each finding with defaults or one non-default grid value, adoption 0.5, all findings together, shift A03/A04, away 50/100 %, under unknown, hourly spot, monthly average and included-in-rent tariffs;
  - fixed price, other combinations, work orders and reports need live mode.
- **Tips:** only the top 3 findings per flat have text (that's the backend's limit).
- **Data:** synthetic data. Appliance identities are inferred.

## Pending LLM integration (Saish)
- `api/texts.ts` is the only place to change.
- **Available today:** student finding text from `/tips` (`source`: llm or template).
- **Unavailable today:** manager summaries, digests and score explanations render an explicit "Not connected yet" card, not invented text.
- **When his contract is final:** map `student_text`, `manager_text`, the score explainer and the digest in `texts.ts`. `components/textCard.ts` already shows the source badge (AI-worded vs standard wording) and the unavailable state. Saish's `DISMISSED` / `fault_found` work-order outcome goes into `api/workorders.ts`.

## Test results (at commit)

| Check | Result |
|---|---|
| `tsc --noEmit` | pass |
| `npm run build` | pass (dist/app.js ≈ 82 kB) |
| Browser smoke test (headless Chromium, offline mode) | 24/24 checks pass, including 375 px layout and no console errors |
| Backend tests | 70 passed (63 existing + 7 new) |
| Math tests | 50 passed, 11 skipped (need the original-engine checkout) |
| Fixture recording twice | byte-identical index |

## Final team integration
1. Keep `mina` as the base.
2. Saish rebases his `llm/` package onto `mina` and exposes texts as additive fields.
3. Map those fields in `watt-wise-ts/src/api/texts.ts`.
4. Run `make fixtures`, `npm run build` and `npm run smoke`.

`origin/Hugo`, `origin/saish` and `main` were not modified.

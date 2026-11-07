# Frontend + LLM integration handoff (Watt Wise × mina engine × Saish's LLM layer)

## Launch

| Mode | Command | Open |
|---|---|---|
| **Offline demo** (presentation fallback: no Python, no LLM) | `cd watt-wise-ts && npm install && npm run serve`, or `make web` | http://localhost:5173 |
| **Live** (FastAPI engine and LLM layer, same origin) | `make api`, which runs `cd backend && uvicorn app.api.main:app --port 8000` | http://localhost:8000/app/ |
| Live, with the frontend served separately | `make api` and `make web` | http://localhost:5173/?mode=live |

**Signing in:**
- **Student:** flat number, e.g. `2` → F002.
- **Manager:** any email and an 8+ character password.

This sign-in is a **demo, not security** (see Limitations).

`config.js` picks the mode: served by the backend under `/app` it uses live mode; served on its own it uses offline mode. `?mode=` and `?api=` override that. Live mode never falls back to offline data: if the backend is down, the page shows an error and no numbers.

## Branches and commits

| Ref | Meaning |
|---|---|
| `mina` (this work) | Engine + Hugo's frontend + Saish's LLM layer |
| `mina-pre-frontend-backup` = `2ee36f8` | Engine before the frontend |
| `mina-offline-demo-checkpoint` = `1958d4d` | The working offline demo before the LLM integration |
| `f317045` | Hugo's `watt-wise-ts/` imported verbatim (`origin/Hugo` `89158cc`) |
| `origin/saish-llm-integration` `26a6292` | Saish's LLM layer on `mina@2ee36f8`, **cherry-picked** (backend, docs, tests) |
| `origin/saish-llm-integration` `4f83c70` | Saish's own frontend wiring: **not taken**, because it competes with ours. Only its idea of serving the app at `/app` from FastAPI was adopted (a few lines in `api/main.py`); `demo.html` was not |

`origin/Hugo`, `origin/saish`, `origin/saish-llm-integration` and `main` are unchanged. Nothing has been pushed.

## What is integrated

**Engine (Mina):** unchanged.
- `docs/api_examples` regenerate with identical values. Only the tip wording changed, now Saish's validated v2 text.
- All 500 earlier fixtures keep every value: 440 scenarios plus the GET views.

**Additive backend endpoints from this work:**
- `GET /flats/{id}/profile`: local-time hourly profile and Stockholm daily totals (DST-aware);
- `GET /interventions`: scenario, tariff and parameter grid;
- the fixture recorder `backend/scripts/frontend_fixtures.py` (now 510 fixtures, deterministic).

**LLM layer (Saish, `backend/app/llm/`):**
- Engine fields go into a FactSheet. The model writes only `{PLACEHOLDERS}`; the backend inserts engine display strings.
- A 21-check validator runs before anything is shown.
- Fallback order: cache → provider → our wording (`phrases.json`) → safe text.
- Dashboard GETs never wait for a provider; generation runs in the background.
- There is no automatic model switch after a refusal (decision 5).
- Providers: `template` (default), `gonka`, `anthropic`.

**Work orders:** Saish's lifecycle is adopted, and it is a **behaviour change**:

| Event | Effect |
|---|---|
| Opening a work order | Does **not** confirm the finding |
| Technician `fault_found: true` | CONFIRMED |
| Technician `fault_found: false` | DISMISSED, which leaves every pillar; work order `closed_no_fault` |
| `repaired` | REPAIRED |
| Simulated verification | Flagged SIMULATED |

Frozen references are not refitted (a recompute does not reload them), so other flats' scores don't move.

**Frontend (Hugo's design kept):**
- typed API layer: `src/api/*`, `src/config.ts`, `src/format.ts`;
- components: charts, findings, score, simulator, tariff, textCard;
- student and manager views.

**Text placement in the UI** (source shown on every card: "AI explanation · checked", "Standard explanation" or "Safe short wording"):

| Text | Field | Where |
|---|---|---|
| Student finding explanation, next step and question | `finding.student_text` | Finding cards |
| 28-day digest | `GET /flats/{id}/digest` | Above the findings |
| Score explanation | `scores.explainer` | Score panel (replaces "Not connected yet") |
| Manager summary, evidence points and suggested check | `finding.manager_text` | Maintenance cards |
| Maintenance triage | `finding.triage` | Maintenance cards |
| Portfolio summary | `GET /portfolio/summary` | Manager overview |

There is no chatbot; none exists in the backend. `docs/llm_integration.md` §10 describes the design for one.

## LLM configuration (`.env`, gitignored)

```
FEC_LLM_PROVIDER=template          # template (default) | gonka | anthropic
GONKA_BROKER_API_KEY=...           # gonka
ANTHROPIC_API_KEY=...              # anthropic
FEC_ADMIN_TOKEN=...                # enables POST /llm/warm and /llm/regenerate
```

A missing key falls back to `template`. `GET /llm/status` shows the provider and `key_present`, never the key.

To pre-generate AI texts for the demo, set a key and run `cd backend && python -m app.export`, which fills `out/llm_cache.json`. Then run `make fixtures` to record them for offline mode. **Not run here:** no provider key is available in this environment, and no paid calls were made. The offline demo therefore shows our validated standard wording, labelled as such.

## Endpoints used by the frontend

**Student:**
- `/flats`, `/flats/{id}/breakdown`, `/profile`, `/scores` (+ explainer), `/findings` (+ student_text);
- `/digest`, `/notifications`, `/tips`;
- `POST /flats/{id}/scenarios`, `POST /flats/{id}/findings/{fid}/report`;
- `/interventions`.

**Manager:**
- `/portfolio`, `/portfolio/summary`, `/portfolio/findings?responsibility=…` (+ manager_text, triage);
- `/workorders` (GET, POST, PATCH `{status | fault_found}`, `/verify`);
- `/reports`, `/notifications`.

**Status:** `/health`, `/llm/status`.

## Validated scenarios (same numbers offline and live)

| Case | Result |
|---|---|
| F002 overview | 173.4 kWh · 99.64 SEK spot · 6.91 kg · resident score 82.0 |
| F002 fridge-like | 23.4 kWh over **14 days**; 11.54 SEK *if hourly spot*; "possible fault"; projection 609 kWh / 301 SEK per year (range 264–337 SEK), labelled as a projection |
| F002 dishwasher | **0.00 kWh** change, 12.94 kWh moved; 6.48 SEK hourly spot; **0.00 SEK** on a monthly average; resident score 82.0 → 88.9 |
| Fixed price 1.5 SEK/kWh, F002 fridge (live) | 35.04 SEK, valued by the backend |
| F007 heater | 9.19 kWh; no yearly figure; needs confirmation |
| Portfolio | 1,904.5 kWh · 1,010.71 SEK · 73.06 kg; combined potential 109.6 kWh / 135.13 SEK if hourly spot / 6.31 kg |

**Sustainability case:** `make case` writes `reports/sustainability_case.md`. Summary:
- 5.8 % of observed kWh could be avoided (indicative, since windows are 14–28 days);
- manager-owned versus resident-controlled actions are split;
- shifts are reported as 0 kWh;
- annual projections only for F002, F004 and F005;
- per-resident figures are averages within each flat.

## Test results (at commit)

| Check | Result |
|---|---|
| `npm run typecheck`, `npm run build` | pass |
| Smoke test, offline (`npm run smoke`) | **30/30** |
| Same smoke test, live via `/app` | **30/30**, so offline and live numbers are identical |
| Live flows on a fresh backend (`npm run live-flows`) | **11/11**: work order open (stays PLAUSIBLE) → sent → fault found (CONFIRMED) → repaired → simulated verification, persisted; backend outage shows an error with no numbers; mobile student and desktop manager layouts |
| LLM unavailable (gonka, fake key, unreachable URL) | GETs answer in about 0.01 s with validated standard wording; the provider error is recorded; the key is never in status or logs; numbers unchanged |
| Backend tests | **98 passed** (Mina 63, frontend endpoints 7, Saish 28; 1 of Mina's updated by Saish for the new work-order flow) |
| Math suite | 50 passed, 11 skipped (need the original-engine checkout) |

## Limitations
- **Security:** no authentication or authorization. Browser sign-in and `X-Flat-Id` are demo filters. Manager routes are open; LLM admin routes need `FEC_ADMIN_TOKEN`. CORS is `*`. Synthetic data only.
- **Storage:** work orders, reports and the LLM background queue live in backend memory and are lost on restart.
- **Offline mode:**
  - only recorded scenario combinations; others, and a fixed price with your own value, say "needs live mode";
  - work orders and reports are disabled offline.
- **AI texts:** no AI-written text has been generated yet (no key here). The validator is pattern-based; review new phrasings (see `docs/llm_integration.md` §8).
- **Committed bundle:** `dist/app.js` is committed although `dist/` is gitignored, so it shows as modified after a rebuild. Commit it after frontend changes.

## Presentation readiness
- **Fallback:** `npm run serve` works with no backend and no internet (system fonts, local fixtures).
- **Live demo:** `make api` → http://localhost:8000/app/. For AI-written text, set a provider key and warm the cache first.

Watt Wise (TypeScript) - LIVE EDITION, connected to the backend engine
=====================================================================
Every number now comes from the backend (Mina's audited engine); every text is validated
against those numbers (app/llm). src/calc.ts and the placeholder data were removed: the
frontend never calculates savings, scores or projections.

RUN
  cd backend && uvicorn app.api.main:app --port 8000
  open http://localhost:8000/app/          (served by the backend, same origin)
  or open watt-wise-ts/index.html directly  (talks to http://localhost:8000; set window.WATT_API to change)

BUILD (after editing src/)
  cd watt-wise-ts && npm install && npm run build      -> dist/app.js (committed for the demo)

WHAT CHANGED vs Hugo's provisional version
  src/api.ts       typed client for the backend endpoints (docs/api_for_frontend.md)
  src/types.ts     backend response shapes
  src/student.ts   score ring + pillars + explainer, 28-day overview, finding cards (validated text,
                   engine figures, tariff selector, report/confirm), "What if?" slider that asks the
                   engine to re-run a scenario, measured usage per day and per appliance
  src/manager.ts   portfolio summary + KPIs, flats table (both lenses, health), findings split into
                   maintenance vs residents, work-order flow (open -> sent -> fault found / no fault ->
                   repaired -> verify with simulated data, labelled)
  src/ui.ts        shared components (badges, score ring, KPI tiles, "where the numbers come from")
  live.css         depth, motion, dark mode and the new components (styles.css tokens kept)
  Login (auth.ts, login.ts) unchanged: still DEMO MODE, not secure (see below).

Watt Wise (TypeScript) - login plus provisional Student and Manager views
AI for Energy Saving hackathon

QUICK START
  Unzip and open index.html in a browser. dist/app.js is already built.

SIGNING IN (DEMO MODE)
  Students:  type a flat number, e.g. 3, 03, F3 or F003. No password.
             Valid flats are F001 to F008. The student sees only that flat.
  Managers:  email + password. In demo mode any well-formed email and a
             password of 8+ characters works. There are no real accounts.
  The session lasts until the tab is closed (sessionStorage). "Sign out"
  is in the top right.

IMPORTANT: THIS LOGIN IS NOT SECURE YET
  Everything runs in the browser, so anyone can read the code, skip the
  login or open the manager view. It is a design and flow demo.
  Also, a flat number is not a secret: with flat-number-only login, any
  student can type another flat's number. Before real use:
    1. Replace loginManager in src/auth.ts with a call to a server that
       checks the password and returns a signed session.
    2. Check the role on the server for every request, not in the page.
    3. Consider adding something only the student's household knows
       (for example a short code printed on the lease or sent by the manager).

CHANGING THE CODE
  npm install
  npm run build        (typechecks with tsc, then bundles src/main.ts to dist/app.js)
  npm run watch        (rebuilds on save; run npm run typecheck separately)

FILES
  index.html        Page shell, header with user area, provisional banner
  styles.css        All styling
  dist/app.js       Built bundle (generated, do not edit)
  src/types.ts      Shared types (including Session)
  src/data.ts       PLACEHOLDER data and text content: edit this first
  src/auth.ts       Flat-number parsing, demo manager login, session storage
  src/login.ts      Login page (student / manager forms)
  src/calc.ts       Totals, scenarios, before/after ranges, portfolio estimate
  src/state.ts      Small shared state (session, flat, scenario, alert statuses)
  src/dom.ts        Helpers (escape, typed querySelector, number formatting)
  src/ui.ts         Shared pieces: badges, evidence lists, scenario controls, projection table
  src/student.ts    Student view
  src/manager.ts    Manager view
  src/main.ts       Entry point: shows login, then the view for the signed-in role
  tsconfig.json, package.json

WHAT EACH VIEW COVERS
  Student:  historical consumption by channel, potential savings scenarios,
            evidence-backed recommendations, before/after kWh, SEK, CO2e,
            score component placeholders, tariff and data limitations
  Manager:  historical consumption across flats, maintenance and efficiency
            opportunities, evidence-backed maintenance alerts, portfolio-level
            conditional savings, score comparison placeholders, data quality
            and responsibility labels

RULES BUILT IN
  - The score is provisional. Score values are placeholders ("-"), no ranking
    is shown, and a banner says it is not audited.
  - Projected savings are never shown as verified. Every saving is labelled
    "Projected - not verified" and shown as a range that assumes 50% to 100%
    of the planned change happens. This holds in the maintenance workflow too:
    confirming a fault on site does not turn a projected saving into a verified one.
  - Alerts are hypotheses with evidence, checks and a responsible owner.

PLACEHOLDERS TO REPLACE (src/data.ts)
  BASE_PROFILE, nightExtraKwh, CHANNELS shares: made-up demo values.
  Evidence items marked "Placeholder - analysis pending": fill in from the CSV analysis.
  ALERTS (flat and channel choices are arbitrary), DATA_SOURCES status text.
  Items marked "Read from the data file" come from hourly_prices.csv (price peaks,
  20 Oct spike). PRICE and CARBON are approximate hour-of-day averages in that
  file's style, not exact values.
  Flat residents and areas come from flats.csv.

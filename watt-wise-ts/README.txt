Watt Wise - student and manager views of the Flat Energy Coach engine
AI for Energy Saving hackathon (frontend by Hugo, connected to the mina engine)

RUN
  npm install
  npm run serve              -> http://localhost:5173  (offline: real engine responses in fixtures/)
  http://localhost:5173/?mode=live   uses the FastAPI backend on :8000 (start it with `make api`)
  npm run build / npm run typecheck / npm run smoke (with serve running)

SIGN IN (DEMO ONLY, NOT SECURITY)
  Student: flat number, e.g. 2 or F002.  Manager: any email + 8-character password.

All numbers come from the engine; this frontend computes none. Details:
docs/FRONTEND_INTEGRATION_HANDOFF.md

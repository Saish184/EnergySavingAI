# Flat Energy Coach - one coherent pipeline: raw data -> validated tables -> engine outputs -> audits -> tests.
# Run from the repository root.

pipeline:   ## raw organiser files -> cleaned, validated, joined data + research outputs
	python analysis/clean_data.py
	python analysis/validate.py
	python analysis/eda.py
	python analysis/opportunities.py
	python analysis/verify_opportunities.py
	python analysis/audit_consistency.py
	python analysis/math_review.py
	python analysis/math_experiments.py

engine:     ## engine outputs as static JSON (out/, git-ignored) for the frontend
	cd backend && python -m app.export

examples:   ## regenerate the committed API examples for the frontend docs
	cd backend && python -m scripts.api_examples

audit:      ## independent invariant audit + original-vs-improved comparison (original needs SAISH_BACKEND)
	python analysis/score_audit/audit_score.py $(if $(SAISH_BACKEND),--teammate,)
	python analysis/score_audit/compare_engines.py

test:       ## mathematical suite (tests/math) + backend suite (backend/tests)
	python -m pytest
	cd backend && python -m pytest -q

all: pipeline engine audit test

api:
	cd backend && uvicorn app.api.main:app --reload --port 8000

mock:
	cd backend && python mock_data.py

fixtures:   ## record real engine responses for the frontend's offline mode (watt-wise-ts/fixtures/)
	cd backend && python -m scripts.frontend_fixtures

web:        ## frontend at http://localhost:5173 (offline fixtures by default; ?mode=live uses `make api`)
	cd watt-wise-ts && npm install && npm run serve

web-build:
	cd watt-wise-ts && npm install && npm run build

web-smoke:  ## needs `make web` running
	cd watt-wise-ts && npm run smoke

.PHONY: pipeline engine examples audit test all api mock web fixtures web-build web-smoke

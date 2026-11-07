mock:
	cd backend && python mock_data.py

api:
	cd backend && uvicorn app.api.main:app --reload --port 8000

test:
	cd backend && python -m pytest -q

export:
	cd backend && python -m app.export

pipeline:
	python -m pipeline.clean && python -m pipeline.anomalies.run

web:
	cd frontend && npm run dev

.PHONY: mock api test export pipeline web

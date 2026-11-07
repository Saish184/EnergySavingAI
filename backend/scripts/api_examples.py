"""Write real API responses (from the engine on the validated data) to docs/api_examples/ for the frontend.
Volatile fields (timings, timestamps) are removed so the files are reproducible.   python -m scripts.api_examples"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["ANTHROPIC_API_KEY"] = ""                       # template tips -> deterministic

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs" / "api_examples"
VOLATILE = {"computed_seconds", "seconds", "created", "at", "history"}


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items() if k not in VOLATILE}
    if isinstance(o, list):
        return [clean(v) for v in o]
    return o


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with TestClient(app) as c:
        calls = {
            "GET_health.json": c.get("/health"),
            "GET_references.json": c.get("/references"),
            "GET_flats.json": c.get("/flats"),
            "GET_flats_F002_scores.json": c.get("/flats/F002/scores"),
            "GET_flats_F002_breakdown.json": c.get("/flats/F002/breakdown"),
            "GET_flats_F002_findings.json": c.get("/flats/F002/findings"),
            "GET_flats_F002_tips.json": c.get("/flats/F002/tips"),
            "POST_flats_F002_scenarios_combined.json": c.post("/flats/F002/scenarios", json={
                "scenario": "apply_interventions",
                "params": {"items": [{"anomaly_id": "FS-F002-A01"}, {"anomaly_id": "PK-F002-A04"}],
                           "tariff": {"type": "hourly_spot"}}}),
            "POST_flats_F005_scenarios_base_load_half.json": c.post("/flats/F005/scenarios", json={
                "scenario": "return_to_baseline",
                "params": {"anomaly_id": "BL-F005-A06", "params": {"avoidable_fraction": 0.5},
                           "tariff": {"type": "fixed_price", "fixed_price_sek_per_kwh": 1.5}}}),
            "GET_portfolio.json": c.get("/portfolio"),
            "GET_portfolio_findings_manager.json": c.get("/portfolio/findings", params={"responsibility": "manager"}),
        }
        for name, r in calls.items():
            assert r.status_code == 200, (name, r.text)
            (OUT / name).write_text(json.dumps(clean(r.json()), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print("wrote", OUT / name)


if __name__ == "__main__":
    main()

"""Record REAL backend responses as offline fixtures for the frontend's mock mode.

    cd backend && python -m scripts.frontend_fixtures          (or: make fixtures)

Every file is a verbatim API response from the engine on the validated data (volatile timestamps removed), so mock mode
shows exactly what live mode would show. Nothing is computed here. Scenario requests are recorded for the request
shapes the UI builds (see watt-wise-ts/src/api/scenarioRequest.ts); any other request is reported by the mock as
"needs the live backend" instead of being approximated.

The request key must match `scenarioKey()` in scenarioRequest.ts: JSON with sorted keys, no spaces, integral floats as
integers (1.0 -> 1), and only non-default intervention parameters.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

os.environ["ANTHROPIC_API_KEY"] = ""                       # deterministic template tips

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "watt-wise-ts" / "fixtures"
VOLATILE = {"computed_seconds", "seconds", "created", "at", "history", "path"}
TARIFFS = ["unknown", "hourly_spot", "monthly_average_spot", "included_in_rent"]   # fixed_price needs a user price -> live only
ADOPTION_VARIANTS = [0.5]


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items() if k not in VOLATILE}
    if isinstance(o, list):
        return [clean(v) for v in o]
    return o


def canon(o):
    """Integral floats -> int so Python and JavaScript produce the same key text."""
    if isinstance(o, dict):
        return {k: canon(v) for k, v in o.items()}
    if isinstance(o, list):
        return [canon(v) for v in o]
    if isinstance(o, float) and o.is_integer():
        return int(o)
    return o


def scenario_key(flat_id: str, scenario: str, params: dict) -> str:
    return json.dumps(canon({"flat_id": flat_id, "scenario": scenario, "params": params}), sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False)


def finding_variants(f: dict, grid: dict) -> list[dict]:
    """Default parameters, each single documented non-default grid value, and the adoption variants."""
    out = [{}]
    for k, spec in grid[f["type"]].items():
        for v in spec["grid"]:
            if v != spec["default"]:
                out.append({k: v})
    out += [{"adoption": a} for a in ADOPTION_VARIANTS]
    return out


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "get").mkdir(parents=True)
    (OUT / "scenarios").mkdir(parents=True)
    index = {"get": {}, "scenarios": {}}
    n = 0

    def save(sub: str, name: str, data) -> str:
        nonlocal n
        n += 1
        rel = f"{sub}/{name}.json"
        (OUT / rel).write_text(json.dumps(clean(data), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return rel

    with TestClient(app) as c:
        def get(path: str, params: dict | None = None):
            r = c.get(path, params=params)
            assert r.status_code == 200, (path, r.text)
            return r.json()

        flats = get("/flats")
        grid = get("/interventions")["parameters"]
        paths = ["/health", "/flats", "/references", "/interventions", "/portfolio", "/portfolio/findings",
                 "/workorders", "/reports", "/notifications"]
        for fl in [f["flat_id"] for f in flats]:
            paths += [f"/flats/{fl}/{p}" for p in ("scores", "breakdown", "profile", "findings", "tips", "notifications")]
        for p in paths:
            index["get"][p] = save("get", p.strip("/").replace("/", "_") or "root", get(p))
        for resp in ("manager", "resident", "unknown"):
            p = f"/portfolio/findings?responsibility={resp}"
            index["get"][p] = save("get", f"portfolio_findings_{resp}", get("/portfolio/findings", {"responsibility": resp}))

        def post(fl: str, scenario: str, params: dict):
            key = scenario_key(fl, scenario, params)
            if key in index["scenarios"]:
                return
            r = c.post(f"/flats/{fl}/scenarios", json={"scenario": scenario, "params": params})
            assert r.status_code == 200, (key, r.text)
            index["scenarios"][key] = save("scenarios", f"s{len(index['scenarios']):04d}", r.json())

        for fl in [f["flat_id"] for f in flats]:
            findings = get(f"/flats/{fl}/findings")
            for t in TARIFFS:
                tariff = {"type": t}
                for f in findings:
                    for v in finding_variants(f, grid):
                        params = {"anomaly_id": f["id"], "tariff": tariff}
                        if v:
                            params["params"] = v
                        post(fl, "return_to_baseline", params)
                if findings:
                    post(fl, "apply_interventions", {"items": [{"anomaly_id": f["id"]} for f in findings], "tariff": tariff})
                for ch in ("A03", "A04"):
                    post(fl, "shift_flexible_load", {"channel": ch, "tariff": tariff})
                for frac in (0.5, 1.0):
                    post(fl, "reduce_away_usage", {"fraction": frac, "tariff": tariff})

        refs = get("/references")["references"]
        index["meta"] = {"recorded_from": "live backend via FastAPI TestClient (scripts/frontend_fixtures.py)",
                         "references_hash": refs["hash"], "data_source": get("/health")["data_source"],
                         "tariffs_recorded": TARIFFS, "files": n}
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    size = sum(p.stat().st_size for p in OUT.rglob("*.json"))
    print(f"wrote {n} fixtures + index.json to {OUT} ({size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()

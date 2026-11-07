from app import config as C
from app.core.counterfactual import run_scenario
from app.core.projection import project
from app.services.findings import build_findings


def _walk(o, path=""):
    if isinstance(o, dict):
        yield path, o
        for k, v in o.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _walk(v, f"{path}[{i}]")


def _check_annual(obj):
    n = 0
    for path, d in _walk(obj):
        is_annual = d.get("horizon") == "annual" or "factor" in d or "annual" in path.split(".")[-1]
        if is_annual and "value" in d:
            n += 1
            assert d.get("label") == "projection", path
            assert d.get("assumptions"), path
            assert "October data only" in d["assumptions"], path
            assert "spot price only, excludes network fee, energy tax, VAT" in d["assumptions"], path
            assert d["low"] <= d["value"] <= d["high"] or d["value"] != d["value"], path
    return n


def test_project_labels():
    p = project(10.0, None, "kWh")
    assert p["label"] == "projection" and p["horizon"] == "annual" and p["assumptions"]
    assert abs(p["value"] - 10 * 365 / 28) < 1e-9
    h = project(10.0, None, "kWh", heater_like=True)
    assert abs(h["value"] - 10 * 182 / 28) < 1e-9


def test_every_annual_number_in_findings_is_projection(ds, ev):
    assert _check_annual(build_findings(ds, ev)) >= 3 * len(ds.anomalies)


def test_every_annual_number_in_scenarios_is_projection(ds, ev):
    res = [run_scenario(ds, "shift_flexible_load", {"flat_id": "F007", "channel": "A04"}, before=ev),
           run_scenario(ds, "reduce_away_usage", {"flat_id": "F002"}, before=ev)]
    assert _check_annual(res) == 6


def test_every_annual_number_in_api_outputs_is_projection():
    from fastapi.testclient import TestClient
    from app.api.main import app
    with TestClient(app) as c:
        n = 0
        for f in c.get("/flats").json():
            fid = f["flat_id"]
            for ep in ("scores", "breakdown", "findings"):
                n += _check_annual(c.get(f"/flats/{fid}/{ep}").json())
        n += _check_annual(c.get("/portfolio/findings").json())
        assert n > 0

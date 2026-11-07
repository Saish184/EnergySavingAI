import numpy as np

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
        is_annual = d.get("horizon") == "annual" or "annual" in path.split(".")[-1]
        if is_annual and "value" in d:
            n += 1
            assert d.get("label") == "projection", path
            assert d.get("assumptions"), path
            assert any("extrapolation" in a for a in d["assumptions"]), path
            assert "spot price only, excludes network fee, energy tax, VAT" in d["assumptions"], path
            if d["value"] is None:
                assert d.get("reason"), path
            else:
                assert d["low"] <= d["value"] <= d["high"], path
    return n


def test_project_labels():
    p = project(np.full(14, 1.0), "kWh", True)
    assert p["label"] == "projection" and p["horizon"] == "annual" and p["assumptions"]
    assert abs(p["value"] - 365.0) < 1e-9 and p["low"] <= p["value"] <= p["high"]
    q = project(np.full(14, 1.0), "kWh", False)
    assert q["value"] is None and q["reason"]


def test_only_persistent_patterns_are_extrapolated(ds, ev):
    for f in build_findings(ds, ev):
        v = f["projection_annual"]["kwh"]["value"]
        if f["type"] in ("heater_pattern", "peak_usage"):
            assert v is None
        else:
            assert v is not None and v > 0


def test_every_annual_number_in_findings_is_projection(ds, ev):
    assert _check_annual(build_findings(ds, ev)) >= 3 * len(ds.anomalies)


def test_every_annual_number_in_scenarios_is_projection(ds, ev):
    res = [run_scenario(ds, "shift_flexible_load", {"flat_id": "F007", "channel": "A04"}, before=ev),
           run_scenario(ds, "reduce_away_usage", {"flat_id": "F004"}, before=ev)]
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

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.services import live_prices


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        yield client


def test_common(c):
    assert c.get("/health").json()["ok"]
    assert len(c.get("/flats").json()) == 8


def test_student_endpoints(c):
    for ep in ("scores", "breakdown", "findings", "tips", "notifications"):
        r = c.get(f"/flats/F003/{ep}")
        assert r.status_code == 200, ep
    s = c.get("/flats/F003/scores").json()
    assert set(s["lenses"]) == {"apartment", "resident"}
    assert "health" not in s["lenses"]["resident"]["pillars"]
    b = c.get("/flats/F003/breakdown").json()
    assert all(ch["assumed_type"] for ch in b["channels"])
    for f in c.get("/flats/F003/findings").json():
        assert f["status"] and f["responsibility"] and f["wording"] and f["assumptions"]
    for t in c.get("/flats/F003/tips").json():
        assert t["source"] == "template" and t["text"] and t["prompt_version"]
    for f in c.get("/flats/F003/findings").json():
        assert f["student_text"]["source"] == "template" and f["student_text"]["prompt_version"]
        assert f["student_text"]["validation"]["passed"]
    for f in c.get("/portfolio/findings").json():
        assert f["manager_text"]["source"] == "template"
    d = c.get("/flats/F003/digest").json()
    assert d["source"] == "template" and len(d["output"]["bullets"]) == 3
    assert s["explainer"]["source"] == "template"


def test_student_own_flat_only(c):
    assert c.get("/flats/F003/scores", headers={"X-Flat-Id": "F001"}).status_code == 403
    assert c.get("/flats/F999/scores").status_code == 404


def test_scenarios(c):
    fid = c.get("/flats/F003/findings").json()[0]["id"]
    for body in ({"scenario": "return_to_baseline", "params": {"anomaly_id": fid}},
                 {"scenario": "shift_flexible_load", "params": {"channel": "A04"}},
                 {"scenario": "reduce_away_usage", "params": {"fraction": 0.5}}):
        r = c.post("/flats/F003/scenarios", json=body)
        assert r.status_code == 200, (body, r.text)
        assert set(r.json()["delta_28d"]) == {"kwh", "sek", "co2_kg"}
    assert c.post("/flats/F003/scenarios", json={"scenario": "teleport"}).status_code == 422
    other = [f for f in c.get("/portfolio/findings").json() if f["flat_id"] != "F003"][0]["id"]
    assert c.post("/flats/F003/scenarios",
                  json={"scenario": "return_to_baseline", "params": {"anomaly_id": other}}).status_code == 400


def test_report_to_manager(c):
    fid = c.get("/flats/F003/findings").json()[0]["id"]
    r = c.post(f"/flats/F003/findings/{fid}/report", json={"message": "fridge is loud"})
    assert r.status_code == 200
    assert any(x["finding_id"] == fid for x in c.get("/reports").json())


def test_manager_workflow_to_verified(c):
    pf = c.get("/portfolio").json()
    assert len(pf["flats"]) == 8
    fs = c.get("/portfolio/findings", params={"responsibility": "manager"}).json()
    sek = [f["projection_annual"]["sek"]["value"] for f in fs]
    assert sek == sorted(sek, reverse=True)
    fid = next(f["id"] for f in fs if f["status"] == "PLAUSIBLE")
    w = c.post("/workorders", json={"finding_id": fid}).json()
    f = next(x for x in c.get("/portfolio/findings").json() if x["id"] == fid)
    assert f["status"] == "PLAUSIBLE"                          # opening a work order confirms nothing
    assert c.post(f"/workorders/{w['id']}/verify", json={"simulate": True}).status_code == 400  # not repaired yet
    assert c.patch(f"/workorders/{w['id']}", json={"status": "repaired"}).status_code == 400   # must be sent first
    assert c.patch(f"/workorders/{w['id']}", json={"status": "sent"}).json()["status"] == "sent"
    assert c.patch(f"/workorders/{w['id']}", json={"fault_found": True}).json()["fault_found"] is True
    f = next(x for x in c.get("/portfolio/findings").json() if x["id"] == fid)
    assert f["status"] == "CONFIRMED"
    assert c.patch(f"/workorders/{w['id']}", json={"status": "repaired"}).json()["status"] == "repaired"
    f = next(x for x in c.get("/portfolio/findings").json() if x["id"] == fid)
    assert f["status"] == "REPAIRED" and f["wording"] == "repaired, awaiting data"
    assert c.post(f"/workorders/{w['id']}/verify", json={}).status_code == 400  # no data, no simulate
    short = [{"timestamp_utc": f"2026-10-29T{h:02d}:00:00Z", "kwh": 0.01} for h in range(24)]
    v = c.post(f"/workorders/{w['id']}/verify", json={"post_readings": short}).json()
    assert v["verification"]["status"] == "REPAIRED"
    v = c.post(f"/workorders/{w['id']}/verify", json={"simulate": True}).json()
    assert v["verification"]["simulated"] is True
    assert v["finding"]["status"] == "VERIFIED" and v["finding"]["simulated"] is True


def test_workorder_no_fault_found_dismisses(c):
    fs = [f for f in c.get("/portfolio/findings", params={"responsibility": "manager"}).json()
          if f["status"] in ("DETECTED", "PLAUSIBLE")]
    target = next(f for f in fs if f["status"] == "PLAUSIBLE") if any(f["status"] == "PLAUSIBLE" for f in fs) else fs[0]
    w = c.post("/workorders", json={"finding_id": target["id"]}).json()
    assert c.patch(f"/workorders/{w['id']}", json={"fault_found": False, "status": "repaired"}).status_code == 400
    r = c.patch(f"/workorders/{w['id']}", json={"fault_found": False}).json()
    assert r["status"] == "closed_no_fault"
    f = next(x for x in c.get("/portfolio/findings").json() if x["id"] == target["id"])
    assert f["status"] == "DISMISSED"


def test_business_case(c):
    body = {"flats": 100, "price_per_flat_sek_per_year": 300, "faults_per_flat_per_year": 0.3,
            "avg_fault_kwh": 500, "marginal_tariff_sek_per_kwh": 1.5, "who_pays_electricity": "landlord"}
    r = c.post("/business-case", json=body).json()
    assert r["inputs"]["price_per_flat_sek_per_year"]["label"] == "hypothesis"
    assert r["yearly_cost_sek"] == 30000 and r["avoided_cost_sek"] == 22500
    assert c.post("/business-case", json={**body, "who_pays_electricity": "nobody"}).status_code == 422


def test_prices(c, monkeypatch):
    assert c.get("/prices/today", params={"hourly_contract": False}).json()["shown"] is False

    def boom(*a, **k):
        raise ConnectionError("offline")
    monkeypatch.setattr(live_prices.requests, "get", boom)
    live_prices._cache.clear()
    r = c.get("/prices/today", params={"hourly_contract": True}).json()
    assert r["shown"] is False and r["message"] == "live prices unavailable"


def test_recompute(c):
    assert c.post("/recompute").json()["ok"]

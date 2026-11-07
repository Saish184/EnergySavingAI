"""Additive read-only endpoints used by the frontend: /flats/{id}/profile and /interventions.
They must not change any existing number and must agree with the existing measured totals."""
import math

import pytest
from fastapi.testclient import TestClient

from app.api.main import app


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        yield client


def test_profile_shape_and_dst(c):
    p = c.get("/flats/F002/profile").json()
    assert p["timezone"] == "Europe/Stockholm"
    assert [h["local_hour"] for h in p["hour_of_day"]] == list(range(24))
    assert sum(h["hours_in_period"] for h in p["hour_of_day"]) == 672
    days = {d["local_date"]: d for d in p["daily"]}
    assert days["2026-10-25"]["hours_in_period"] == 25          # DST ends: 02:00 occurs twice
    assert days["2026-10-01"]["hours_in_period"] == 22          # period starts 00:00 UTC = 02:00 CEST
    assert days["2026-10-29"]["hours_in_period"] == 1           # period ends 00:00 UTC = 01:00 CET
    assert not days["2026-10-29"]["complete_day"] and days["2026-10-25"]["complete_day"]
    assert sum(d["hours_in_period"] for d in p["daily"]) == 672


def test_profile_daily_sums_equal_measured_totals(c):
    for fl in ("F002", "F005", "F007"):
        p = c.get(f"/flats/{fl}/profile").json()
        t = c.get(f"/flats/{fl}/breakdown").json()["totals"]
        assert sum(d["kwh"] for d in p["daily"]) == pytest.approx(t["kwh"], abs=2e-3)
        assert sum(d["sek"] for d in p["daily"]) == pytest.approx(t["sek"], abs=2e-3)
        assert sum(d["co2_kg"] for d in p["daily"]) == pytest.approx(t["co2_kg"], abs=2e-3)


def test_profile_peak_flags_follow_references(c):
    p = c.get("/flats/F001/profile").json()
    ref = c.get("/references").json()["references"]["peak_hours_local"]
    assert [h["local_hour"] for h in p["hour_of_day"] if h["is_peak"]] == ref == p["peak_hours_local"]
    for h in p["hour_of_day"]:
        if h["mean_kwh"] is not None:
            assert h["mean_kwh"] == pytest.approx(sum(v for v in h["mean_kwh_by_channel"].values()), abs=1e-3)
            assert math.isfinite(h["mean_spot_sek_per_kwh"])


def test_profile_respects_student_header_guard(c):
    assert c.get("/flats/F002/profile", headers={"X-Flat-Id": "F003"}).status_code == 403
    assert c.get("/flats/F999/profile").status_code == 404


def test_interventions_lists_engine_parameters(c):
    from app.core import interventions as IV
    from app.core.valuation import TARIFFS
    r = c.get("/interventions").json()
    assert set(r["tariffs"]) == set(TARIFFS)
    assert "apply_interventions" in r["scenarios"]
    for t, ps in IV.PARAMS.items():
        for k, (default, grid) in ps.items():
            assert r["parameters"][t][k] == {"default": default, "grid": grid}
    assert r["kind"]["peak_usage"] == "shift" and r["kind"]["base_load_outlier"] == "reduction"


def test_additive_endpoints_do_not_change_numbers(c):
    before = c.get("/portfolio").json()["totals"]
    c.get("/flats/F002/profile")
    c.get("/interventions")
    assert c.get("/portfolio").json()["totals"] == before


def test_local_daily_partition_is_exact_in_process(loaded):
    """Unrounded: local-date windows partition the 672 h, so their sums equal the period totals exactly."""
    from app.core import metrics
    from app.core.hourly import totals
    for fl, fd in loaded.flats.items():
        prof = metrics.local_profile(fd, set(loaded.refs.peak_hours))
        t = totals(fd)
        assert sum(d["kwh"] for d in prof["daily"]) == pytest.approx(t["kwh"], rel=1e-12)
        assert sum(d["sek"] for d in prof["daily"]) == pytest.approx(t["sek_spot_hourly"], rel=1e-12)

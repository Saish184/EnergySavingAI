"""Audit of the teammate's engine (branch saish, commit ddc02ce) on our validated data.

Skipped unless $SAISH_BACKEND points to a read-only checkout of that branch's backend/ folder.
Confirmed defects are encoded as xfail(strict=True): the test states the REQUIREMENT; it is expected to fail on
ddc02ce. If a later commit fixes the defect the test XPASSes, which pytest reports as a failure (strict), so the
review list is updated deliberately rather than silently.
"""
import os

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("SAISH_BACKEND"), reason="SAISH_BACKEND not set (teammate engine checkout)")


@pytest.fixture(scope="module")
def S():
    import saish_engine
    return saish_engine


@pytest.fixture(scope="module")
def engine(S):
    C, loader, evaluate, cf, Dataset = S._import()
    ds = S.dataset(variant="A_O2_as_resident")
    return {"C": C, "evaluate": evaluate, "cf": cf, "ds": ds, "before": evaluate.evaluate(ds, with_sensitivity=False)}


@pytest.fixture(scope="module")
def audits(S, flats):
    import invariants as inv
    return {lens: inv.run_all(S.SaishLensModel(lens), flats) for lens in ("apartment", "resident")}


def _failed(results, check, flat=None):
    return [r for r in results if r["check"] == check and r["passed"] is False and (flat is None or r["flat"] == flat)]


# ---------------------------------------------------------------- what is correct
def test_reproducible_and_geometric_le_arithmetic(engine):
    a = engine["evaluate"].evaluate(engine["ds"], with_sensitivity=False)["lenses"]["apartment"]
    b = engine["before"]["lenses"]["apartment"]
    assert a.equals(b)
    assert (a.score <= a.arithmetic_mean + 1e-9).all()


def test_F002_repair_counterfactual_matches_validated_savings(engine, opportunities):
    r = engine["cf"].run_scenario(engine["ds"], "return_to_baseline", {"anomaly_id": "O3"}, engine["before"])
    c = next(s for s in opportunities["O3_F002_refrigerator_step"]["scenarios"] if s["role"] == "central")
    assert -r["delta_28d"]["kwh"] == pytest.approx(c["kwh"], abs=0.02)
    assert -r["delta_28d"]["sek"] == pytest.approx(c["value_spot_hourly_sek"], abs=0.02)
    assert -r["delta_28d"]["co2_kg"] == pytest.approx(c["co2e_kg"], abs=0.002)


def test_load_shift_conserves_kwh_in_engine(engine):
    r = engine["cf"].run_scenario(engine["ds"], "shift_flexible_load", {"flat_id": "F004", "channel": "A05"}, engine["before"])
    assert r["delta_28d"]["kwh"] == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------- confirmed defects (requirements stated positively)
@pytest.mark.xfail(strict=True, reason="D1 R7: USE benchmark (P20 across flats) recomputed on every evaluation")
def test_R7_peer_invariance_apartment(audits):
    assert not _failed(audits["apartment"], "peer invariance under frozen references")


@pytest.mark.xfail(strict=True, reason="D2 R3: missing hours filled with the appliance's 28-day mean (mixes F002 regimes)")
def test_R3_missing_data_apartment(audits):
    assert not _failed(audits["apartment"], "deleting typical readings does not act like zero consumption")


@pytest.mark.xfail(strict=True, reason="D3 R4: Resident lens falls when F002's fridge is repaired (excess removed twice)")
def test_R4_resident_monotone_under_repair(audits):
    assert not _failed(audits["resident"], "score non-decreasing under pure reduction", "F002")


@pytest.mark.xfail(strict=True, reason="D4: PEAK_HOURS_LOCAL omits 09 and 20 (both > 0.86 SEK/kWh); every dishwasher run starts at 20:00")
def test_dishwasher_shift_captures_validated_opportunity(engine, opportunities):
    total = sum(-engine["cf"].run_scenario(engine["ds"], "shift_flexible_load", {"flat_id": fl, "channel": "A04"}, engine["before"])["delta_28d"]["sek"]
                for fl in engine["ds"].flat_ids)
    assert total > 0.5 * next(s for s in opportunities["O5_dishwasher_price_timing"]["scenarios"] if s["role"] == "central")["value_spot_hourly_sek"]


@pytest.mark.xfail(strict=True, reason="D5: heater_pattern return_to_baseline has no hour restriction -> removes all heater kWh (336 vs <= 23.27 validated)")
def test_heater_scenario_bounded_by_validated_evidence(engine, opportunities):
    r = engine["cf"].run_scenario(engine["ds"], "return_to_baseline", {"anomaly_id": "O1"}, engine["before"])
    upper = next(s for s in opportunities["O1_F007_heating_unoccupied"]["scenarios"] if s["role"] == "upper_measured")["kwh"]
    assert -r["delta_28d"]["kwh"] <= upper + 0.01


@pytest.mark.xfail(strict=True, reason="D6 R4 (pillar): WASTE and HEALTH are shares of total kWh, so cutting other use lowers them")
def test_ratio_pillars_do_not_fall_under_pure_reduction(audits):
    bad = [r for r in audits["apartment"] if r["check"] == "no pillar decreases under pure reduction" and r["passed"] is False
           and set(r["detail"]) & {"waste", "health"}]
    assert not bad


@pytest.mark.xfail(strict=True, reason="D7 R9: one-kWh-per-cell contract cannot carry energy shifted into a missing hour; USE moves")
def test_R9_energy_pillar_unchanged_by_pure_shift(audits):
    assert not _failed(audits["apartment"], "energy pillars unchanged by pure shift")

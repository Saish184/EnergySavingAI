"""Score-audit harness: (1) prove each check detects the violation it targets (tests of the tests),
(2) audit the teammate's model when it becomes available (skipped until then; never faked).
"""
import pytest

import fixtures as fx
import invariants as inv
import teammate_adapter


def failed(results, cls="universal"):
    return {r["check"] for r in results if r["cls"] == cls and r["passed"] is False}


@pytest.fixture(scope="module")
def audits(flats):
    e, t = fx.EnergyTotalFixture(), fx.WholeFlatPriceRatioFixture()
    models = {
        "coverage": fx.CoverageAdjustedEnergyFixture(), "plain_sum": e, "ratio_timing": t,
        "unfrozen_peers": fx.PeerRelativeUnfrozenFixture(),
        "geo0": fx.CompositeFixture({"energy": fx.CoverageAdjustedEnergyFixture(), "timing": t}, {"energy": 0.6, "timing": 0.4}, "geometric"),
        "arith": fx.CompositeFixture({"energy": fx.CoverageAdjustedEnergyFixture(), "timing": t}, {"energy": 0.6, "timing": 0.4}, "arithmetic"),
    }
    return {k: inv.run_all(m, flats) for k, m in models.items()}


def test_reference_fixture_passes_every_universal_check(audits):
    assert failed(audits["coverage"]) == set()


def test_plain_observed_sum_is_flagged_for_rewarding_missing_data(audits):
    assert failed(audits["plain_sum"]) == {"deleting typical readings does not act like zero consumption"}


def test_whole_flat_ratio_timing_is_flagged_for_non_monotonicity(audits):
    fails = [r for r in audits["ratio_timing"] if r["check"] == "score non-decreasing under pure reduction" and r["passed"] is False]
    assert {r["flat"] for r in fails} >= {"F004"}            # documented counterexample: F004 + O4


def test_unfrozen_peer_normalisation_is_flagged(audits):
    assert "peer invariance under frozen references" in failed(audits["unfrozen_peers"])


def test_geometric_zero_collapse_is_reported_as_policy(audits):
    pol = [r for r in audits["geo0"] if r["check"] == "no zero-collapse of geometric aggregate"]
    assert pol and pol[0]["passed"] is False                 # ratio pillar is 0 for its worst flat -> score 0


def test_monotone_pillar_cannot_rescue_non_monotone_pillar_in_aggregate(audits):
    assert "score non-decreasing under pure reduction" in failed(audits["arith"])


def test_teammate_model_universal_invariants(flats):
    try:
        model = teammate_adapter.load()
    except teammate_adapter.Unavailable as e:
        pytest.skip(f"teammate score.py unavailable - no verification performed: {e}")
    results = inv.run_all(model, flats)
    bad = failed(results)
    if bad and "ddc02ce" in model.name:
        pytest.xfail(f"known universal failures on ddc02ce (pinned individually in test_saish_engine.py): {sorted(bad)}")
    assert bad == set(), [r for r in results if r["passed"] is False and r["cls"] == "universal"]

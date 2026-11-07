"""Invariants on the existing machine-readable outputs and contracts (they must be preserved)."""
import json

import pytest
from jsonschema import Draft202012Validator

ENUM = {"measured", "inferred", "hypothetical", "simulated", "unknown"}


def test_R6_no_unsupported_claims_of_confirmed_waste_or_verified_savings(opportunities):
    for oid, o in opportunities.items():
        assert o["waste_status"] == "unconfirmed", oid
        assert o["verification_status"] == "not_verified", oid
        assert o["evidence_classification"]["pattern"] == "measured"
        assert o["evidence_classification"]["appliance_identity"] == "inferred"
        assert o["evidence_classification"]["avoidability"] == "hypothetical"
        assert o["evidence_classification"]["savings"] == "simulated"
        assert set(o["evidence_classification"].values()) <= ENUM


def test_R10_every_scenario_states_period_and_tariff(opportunities):
    for oid, o in opportunities.items():
        for s in o["scenarios"]:
            assert s["period"]["window_hours"] in (336, 672)
            assert s["tariff_applicability"]
    assert all(s["period"]["window_hours"] == 336 for s in opportunities["O3_F002_refrigerator_step"]["scenarios"])


def test_R14_statistical_and_scenario_uncertainty_are_reported_separately(opportunities):
    for oid, o in opportunities.items():
        roles = {s["role"] for s in o["scenarios"]}
        assert "central" in roles and len(o["scenarios"]) >= 3       # scenario range
        c = next(s for s in o["scenarios"] if s["role"] == "central")
        assert "ci95_value_spot_hourly_sek" in c                     # sampling interval, separate field
        if c["type"] == "reduction":
            lo, hi = c["ci95_kwh"]
            assert lo <= c["kwh"] <= hi


def test_contracts_and_examples_still_validate(root):
    S = json.loads((root / "docs/design/contracts.schema.json").read_text())
    Draft202012Validator.check_schema(S)
    for name, path in [("savingsRecord", "docs/design/examples/record_O3_F002.json"),
                       ("calculatorResult", "docs/design/examples/calculator_result_O5_F002.json")]:
        v = Draft202012Validator({**S, "$ref": f"#/$defs/{name}"})
        assert not list(v.iter_errors(json.loads((root / path).read_text())))

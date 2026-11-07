import numpy as np
import pytest

from app import config as C
from app.core import attribution
from app.core.claims import WORDING, Status, human_transition


def test_engine_status_follows_stated_criteria(loaded):
    """Engine can only assign DETECTED/PLAUSIBLE, and PLAUSIBLE only when the stated statistical criterion holds."""
    for a in loaded.anomalies:
        assert a["status"] in (Status.DETECTED, Status.PLAUSIBLE)
        if a["status"] == Status.PLAUSIBLE:
            assert (a["end"] - a["start"]).total_seconds() / 86400 >= C.PLAUSIBLE_MIN_DAYS
            st = a["stats"]
            if a["type"] == "fault_step_change":
                assert st["p_value"] < C.DETECTION_ALPHA
            if a["type"] == "base_load_outlier":
                assert st["weeks_above_peer_range"] == st["weeks"]
            if a["type"] in ("heater_pattern", "peak_usage"):
                assert st["days"] >= C.MIN_EVIDENCE_DAYS
        assert a["confidence"] is None          # no probability is claimed


def test_engine_never_assigns_human_levels(loaded):
    assert all(a["status"] in (Status.DETECTED, Status.PLAUSIBLE) for a in loaded.anomalies)


def test_wording():
    assert WORDING[Status.DETECTED] == "unusual pattern"
    assert WORDING[Status.PLAUSIBLE] == "possible fault"
    assert WORDING[Status.CONFIRMED] == "confirmed"
    assert WORDING[Status.REPAIRED] == "repaired, awaiting data"
    assert WORDING[Status.VERIFIED] == "saving measured"


def test_human_transitions():
    assert human_transition(Status.DETECTED, Status.CONFIRMED) == Status.CONFIRMED
    assert human_transition(Status.CONFIRMED, Status.REPAIRED) == Status.REPAIRED
    with pytest.raises(ValueError):
        human_transition(Status.CONFIRMED, Status.DETECTED)
    with pytest.raises(ValueError):
        human_transition(Status.REPAIRED, Status.CONFIRMED)


def test_attribution():
    assert attribution.responsibility("fault_step_change") == "manager"
    for t in ("base_load_outlier", "scheduled_block", "peak_usage"):
        assert attribution.responsibility(t) == "resident"
    assert attribution.responsibility("heater_pattern") == "unknown"
    assert "needs confirmation" in attribution.note("unknown")


def test_detects_exactly_the_validated_patterns(loaded):
    ids = {a["id"] for a in loaded.anomalies if a["type"] != "peak_usage"}
    assert ids == {"FS-F002-A01", "SB-F004-A05", "BL-F005-A06", "HU-F007-A07"}
    peak = {a["flat_id"] for a in loaded.anomalies if a["type"] == "peak_usage" and a["channel"] == "A04"}
    assert peak == {f"F00{i}" for i in range(1, 9)}
    f2 = loaded.anomaly("FS-F002-A01")
    assert str(f2["start"]) == "2026-10-15 00:00:00+00:00" and f2["responsibility"] == "manager"


def test_fault_wording_reserved_for_equipment(ds, ev):
    """Behaviour/timing patterns are never called a 'fault'; heating says it needs confirmation."""
    from app.services.findings import build_findings
    for f in build_findings(ds, ev):
        if f["responsibility"] != "manager":
            assert "fault" not in f["wording"], (f["id"], f["wording"])
        if f["type"] == "heater_pattern":
            assert "needs confirmation" in f["wording"]

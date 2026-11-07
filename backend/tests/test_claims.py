import pytest

from app.core import attribution
from app.core.claims import WORDING, Status, human_transition, initial_status


def test_initial_status_rule():
    assert initial_status(0.7, "2026-10-01", "2026-10-04") == Status.PLAUSIBLE
    assert initial_status(0.69, "2026-10-01", "2026-10-10") == Status.DETECTED
    assert initial_status(0.95, "2026-10-01", "2026-10-03T23:00") == Status.DETECTED
    assert initial_status(None, "2026-10-01", "2026-10-10") == Status.DETECTED


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
    assert attribution.responsibility("peer_outlier") == "manager"
    for t in ("away_usage", "night_baseload", "peak_usage"):
        assert attribution.responsibility(t) == "resident"
    assert attribution.responsibility("heater_pattern") == "unknown"
    assert "needs confirmation" in attribution.note("unknown")

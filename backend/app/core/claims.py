"""Claim levels: how strongly we are allowed to talk about a finding.

DETECTED  -> "unusual pattern"            (engine, default)
PLAUSIBLE -> "possible fault"             (engine: confidence >= 0.7 and duration >= 3 days)
CONFIRMED -> "confirmed"                  (human only)
REPAIRED  -> "repaired, awaiting data"    (human only)
VERIFIED  -> "saving measured"            (verification.py only)
"""
from __future__ import annotations

from enum import IntEnum

import pandas as pd

from .. import config as C


class Status(IntEnum):
    DISMISSED = 0      # technician checked, no fault found (human only); below DETECTED -> never in HEALTH
    DETECTED = 1
    PLAUSIBLE = 2
    CONFIRMED = 3
    REPAIRED = 4
    VERIFIED = 5


WORDING = {
    Status.DISMISSED: "checked, no fault found",
    Status.DETECTED: "unusual pattern",
    Status.PLAUSIBLE: "possible fault",
    Status.CONFIRMED: "confirmed",
    Status.REPAIRED: "repaired, awaiting data",
    Status.VERIFIED: "saving measured",
}


def duration_days(start, end) -> float:
    return (pd.Timestamp(end) - pd.Timestamp(start)) / pd.Timedelta(days=1)


def initial_status(confidence: float | None, start, end) -> Status:
    """The engine can only ever assign DETECTED or PLAUSIBLE."""
    conf = confidence if confidence is not None else 0.0
    if conf >= C.PLAUSIBLE_MIN_CONFIDENCE and duration_days(start, end) >= C.PLAUSIBLE_MIN_DAYS:
        return Status.PLAUSIBLE
    return Status.DETECTED


def human_transition(current: Status, target: Status) -> Status:
    """A person (manager/technician) moves a finding to CONFIRMED, REPAIRED or DISMISSED. Never VERIFIED."""
    if target == Status.VERIFIED:
        raise ValueError("VERIFIED can only be set by verification with >= 7 days of post-repair data")
    if current == Status.DISMISSED:
        raise ValueError("finding was dismissed (no fault found)")
    if target == Status.DISMISSED:
        if current >= Status.REPAIRED:
            raise ValueError(f"cannot dismiss a finding that is {current.name}")
        return target
    if target not in (Status.CONFIRMED, Status.REPAIRED):
        raise ValueError(f"humans can only set CONFIRMED, REPAIRED or DISMISSED, not {target.name}")
    if current >= Status.REPAIRED:
        raise ValueError(f"finding is already {current.name}")
    if target <= current:
        raise ValueError(f"cannot move from {current.name} to {target.name}")
    return target


def verification_transition(current: Status, saving_measured: bool) -> Status:
    """Only verification.py calls this. Requires REPAIRED first."""
    if current != Status.REPAIRED:
        raise ValueError("verification needs status REPAIRED")
    return Status.VERIFIED if saving_measured else Status.REPAIRED


def describe(status: Status) -> dict:
    return {"status": status.name, "wording": WORDING[status], "level": int(status)}

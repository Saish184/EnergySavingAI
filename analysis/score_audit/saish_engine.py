"""Bridge to the teammate's quantitative engine (branch `saish`, commit ddc02ce) WITHOUT modifying it.

The engine is imported from a read-only checkout given by $SAISH_BACKEND (the `backend/` folder), e.g.
    git worktree add --detach /tmp/saish_wt origin/saish
    export SAISH_BACKEND=/tmp/saish_wt/backend
Data fed to it: our validated readings (data/processed/readings_clean.csv) + the organiser raw files through the
teammate's own loader guards + anomalies translated from our validated opportunities. Every translation choice is
an explicit, documented ASSUMPTION (their anomaly schema forces categories our analysis did not make).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from common import PROCESSED
from mathcore import CHANNELS, FlatData

EXPECTED_COMMIT = "ddc02cec329a8d3cb810a3d349992ba2bb604488"


class Unavailable(RuntimeError):
    pass


def backend_dir() -> Path:
    p = os.environ.get("SAISH_BACKEND")
    if not p or not (Path(p) / "app" / "core" / "score.py").is_file():
        raise Unavailable("Set SAISH_BACKEND to the teammate's backend/ folder (read-only checkout of origin/saish).")
    return Path(p)


def _import():
    b = str(backend_dir())
    if b not in sys.path:
        sys.path.insert(0, b)
    from app import config as C  # noqa: E402
    from app import loader  # noqa: E402
    from app.core import counterfactual, evaluate  # noqa: E402
    from app.core.dataset import Dataset  # noqa: E402
    return C, loader, evaluate, counterfactual, Dataset


# --------------------------------------------------------------------------- validated anomalies -> their schema
# Confidence values are OUR assumption (their schema needs a number; our analysis gives categorical evidence).
VALIDATED = {
    "O3": dict(id="O3", flat_id="F002", appliance_id="F002-A01", type="fault_step_change",
               start="2026-10-15T00:00:00Z", end="2026-10-29T00:00:00Z", excess_kwh=23.36,
               baseline_kwh_per_h=0.0517, observed_kwh_per_h=0.1220, confidence=0.95,
               evidence="x2.36 sustained step from 2026-10-15T00Z (Welch t ~ 90)"),
    "O2_resident": dict(id="O2", flat_id="F005", appliance_id="F005-A06", type="night_baseload",
                        start="2026-10-01T00:00:00Z", end="2026-10-29T00:00:00Z", excess_kwh=62.79,
                        baseline_kwh_per_h=0.033, observed_kwh_per_h=0.128, confidence=0.90,
                        evidence="constant +95 W floor in every one of 661 valid hours"),
    "O2_manager": dict(id="O2", flat_id="F005", appliance_id="F005-A06", type="peer_outlier",
                       start="2026-10-01T00:00:00Z", end="2026-10-29T00:00:00Z", excess_kwh=62.79,
                       baseline_kwh_per_h=0.033, observed_kwh_per_h=0.128, confidence=0.90,
                       evidence="constant +95 W floor in every one of 661 valid hours"),
    "O4": dict(id="O4", flat_id="F004", appliance_id="F004-A05", type="away_usage",
               start="2026-10-01T00:00:00Z", end="2026-10-29T00:00:00Z", excess_kwh=14.30,
               baseline_kwh_per_h=0.004, observed_kwh_per_h=0.069, confidence=0.90,
               evidence="69 W block 09:00-16:59 local on 28/28 days"),
    "O1": dict(id="O1", flat_id="F007", appliance_id="F007-A07", type="heater_pattern",
               start="2026-10-01T00:00:00Z", end="2026-10-29T00:00:00Z", excess_kwh=23.27,
               baseline_kwh_per_h=0.0, observed_kwh_per_h=0.5003, confidence=0.60,
               evidence="heater on in 56 unoccupied hours (simulated occupancy)"),
}
VARIANTS = {
    "A_O2_as_resident": ["O3", "O2_resident", "O4", "O1"],
    "B_O2_as_manager": ["O3", "O2_manager", "O4", "O1"],
    "none": [],
}


def anomalies(variant: str) -> list[dict]:
    C, loader, *_ = _import()
    return loader.prepare_anomalies([dict(VALIDATED[k]) for k in VARIANTS[variant]])


def our_readings() -> pd.DataFrame:
    r = pd.read_csv(PROCESSED / "readings_clean.csv")
    out = pd.DataFrame({"flat_id": r.flat_id, "appliance_id": r.appliance_id, "channel": r.appliance_code,
                        "timestamp_utc": pd.to_datetime(r.timestamp_utc, utc=True), "kwh": r.energy_kwh})
    return out


def dataset(readings: pd.DataFrame | None = None, variant: str = "A_O2_as_resident"):
    C, loader, evaluate, counterfactual, Dataset = _import()
    q: dict = {}
    flats = loader.load_flats()
    return Dataset(readings=our_readings() if readings is None else readings, flats=flats,
                   prices=loader.load_prices(q), context=loader.load_context(flats, q), anomalies=anomalies(variant))


def readings_from_flats(flats: dict[str, FlatData]) -> pd.DataFrame:
    """Our FlatData (possibly counterfactual) -> their readings table. Energy moved into hours with a missing
    reading (fd.extra) cannot be represented in their schema (one kWh per cell); it is added to the cell, which
    turns 'unknown + known' into 'known' - recorded as a limitation of their data contract."""
    t0 = pd.Timestamp("2026-10-01T00:00:00Z")
    rows = []
    for fl, fd in flats.items():
        k = fd.kwh.copy()
        if fd.extra is not None:
            k = k.where(~(k.isna() & (fd.extra != 0)), fd.extra)
        long = k.stack(future_stack=True).rename("kwh").reset_index()
        long.columns = ["hour_idx", "channel", "kwh"]
        long["flat_id"] = fl
        long["appliance_id"] = fl + "-" + long.channel
        long["timestamp_utc"] = t0 + pd.to_timedelta(long.hour_idx, unit="h")
        rows.append(long[["flat_id", "appliance_id", "channel", "timestamp_utc", "kwh"]])
    return pd.concat(rows, ignore_index=True)


class SaishLensModel:
    """Wraps the teammate's evaluate() for one lens into our ScoreModel interface (audit only)."""
    aggregation = "geometric"
    score_range = (0.0, 100.0)

    def __init__(self, lens: str = "apartment", variant: str = "A_O2_as_resident"):
        C, *_ = _import()
        self.lens, self.variant = lens, variant
        self.pillar_weights = dict(C.LENSES[lens])
        self.energy_pillars = ("use",)
        self.name = f"saish@{EXPECTED_COMMIT[:7]}:{lens}:{variant}"

    def fit_references(self, flats):
        return {}  # the engine has no frozen-reference mechanism; it recomputes benchmarks on every call

    def score(self, flats, references):
        C, loader, evaluate, *_ = _import()
        ev = evaluate.evaluate(dataset(readings_from_flats(flats), self.variant), with_sensitivity=False)
        tab = ev["lenses"][self.lens]
        return {fl: {"score": float(tab.loc[fl, "score"]), "pillars": {k: float(tab.loc[fl, k]) for k in self.pillar_weights}}
                for fl in flats}

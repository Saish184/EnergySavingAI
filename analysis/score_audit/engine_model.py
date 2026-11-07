"""ScoreModel wrapper for the project's engine (backend/app/core), so the independent invariant suite in
invariants.py audits it exactly like it audited the original engine."""
from __future__ import annotations

import sys

from common import ROOT

if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app import config as C  # noqa: E402
from app.core.dataset import Dataset  # noqa: E402
from app.core.evaluate import evaluate, prepare  # noqa: E402


class EngineLensModel:
    aggregation = "geometric"
    score_range = (0.0, 100.0)

    def __init__(self, lens: str = "apartment"):
        self.lens = lens
        self.pillar_weights = dict(C.LENSES[lens])
        # pillars that depend on whether energy is used, not when (must not move under a pure shift)
        self.energy_pillars = tuple(k for k in ("use", "waste", "health") if k in self.pillar_weights)
        self.name = f"engine(mina):{lens}"

    def fit_references(self, flats):
        import pandas as pd
        meta = pd.DataFrame([{"flat_id": fl, "residents": fd.residents, "floor_area_m2": fd.floor_area_m2, "price_area": "SE3"}
                             for fl, fd in sorted(flats.items())])
        return {"ds": prepare(Dataset(flats=dict(flats), meta=meta))}

    def score(self, flats, references):
        ds = references["ds"]
        trajs = {fl: fd.trajectory() for fl, fd in flats.items()}
        tab = evaluate(ds, trajs, with_sensitivity=False)["lenses"][self.lens]
        return {fl: {"score": float(tab.loc[fl, "score"]), "pillars": {k: float(tab.loc[fl, k]) for k in self.pillar_weights}} for fl in flats}

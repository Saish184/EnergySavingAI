"""Loader for the teammate's sustainability-score implementation.

STATUS (updated): the implementation exists on branch `saish`, commit ddc02ce, as the package backend/app/core/
(score.py, pillars.py, evaluate.py, ...). Set $SAISH_BACKEND to a read-only checkout of that backend/ folder;
load() then wraps it via saish_engine.SaishLensModel. Earlier inspections preceded that push (see decision report).
This module therefore does not, and must not, guess its code. It only:
  1. locates a score.py (env var SCORE_PY, or known candidate paths),
  2. imports it in isolation,
  3. hands it to a small WRAPPER that the reviewer writes once the real API is known.

To audit the real model when it arrives:
  a) put/point to the file:      export SCORE_PY=/path/to/score.py
  b) fill in `wrap()` below so it returns an object satisfying score_audit.interface.ScoreModel
     (usually 10-20 lines: call the teammate's function on interface.flats_to_table(flats), map its columns
      to {"score": ..., "pillars": {"Use":..,"Waste":..,"Timing":..,"Health":..}}).
  c) run:  python analysis/score_audit/audit_score.py --teammate
Do not edit the teammate's file; all adaptation happens in wrap().
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from common import ROOT

CANDIDATES = ["score.py", "analysis/score.py", "src/score.py", "engine/score.py", "scoring/score.py", "wattwise-site/score.py"]
DOCUMENTED_METHOD = {
    "pillars": {"Use": 0.40, "Waste": 0.25, "Timing": 0.20, "Health": 0.15},
    "aggregation": "weighted geometric",
    "source": "described by the team (no code available); used only to configure checks that need weights",
}


class Unavailable(RuntimeError):
    pass


def locate() -> Path | None:
    env = os.environ.get("SCORE_PY")
    if env and Path(env).is_file():
        return Path(env)
    for c in CANDIDATES:
        p = ROOT / c
        if p.is_file():
            return p
    return None


def import_module(path: Path):
    spec = importlib.util.spec_from_file_location("teammate_score", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wrap(module):  # pragma: no cover - written by the reviewer once the real API is known
    raise Unavailable(
        "score.py was found but wrap() has not been written yet: map the teammate's API to the ScoreModel "
        "interface (see module docstring). Its functions are: "
        + ", ".join(n for n in dir(module) if not n.startswith("_")))


def load(lens: str | None = None):
    """Return a ScoreModel for the teammate's implementation, or raise Unavailable with the reason.

    UPDATE: the implementation was found on branch `saish` (commit ddc02ce, backend/app/core/). It is a package,
    not a single score.py; it is wrapped by saish_engine.SaishLensModel when $SAISH_BACKEND points to a read-only
    checkout of that branch's backend/ folder."""
    if os.environ.get("SAISH_BACKEND"):
        import saish_engine
        try:
            return saish_engine.SaishLensModel(lens or os.environ.get("SAISH_LENS", "apartment"),
                                               os.environ.get("SAISH_VARIANT", "A_O2_as_resident"))
        except saish_engine.Unavailable as e:
            raise Unavailable(str(e)) from e
    path = locate()
    if path is None:
        raise Unavailable("Teammate score.py not found in the repository, candidate paths, or $SCORE_PY.")
    return wrap(import_module(path))

"""TEST DOUBLES for the audit harness. NOT proposals and NOT the teammate's model.

Each fixture is the simplest model that exhibits one behaviour, so that tests can prove the invariant checks
detect it (a check that never fails cannot be trusted):
  EnergyTotalFixture        monotone energy pillar (should PASS monotonicity)
  WholeFlatPriceRatioFixture ratio timing pillar over all loads (known to FAIL monotonicity: F004 + O4)
  EnergyTotalFixture uses a plain sum over observed hours -> deleting readings looks like saving (FLAGGED, R3)
  CoverageAdjustedEnergyFixture scales each channel by its coverage (should PASS the missing-data check)
  PeerRelativeUnfrozenFixture re-normalises against current peers (should FAIL peer invariance)
  CompositeFixture          combines fixture pillars arithmetically or geometrically (zero handling checks)
"""
from __future__ import annotations

import numpy as np

from mathcore import totals


class _Base:
    pillar_weights = None
    aggregation = "other"
    energy_pillars: tuple[str, ...] = ()
    score_range = (0.0, 100.0)

    def fit_references(self, flats):
        return {}


class EnergyTotalFixture(_Base):
    """pillar 'energy' = 100 * clip(1 - E_f / (2 * E_ref_f)), E = observed kWh, E_ref frozen at baseline."""
    name = "fixture:energy-total"
    energy_pillars = ("energy",)

    def fit_references(self, flats):
        return {fl: totals(fd)["kwh"] for fl, fd in flats.items()}

    def score(self, flats, references):
        out = {}
        for fl, fd in flats.items():
            e = totals(fd)["kwh"]
            p = 100 * float(np.clip(1 - e / (2 * references[fl]), 0, 1))
            out[fl] = {"score": p, "pillars": {"energy": p}}
        return out


class WholeFlatPriceRatioFixture(_Base):
    """pillar 'timing' = min-max of (load-weighted price / time-average price) over ALL loads, anchors frozen."""
    name = "fixture:whole-flat-price-ratio"

    @staticmethod
    def _ratio(fd):
        t = totals(fd)
        return (t["sek_spot_hourly"] / (t["kwh"] - t["kwh_unpriced"])) / float(fd.price.mean())

    def fit_references(self, flats):
        r = [self._ratio(fd) for fd in flats.values()]
        return {"lo": min(r), "hi": max(r)}

    def score(self, flats, references):
        out = {}
        for fl, fd in flats.items():
            p = 100 * float(np.clip((references["hi"] - self._ratio(fd)) / (references["hi"] - references["lo"]), 0, 1))
            out[fl] = {"score": p, "pillars": {"timing": p}}
        return out


class CoverageAdjustedEnergyFixture(EnergyTotalFixture):
    """Like EnergyTotalFixture, but missing hours are neither zero nor ignored. Each missing cell is imputed from the
    same channel's observed mean on the same UTC day (local in time, so regime changes such as F002's step are
    respected). Imputations of cells missing at BASELINE are frozen in fit_references, so an intervention cannot
    change the assumed value of an unobserved hour."""
    name = "fixture:energy-coverage-adjusted"

    @staticmethod
    def _local_imputation(x):
        day = x.index // 24
        return x.groupby(day).transform("mean").fillna(x.mean())

    def _e(self, fd, frozen):
        x = fd.kwh
        imp = self._local_imputation(x)
        if frozen is not None:
            imp = frozen.where(frozen.notna(), imp)  # baseline-missing cells keep their frozen imputation
        e = float(np.nansum(x.values) + np.nansum(imp.where(x.isna()).values))
        return e + (float(fd.extra.values.sum()) if fd.extra is not None else 0.0)

    def fit_references(self, flats):
        refs = {}
        for fl, fd in flats.items():
            frozen = self._local_imputation(fd.kwh).where(fd.kwh.isna())
            refs[fl] = {"frozen_imputation": frozen, "E_ref": self._e(fd, frozen)}
        return refs

    def score(self, flats, references):
        out = {}
        for fl, fd in flats.items():
            r = references[fl]
            p = 100 * float(np.clip(1 - self._e(fd, r["frozen_imputation"]) / (2 * r["E_ref"]), 0, 1))
            out[fl] = {"score": p, "pillars": {"energy": p}}
        return out


class PeerRelativeUnfrozenFixture(EnergyTotalFixture):
    """Ignores frozen references and re-normalises against the current peer maximum (violates peer invariance)."""
    name = "fixture:peer-relative-unfrozen"

    def score(self, flats, references):
        e = {fl: totals(fd)["kwh"] for fl, fd in flats.items()}
        hi = max(e.values())
        return {fl: {"score": 100 * (1 - v / hi), "pillars": {"energy": 100 * (1 - v / hi)}} for fl, v in e.items()}


class CompositeFixture(_Base):
    """Combines named fixture pillars with weights; aggregation 'arithmetic' or 'geometric' (optional floor)."""

    def __init__(self, parts: dict, weights: dict, aggregation: str, floor: float = 0.0):
        self.parts, self.pillar_weights, self.aggregation, self.floor = parts, weights, aggregation, floor
        self.name = f"fixture:composite-{aggregation}-floor{floor:g}"
        self.energy_pillars = tuple(k for k, m in parts.items() if m.energy_pillars)

    def fit_references(self, flats):
        return {k: m.fit_references(flats) for k, m in self.parts.items()}

    def score(self, flats, references):
        res = {k: m.score(flats, references[k]) for k, m in self.parts.items()}
        out = {}
        for fl in flats:
            pil = {k: res[k][fl]["score"] for k in self.parts}
            if self.aggregation == "arithmetic":
                s = sum(self.pillar_weights[k] * v for k, v in pil.items())
            else:
                s = float(np.prod([max(v, self.floor) ** self.pillar_weights[k] for k, v in pil.items()]))
            out[fl] = {"score": s, "pillars": pil}
        return out

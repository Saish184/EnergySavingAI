"""prepare(): detect anomalies and freeze references ONCE on the baseline.
evaluate(): metrics + both score lenses for the baseline or for counterfactual trajectories. Before and after use
exactly the same frozen references, so differences come only from the hourly energy that changed."""
from __future__ import annotations

import pandas as pd

from .. import config as C
from . import metrics
from .dataset import Dataset
from .detect import detect_all
from .pillars import partition, pillars
from .references import fit
from .score import score_table
from .sensitivity import sensitivity


def prepare(ds: Dataset) -> Dataset:
    ds.anomalies = detect_all(ds.flats)
    ds.refs = fit(ds.flats, ds.anomalies)
    return ds


def evaluate(ds: Dataset, trajectories: dict | None = None, with_sensitivity: bool = True) -> dict:
    if ds.refs is None:
        prepare(ds)
    trajectories = trajectories or {}
    parts, pil = {}, {}
    for fl, fd in ds.flats.items():
        parts[fl] = partition(fd, trajectories.get(fl), ds.anomalies, ds.refs)
        pil[fl] = pillars(fd, parts[fl], ds.refs)
    out = {"totals": metrics.flat_totals(ds, trajectories, parts), "partition": parts, "lenses": {}, "detail": {},
           "sensitivity": {}, "references": ds.refs.summary()}
    for lens in C.LENSES:
        tab = pd.DataFrame({fl: pil[fl][lens] for fl in ds.flat_ids}).T
        tab.index.name = "flat_id"
        out["lenses"][lens] = score_table(tab, C.LENSES[lens])
        out["detail"][lens] = pd.DataFrame({fl: {**pil[fl]["intensities"], **{k: v for k, v in parts[fl].items() if k != "excess_by_anomaly"}}
                                            for fl in ds.flat_ids}).T
    if with_sensitivity:
        for lens, t in out["lenses"].items():
            out["sensitivity"][lens] = sensitivity(t, C.LENSES[lens])
    return out

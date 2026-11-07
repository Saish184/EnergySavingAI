"""In-memory container passed between engine functions. No I/O here."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import pandas as pd

from .hourly import FlatData


@dataclass
class Dataset:
    flats: dict[str, FlatData]                       # BASELINE hourly data per flat (never modified)
    meta: pd.DataFrame                               # flat_id, residents, floor_area_m2, price_area
    anomalies: list[dict] = field(default_factory=list)   # engine-detected (frozen references inside)
    refs: object | None = None                       # references.References, fitted once on the baseline

    def copy(self, anomalies: list[dict] | None = None) -> "Dataset":
        return Dataset(flats=self.flats, meta=self.meta,
                       anomalies=copy.deepcopy(anomalies if anomalies is not None else self.anomalies), refs=self.refs)

    def anomaly(self, anomaly_id: str) -> dict:
        for a in self.anomalies:
            if a["id"] == anomaly_id:
                return a
        raise KeyError(f"unknown anomaly {anomaly_id}")

    @property
    def flat_ids(self) -> list[str]:
        return sorted(self.flats)

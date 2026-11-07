"""In-memory container passed between engine functions. No I/O here."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Dataset:
    # readings: flat_id, appliance_id, channel, timestamp_utc (tz-aware UTC), kwh (NaN = missing)
    readings: pd.DataFrame
    # flats: flat_id, residents, floor_area_m2, price_area
    flats: pd.DataFrame
    # prices: timestamp_utc, price_area, spot, carbon
    prices: pd.DataFrame
    # context: flat_id, timestamp_utc, occupants_home (NaN = unknown), indoor_temp_c, outdoor_temp_c
    context: pd.DataFrame
    # anomalies: list of dicts (teammate schema) + "status" (claims.Status) + "responsibility"
    anomalies: list[dict] = field(default_factory=list)

    def copy(self, readings: pd.DataFrame | None = None, anomalies: list[dict] | None = None) -> "Dataset":
        """Counterfactuals always work on a copy; the original is never modified."""
        return Dataset(
            readings=(readings if readings is not None else self.readings).copy(),
            flats=self.flats,
            prices=self.prices,
            context=self.context,
            anomalies=copy.deepcopy(anomalies if anomalies is not None else self.anomalies),
        )

    def anomaly(self, anomaly_id: str) -> dict:
        for a in self.anomalies:
            if a["id"] == anomaly_id:
                return a
        raise KeyError(f"unknown anomaly {anomaly_id}")

    @property
    def flat_ids(self) -> list[str]:
        return sorted(self.flats["flat_id"].tolist())

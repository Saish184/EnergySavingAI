"""The single interface every audited sustainability-score implementation is wrapped into.

A model receives all flats (so peer-relative formulas are possible) and optional frozen references.
Contract:
  references = model.fit_references(flats)                 # computed ONCE on the baseline, then frozen
  result     = model.score(flats, references)              # {flat_id: {"score": float, "pillars": {name: float}}}
Attributes:
  name               human-readable identifier
  pillar_weights     {pillar: weight} or None if not weight-based
  aggregation        "arithmetic" | "geometric" | "other"
  energy_pillars     pillars that should depend on WHETHER energy is used, not WHEN (used by shift checks)
  score_range        (low, high) the model promises, e.g. (0, 100)
"""
from __future__ import annotations

from typing import Protocol

from mathcore import FlatData


class ScoreModel(Protocol):
    name: str
    pillar_weights: dict[str, float] | None
    aggregation: str
    energy_pillars: tuple[str, ...]
    score_range: tuple[float, float]

    def fit_references(self, flats: dict[str, FlatData]) -> dict: ...

    def score(self, flats: dict[str, FlatData], references: dict | None) -> dict[str, dict]: ...


def flats_to_table(flats: dict[str, FlatData]):
    """Rebuild a long table (analytical_table-like columns) from possibly-modified flats, so that a teammate model
    that expects a DataFrame can be called on counterfactual data. Missing kWh stay NaN."""
    import pandas as pd
    rows = []
    for fl, fd in flats.items():
        long = fd.kwh.stack(future_stack=True).rename("energy_kwh").reset_index()
        long.columns = ["hour_idx", "appliance_code", "energy_kwh"]
        long["flat_id"] = fl
        long["appliance_id"] = fl + "-" + long.appliance_code
        long["residents"] = fd.residents
        long["floor_area_m2"] = fd.floor_area_m2
        for col, s in (("spot_sek_per_kwh", fd.price), ("carbon_gco2e_per_kwh", fd.carbon), ("occupants_home", fd.occupants),
                       ("outdoor_temp_c", fd.outdoor), ("local_hour", fd.local_hour)):
            long[col] = long.hour_idx.map(s)
        long["energy_missing"] = long.energy_kwh.isna()
        rows.append(long)
    return pd.concat(rows, ignore_index=True)

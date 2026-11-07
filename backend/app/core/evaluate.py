"""One pure function that turns a Dataset into metrics + both score lenses.
Counterfactuals call this on a modified copy, so before/after always use the same method."""
from __future__ import annotations

import pandas as pd

from .. import config as C
from . import metrics, pillars as P
from .attribution import remove_manager_excess
from .dataset import Dataset
from .score import score_table
from .sensitivity import sensitivity


def _lens(e: pd.DataFrame, ds: Dataset, lens: str, totals: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    flats = ds.flats.set_index("flat_id")
    kwh_adj = metrics.coverage_adjusted_kwh(e).reindex(flats.index)
    x, use, bench = P.use_pillar(kwh_adj, flats["residents"])
    waste, avoidable = P.waste_pillar(e, P.heater_confirmed_flats(ds.anomalies))
    timing, cti = P.timing_pillar(e, ds.prices)
    cols = {"use": use, "waste": waste.reindex(flats.index), "timing": timing.reindex(flats.index)}
    detail = {"use_x": x, "use_bench": bench, "avoidable_away_kwh": avoidable.reindex(flats.index),
              "cti": cti.reindex(flats.index)}
    if "health" in C.LENSES[lens]:
        health, fk = P.health_pillar(totals["kwh"], ds.anomalies)
        cols["health"] = health
        detail["fault_kwh"] = fk
    table = score_table(pd.DataFrame(cols), C.LENSES[lens])
    return table, detail


def evaluate(ds: Dataset, with_sensitivity: bool = True) -> dict:
    e = metrics.enrich(ds.readings, ds.flats, ds.prices, ds.context)
    totals = metrics.flat_totals(e, ds.flats)
    out = {"enriched": e, "totals": totals, "lenses": {}, "detail": {}, "sensitivity": {}}

    # Apartment Performance: everything the flat consumed, incl. equipment faults
    out["lenses"]["apartment"], out["detail"]["apartment"] = _lens(e, ds, "apartment", totals)

    # Resident Actions: same method on readings with manager-attributed excess removed
    adj = ds.copy(readings=remove_manager_excess(ds.readings, ds.anomalies))
    e_res = metrics.enrich(adj.readings, adj.flats, adj.prices, adj.context)
    out["lenses"]["resident"], out["detail"]["resident"] = _lens(e_res, adj, "resident", totals)

    if with_sensitivity:
        for lens, t in out["lenses"].items():
            out["sensitivity"][lens] = sensitivity(t, C.LENSES[lens])
    return out

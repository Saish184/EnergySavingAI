"""Application state: the loaded Dataset, its frozen references, evaluation, findings and in-memory stores.
Student and manager views are built from the SAME evaluation and savings calculations."""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from . import config as C
from .core import claims, metrics
from .core import savings as SV
from .core.claims import Status
from .core.counterfactual import run_scenario
from .core.evaluate import evaluate, prepare
from .core.projection import project_triplet
from .core.verification import simulate_post_repair, verify
from .loader import load
from .services import business_case, findings as F, notifications
from .services.reports import Reports
from .services.workorders import WorkOrders

SCORE_ASSUMPTIONS = [
    "28 days of synthetic October data (2026-10-01..2026-10-28, UTC); cleaned by analysis/clean_data.py",
    "energy is partitioned: explained use (USE) + possible avoidable use (WASTE) + possible equipment fault (HEALTH); each kWh counts once",
    "per equivalent resident = residents ** 0.5 (OECD square-root scale; shared appliances do not scale with people)",
    "USE benchmark = 20th percentile of the 8 flats AT BASELINE, frozen (relative, not an absolute standard)",
    "WASTE/HEALTH/TIMING scales are frozen typical-flat levels; no pillar can fall when energy is saved",
    "missing readings: frozen local imputation (same channel, same day) for scores; savings use observed hours only",
    "unknown occupancy is never treated as 'away'",
    "patterns count once they meet a stated statistical criterion (PLAUSIBLE); this is never 'confirmed waste'",
    "heater-like use counts only in hours with nobody home; weather-driven heating is in the apartment lens USE only",
    "peak hours are the local hours whose mean spot price exceeds the time-average price",
    "carbon factors are synthetic operational averages, not marginal or lifecycle emissions",
]


class AppState:
    def __init__(self):
        self.workorders = WorkOrders()
        self.reports = Reports()
        self.recompute(reload=True)

    # ---------- compute ----------
    def recompute(self, reload: bool = False) -> dict:
        t0 = time.time()
        if reload:
            self.ds, self.quality = load()
            prepare(self.ds)                    # detect anomalies + freeze references on the baseline
            self._apply_overrides()
        self.ev = evaluate(self.ds)
        self.findings = F.build_findings(self.ds, self.ev)
        self.findings_by_id = {f["id"]: f for f in self.findings}
        self.computed_seconds = time.time() - t0
        return {"ok": True, "seconds": self.computed_seconds, "data_source": self.quality["data_source"],
                "references_hash": self.ev["references"]["hash"]}

    def _apply_overrides(self):
        for w in self.workorders.items.values():
            try:
                a = self.ds.anomaly(w["finding_id"])
            except KeyError:
                continue
            if w.get("fault_found") is False:
                a["status"] = Status.DISMISSED
                continue
            if w.get("fault_found"):
                a["status"] = max(a["status"], Status.CONFIRMED)
            if w["status"] == "repaired":
                a["status"] = Status.REPAIRED
            if w.get("verification") and w["verification"]["status"] == "VERIFIED":
                a["status"] = Status.VERIFIED
                a["verification"] = w["verification"]

    def check_flat(self, flat_id: str):
        if flat_id not in self.ds.flat_ids:
            raise KeyError(f"unknown flat {flat_id}")

    def detector_summary(self) -> list[dict]:
        return [{"id": a["id"], "flat_id": a["flat_id"], "type": a["type"], "status": a["status"].name,
                 "responsibility": a["responsibility"], "evidence": a["evidence"], "statistics": a["stats"]} for a in self.ds.anomalies]

    # ---------- student views ----------
    def lens_view(self, lens: str, flat_id: str) -> dict:
        row = self.ev["lenses"][lens].loc[flat_id]
        sens = self.ev["sensitivity"][lens].loc[flat_id]
        return {
            "label": C.LENS_LABELS[lens],
            "score": row["score"], "band": row["band"], "arithmetic_mean": row["arithmetic_mean"],
            "rank": row["rank"], "of": len(self.ds.flat_ids),
            "pillars": {k: row[k] for k in C.LENSES[lens]},
            "weights": C.LENSES[lens],
            "sensitivity": {k: sens[k] for k in ("score_p5", "score_p95", "rank_p5", "rank_p95", "draws")},
            "responsibility": "residents + building manager" if lens == "apartment" else "residents only",
            "excludes": [] if lens == "apartment" else ["possible equipment faults (HEALTH)", "weather-driven heater-like use"],
        }

    def scores(self, flat_id: str) -> dict:
        self.check_flat(flat_id)
        d = self.ev["detail"]["apartment"].loc[flat_id]
        R = self.ev["references"]
        return {
            "flat_id": flat_id, "horizon": "28d measured", "status": "measured", "data_source": self.quality["data_source"],
            "lenses": {lens: self.lens_view(lens, flat_id) for lens in C.LENSES},
            "benchmark": {
                "metric": "explained kWh / sqrt(residents) / day",
                "flat_value": d["u_apartment"], "benchmark_value": R["use_bench_kwh_per_eq_resident_day"]["apartment"],
                "flat_value_resident_lens": d["u_resident"],
                "benchmark_value_resident_lens": R["use_bench_kwh_per_eq_resident_day"]["resident"],
                "percentile": C.USE_BENCH_PERCENTILE, "frozen": True, "references_hash": R["hash"],
            },
            "partition_kwh": {k: d[k] for k in ("total_kwh", "explained_apartment", "explained_resident", "resident_excess_kwh",
                                                 "fault_kwh", "heater_kwh", "flexible_kwh", "peak_flexible_kwh")},
            "pillar_detail": {"possible_avoidable_kwh": d["resident_excess_kwh"], "possible_fault_kwh": d["fault_kwh"],
                              "peak_flexible_kwh": d["peak_flexible_kwh"]},
            "assumptions": SCORE_ASSUMPTIONS,
            "uncertainty": {"method": f"{C.SENS_DRAWS} Dirichlet weight draws (alpha = weight x {C.SENS_CONCENTRATION})",
                            "data_coverage": self.ev["totals"].loc[flat_id, "coverage"]},
        }

    def breakdown(self, flat_id: str) -> dict:
        self.check_flat(flat_id)
        t = self.ev["totals"].loc[flat_id]
        b = metrics.channel_breakdown(self.ds, flat_id)
        daily = metrics.daily_flat_series(self.ds.flats[flat_id])
        return {
            "flat_id": flat_id, "horizon": "28d measured", "status": "measured", "responsibility": "n/a",
            "totals": {k: t[k] for k in ("kwh", "sek", "co2_kg", "kwh_per_resident", "sek_per_resident", "co2_kg_per_resident",
                                          "kwh_per_m2", "peak_share", "coverage", "price_coverage", "residents", "floor_area_m2",
                                          "kwh_coverage_adjusted")},
            "per_resident_label": "average per resident (flat total / residents), not measured per person",
            "channels": b.to_dict("records"),
            "daily": [{"day": i, **r} for i, r in daily.to_dict("index").items()],
            "projection_annual": project_triplet(None, False, "whole-flat use is not extrapolated: heating and behaviour depend on season"),
            "assumptions": [
                "channel types are ASSUMPTIONS from load shape; the dataset has no appliance labels",
                "SEK = kWh x spot price (excl. VAT, network fee, energy tax)",
                "kgCO2e = kWh x synthetic carbon factor / 1000",
                f"peak = local hours {sorted(self.ds.refs.peak_hours)} (mean spot price above the time-average)",
            ],
            "uncertainty": {"coverage": t["coverage"], "price_coverage": t["price_coverage"],
                            "note": "hours with missing kWh or price are excluded from measured sums, not set to zero"},
        }

    def local_profile(self, flat_id: str) -> dict:
        """Measured hour-of-day profile and daily totals in Europe/Stockholm time (additive view for the frontend)."""
        self.check_flat(flat_id)
        R = self.ev["references"]
        prof = metrics.local_profile(self.ds.flats[flat_id], set(self.ds.refs.peak_hours))
        return {
            "flat_id": flat_id, "timezone": C.TZ_LOCAL, "horizon": "28d measured", "status": "measured",
            "period_utc": {"start": C.PERIOD_START, "end_exclusive": "2026-10-29T00:00:00Z"},
            "peak_hours_local": R["peak_hours_local"], "time_avg_price_sek_per_kwh": R["time_avg_price_sek_per_kwh"],
            **prof,
            "assumptions": [
                "local clock hours in Europe/Stockholm; 25 October has 25 hours (the 02:00 hour occurs twice)",
                "means and sums of observed readings only: missing readings are excluded, never treated as 0",
                "mean_kwh is null for an hour if a channel has no observed reading at that hour",
                "SEK = kWh x spot price (excl. VAT, network fee, energy tax); hours without a price are excluded",
                "first and last local dates are partial (22 h and 1 h) because the data period is defined in UTC",
            ],
        }

    def flat_findings(self, flat_id: str) -> list[dict]:
        self.check_flat(flat_id)
        return [f for f in self.findings if f["flat_id"] == flat_id]

    def scenario(self, flat_id: str, scenario: str, params: dict) -> dict:
        self.check_flat(flat_id)
        params = dict(params or {})
        if scenario == "return_to_baseline":
            if self.ds.anomaly(params["anomaly_id"])["flat_id"] != flat_id:
                raise ValueError("anomaly does not belong to this flat")
        elif scenario == "apply_interventions":
            params["flat_id"] = flat_id
            for it in params.get("items") or []:
                if self.ds.anomaly(it["anomaly_id"])["flat_id"] != flat_id:
                    raise ValueError("every intervention must belong to this flat")
        else:
            params["flat_id"] = flat_id
        return run_scenario(self.ds, scenario, params, before=self.ev, tariff=params.get("tariff"))

    def combined_potential(self, flat_id: str) -> dict | None:
        """All of the flat's findings applied together on one trajectory (no double counting)."""
        ids = [a["id"] for a in self.ds.anomalies if a["flat_id"] == flat_id]
        if not ids:
            return None
        r = SV.run(self.ds, [{"anomaly_id": i, "params": None} for i in ids], before=self.ev, with_range=False)
        return {"findings": ids, "kwh": r["delta"]["kwh"], "sek_if_hourly_spot": r["delta"]["sek_spot_hourly"],
                "co2_kg": r["delta"]["co2e_kg"], "overlap_kwh": r["overlap"]["kwh"], "score_after": r["scores"]["after"],
                "label": "potential if every finding were acted on fully (simulated)"}

    # ---------- manager views ----------
    def portfolio(self) -> dict:
        rows = []
        for fid in self.ds.flat_ids:
            ap = self.ev["lenses"]["apartment"].loc[fid]
            rs = self.ev["lenses"]["resident"].loc[fid]
            t = self.ev["totals"].loc[fid]
            d = self.ev["detail"]["apartment"].loc[fid]
            open_f = [f for f in self.findings if f["flat_id"] == fid and f["status_level"] not in (Status.VERIFIED, Status.DISMISSED)]
            rows.append({
                "flat_id": fid, "residents": t["residents"], "floor_area_m2": t["floor_area_m2"],
                "apartment_score": ap["score"], "apartment_band": ap["band"], "apartment_rank": ap["rank"],
                "resident_score": rs["score"], "resident_band": rs["band"], "health": ap["health"],
                "open_findings": len(open_f),
                "open_manager_findings": sum(f["responsibility"] == "manager" for f in open_f),
                "kwh_28d": t["kwh"], "sek_28d": t["sek"], "co2_kg_28d": t["co2_kg"], "coverage": t["coverage"],
                "comparison": {"explained_kwh_per_eq_resident_day": d["u_apartment"], "kwh_per_m2": t["kwh_per_m2"],
                               "heater_kwh": d["heater_kwh"], "possible_fault_kwh": d["fault_kwh"],
                               "possible_avoidable_kwh": d["resident_excess_kwh"]},
                "combined_potential": self.combined_potential(fid),
            })
        tot = self.ev["totals"]
        mgr = [f for f in self.findings if f["responsibility"] == "manager"]
        return {
            "horizon": "28d measured", "status": "measured", "data_source": self.quality["data_source"],
            "flats": rows,
            "totals": {"kwh": tot["kwh"].sum(), "sek": tot["sek"].sum(), "co2_kg": tot["co2_kg"].sum()},
            "potential": {"kwh": sum((r["combined_potential"] or {}).get("kwh", 0) for r in rows),
                          "sek_if_hourly_spot": sum((r["combined_potential"] or {}).get("sek_if_hourly_spot", 0) for r in rows),
                          "co2_kg": sum((r["combined_potential"] or {}).get("co2_kg", 0) for r in rows),
                          "label": "sum over flats of each flat's combined potential (flats are disjoint; simulated)"},
            "maintenance": [{"finding_id": f["id"], "flat_id": f["flat_id"], "status": f["status"], "wording": f["wording"],
                             "evidence": f["evidence"]["text"], "excess_kwh_per_day": f["evidence"]["reported_excess_kwh"] / max(f["window"]["days"], 1e-9),
                             "potential_kwh": f["avoidable_28d"]["kwh"], "window_days": f["avoidable_28d"]["window_days"]} for f in mgr],
            "data_quality": {"coverage_by_flat": tot["coverage"].to_dict(), **{k: v for k, v in self.quality.items() if k != "path"}},
            "evidence_quality": {"findings_by_status": pd.Series([f["status"] for f in self.findings]).value_counts().to_dict(),
                                 "note": "PLAUSIBLE = met a stated statistical criterion; CONFIRMED needs a person; VERIFIED needs post-change data"},
            "references": self.ev["references"],
            "assumptions": SCORE_ASSUMPTIONS,
            "uncertainty": {"note": "see /flats/{id}/scores for score p5-p95 and rank p5-p95; findings carry sampling CI and scenario range"},
        }

    def portfolio_findings(self, status: str | None = None, responsibility: str | None = None) -> list[dict]:
        out = self.findings
        if status:
            out = [f for f in out if f["status"] == status.upper()]
        if responsibility:
            out = [f for f in out if f["responsibility"] == responsibility]
        return out

    # ---------- actions ----------
    def _set_status(self, finding_id: str, target: Status):
        a = self.ds.anomaly(finding_id)
        a["status"] = claims.human_transition(a["status"], target)

    def report(self, flat_id: str, finding_id: str, message: str | None) -> dict:
        f = self.findings_by_id.get(finding_id)
        if not f or f["flat_id"] != flat_id:
            raise KeyError(f"finding {finding_id} not found for {flat_id}")
        return self.reports.add(flat_id, finding_id, message)

    def create_workorder(self, finding_id: str, note: str | None) -> dict:
        f = self.findings_by_id.get(finding_id)
        if not f:
            raise KeyError(f"unknown finding {finding_id}")
        # Opening a work order proves nothing: the finding keeps its engine status until the technician reports.
        return self.workorders.create(f, note)

    def patch_workorder(self, wid: str, status: str | None = None, fault_found: bool | None = None) -> dict:
        """Technician outcome: fault_found=true -> CONFIRMED; fault_found=false -> DISMISSED (no longer counted in
        any pillar); status=repaired -> REPAIRED (a saving still needs verification)."""
        w = self.workorders.get(wid)
        if status is None and fault_found is None:
            raise ValueError("send status and/or fault_found")
        if fault_found is False and status == "repaired":
            raise ValueError("cannot be repaired when no fault was found")
        a = self.ds.anomaly(w["finding_id"])
        if fault_found is False:
            self._set_status(a["id"], Status.DISMISSED)
            w["fault_found"] = False
            self.workorders.advance(wid, "closed_no_fault")
        elif fault_found:
            if a["status"] < Status.CONFIRMED:
                self._set_status(a["id"], Status.CONFIRMED)
            w["fault_found"] = True
        if status:
            self.workorders.advance(wid, status)
            if status == "repaired":
                w["fault_found"] = True
                if a["status"] < Status.REPAIRED:
                    self._set_status(a["id"], Status.REPAIRED)
        self.recompute()
        return w

    def verify_workorder(self, wid: str, post_readings: list[dict] | None, simulate: bool) -> dict:
        w = self.workorders.get(wid)
        if w["status"] != "repaired":
            raise ValueError("work order must be 'repaired' before verification")
        a = self.ds.anomaly(w["finding_id"])
        if post_readings:
            post, simulated = pd.DataFrame(post_readings), False
        elif simulate:
            post, simulated = simulate_post_repair(a), True
        else:
            raise ValueError("send post_readings, or simulate=true for a flagged demo")
        res = verify(a["observed_kwh_per_h"], post, a["status"], simulated=simulated)
        res["finding_id"] = a["id"]
        w["verification"] = res
        if res["status"] == "VERIFIED":
            a["status"] = Status.VERIFIED
            a["verification"] = res
            daily = np.full(int(round(res["post_days"])), res["saving_kwh"] / res["post_days"])
            res["projection_annual_kwh"] = project_triplet({"kwh": daily}, a["type"] in C.PROJECTABLE_TYPES, None,
                                                           ["scaled from measured post-repair saving"] + (["SIMULATED post-repair data"] if simulated else []))["kwh"]
        self.recompute()
        return {"workorder": w, "verification": res, "finding": self.findings_by_id[a["id"]]}

    def notifications_flat(self, flat_id):
        return notifications.for_flat(flat_id, self.findings, list(self.workorders.items.values()))

    def notifications_manager(self):
        return notifications.for_manager(self.reports.items, list(self.workorders.items.values()))

    def business_reference(self):
        return business_case.engine_reference(self.findings, len(self.ds.flat_ids))

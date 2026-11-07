"""Application state: the loaded Dataset, its evaluation, findings and the in-memory stores.
Views here are shared by the API and the static export."""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from . import config as C
from .core import claims, metrics
from .core.claims import Status
from .core.counterfactual import run_scenario
from .core.evaluate import evaluate
from .core.projection import project_triplet
from .core.verification import simulate_post_repair, verify
from .loader import load
from .llm import prompts as LP
from .llm.generate import generate, generate_many
from .services import business_case, findings as F, notifications
from .services.reports import Reports
from .services.workorders import WorkOrders

SCORE_ASSUMPTIONS = [
    "28 days of synthetic October data (2026-10-01..2026-10-28, UTC)",
    "USE is normalised by sqrt(residents): shared appliances don't scale with people",
    "USE benchmark = 20th percentile of the 8 flats (relative, not an absolute standard)",
    "base load = 10th percentile of each appliance's hourly kWh",
    "missing readings are filled with that appliance's own average for USE, never with zero",
    "unknown occupancy is not treated as 'away'",
    "heater-like use is not counted as waste unless a person confirms the finding",
    "carbon factors are synthetic operational values, not marginal or lifecycle emissions",
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
            self._apply_overrides()
        self.ev = evaluate(self.ds)
        self.findings = F.build_findings(self.ds, self.ev)
        self.findings_by_id = {f["id"]: f for f in self.findings}
        self.llm_ctx = self._llm_context()
        self.computed_seconds = time.time() - t0
        return {"ok": True, "seconds": self.computed_seconds, "data_source": self.quality["data_source"]}

    def _apply_overrides(self):
        """Re-apply human status changes (from work orders) after a reload."""
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

    def _llm_context(self) -> dict:
        """Engine facts the LLM may quote (it never derives them itself)."""
        p = self.ds.prices.dropna(subset=["spot"])
        hod = p["timestamp_utc"].dt.tz_convert(C.TZ_LOCAL).dt.hour
        by_h = p.groupby(hod)["spot"].mean().drop(list(C.PEAK_HOURS_LOCAL), errors="ignore")
        live = [f for f in self.findings if f["status"] != "DISMISSED"]
        largest = max(live, key=lambda f: f["avoidable_28d"]["sek"] or 0)["id"] if live else None
        return {"cheapest_hour_local": f"{int(by_h.idxmin()):02d}:00", "largest_sek_finding_id": largest}

    def week_summary(self, flat_id: str) -> dict:
        d = metrics.daily_flat_series(self.ev["enriched"], flat_id).sort_index()
        last, prev = d.iloc[-7:], d.iloc[-14:-7]
        fmt = lambda ix: f"{ix[0].day} {ix[0].strftime('%b')} - {ix[-1].day} {ix[-1].strftime('%b')}"  # noqa: E731
        ls, ps = last["sek"].sum(), prev["sek"].sum()
        return {"last_7d": {"kwh": last["kwh"].sum(), "sek": ls, "dates": fmt(last.index)},
                "prev_7d": {"kwh": prev["kwh"].sum(), "sek": ps, "dates": fmt(prev.index)},
                "change_pct": (ls - ps) / ps * 100 if ps else None,
                "horizon": "last 7 days of data vs the 7 days before", "status": "measured"}

    # ---------- LLM texts (wording only) ----------
    def _student_job(self, f):
        return ("finding_student", LP.payload_finding_student(f, self.llm_ctx),
                {"flat_id": f["flat_id"], "finding_id": f["id"]})

    def _manager_job(self, f):
        return ("finding_manager", LP.payload_finding_manager(f, self.llm_ctx),
                {"flat_id": f["flat_id"], "finding_id": f["id"]})

    def digest(self, flat_id: str) -> dict:
        self.check_flat(flat_id)
        mine = [f for f in self.findings if f["flat_id"] == flat_id and f["status"] != "DISMISSED"]
        week = self.week_summary(flat_id)
        payload = LP.payload_digest(self.scores(flat_id, with_explainer=False), week, mine[0] if mine else None,
                                    self.llm_ctx)
        res = generate("weekly_digest", payload, {"flat_id": flat_id})
        return {"flat_id": flat_id, **res, "week": week, "horizon": week["horizon"],
                "assumptions": ["texts only reword engine numbers", "synthetic data"]}

    def explainer(self, flat_id: str) -> dict:
        payload = LP.payload_score(self.scores(flat_id, with_explainer=False))
        return generate("score_explainer", payload, {"flat_id": flat_id})

    def warm_llm(self) -> dict:
        """Pre-generate every text (fills out/llm_cache.json for the demo)."""
        jobs = [self._student_job(f) for f in self.findings] + [self._manager_job(f) for f in self.findings]
        res = generate_many(jobs)
        for fid in self.ds.flat_ids:
            res += [self.digest(fid), self.explainer(fid)]
        return {"texts": len(res), "llm": sum(r["source"] == "llm" for r in res),
                "template": sum(r["source"] == "template" for r in res)}

    def check_flat(self, flat_id: str):
        if flat_id not in self.ds.flat_ids:
            raise KeyError(f"unknown flat {flat_id}")

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
            "excludes": [] if lens == "apartment" else ["manager-attributed equipment excess", "HEALTH pillar"],
        }

    def scores(self, flat_id: str, with_explainer: bool = True) -> dict:
        self.check_flat(flat_id)
        d = self.ev["detail"]
        out = {
            "flat_id": flat_id,
            "horizon": "28d measured",
            "status": "measured",
            "data_source": self.quality["data_source"],
            "lenses": {lens: self.lens_view(lens, flat_id) for lens in C.LENSES},
            "benchmark": {
                "metric": "kWh / sqrt(residents) / day",
                "flat_value": d["apartment"]["use_x"].loc[flat_id],
                "benchmark_value": d["apartment"]["use_bench"],
                "benchmark_value_resident_lens": d["resident"]["use_bench"],
                "percentile": C.USE_BENCH_PERCENTILE,
            },
            "pillar_detail": {
                "avoidable_away_kwh": d["apartment"]["avoidable_away_kwh"].loc[flat_id],
                "carbon_timing_index": d["apartment"]["cti"].loc[flat_id],
                "fault_kwh_plausible_or_higher": d["apartment"]["fault_kwh"].loc[flat_id],
            },
            "assumptions": SCORE_ASSUMPTIONS,
            "uncertainty": {"method": f"{C.SENS_DRAWS} Dirichlet weight draws (alpha = weight x {C.SENS_CONCENTRATION})",
                            "data_coverage": self.ev["totals"].loc[flat_id, "coverage"]},
        }
        if with_explainer:
            out["explainer"] = self.explainer(flat_id)
        return out

    def breakdown(self, flat_id: str) -> dict:
        self.check_flat(flat_id)
        t = self.ev["totals"].loc[flat_id]
        b = metrics.channel_breakdown(self.ev["enriched"], flat_id)
        daily = metrics.daily_flat_series(self.ev["enriched"], flat_id)
        return {
            "flat_id": flat_id, "horizon": "28d measured", "status": "measured", "responsibility": "n/a",
            "totals": {k: t[k] for k in ("kwh", "sek", "co2_kg", "kwh_per_resident", "sek_per_resident",
                                          "co2_kg_per_resident", "kwh_per_m2", "peak_share", "coverage",
                                          "price_coverage", "residents", "floor_area_m2")},
            "channels": b.to_dict("records"),
            "daily": [{"day": i, **r} for i, r in daily.to_dict("index").items()],
            "projection_annual": project_triplet(t["kwh"], t["sek"], t["co2_kg"],
                                                 {k: daily[k].to_numpy() for k in daily}),
            "assumptions": [
                "channel types are ASSUMPTIONS from load shape; the dataset has no appliance labels",
                "SEK = kWh x spot price (excl. VAT, network fee, energy tax)",
                "kgCO2e = kWh x synthetic carbon factor / 1000",
                "peak = local 07-09 and 17-20 (Europe/Stockholm)",
            ],
            "uncertainty": {"coverage": t["coverage"], "price_coverage": t["price_coverage"],
                            "note": "hours with missing kWh or price are excluded from sums, not set to zero"},
        }

    def flat_findings(self, flat_id: str) -> list[dict]:
        self.check_flat(flat_id)
        mine = [f for f in self.findings if f["flat_id"] == flat_id]
        texts = generate_many([self._student_job(f) for f in mine])
        return [{**f, "student_text": t} for f, t in zip(mine, texts)]

    def scenario(self, flat_id: str, scenario: str, params: dict) -> dict:
        self.check_flat(flat_id)
        params = dict(params or {})
        if scenario == "return_to_baseline":
            if self.ds.anomaly(params["anomaly_id"])["flat_id"] != flat_id:
                raise ValueError("anomaly does not belong to this flat")
        else:
            params["flat_id"] = flat_id
            if scenario == "shift_flexible_load":
                params.setdefault("channel", sorted(C.FLEXIBLE_CHANNELS)[0])
        return run_scenario(self.ds, scenario, params, before=self.ev)

    # ---------- manager views ----------
    def portfolio(self) -> dict:
        rows = []
        for fid in self.ds.flat_ids:
            ap = self.ev["lenses"]["apartment"].loc[fid]
            rs = self.ev["lenses"]["resident"].loc[fid]
            t = self.ev["totals"].loc[fid]
            open_f = [f for f in self.findings if f["flat_id"] == fid and f["status_level"] not in (Status.VERIFIED, Status.DISMISSED)]
            rows.append({
                "flat_id": fid, "residents": t["residents"], "floor_area_m2": t["floor_area_m2"],
                "apartment_score": ap["score"], "apartment_band": ap["band"], "apartment_rank": ap["rank"],
                "resident_score": rs["score"], "resident_band": rs["band"],
                "health": ap["health"],
                "open_findings": len(open_f),
                "open_manager_findings": sum(f["responsibility"] == "manager" for f in open_f),
                "kwh_28d": t["kwh"], "sek_28d": t["sek"], "co2_kg_28d": t["co2_kg"],
                "coverage": t["coverage"],
            })
        tot = self.ev["totals"]
        return {
            "horizon": "28d measured", "status": "measured", "data_source": self.quality["data_source"],
            "flats": rows,
            "totals": {"kwh": tot["kwh"].sum(), "sek": tot["sek"].sum(), "co2_kg": tot["co2_kg"].sum()},
            "assumptions": SCORE_ASSUMPTIONS,
            "uncertainty": {"note": "see /flats/{id}/scores for score p5-p95 and rank p5-p95"},
        }

    def portfolio_findings(self, status: str | None = None, responsibility: str | None = None) -> list[dict]:
        out = self.findings
        if status:
            out = [f for f in out if f["status"] == status.upper()]
        if responsibility:
            out = [f for f in out if f["responsibility"] == responsibility]
        texts = generate_many([self._manager_job(f) for f in out])
        return [{**f, "manager_text": t} for f, t in zip(out, texts)]

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
        # opening a work order does NOT confirm anything: the finding keeps its engine status
        return self.workorders.create(f, note)

    def patch_workorder(self, wid: str, status: str | None = None, fault_found: bool | None = None) -> dict:
        """Technician outcome: fault_found=true -> CONFIRMED, false -> DISMISSED (excluded from HEALTH);
        status=repaired -> REPAIRED."""
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
        rate = a["observed_kwh_per_h"]
        res = verify(rate, post, a["status"], simulated=simulated)
        res["finding_id"] = a["id"]
        w["verification"] = res
        if res["status"] == "VERIFIED":
            a["status"] = Status.VERIFIED
            a["verification"] = res
            proj = project_triplet(res["saving_kwh"] / res["post_days"] * C.PERIOD_DAYS, np.nan, np.nan,
                                   extra_assumptions=["scaled from measured post-repair saving"]
                                   + (["SIMULATED post-repair data"] if simulated else []))
            res["projection_annual_kwh"] = proj["kwh"]
        self.recompute()
        return {"workorder": w, "verification": res, "finding": self.findings_by_id[a["id"]]}

    def notifications_flat(self, flat_id):
        return notifications.for_flat(flat_id, self.findings, list(self.workorders.items.values()))

    def notifications_manager(self):
        return notifications.for_manager(self.reports.items, list(self.workorders.items.values()))

    def business_reference(self):
        return business_case.engine_reference(self.findings, len(self.ds.flat_ids))

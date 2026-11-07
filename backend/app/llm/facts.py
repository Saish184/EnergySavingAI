"""Engine output -> a FactSheet: the ONLY quantities any text may contain.

Every Fact carries value, unit, a ready-made display string (unit and tariff condition included), the
evidence category, the period it refers to and the engine field it came from. Texts (LLM or template) refer
to facts by {PLACEHOLDER}; the renderer inserts `display`. Nothing here calculates kWh, SEK, CO2e, scores,
projections or savings: values are copied from Mina's engine output (findings, scores, portfolio). The only
operations are rounding for display, ordering three pillar values, and formatting the engine's peak-hour list.

Evidence categories (never conflated; see validator.CATEGORY_RULES):
  observed            measured consumption in the pattern's hours
  unusual             statistical evidence / measured excess attributed to a possible equipment fault
  possible_waste      measured excess counted as possible avoidable use (never "confirmed waste")
  avoidable_estimate  simulated avoidable kWh at the stated assumptions, and its scenario range
  simulated_saving    potential saving if followed fully (counterfactual over the observed window)
  estimated_realized  saving at the student's adoption estimate (only if the engine provides it)
  verified            measured saving from post-change data (only if VERIFIED)
  projection          annual extrapolation (only where the engine provides one)
Plus non-quantity facts: period, evidence (test statistics), score, label, id.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from .. import config as C

DEMO_DISCLAIMER = ("Synthetic demonstration data (fictional flats). Numbers show the method; "
                   "they are not evidence about real students or real savings.")

QUANTITY_CATEGORIES = {"observed", "unusual", "possible_waste", "avoidable_estimate", "simulated_saving",
                       "estimated_realized", "verified", "projection"}
TARIFF_TEXT = {
    "hourly_spot": "if you have an hourly spot-price contract",
    "monthly_average_spot": "on a monthly-average spot contract",
    "included_in_rent": "if electricity is included in the rent",
}


@dataclass
class Fact:
    id: str
    value: Any
    unit: str
    display: str
    category: str
    source: str
    period: str | None = None          # id of the period fact this quantity refers to
    tariff: str | None = None


@dataclass
class FactSheet:
    use_case: str
    audience: str                      # "student" | "manager"
    facts: dict[str, Fact] = field(default_factory=dict)
    context: dict = field(default_factory=dict)   # non-numeric engine labels (title, wording, type, ...)
    required: list[str] = field(default_factory=list)
    rules: dict = field(default_factory=dict)

    def add(self, fid, value, unit, display, category, source, period=None, tariff=None):
        if value is None:
            return None
        if isinstance(value, float) and value != value:     # NaN
            return None
        self.facts[fid] = Fact(fid, value, unit, display, category, source, period, tariff)
        return fid

    def to_prompt(self) -> dict:
        """What a provider sees: placeholders + meaning, never raw numbers to copy."""
        return {"context": self.context,
                "facts": {k: {"means": f"{f.category} | {f.unit}" + (f" | period: {{{f.period}}}" if f.period else "")
                              + (f" | tariff: {f.tariff}" if f.tariff else ""),
                              "renders_as": f.display} for k, f in self.facts.items()},
                "required_placeholders": self.required, "rules": self.rules}

    def to_dict(self) -> dict:
        return {"use_case": self.use_case, "audience": self.audience, "context": self.context,
                "facts": {k: asdict(v) for k, v in self.facts.items()}, "required": self.required, "rules": self.rules}


# ---------------------------------------------------------------- formatting only

def _kwh(x):
    return f"{x:.1f} kWh" if abs(x) >= 1 else f"{x:.2f} kWh"


def _sek(x):
    return f"{x:.0f} SEK" if abs(x) >= 100 else f"{x:.1f} SEK"


def _kg(x):
    return f"{x:.2f} kg CO2e"


def _num(x):
    return None if x is None or (isinstance(x, float) and x != x) else float(x)


def _date(ts) -> str:
    t = pd.Timestamp(ts).tz_convert(C.TZ_LOCAL)
    return f"{t.day} {t.strftime('%b')}"


def _hour_ranges(hours) -> str:
    """Engine peak-hour list -> '07:00-10:00 and 17:00-21:00' (formatting of start hours, no new data)."""
    hs = sorted(int(h) for h in hours)
    if not hs:
        return ""
    groups, start, prev = [], hs[0], hs[0]
    for h in hs[1:]:
        if h != prev + 1:
            groups.append((start, prev))
            start = h
        prev = h
    groups.append((start, prev))
    return " and ".join(f"{a:02d}:00-{(b + 1) % 24:02d}:00" for a, b in groups) + " local time"


def _appliance(f: dict) -> str:
    t = f.get("assumed_type") or ""
    return f"{t} appliance" if t.endswith("-like") else "appliance (type unknown)"


SAFE_ACTION_KIND = {
    "fault_step_change": "report",
    "base_load_outlier": "confirm",
    "scheduled_block": "confirm",
    "heater_pattern": "confirm",
    "peak_usage": "try",
}


# ---------------------------------------------------------------- findings

def finding_sheet(f: dict, audience: str) -> FactSheet:
    """Facts for one finding (Mina's finding card)."""
    uc = f"finding_{audience}"
    s = FactSheet(uc, audience)
    a, q, u = f.get("avoidable_28d") or {}, f.get("quantities") or {}, f.get("uncertainty") or {}
    ev, val, tiers = f.get("evidence") or {}, f.get("valuation") or {}, f.get("tiers") or {}
    stats = ev.get("statistics") or {}
    shift = a.get("kind") == "shift"
    days = _num(a.get("window_days"))
    s.context = {
        "finding_type": f["type"], "title": f["title"], "wording": f["wording"], "status": f["status"],
        "responsibility": f["responsibility"], "responsibility_note": f.get("responsibility_note"),
        "counts_as": f.get("counts_as"), "appliance": _appliance(f), "appliance_type_is_assumption": True,
        "kind": a.get("kind"), "method": a.get("method"),
        "money_note": "spot-energy component only (excl. VAT, network fee, energy tax, markup, fixed fees); not a bill saving",
        "simulated_post_repair_data": bool(f.get("simulated")),
        "projection_available": (f.get("projection_annual") or {}).get("sek", {}).get("value") is not None,
        "projection_reason": (f.get("projection_annual") or {}).get("kwh", {}).get("reason"),
        "estimated_realized_reason": tiers.get("estimated_realized_reason"),
        "verified_reason": tiers.get("verified_reason"),
    }
    # period
    P = s.add("P_WINDOW", days, "days", f"the {days:g} observed days" if days else "the observed period",
              "period", "avoidable_28d.window_days")
    s.add("SINCE", _date(f["window"]["start"]), "date", _date(f["window"]["start"]), "period", "window.start")

    # potential saving (simulated, if followed fully)
    if not shift:
        s.add("SAVE_KWH", _num(a.get("kwh")), "kWh", _kwh(a["kwh"]), "simulated_saving", "avoidable_28d.kwh", P)
    s.add("SAVE_CO2", _num(a.get("co2_kg")), "kgCO2e", _kg(a["co2_kg"]), "simulated_saving", "avoidable_28d.co2_kg", P)
    hourly = _num((val.get("sek_by_tariff") or {}).get("hourly_spot"))
    if hourly is None:
        hourly = _num(val.get("sek_if_hourly_spot"))
    s.add("SAVE_SEK_HOURLY", hourly, "SEK", f"{_sek(hourly)} {TARIFF_TEXT['hourly_spot']}" if hourly is not None else "",
          "simulated_saving", "valuation.sek_by_tariff.hourly_spot", P, "hourly_spot")
    monthly = _num((val.get("sek_by_tariff") or {}).get("monthly_average_spot"))
    if monthly is not None and (monthly > 0 or shift):
        s.add("SAVE_SEK_MONTHLY", monthly, "SEK", f"{_sek(monthly)} {TARIFF_TEXT['monthly_average_spot']}",
              "simulated_saving", "valuation.sek_by_tariff.monthly_average_spot", P, "monthly_average_spot")
    rent = _num((val.get("sek_by_tariff") or {}).get("included_in_rent"))
    if rent is not None and audience == "student":
        s.add("SAVE_SEK_RENT", rent, "SEK", f"{_sek(rent)} {TARIFF_TEXT['included_in_rent']}", "simulated_saving",
              "valuation.sek_by_tariff.included_in_rent", P, "included_in_rent")

    # ladder: observed / measured excess / simulated avoidable
    s.add("OBS_KWH", _num(q.get("observed_kwh")), "kWh", _kwh(q["observed_kwh"]) if q.get("observed_kwh") is not None else "",
          "observed", "quantities.observed_kwh", P)
    if not shift:
        cat = "unusual" if f["responsibility"] == "manager" else "possible_waste"
        s.add("EXCESS_KWH", _num(q.get("unexplained_excess_kwh")), "kWh", _kwh(q.get("unexplained_excess_kwh") or 0),
              cat, "quantities.unexplained_excess_kwh", P)
        rk = (u.get("scenario_range") or {}).get("kwh")
        if rk and rk[0] is not None and rk[1] is not None and abs(rk[1] - rk[0]) > 1e-9:
            s.add("RANGE_KWH", [float(rk[0]), float(rk[1])], "kWh", f"between {_kwh(rk[0])} and {_kwh(rk[1])}",
                  "avoidable_estimate", "uncertainty.scenario_range.kwh", P)
    else:
        s.add("MOVED_KWH", _num(q.get("kwh_moved")), "kWh", _kwh(q.get("kwh_moved") or 0), "observed",
              "quantities.kwh_moved", P)
        rs = (u.get("scenario_range") or {}).get("sek_spot_hourly")
        if rs and rs[0] is not None and abs(rs[1] - rs[0]) > 1e-9:
            s.add("RANGE_SEK_HOURLY", [float(rs[0]), float(rs[1])], "SEK",
                  f"between {_sek(rs[0])} and {_sek(rs[1])} {TARIFF_TEXT['hourly_spot']}", "simulated_saving",
                  "uncertainty.scenario_range.sek_spot_hourly", P, "hourly_spot")
        if stats.get("peak_hours_local"):
            s.add("PEAK_HOURS", list(stats["peak_hours_local"]), "local hours", _hour_ranges(stats["peak_hours_local"]),
                  "evidence", "evidence.statistics.peak_hours_local")
        s.add("RUNS_IN_PEAK", stats.get("runs_in_peak"), "runs", f"{stats.get('runs_in_peak')}", "evidence",
              "evidence.statistics.runs_in_peak")
        s.add("RUNS_TOTAL", stats.get("runs_total"), "runs", f"{stats.get('runs_total')}", "evidence",
              "evidence.statistics.runs_total")
        s.context["schedule_rule"] = "the engine moves each run to the first later hour outside the peak-price hours"
    # estimated realised / verified / projection: only when the engine provides them
    er = tiers.get("estimated_realized")
    if isinstance(er, dict) and er.get("kwh") is not None:
        s.add("REALIZED_KWH", float(er["kwh"]), "kWh", _kwh(er["kwh"]), "estimated_realized", "tiers.estimated_realized.kwh", P)
    if f["status"] == "VERIFIED" and tiers.get("verified") is not None:
        s.add("VERIFIED_KWH", float(tiers["verified"]), "kWh", _kwh(tiers["verified"]) + (" (simulated data)" if f.get("simulated") else ""),
              "verified", "tiers.verified")
    pj = (f.get("projection_annual") or {}).get("sek") or {}
    if pj.get("value") is not None and pj.get("low") is not None:
        s.add("PROJ_SEK_RANGE", [pj["low"], pj["high"]], "SEK per year",
              f"{_sek(pj['low'])} to {_sek(pj['high'])} per year {TARIFF_TEXT['hourly_spot']}",
              "projection", "projection_annual.sek", None, "hourly_spot")
    # evidence statistics (no probabilities; occupancy details minimised)
    _evidence_facts(s, f["type"], stats, ev, audience)
    if audience == "manager":
        s.add("FLAT", f["flat_id"], "id", f["flat_id"], "label", "flat_id")
        s.add("APPLIANCE_ID", f["appliance_id"], "id", f["appliance_id"], "label", "appliance_id")
        s.add("BASE_RATE", _num(ev.get("baseline_kwh_per_h")), "kWh/h", f"{ev.get('baseline_kwh_per_h'):.3f} kWh/h"
              if ev.get("baseline_kwh_per_h") is not None else "", "evidence", "evidence.baseline_kwh_per_h")
        s.add("OBS_RATE", _num(ev.get("observed_kwh_per_h")), "kWh/h", f"{ev.get('observed_kwh_per_h'):.3f} kWh/h"
              if ev.get("observed_kwh_per_h") is not None else "", "evidence", "evidence.observed_kwh_per_h")
    s.required, s.rules = _requirements(f, s, audience)
    return s


def _evidence_facts(s: FactSheet, typ: str, st: dict, ev: dict, audience: str):
    if typ == "fault_step_change":
        s.add("P_VALUE", st.get("p_value"), "p-value", f"p = {st.get('p_value')}", "evidence", "evidence.statistics.p_value")
        s.add("ALPHA", st.get("alpha"), "alpha", f"{st.get('alpha')}", "evidence", "evidence.statistics.alpha")
        if st.get("ratio") is not None:
            s.add("RATIO", st.get("ratio"), "x", f"{st['ratio']:.1f} times", "evidence", "evidence.statistics.ratio")
    elif typ == "base_load_outlier":
        s.add("WEEKS_ABOVE", st.get("weeks_above_peer_range"), "weeks", f"{st.get('weeks_above_peer_range')}", "evidence",
              "evidence.statistics.weeks_above_peer_range")
        s.add("WEEKS", st.get("weeks"), "weeks", f"{st.get('weeks')}", "evidence", "evidence.statistics.weeks")
        if st.get("excess_w") is not None:
            s.add("EXCESS_W", st["excess_w"], "W", f"{st['excess_w']:.0f} W", "evidence", "evidence.statistics.excess_w")
    elif typ == "scheduled_block":
        if st.get("local_hours"):
            s.add("BLOCK_HOURS", list(st["local_hours"]), "local hours", _hour_ranges(st["local_hours"]), "evidence",
                  "evidence.statistics.local_hours")
    elif typ == "heater_pattern":
        # occupancy minimisation: only the number of days, no hours or timestamps of absences
        s.add("HEAT_DAYS", st.get("days"), "days", f"{st.get('days')} days", "evidence", "evidence.statistics.days")
        s.context["occupancy_note"] = "occupancy is a simulated sensor estimate"


def _requirements(f: dict, s: FactSheet, audience: str) -> tuple[list[str], dict]:
    t = f["type"]
    req: list[str] = []
    rules = {"kind": (f.get("avoidable_28d") or {}).get("kind"), "type": t, "status": f["status"],
             "responsibility": f["responsibility"], "suggested_cta": "none" if f["status"] in ("REPAIRED", "VERIFIED", "DISMISSED")
             else ("report" if f["responsibility"] == "manager" else SAFE_ACTION_KIND.get(t, "try"))}
    if t == "fault_step_change":
        req += ["SAVE_KWH", "P_WINDOW"]
    elif t == "base_load_outlier":
        req += ["EXCESS_KWH", "RANGE_KWH", "P_WINDOW"]
        rules["must_distinguish_excess_from_avoidable"] = True
    elif t == "scheduled_block":
        req += ["SAVE_KWH", "P_WINDOW"]
        rules["must_say_potentially_unnecessary"] = True
        rules["must_ask_confirmation"] = audience == "student"
    elif t == "heater_pattern":
        req += ["SAVE_KWH", "P_WINDOW"]
        rules["heating_safety"] = True
        rules["must_ask_confirmation"] = audience == "student"
    elif t == "peak_usage":
        req += ["SAVE_SEK_HOURLY", "MOVED_KWH"]
        rules["shift_saves_money_not_energy"] = True
    return [r for r in req if r in s.facts], rules


# ---------------------------------------------------------------- scores / overview / portfolio

def score_sheet(scores: dict) -> FactSheet:
    s = FactSheet("score_explainer", "student")
    lens = scores["lenses"]["resident"]
    p = {k: float(v) for k, v in lens["pillars"].items()}
    order = sorted(p, key=lambda k: p[k])                       # ordering of three engine values (no maths)
    s.context = {"score_name": "Resident Actions", "band": lens["band"], "excludes": lens.get("excludes"),
                 "pillar_meaning": {"use": "electricity used compared with the most efficient flats",
                                    "waste": "possible avoidable use the engine found",
                                    "timing": "flexible appliances run in peak-price hours"},
                 "strongest_pillar": order[-1], "weakest_pillar": order[0], "period": "the 28-day period"}
    s.add("SCORE", float(lens["score"]), "score", f"{lens['score']:.0f} out of 100", "score", "lenses.resident.score")
    s.add("BAND", lens["band"], "band", f"band {lens['band']}", "label", "lenses.resident.band")
    for k, v in p.items():
        s.add(f"PILLAR_{k.upper()}", v, "score", f"{v:.0f} out of 100", "score", f"lenses.resident.pillars.{k}")
    s.add("STRONGEST_VALUE", p[order[-1]], "score", f"{p[order[-1]]:.0f} out of 100", "score", f"lenses.resident.pillars.{order[-1]}")
    s.add("WEAKEST_VALUE", p[order[0]], "score", f"{p[order[0]]:.0f} out of 100", "score", f"lenses.resident.pillars.{order[0]}")
    s.add("P_28", 28, "days", "the 28-day period", "period", "horizon")
    sens = lens.get("sensitivity") or {}
    if sens.get("score_p5") is not None:
        s.add("SCORE_RANGE", [sens["score_p5"], sens["score_p95"]], "score",
              f"between {sens['score_p5']:.0f} and {sens['score_p95']:.0f}", "score", "lenses.resident.sensitivity")
    s.required = ["SCORE", f"PILLAR_{order[-1].upper()}", f"PILLAR_{order[0].upper()}"]
    s.rules = {"strongest_pillar": order[-1], "weakest_pillar": order[0], "no_health": True}
    return s


def overview_sheet(scores: dict, findings: list[dict], combined: dict | None) -> FactSheet:
    """The flat's 28-day overview (served at /flats/{id}/digest). No weekly sums: the engine does not provide them."""
    s = FactSheet("weekly_digest", "student")
    sc = score_sheet(scores)
    s.facts.update({k: v for k, v in sc.facts.items() if k in ("SCORE", "BAND", "STRONGEST_VALUE", "P_28")})
    strong = sc.rules["strongest_pillar"]
    s.context = {"strongest_pillar": strong, "period": "the 28-day period", "top_finding": None}
    live = [f for f in findings if f["status"] not in ("DISMISSED",)]
    if live:
        top = live[0]                                            # engine order (sorted by potential SEK)
        ts = finding_sheet(top, "student")
        s.context["top_finding"] = {k: ts.context[k] for k in ("title", "wording", "status", "responsibility", "appliance", "kind")}
        for k in ("SAVE_SEK_HOURLY", "SAVE_KWH", "P_WINDOW", "MOVED_KWH"):
            if k in ts.facts:
                s.facts["TOP_" + k] = Fact("TOP_" + k, ts.facts[k].value, ts.facts[k].unit, ts.facts[k].display, ts.facts[k].category,
                                           "findings[0]." + ts.facts[k].source, "TOP_P_WINDOW" if ts.facts[k].period else None,
                                           ts.facts[k].tariff)
        s.rules.update({k: v for k, v in ts.rules.items() if k in ("shift_saves_money_not_energy", "heating_safety")})
        s.rules["status"], s.rules["responsibility"], s.rules["type"] = top["status"], top["responsibility"], top["type"]
    if combined and combined.get("kwh") is not None:
        s.add("P_ALL", "observed period", "period", "the observed period of each finding", "period", "combined_potential")
        s.add("ALL_KWH", float(combined["kwh"]), "kWh", _kwh(combined["kwh"]), "simulated_saving", "combined_potential.kwh", "P_ALL")
        s.add("ALL_SEK_HOURLY", float(combined["sek_if_hourly_spot"]), "SEK",
              f"{_sek(combined['sek_if_hourly_spot'])} {TARIFF_TEXT['hourly_spot']}", "simulated_saving",
              "combined_potential.sek_if_hourly_spot", "P_ALL", "hourly_spot")
    s.required = ["SCORE"]
    return s


def portfolio_sheet(portfolio: dict) -> FactSheet:
    s = FactSheet("portfolio_manager", "manager")
    flats = portfolio["flats"]
    s.add("P_28", 28, "days", "the 28-day period", "period", "horizon")
    s.add("N_FLATS", len(flats), "flats", f"{len(flats)} flats", "label", "flats")
    s.add("TOTAL_KWH", float(portfolio["totals"]["kwh"]), "kWh", _kwh(portfolio["totals"]["kwh"]), "observed", "totals.kwh", "P_28")
    pot = portfolio.get("potential") or {}
    s.add("P_ALL", "observed period", "period", "the observed period of each finding", "period", "potential")
    if pot.get("kwh") is not None:
        s.add("POT_KWH", float(pot["kwh"]), "kWh", _kwh(pot["kwh"]), "simulated_saving", "potential.kwh", "P_ALL")
        s.add("POT_SEK_HOURLY", float(pot["sek_if_hourly_spot"]), "SEK", f"{_sek(pot['sek_if_hourly_spot'])} if every flat had an "
              "hourly spot-price contract", "simulated_saving", "potential.sek_if_hourly_spot", "P_ALL", "hourly_spot")
    maint = portfolio.get("maintenance") or []
    s.add("N_MAINT", len(maint), "findings", f"{len(maint)}", "label", "maintenance")
    by = (portfolio.get("evidence_quality") or {}).get("findings_by_status") or {}
    for st, n in by.items():
        s.add(f"N_{st}", int(n), "findings", f"{int(n)}", "evidence", f"evidence_quality.findings_by_status.{st}")
    top = min(flats, key=lambda r: r["apartment_rank"])
    low = max(flats, key=lambda r: r["apartment_rank"])
    s.add("BEST_FLAT", top["flat_id"], "id", top["flat_id"], "label", "flats[apartment_rank=1].flat_id")
    s.add("LOW_FLAT", low["flat_id"], "id", low["flat_id"], "label", f"flats[apartment_rank={int(low['apartment_rank'])}].flat_id")
    s.context = {"maintenance_findings": [{"finding_id": m["finding_id"], "flat_id": m["flat_id"], "status": m["status"],
                                           "wording": m["wording"]} for m in maint],
                 "note": "potential is simulated (if every finding were acted on fully), not verified",
                 "money_note": "spot-energy component only; not a bill saving"}
    for i, m in enumerate(maint[:5]):
        s.add(f"MAINT_{i + 1}", m["finding_id"], "id", m["finding_id"], "label", f"maintenance[{i}].finding_id")
    s.required = ["POT_KWH"] if "POT_KWH" in s.facts else []
    s.rules = {"behaviour_not_maintenance": True}
    return s

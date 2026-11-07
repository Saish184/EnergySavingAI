"""System prompts (versioned) and payload builders that turn engine output into the LLM input JSON.
Payloads contain ONLY engine numbers, already rounded; the validator checks replies against them."""
from __future__ import annotations

import json

import pandas as pd

from .. import config as C
from . import schemas

PROMPT_VERSION = "v1"

SHARED_RULES = """
You write short messages for an energy-saving app used in shared student flats in Sweden.
You receive engine output as JSON. Follow these rules strictly:
1. Use ONLY numbers that appear in the input. You may round them. Never compute,
   estimate, add, or convert numbers yourself.
2. Keep the evidence level exactly:
   DETECTED  → say "unusual pattern"
   PLAUSIBLE → say "possible" (e.g. "possible fault")
   CONFIRMED → say "confirmed"
   REPAIRED  → say "repaired, waiting for new data to measure the saving"
   VERIFIED  → say "measured saving"
   Never describe something as certain if the status is DETECTED or PLAUSIBLE.
3. Any yearly value must be called "projected" and is never a promise.
   28-day values are "measured over the last 4 weeks".
4. Appliance types are assumptions: say "fridge-like appliance", not "your fridge".
5. If responsibility is "manager", never suggest the residents caused it; tell them
   what they can check and that they can report it.
6. If responsibility is "unknown", present it as an opportunity that needs confirmation.
7. A load-shift scenario saves money, not energy: never claim it reduces kWh.
8. No guilt, no exaggeration, no emojis, no jargon (avoid "kWh" for students unless
   it is in the input; always prefer SEK first for students).
9. Output only via the provided tool.
"""

STUDENT_PROMPT = SHARED_RULES + """
Audience: a student with no energy background. Friendly, concrete, max 2 sentences
in body. The action must be something a student can do in under 5 minutes.
"""

MANAGER_PROMPT = SHARED_RULES + """
Audience: a housing manager deciding whether to send a technician. Precise and neutral.
Mention since when, how strong the evidence is (status + confidence), and the
measured 28-day impact. Priority: high if status >= PLAUSIBLE and 28-day SEK impact
is the largest in the portfolio input, medium if PLAUSIBLE, low if DETECTED.
"""

DIGEST_PROMPT = SHARED_RULES + """
Audience: residents of one flat. Summarise the week in exactly 3 bullets:
1 thing that went well, 1 finding to look at, 1 simple action. Positive tone.
"""

SCORE_PROMPT = SHARED_RULES + """
Audience: a student. Explain the Resident Actions score in plain words using the
pillar values given. Name the strongest and weakest pillar and one next step.
Never mention the Health pillar (it is not part of the resident score).
"""

SYSTEM_PROMPTS = {
    "finding_student": STUDENT_PROMPT,
    "finding_manager": MANAGER_PROMPT,
    "weekly_digest": DIGEST_PROMPT,
    "score_explainer": SCORE_PROMPT,
}

# phrase that must appear for each status (shared with validator and templates)
REQUIRED_PHRASE = {
    "DETECTED": "unusual pattern",
    "PLAUSIBLE": "possible",
    "CONFIRMED": "confirmed",
    "REPAIRED": "repaired",
    "VERIFIED": "measured saving",
    "DISMISSED": "no fault found",
}


def user_message(use_case: str, payload: dict, failures: list[str] | None = None) -> str:
    msg = (f"Engine output (JSON):\n{json.dumps(payload, ensure_ascii=False, indent=1)}\n\n"
           f"Call the tool `{schemas.TOOL_NAMES[use_case]}` exactly once with your message.")
    if failures:
        msg += ("\n\nYour previous answer was rejected by the checker for these reasons; fix them:\n- "
                + "\n- ".join(failures))
    return msg


# ---------------- payload builders (engine output -> LLM input) ----------------

def _r(x, nd=2):
    return None if x is None or x != x else round(float(x), nd)


def _date(ts) -> str:
    t = pd.Timestamp(ts).tz_convert(C.TZ_LOCAL)
    return f"{t.day} {t.strftime('%b')}"


def _appliance(f: dict) -> str:
    t = f["assumed_type"]
    return f"{t} appliance" if t.endswith("-like") else f"appliance on channel {f['channel']} (type unknown)"


def payload_finding_student(f: dict, ctx: dict) -> dict:
    m, p = f["avoidable_28d"], f["projection_annual"]["sek"]
    shift = m.get("scenario") == "shift_flexible_load"
    measured = {"sek": _r(m["sek"]), "co2_kg": _r(m["co2_kg"])}
    if not shift:
        measured["kwh"] = _r(m["kwh"], 1)
    out = {
        "finding_type": f["type"],
        "title": f["title"],
        "appliance": _appliance(f),
        "appliance_type_is_assumption": True,
        "status": f["status"],
        "required_wording": REQUIRED_PHRASE[f["status"]],
        "responsibility": f["responsibility"],
        "responsibility_note": f["responsibility_note"],
        "since": _date(f["window"]["start"]),
        "fix": "run it later (load shift: saves money and CO2, NOT energy)" if shift
               else "return to normal use",
        "measured_last_4_weeks": measured,
        "projected_per_year_sek": {"low": _r(p["low"], 0), "high": _r(p["high"], 0)},
        "suggested_cta": "none" if f["status"] in ("REPAIRED", "VERIFIED", "DISMISSED")
                         else {"manager": "report", "resident": "try", "unknown": "report"}[f["responsibility"]],
    }
    if shift:
        out["cheapest_hour_local"] = ctx.get("cheapest_hour_local")
    return out


def payload_finding_manager(f: dict, ctx: dict) -> dict:
    m = f["avoidable_28d"]
    pk, ps = f["projection_annual"]["kwh"], f["projection_annual"]["sek"]
    ev = f["evidence"]
    return {
        "flat_id": f["flat_id"],
        "appliance_id": f["appliance_id"],
        "appliance": _appliance(f),
        "appliance_type_is_assumption": True,
        "finding_type": f["type"],
        "title": f["title"],
        "status": f["status"],
        "required_wording": REQUIRED_PHRASE[f["status"]],
        "detector_confidence": _r(ev["confidence"]),
        "responsibility": f["responsibility"],
        "since": _date(f["window"]["start"]),
        "window_days": _r(f["window"]["days"], 1),
        "baseline_kwh_per_h": _r(ev["baseline_kwh_per_h"], 3),
        "observed_kwh_per_h": _r(ev["observed_kwh_per_h"], 3),
        "evidence_text": ev["text"],
        "measured_last_4_weeks": {"kwh": _r(m["kwh"], 1), "sek": _r(m["sek"]), "co2_kg": _r(m["co2_kg"])},
        "fix_scenario": m.get("scenario"),
        "projected_per_year": {"kwh_low": _r(pk["low"], 0), "kwh_high": _r(pk["high"], 0),
                               "sek_low": _r(ps["low"], 0), "sek_high": _r(ps["high"], 0)},
        "is_largest_28d_sek_impact_in_portfolio": f["id"] == ctx.get("largest_sek_finding_id"),
    }


def payload_score(scores: dict) -> dict:
    lens = scores["lenses"]["resident"]
    pillars = {k: _r(v, 0) for k, v in lens["pillars"].items()}
    order = sorted(pillars, key=lambda k: pillars[k])
    sens = lens["sensitivity"]
    return {
        "flat_id": scores["flat_id"],
        "score_name": "Resident Actions",
        "score": _r(lens["score"], 0),
        "band": lens["band"],
        "rank": int(lens["rank"]),
        "of_flats": lens["of"],
        "pillars_out_of_100": pillars,
        "pillar_meaning": {
            "use": "how much electricity the flat uses compared with the most efficient flats",
            "waste": "electricity used while nobody is home",
            "timing": "whether flexible use happens in cleaner hours",
        },
        "strongest_pillar": order[-1],
        "weakest_pillar": order[0],
        "score_range_with_other_weights": [_r(sens["score_p5"], 0), _r(sens["score_p95"], 0)],
        "horizon": "measured over the last 4 weeks",
    }


def payload_digest(scores: dict, week: dict, top_finding: dict | None, ctx: dict) -> dict:
    sp = payload_score(scores)
    out = {
        "flat_id": scores["flat_id"],
        "resident_score": sp["score"],
        "band": sp["band"],
        "strongest_pillar": {"name": sp["strongest_pillar"],
                             "value": sp["pillars_out_of_100"][sp["strongest_pillar"]]},
        "last_7_days": {"sek": _r(week["last_7d"]["sek"], 0), "kwh": _r(week["last_7d"]["kwh"], 0),
                        "dates": week["last_7d"]["dates"]},
        "previous_7_days": {"sek": _r(week["prev_7d"]["sek"], 0), "kwh": _r(week["prev_7d"]["kwh"], 0)},
        "change_vs_previous_week_pct": _r(week["change_pct"], 0),
        "cheapest_hour_local": ctx.get("cheapest_hour_local"),
        "top_finding": None,
    }
    if top_finding:
        s = payload_finding_student(top_finding, ctx)
        out["top_finding"] = {k: s[k] for k in ("finding_type", "title", "appliance", "status", "required_wording",
                                                 "responsibility", "fix", "measured_last_4_weeks")}
        out["status"] = s["status"]                   # wording rule applies to the digest too
    return out

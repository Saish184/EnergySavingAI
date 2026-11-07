"""Text from our own wording (phrases.json) + engine numbers. No API, no key, deterministic.

Each list in phrases.json is a set of variants; a card picks one by a stable hash of its payload
(pass `variant=` to force one, used by the tests to check every variant)."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

PHRASES_PATH = Path(__file__).with_name("phrases.json")


@lru_cache(maxsize=1)
def phrases() -> dict:
    return json.loads(PHRASES_PATH.read_text(encoding="utf-8"))


def reload_phrases():
    phrases.cache_clear()


def _pick(options, payload: dict, salt: str, variant: int | None):
    if isinstance(options, str):
        return options
    if variant is not None:
        return options[variant % len(options)]
    h = hashlib.sha256((salt + json.dumps(payload, sort_keys=True)).encode()).hexdigest()
    return options[int(h, 16) % len(options)]


def n_variants() -> int:
    """Largest number of variants anywhere (tests loop over all of them)."""
    def walk(o):
        if isinstance(o, list):
            return len(o)
        if isinstance(o, dict):
            return max([walk(v) for v in o.values()] or [1])
        return 1
    return walk(phrases())


def _n(x, nd=0) -> str:
    return "?" if x is None else f"{x:.{nd}f}"


def _phrase(status: str, resp: str) -> str:
    p = phrases()["status_phrase"][status]
    return p[resp] if isinstance(p, dict) else p


def _fill(text: str, values: dict) -> str:
    return text.format_map(values)


def finding_student(p: dict, variant: int | None = None) -> dict:
    P = phrases()["finding_student"]
    t = p["finding_type"]
    m, y = p["measured_last_4_weeks"], p["projected_per_year_sek"]
    v = {"appliance": p["appliance"], "phrase": _phrase(p["status"], p["responsibility"]), "since": p["since"],
         "sek": _n(m["sek"]), "low": _n(y["low"]), "high": _n(y["high"]), "hour": p.get("cheapest_hour_local")}
    closed = p["status"] in ("REPAIRED", "VERIFIED", "DISMISSED")
    if "cheapest_hour_local" in p:
        body = _fill(_pick(P["body_shift"], p, "body", variant), v)
        action = _fill(_pick(P["action_shift"], p, "action", variant), v)
    else:
        body = _fill(_pick(P["body"], p, "body", variant), v)
        if p["responsibility"] == "manager":
            body += _pick(P["manager_suffix"], p, "suffix", variant)
        action = _pick(P["action"].get(t, P["action"]["_default"]), p, "action", variant)
    if closed:
        action = _pick(P["action_closed"], p, "closed", variant)
    title = _pick(phrases()["titles"].get(t, [p["title"]]), p, "title", variant)
    return {"title": title[:60], "body": body, "action": action,
            "cta": "none" if closed else p["suggested_cta"]}


def finding_manager(p: dict, variant: int | None = None) -> dict:
    from .validator import expected_priority
    P = phrases()["finding_manager"]
    m, y = p["measured_last_4_weeks"], p["projected_per_year"]
    v = {"flat_id": p["flat_id"], "appliance_id": p["appliance_id"], "appliance": p["appliance"],
         "title": p["title"], "status": p["status"], "phrase": _phrase(p["status"], p["responsibility"]),
         "since": p["since"], "confidence": _n(p["detector_confidence"], 2), "kwh": _n(m["kwh"], 1),
         "sek": _n(m["sek"]), "sek_low": _n(y["sek_low"]), "sek_high": _n(y["sek_high"]),
         "observed": _n(p["observed_kwh_per_h"], 3), "baseline": _n(p["baseline_kwh_per_h"], 3),
         "days": _n(p["window_days"], 1), "responsibility": p["responsibility"]}
    points = [_fill(e, v) for e in P["evidence"]]
    if p.get("evidence_text"):
        points.append(p["evidence_text"])
    return {"title": _fill(P["title"], v)[:80],
            "summary": _fill(_pick(P["summary"], p, "summary", variant), v),
            "evidence_points": points[:3],
            "suggested_check": P["check"].get(p["finding_type"], P["check"]["_default"]),
            "priority": expected_priority(p)}


def weekly_digest(p: dict, variant: int | None = None) -> dict:
    P = phrases()["weekly_digest"]
    sp = p["strongest_pillar"]
    bullets = [_fill(_pick(P["went_well"], p, "well", variant), {"pillar": sp["name"], "value": _n(sp["value"])})]
    tf = p.get("top_finding")
    if tf:
        bullets.append(_fill(_pick(P["look_at"], p, "look", variant),
                             {"title": tf["title"].lower(), "appliance": tf["appliance"],
                              "phrase": _phrase(tf["status"], tf["responsibility"])}))
    else:
        bullets.append(_pick(P["look_at_none"], p, "look", variant))
    if p.get("cheapest_hour_local"):
        bullets.append(_fill(_pick(P["action_hour"], p, "act", variant), {"hour": p["cheapest_hour_local"]}))
    else:
        bullets.append(_pick(P["action_default"], p, "act", variant))
    return {"headline": _fill(_pick(P["headline"], p, "head", variant), {"sek": _n(p["last_7_days"]["sek"])}),
            "bullets": bullets,
            "encouragement": _pick(P["encouragement"], p, "enc", variant)}


def score_explainer(p: dict, variant: int | None = None) -> dict:
    P = phrases()["score_explainer"]
    pl = p["pillars_out_of_100"]
    v = {"score": _n(p["score"]), "band": p["band"], "use": _n(pl["use"]), "waste": _n(pl["waste"]),
         "timing": _n(pl["timing"]), "strongest": p["strongest_pillar"], "weakest": p["weakest_pillar"],
         "Strongest": p["strongest_pillar"].capitalize()}
    return {"summary": _fill(_pick(P["summary"], p, "summary", variant), v),
            "strongest_pillar": p["strongest_pillar"], "weakest_pillar": p["weakest_pillar"],
            "next_step": _pick(P["next_step"][p["weakest_pillar"]], p, "next", variant)}


RENDER = {"finding_student": finding_student, "finding_manager": finding_manager,
          "weekly_digest": weekly_digest, "score_explainer": score_explainer}


def render(use_case: str, payload: dict, variant: int | None = None) -> dict:
    return RENDER[use_case](payload, variant)

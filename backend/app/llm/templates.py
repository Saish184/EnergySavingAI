"""Our own wording (phrases.json) -> raw output with {PLACEHOLDERS}, exactly like an LLM reply.
It is validated by the same validator before it is served. No API, no key, deterministic."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .facts import FactSheet

PHRASES_PATH = Path(__file__).with_name("phrases.json")
PH = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")
CTX = re.compile(r"\[\[([A-Za-z_]+)\]\]")
CLOSED = {"REPAIRED", "VERIFIED", "DISMISSED"}


@lru_cache(maxsize=1)
def phrases() -> dict:
    return json.loads(PHRASES_PATH.read_text(encoding="utf-8"))


def phrases_version() -> str:
    return phrases()["version"]


def status_phrase(status: str | None, responsibility: str | None) -> str:
    p = phrases()["status_phrase"].get(status or "", "")
    return p.get(responsibility, "") if isinstance(p, dict) else p


def _labels(sheet: FactSheet) -> dict:
    c = dict(sheet.context)
    ph = status_phrase(c.get("status") or sheet.rules.get("status"), c.get("responsibility") or sheet.rules.get("responsibility"))
    c["phrase"], c["Phrase"] = ph, ph[:1].upper() + ph[1:]
    tf = c.get("top_finding") or {}
    if tf:
        c["top_title_lower"] = tf["title"][:1].lower() + tf["title"][1:]
        c["top_appliance"] = tf["appliance"]
        c["top_phrase"] = status_phrase(tf["status"], tf["responsibility"])
    c["strongest"] = c.get("strongest_pillar", "")
    c["weakest"] = c.get("weakest_pillar", "")
    return {k: v for k, v in c.items() if isinstance(v, str)}


def _fill(text: str, sheet: FactSheet, labels: dict) -> str | None:
    """None if the variant needs a fact or label this sheet does not have."""
    if any(p not in sheet.facts for p in PH.findall(text)) or any(k not in labels for k in CTX.findall(text)):
        return None
    return CTX.sub(lambda m: labels[m.group(1)], text)


def _first(variants, sheet, labels) -> str | None:
    for v in variants if isinstance(variants, list) else [variants]:
        out = _fill(v, sheet, labels)
        if out is not None:
            return out
    return None


def render(use_case: str, sheet: FactSheet) -> dict | None:
    """Raw template output (placeholders kept), or None if no variant fits."""
    P, L = phrases()[use_case], _labels(sheet)
    try:
        if use_case == "finding_student":
            t = sheet.context["finding_type"]
            block = P["_closed"] if sheet.context["status"] in CLOSED else P.get(t, P["_closed"])
            return {"headline": sheet.context["title"], "explanation": _first(block["explanation"], sheet, L),
                    "action": _first(block["action"], sheet, L), "question": _first(block["question"], sheet, L) or "",
                    "cta": sheet.rules.get("suggested_cta", "none")}
        if use_case == "finding_manager":
            block = P[sheet.context["finding_type"]]
            pts = [x for x in (_fill(v, sheet, L) for v in block["evidence_points"]) if x]
            return {"headline": _first(P["_headline"], sheet, L), "summary": _first(block["summary"], sheet, L),
                    "evidence_points": pts[:3], "suggested_check": _first(block["suggested_check"], sheet, L)}
        if use_case == "weekly_digest":
            tf = sheet.context.get("top_finding")
            if tf:
                look = _first(P["look_at"], sheet, L)
                act = P["action_shift"] if tf.get("kind") == "shift" else \
                    P["action_report"] if tf["responsibility"] == "manager" else P["action_default"]
            else:
                look, act = _first(P["look_at_none"], sheet, L), P["action_default"]
            return {"headline": _first(P["headline"], sheet, L),
                    "bullets": [_first(P["went_well"], sheet, L), look, _first(act, sheet, L)],
                    "encouragement": _first(P["encouragement"], sheet, L)}
        if use_case == "score_explainer":
            w = sheet.rules["weakest_pillar"]
            return {"summary": _first(P["summary"], sheet, L), "strongest_pillar": sheet.rules["strongest_pillar"],
                    "weakest_pillar": w, "next_step": _first(P["next_step"][w], sheet, L)}
        if use_case == "portfolio_manager":
            bullets = [x for x in (_fill(b, sheet, L) for b in P["bullets"]) if x]
            return {"headline": _first(P["headline"], sheet, L), "bullets": bullets[:4],
                    "maintenance_note": _first(P["maintenance_note"], sheet, L)}
    except (KeyError, TypeError):
        return None
    return None

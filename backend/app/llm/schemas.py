"""Output models per use case (v2). Every text field may contain {PLACEHOLDER} references to facts and
must contain no digits. Strict tool schemas cannot express length limits, so LIMITS live in the validator.
Deterministic fields (priority, owner, cta) are set by code, not by the model."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Pillar = Literal["use", "waste", "timing"]


class FindingStudent(BaseModel):
    headline: str
    explanation: str
    action: str
    question: str                      # "" or one confirmation question (appliance identity, can it be switched off)
    cta: Literal["report", "try", "confirm", "none"]


class FindingManager(BaseModel):
    headline: str
    summary: str
    evidence_points: list[str]
    suggested_check: str


class WeeklyDigest(BaseModel):          # served as the flat's 28-day overview
    headline: str
    bullets: list[str]
    encouragement: str


class ScoreExplainer(BaseModel):
    summary: str
    strongest_pillar: Pillar
    weakest_pillar: Pillar
    next_step: str


class PortfolioManager(BaseModel):
    headline: str
    bullets: list[str]
    maintenance_note: str


SCHEMAS: dict[str, type[BaseModel]] = {
    "finding_student": FindingStudent,
    "finding_manager": FindingManager,
    "weekly_digest": WeeklyDigest,
    "score_explainer": ScoreExplainer,
    "portfolio_manager": PortfolioManager,
}

LIMITS = {
    "finding_student": {"headline": {"chars": 70}, "explanation": {"sentences": 2, "chars": 380},
                        "action": {"sentences": 1, "chars": 180}, "question": {"sentences": 1, "chars": 160}},
    "finding_manager": {"headline": {"chars": 90}, "summary": {"sentences": 3, "chars": 520},
                        "evidence_points": {"items": (2, 3)}, "suggested_check": {"sentences": 2, "chars": 260}},
    "weekly_digest": {"headline": {"chars": 90}, "bullets": {"items": (3, 3)}, "encouragement": {"sentences": 1, "chars": 160}},
    "score_explainer": {"summary": {"sentences": 2, "chars": 360}, "next_step": {"sentences": 1, "chars": 200}},
    "portfolio_manager": {"headline": {"chars": 90}, "bullets": {"items": (3, 4)}, "maintenance_note": {"sentences": 2, "chars": 300}},
}
ENUM_FIELDS = {"cta", "strongest_pillar", "weakest_pillar"}

TOOL_NAMES = {uc: f"write_{uc}" for uc in SCHEMAS}
TOOL_DESCRIPTIONS = {
    "finding_student": "Write the student-facing card for one finding, using {PLACEHOLDERS} for every number.",
    "finding_manager": "Write the manager-facing summary for one finding, using {PLACEHOLDERS} for every number.",
    "weekly_digest": "Write the flat's 28-day overview, using {PLACEHOLDERS} for every number.",
    "score_explainer": "Explain the flat's Resident Actions score, using {PLACEHOLDERS} for every number.",
    "portfolio_manager": "Write the manager's portfolio overview, using {PLACEHOLDERS} for every number.",
}


def _clean(schema: dict) -> dict:
    """Pydantic JSON schema -> strict-tool-compatible schema (no title keywords, closed objects)."""
    if isinstance(schema, dict):
        out = {}
        for k, v in schema.items():
            if k == "properties":
                out[k] = {name: _clean(sub) for name, sub in v.items()}
            elif k not in ("title", "default"):
                out[k] = _clean(v)
        if out.get("type") == "object":
            out["additionalProperties"] = False
            out["required"] = list(out.get("properties", {}))
        return out
    if isinstance(schema, list):
        return [_clean(v) for v in schema]
    return schema


def tool_for(use_case: str) -> dict:
    return {"name": TOOL_NAMES[use_case], "description": TOOL_DESCRIPTIONS[use_case],
            "input_schema": _clean(SCHEMAS[use_case].model_json_schema()), "strict": True}


def text_fields(output: dict) -> dict[str, str]:
    out = {}
    for k, v in output.items():
        if k in ENUM_FIELDS:
            continue
        if isinstance(v, list):
            for i, x in enumerate(v):
                out[f"{k}[{i}]"] = str(x)
        else:
            out[k] = str(v)
    return out

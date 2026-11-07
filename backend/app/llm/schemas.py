"""Output models per use case + the tool definition sent to the API.

Strict tool schemas can't express length limits, so LIMITS are enforced by validator.py."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Pillar = Literal["use", "waste", "timing"]


class FindingStudent(BaseModel):
    title: str
    body: str
    action: str
    cta: Literal["report", "try", "none"]


class FindingManager(BaseModel):
    title: str
    summary: str
    evidence_points: list[str]
    suggested_check: str
    priority: Literal["low", "medium", "high"]


class WeeklyDigest(BaseModel):
    headline: str
    bullets: list[str]
    encouragement: str


class ScoreExplainer(BaseModel):
    summary: str
    strongest_pillar: Pillar
    weakest_pillar: Pillar
    next_step: str


SCHEMAS: dict[str, type[BaseModel]] = {
    "finding_student": FindingStudent,
    "finding_manager": FindingManager,
    "weekly_digest": WeeklyDigest,
    "score_explainer": ScoreExplainer,
}

# field -> {"chars": n, "sentences": n, "items": (min, max)}
LIMITS = {
    "finding_student": {"title": {"chars": 60}, "body": {"sentences": 2, "chars": 320},
                        "action": {"sentences": 1, "chars": 160}},
    "finding_manager": {"title": {"chars": 80}, "summary": {"sentences": 3, "chars": 500},
                        "evidence_points": {"items": (2, 3)}, "suggested_check": {"sentences": 2, "chars": 240}},
    "weekly_digest": {"headline": {"chars": 80}, "bullets": {"items": (3, 3)},
                      "encouragement": {"sentences": 1, "chars": 160}},
    "score_explainer": {"summary": {"sentences": 2, "chars": 320}, "next_step": {"sentences": 1, "chars": 200}},
}

TOOL_NAMES = {uc: f"write_{uc}" for uc in SCHEMAS}
TOOL_DESCRIPTIONS = {
    "finding_student": "Write the student-facing card for one finding.",
    "finding_manager": "Write the manager-facing summary for one finding.",
    "weekly_digest": "Write the weekly digest for one flat.",
    "score_explainer": "Explain the flat's Resident Actions score.",
}


def _clean(schema: dict) -> dict:
    """Pydantic JSON schema -> strict-tool-compatible schema (no title keywords, closed objects).
    Property NAMES are kept even if a field is called "title"."""
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
    return {
        "name": TOOL_NAMES[use_case],
        "description": TOOL_DESCRIPTIONS[use_case],
        "input_schema": _clean(SCHEMAS[use_case].model_json_schema()),
        "strict": True,
    }


def text_fields(use_case: str, output: dict) -> dict[str, str]:
    """All free-text pieces of an output, flattened (lists -> field[i])."""
    out = {}
    for k, v in output.items():
        if isinstance(v, list):
            for i, x in enumerate(v):
                out[f"{k}[{i}]"] = str(x)
        elif k not in ("cta", "priority", "strongest_pillar", "weakest_pillar"):
            out[k] = str(v)
    return out

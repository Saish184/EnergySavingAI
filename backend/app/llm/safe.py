"""Last-resort safe responses: no quantities at all, only engine labels. Used when neither the provider nor
the template passes validation. They are validated too (all checks except completeness, since they
deliberately leave the numbers to the card the frontend already shows)."""
from __future__ import annotations

import copy

from .facts import FactSheet
from .templates import _labels


def safe_sheet(sheet: FactSheet) -> FactSheet:
    s = copy.copy(sheet)
    s.required = []
    if sheet.use_case == "weekly_digest":          # the safe overview names no finding, so no finding wording applies
        s.context = {**sheet.context, "top_finding": None}
        s.rules = {}
        return s
    s.rules = {k: v for k, v in sheet.rules.items() if not k.startswith("must_")}
    return s


def render(use_case: str, sheet: FactSheet) -> dict:
    L = _labels(sheet)
    ph = L.get("phrase") or "a pattern"
    app = L.get("appliance", "appliance")
    if use_case == "finding_student":
        return {"headline": L.get("title", "Finding"), "explanation": f"The {app} shows {ph}; the measured numbers are on this card.",
                "action": "Have a look at the card and ask your building manager if anything is unclear.", "question": "",
                "cta": sheet.rules.get("suggested_cta", "none")}
    if use_case == "finding_manager":
        return {"headline": L.get("title", "Finding"), "summary": f"{L.get('Phrase', 'A pattern')} on the {app}; see the card for the evidence and numbers.",
                "evidence_points": ["Evidence statistics are listed on the card", "Status follows the stated statistical criterion"],
                "suggested_check": "Review the card before deciding on a technician visit."}
    if use_case == "weekly_digest":
        return {"headline": "Your flat overview", "bullets": ["Your scores are shown above.", "Findings are listed below.",
                                                            "Open a finding to see what you can do."],
                "encouragement": "Every check helps the whole flat."}
    if use_case == "score_explainer":
        return {"summary": "Your Resident Actions score combines use, waste and timing; the values are shown above.",
                "strongest_pillar": sheet.rules["strongest_pillar"], "weakest_pillar": sheet.rules["weakest_pillar"],
                "next_step": "Open the findings to see what would improve the score."}
    return {"headline": "Portfolio overview", "bullets": ["Scores per flat are in the table.", "Findings are listed by potential.",
                                                         "Equipment findings are in the maintenance list."],
            "maintenance_note": "Behavioural findings are for residents, not maintenance."}

"""Student endpoints: one flat only. If the X-Flat-Id header is sent it must match the path.
This is a DEMO FILTER, not access control (no authentication; synthetic data only, see config.DEMO_NOTICE).
Text fields (student_text, explainer, digest) come from app/llm and never wait for a provider."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query, Request

from ..models import ReportRequest, ScenarioRequest
from ..llm import service as LLM
from ..utils import jsonable

router = APIRouter(prefix="/flats/{flat_id}", tags=["student"])


def _engine(request: Request, flat_id: str, x_flat_id: str | None):
    if x_flat_id and x_flat_id != flat_id:
        raise HTTPException(403, "students can only see their own flat")
    s = request.app.state.engine
    s.check_flat(flat_id)
    return s


@router.get("/scores")
def scores(flat_id: str, request: Request, x_flat_id: str | None = Header(None), texts: bool = Query(True)):
    s = _engine(request, flat_id, x_flat_id)
    out = s.scores(flat_id)
    if texts:
        out["explainer"] = LLM.score_explainer(s, flat_id)
    return jsonable(out)


@router.get("/breakdown")
def breakdown(flat_id: str, request: Request, x_flat_id: str | None = Header(None)):
    return jsonable(_engine(request, flat_id, x_flat_id).breakdown(flat_id))


@router.get("/findings")
def findings(flat_id: str, request: Request, x_flat_id: str | None = Header(None), texts: bool = Query(True)):
    """Finding cards; each gets `student_text` (validated; source llm/template/safe)."""
    return jsonable(LLM.student_findings(_engine(request, flat_id, x_flat_id), flat_id, with_text=texts))


@router.post("/findings/{finding_id}/report")
def report(flat_id: str, finding_id: str, body: ReportRequest, request: Request, x_flat_id: str | None = Header(None)):
    return jsonable(_engine(request, flat_id, x_flat_id).report(flat_id, finding_id, body.message))


@router.post("/scenarios")
def scenarios(flat_id: str, body: ScenarioRequest, request: Request, x_flat_id: str | None = Header(None)):
    return jsonable(_engine(request, flat_id, x_flat_id).scenario(flat_id, body.scenario, body.params))


@router.get("/tips")
def get_tips(flat_id: str, request: Request, x_flat_id: str | None = Header(None)):
    return jsonable(LLM.tips(_engine(request, flat_id, x_flat_id), flat_id))


@router.get("/digest")
def digest(flat_id: str, request: Request, x_flat_id: str | None = Header(None)):
    """The flat's 28-day overview (3 bullets). Weekly totals are not provided by the engine."""
    return jsonable(LLM.overview(_engine(request, flat_id, x_flat_id), flat_id))


@router.get("/notifications")
def get_notifications(flat_id: str, request: Request, x_flat_id: str | None = Header(None)):
    return jsonable(_engine(request, flat_id, x_flat_id).notifications_flat(flat_id))

"""Student endpoints: one flat only. If the X-Flat-Id header is sent it must match the path
(lightweight demo guard, not real auth)."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from ..models import ReportRequest, ScenarioRequest
from ..services import tips
from ..utils import jsonable

router = APIRouter(prefix="/flats/{flat_id}", tags=["student"])


def _engine(request: Request, flat_id: str, x_flat_id: str | None):
    if x_flat_id and x_flat_id != flat_id:
        raise HTTPException(403, "students can only see their own flat")
    s = request.app.state.engine
    s.check_flat(flat_id)
    return s


@router.get("/scores")
def scores(flat_id: str, request: Request, x_flat_id: str | None = Header(None)):
    return jsonable(_engine(request, flat_id, x_flat_id).scores(flat_id))


@router.get("/breakdown")
def breakdown(flat_id: str, request: Request, x_flat_id: str | None = Header(None)):
    return jsonable(_engine(request, flat_id, x_flat_id).breakdown(flat_id))


@router.get("/findings")
def findings(flat_id: str, request: Request, x_flat_id: str | None = Header(None)):
    return jsonable(_engine(request, flat_id, x_flat_id).flat_findings(flat_id))


@router.post("/findings/{finding_id}/report")
def report(flat_id: str, finding_id: str, body: ReportRequest, request: Request, x_flat_id: str | None = Header(None)):
    return jsonable(_engine(request, flat_id, x_flat_id).report(flat_id, finding_id, body.message))


@router.post("/scenarios")
def scenarios(flat_id: str, body: ScenarioRequest, request: Request, x_flat_id: str | None = Header(None)):
    return jsonable(_engine(request, flat_id, x_flat_id).scenario(flat_id, body.scenario, body.params))


@router.get("/tips")
def get_tips(flat_id: str, request: Request, x_flat_id: str | None = Header(None)):
    s = _engine(request, flat_id, x_flat_id)
    return jsonable(tips.tips_for_flat(s, flat_id))


@router.get("/digest")
def digest(flat_id: str, request: Request, x_flat_id: str | None = Header(None)):
    return jsonable(_engine(request, flat_id, x_flat_id).digest(flat_id))


@router.get("/notifications")
def get_notifications(flat_id: str, request: Request, x_flat_id: str | None = Header(None)):
    return jsonable(_engine(request, flat_id, x_flat_id).notifications_flat(flat_id))

"""Manager endpoints: all flats."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ..models import BusinessCaseInput, VerifyRequest, WorkOrderCreate, WorkOrderPatch
from ..llm import service as LLM
from ..services import business_case
from ..utils import jsonable

router = APIRouter(tags=["manager"])


@router.get("/portfolio")
def portfolio(request: Request):
    return jsonable(request.app.state.engine.portfolio())


@router.get("/portfolio/findings")
def portfolio_findings(request: Request, status: str | None = None, responsibility: str | None = None,
                       texts: bool = Query(True)):
    """Sorted by 28-day potential SEK if hourly spot (high first), then id. Each finding gets `triage`
    (deterministic; behaviour is never maintenance) and `manager_text`."""
    return jsonable(LLM.manager_findings(request.app.state.engine, status, responsibility, with_text=texts))


@router.get("/portfolio/summary")
def portfolio_summary(request: Request):
    """Manager overview text built from /portfolio (performance, simulated potential, evidence quality, maintenance)."""
    return jsonable(LLM.portfolio_summary(request.app.state.engine))


@router.get("/reports")
def reports(request: Request):
    return jsonable(request.app.state.engine.reports.items)


@router.get("/notifications")
def notifications(request: Request):
    return jsonable(request.app.state.engine.notifications_manager())


@router.get("/workorders")
def list_workorders(request: Request):
    return jsonable(list(request.app.state.engine.workorders.items.values()))


@router.post("/workorders")
def create_workorder(body: WorkOrderCreate, request: Request):
    """Opening a work order does NOT confirm the finding; the technician outcome does (PATCH fault_found)."""
    return jsonable(request.app.state.engine.create_workorder(body.finding_id, body.note))


@router.patch("/workorders/{wid}")
def patch_workorder(wid: str, body: WorkOrderPatch, request: Request):
    return jsonable(request.app.state.engine.patch_workorder(wid, body.status, body.fault_found))


@router.post("/workorders/{wid}/verify")
def verify_workorder(wid: str, body: VerifyRequest, request: Request):
    posts = [p.model_dump() for p in body.post_readings] if body.post_readings else None
    return jsonable(request.app.state.engine.verify_workorder(wid, posts, body.simulate))


@router.get("/business-case/reference")
def business_reference(request: Request):
    return jsonable(request.app.state.engine.business_reference())


@router.post("/business-case")
def business(body: BusinessCaseInput, request: Request):
    out = business_case.calculate(**body.model_dump())
    out["engine_reference"] = request.app.state.engine.business_reference()
    return jsonable(out)

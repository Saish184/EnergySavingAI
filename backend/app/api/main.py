"""FastAPI app.  Run from backend/:  uvicorn app.api.main:app --reload"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..state import AppState
from ..utils import jsonable
from . import llm, manager, prices, student


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = AppState()               # compute everything once at startup
    yield


app = FastAPI(title="Flat Energy Coach API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(KeyError)
async def _not_found(_: Request, exc: KeyError):
    return JSONResponse(status_code=404, content={"detail": str(exc).strip("'\"")})


@app.exception_handler(ValueError)
async def _bad_request(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/health")
def health(request: Request):
    s = request.app.state.engine
    return jsonable({"ok": True, "data_source": s.quality["data_source"], "computed_seconds": s.computed_seconds,
                     "data_quality": s.quality, "flats": len(s.ds.flat_ids), "findings": len(s.findings)})


@app.get("/flats")
def flats(request: Request):
    s = request.app.state.engine
    return jsonable(s.ds.flats.to_dict("records"))


@app.post("/recompute")
def recompute(request: Request):
    """Reload files from disk (e.g. teammate dropped new processed/ files) and recompute everything."""
    return jsonable(request.app.state.engine.recompute(reload=True))


app.include_router(student.router)
app.include_router(manager.router)
app.include_router(prices.router)
app.include_router(llm.router)

"""LLM text management."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..llm.cache import cache
from ..llm.generate import get_client
from ..llm.prompts import PROMPT_VERSION
from ..utils import jsonable

router = APIRouter(prefix="/llm", tags=["llm"])


class RegenerateRequest(BaseModel):
    flat_id: str | None = None
    finding_id: str | None = None


@router.post("/regenerate")
def regenerate(body: RegenerateRequest):
    """Clear cached LLM texts for a flat and/or finding (all if empty). Next GET regenerates them."""
    n = cache.clear(body.flat_id, body.finding_id)
    return {"cleared": n, "prompt_version": PROMPT_VERSION}


@router.post("/warm")
def warm(request: Request):
    """Generate all texts now (fills out/llm_cache.json)."""
    return jsonable(request.app.state.engine.warm_llm())


@router.get("/status")
def status():
    """Provider status. Shows whether a key is present, never the key itself."""
    from .. import config as C
    from ..llm.templates import phrases
    c = get_client()
    return {"requested_provider": C.LLM_PROVIDER, "provider": c.name, "llm_enabled": c.enabled,
            "model": c.model if c.enabled else None, "key_present": c.key_present,
            "base_url": getattr(c, "base_url", None), "calls": c.calls, "last_error": c.last_error,
            "phrases_version": phrases()["version"], "prompt_version": PROMPT_VERSION,
            "cached_texts": len(cache.entries())}

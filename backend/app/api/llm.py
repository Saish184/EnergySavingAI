"""LLM text management. Read-only status is public; generating or clearing texts is an admin operation:
X-Admin-Token must equal FEC_ADMIN_TOKEN (unset = admin operations disabled) and is rate-limited."""
from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from .. import config as C
from ..llm import service as LLM
from ..llm.cache import cache
from ..llm.prompts import PROMPT_VERSION
from ..utils import jsonable

router = APIRouter(prefix="/llm", tags=["llm"])
_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def require_admin(request: Request, token: str | None):
    expected = C.env("FEC_ADMIN_TOKEN")
    if not expected:
        raise HTTPException(403, "admin LLM operations are disabled (set FEC_ADMIN_TOKEN)")
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(403, "admin token required (X-Admin-Token)")
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    with _lock:
        q = _hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= C.ADMIN_RATE_LIMIT_PER_MIN:
            raise HTTPException(429, "rate limit: try again in a minute")
        q.append(now)


class RegenerateRequest(BaseModel):
    flat_id: str | None = None
    finding_id: str | None = None


@router.get("/status")
def status():
    """Provider, model, whether a key is present (never the key), cache size, last error."""
    return jsonable(LLM.status())


@router.post("/regenerate")
def regenerate(body: RegenerateRequest, request: Request, x_admin_token: str | None = Header(None)):
    """Clear cached texts for a flat and/or finding (all if empty). The next request regenerates them."""
    require_admin(request, x_admin_token)
    return {"cleared": cache.clear(body.flat_id, body.finding_id), "prompt_version": PROMPT_VERSION}


@router.post("/warm")
def warm(request: Request, x_admin_token: str | None = Header(None)):
    """Generate every text now (synchronous provider calls; fills out/llm_cache.json)."""
    require_admin(request, x_admin_token)
    return jsonable(LLM.warm(request.app.state.engine))

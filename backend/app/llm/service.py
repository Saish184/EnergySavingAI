"""The single integration point between Mina's AppState and the LLM layer.

Every function takes engine output that AppState already computed (findings, scores, combined potential,
portfolio) and returns validated text. Nothing here computes quantities."""
from __future__ import annotations

from . import facts as FX
from .cache import cache
from .generate import get_client, produce, produce_many, stats

MAINTENANCE_TYPES = {"fault_step_change"}          # equipment patterns (manager responsibility in the engine)


def triage(f: dict) -> dict:
    """Deterministic manager triage. Behavioural findings never enter the maintenance priority."""
    if f["responsibility"] != "manager":
        owner = "residents (confirm first)" if f["responsibility"] == "unknown" else "residents"
        return {"maintenance": False, "priority": "none", "action_owner": owner,
                "reason": "behaviour/heating finding: no technician unless residents report a device they cannot control"}
    if f["status"] in ("DISMISSED", "VERIFIED"):
        return {"maintenance": False, "priority": "none", "action_owner": "management", "reason": f"finding is {f['status']}"}
    if f["status"] == "REPAIRED":
        return {"maintenance": False, "priority": "verify", "action_owner": "management",
                "reason": "repaired: wait for >= 7 days of post-change data, then verify"}
    if f["status"] in ("PLAUSIBLE", "CONFIRMED"):
        return {"maintenance": True, "priority": "inspect", "action_owner": "management",
                "reason": "equipment pattern met its statistical criterion; a technician check decides if it is a fault"}
    return {"maintenance": True, "priority": "monitor", "action_owner": "management",
            "reason": "unusual pattern below the evidence criterion; monitor"}


def _meta(f: dict, audience: str) -> dict:
    return {"flat_id": f["flat_id"], "finding_id": f["id"], "audience": audience}


def finding_texts(findings: list[dict], audience: str, mode: str = "nonblock") -> list[dict]:
    jobs = [(f"finding_{audience}", FX.finding_sheet(f, audience), _meta(f, audience)) for f in findings]
    return produce_many(jobs, mode)


def student_findings(state, flat_id: str, mode: str = "nonblock", with_text: bool = True) -> list[dict]:
    mine = state.flat_findings(flat_id)
    if not with_text:
        return mine
    return [{**f, "student_text": t} for f, t in zip(mine, finding_texts(mine, "student", mode))]


def manager_findings(state, status=None, responsibility=None, mode: str = "nonblock", with_text: bool = True) -> list[dict]:
    fs = state.portfolio_findings(status, responsibility)
    texts = finding_texts(fs, "manager", mode) if with_text else [None] * len(fs)
    return [{**f, "triage": triage(f), **({"manager_text": t} if with_text else {})} for f, t in zip(fs, texts)]


def score_explainer(state, flat_id: str, mode: str = "nonblock") -> dict:
    return produce("score_explainer", FX.score_sheet(state.scores(flat_id)), {"flat_id": flat_id, "audience": "student"}, mode)


def overview(state, flat_id: str, mode: str = "nonblock") -> dict:
    """The flat's 28-day overview (endpoint /flats/{id}/digest)."""
    sheet = FX.overview_sheet(state.scores(flat_id), state.flat_findings(flat_id), state.combined_potential(flat_id))
    res = produce("weekly_digest", sheet, {"flat_id": flat_id, "audience": "student"}, mode)
    return {"flat_id": flat_id, "horizon": "28-day period (the engine provides no weekly totals)", **res}


def portfolio_summary(state, mode: str = "nonblock") -> dict:
    return produce("portfolio_manager", FX.portfolio_sheet(state.portfolio()), {"audience": "manager"}, mode)


def tips(state, flat_id: str, limit: int = 3, mode: str = "nonblock") -> list[dict]:
    """Backward-compatible /flats/{id}/tips: same fields as before (+ structured text and provenance)."""
    out = []
    for f in student_findings(state, flat_id, mode)[:limit]:
        t = f["student_text"]
        o = t["output"] or {}
        text = " ".join(x for x in (o.get("explanation"), o.get("action")) if x)
        out.append({"finding_id": f["id"], "flat_id": flat_id, "status": f["status"], "wording": f["wording"],
                    "responsibility": f["responsibility"], "text": text, "source": t["source"],
                    "horizon": f["avoidable_28d"]["horizon"], "assumptions": f["assumptions"],
                    "title": o.get("headline"), "question": o.get("question"), "cta": o.get("cta"),
                    "text_status": t["status"], "provider": t["provider"], "model": t["model"],
                    "prompt_version": t["prompt_version"], "claims": t["claims"], "disclaimer": t["disclaimer"]})
    return out


def warm(state) -> dict:
    """Generate every text synchronously (fills out/llm_cache.json for the offline demo)."""
    res = finding_texts(state.findings, "student", "sync") + finding_texts(state.findings, "manager", "sync")
    for fid in state.ds.flat_ids:
        res += [score_explainer(state, fid, "sync"), overview(state, fid, "sync")]
    res.append(portfolio_summary(state, "sync"))
    by = {}
    for r in res:
        by[r["source"] or "unavailable"] = by.get(r["source"] or "unavailable", 0) + 1
    return {"texts": len(res), "by_source": by}


def status() -> dict:
    from .. import config as C
    from .prompts import PROMPT_VERSION
    from .templates import phrases_version
    from .validator import VALIDATOR_VERSION
    c = get_client()
    return {"requested_provider": C.LLM_PROVIDER, "provider": c.name, "llm_enabled": c.enabled,
            "model": c.model if c.enabled else None, "key_present": c.key_present,
            "base_url": getattr(c, "base_url", None), "calls": c.calls, "last_error": c.last_error,
            "cached_texts": len(cache.entries()), "background": dict(stats),
            "prompt_version": PROMPT_VERSION, "validator_version": VALIDATOR_VERSION, "phrases_version": phrases_version(),
            "demo_notice": C.DEMO_NOTICE}

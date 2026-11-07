"""generate(use_case, payload) -> validated provider output, or our own wording if anything fails.

Flow: provider reply -> validator -> one retry with the failures -> template fallback."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .. import config as C
from . import templates
from .cache import cache
from .prompts import PROMPT_VERSION, SYSTEM_PROMPTS, user_message
from .providers import Provider, select_provider
from .schemas import tool_for
from .validator import ValidationReport, validate

_client: Provider | None = None


def get_client() -> Provider:
    global _client
    if _client is None:
        _client = select_provider()
    return _client


def set_client(client: Provider | None):
    """Tests inject a fake provider; None re-selects from FEC_LLM_PROVIDER on next use."""
    global _client
    _client = client


def _result(use_case, source, output, report, provider, model=None, attempts=None):
    return {"use_case": use_case, "source": source, "provider": provider, "model": model,
            "prompt_version": PROMPT_VERSION, "phrases_version": templates.phrases()["version"],
            "output": output, "validation": report.to_dict(), "llm_attempts": attempts or [], "cached": False}


def generate(use_case: str, payload: dict, meta: dict | None = None, use_cache: bool = True,
             client: Provider | None = None) -> dict:
    client = client or get_client()
    pname = getattr(client, "name", "custom")
    if client.enabled:
        key = cache.key(use_case, payload, PROMPT_VERSION, f"{pname}:{client.model}")
        if use_cache:
            hit = cache.get(key)
            if hit:
                return {**{k: v for k, v in hit.items() if k != "meta"}, "cached": True}

        attempts, failures = [], None
        for _ in range(1 + C.LLM_REPAIR_ATTEMPTS):
            raw, info = client.call(SYSTEM_PROMPTS[use_case], tool_for(use_case),
                                    user_message(use_case, payload, failures))
            if raw is None:
                rep = ValidationReport()
                rep.fail("schema", info.get("error") or "no reply")
            else:
                rep = validate(use_case, raw, payload)
            attempts.append({"reply": raw, "validation": rep.to_dict(), **info})
            if rep.passed:
                res = _result(use_case, "llm", raw, rep, pname, client.model, attempts)
                cache.set(key, res, meta)
                return res
            if raw is None:                       # API problem: don't hammer it, fall back now
                break
            failures = rep.messages()
    else:
        attempts = []

    out = templates.render(use_case, payload)
    res = _result(use_case, "template", out, validate(use_case, out, payload), "template", None, attempts)
    res["fallback_from"] = pname if attempts else None
    return res


def generate_many(jobs: list[tuple[str, dict, dict]], use_cache: bool = True, workers: int | None = None) -> list[dict]:
    """jobs: [(use_case, payload, meta)] -> results in the same order (parallel API calls)."""
    client = get_client()
    if not client.enabled or len(jobs) <= 1:
        return [generate(u, p, m, use_cache, client) for u, p, m in jobs]
    with ThreadPoolExecutor(max_workers=workers or C.LLM_WORKERS) as ex:
        return list(ex.map(lambda j: generate(j[0], j[1], j[2], use_cache, client), jobs))

"""produce(use_case, sheet) -> a validated text, never an unvalidated one.

Order: cached LLM text (re-validated) -> provider (one repair retry with the validator's failures) ->
our own wording (phrases.json, validated) -> safe response (validated) -> status "unavailable".

mode="sync"      : may call the provider (export, warm, evaluate).
mode="nonblock"  : never waits for a provider (dashboard GETs). A cache miss is answered with the template
                   at once and the LLM text is generated in the background for the next request."""
from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor

from .. import config as C
from . import safe, templates
from .cache import cache
from .facts import DEMO_DISCLAIMER, FactSheet
from .prompts import PROMPT_VERSION, SYSTEM_PROMPTS, user_message
from .providers import Provider, log, select_provider
from .schemas import tool_for
from .validator import VALIDATOR_VERSION, ValidationReport, quantity_facts_used, validate

_client: Provider | None = None
_bg: ThreadPoolExecutor | None = None
_pending: set[str] = set()
_lock = threading.Lock()
stats = {"background_scheduled": 0, "background_dropped": 0}


def get_client() -> Provider:
    global _client
    if _client is None:
        _client = select_provider()
    return _client


def set_client(client: Provider | None):
    """Tests inject a fake provider; None re-selects from FEC_LLM_PROVIDER on next use."""
    global _client
    _client = client


def cache_key(use_case: str, sheet: FactSheet, client: Provider) -> str:
    raw = json.dumps([use_case, sheet.to_dict(), PROMPT_VERSION, VALIDATOR_VERSION, getattr(client, "name", "custom"),
                      client.model], sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _result(use_case, sheet, status, source, raw, rendered, report, provider=None, model=None, attempts=None,
            llm_status="disabled", cached=False):
    return {"use_case": use_case, "audience": sheet.audience, "status": status, "source": source,
            "provider": provider, "model": model, "prompt_version": PROMPT_VERSION, "validator_version": VALIDATOR_VERSION,
            "phrases_version": templates.phrases_version(), "output": rendered,
            "claims": quantity_facts_used(raw, sheet) if raw and rendered else [],
            "validation": report.to_dict() if report else None, "llm_status": llm_status, "cached": cached,
            "llm_attempts": attempts or [], "disclaimer": DEMO_DISCLAIMER}


def _call_provider(use_case: str, sheet: FactSheet, client: Provider) -> tuple[dict | None, dict | None, list]:
    attempts, failures = [], None
    for _ in range(1 + C.LLM_REPAIR_ATTEMPTS):
        raw, info = client.call(SYSTEM_PROMPTS[use_case], tool_for(use_case), user_message(use_case, sheet.to_prompt(), failures))
        if raw is None:
            rep = ValidationReport()
            rep.fail("schema", info.get("error") or "no reply")
            attempts.append({"reply": None, "validation": rep.to_dict(), **info})
            break                                   # provider problem: do not hammer it
        rep, rendered = validate(use_case, raw, sheet)
        attempts.append({"reply": raw, "validation": rep.to_dict(), **info})
        if rep.passed:
            return raw, rendered, attempts
        failures = rep.messages()
    return None, None, attempts


def _background(use_case: str, sheet: FactSheet, meta: dict | None, key: str):
    try:
        produce(use_case, sheet, meta, mode="sync")
    except Exception as e:  # noqa: BLE001
        log.warning("background generation failed: %s", type(e).__name__)
    finally:
        with _lock:
            _pending.discard(key)


def _schedule(use_case: str, sheet: FactSheet, meta: dict | None, key: str) -> str:
    global _bg
    if not C.LLM_BACKGROUND:
        return "not_generated"
    with _lock:
        if key in _pending:
            return "pending"
        if len(_pending) >= C.LLM_BACKGROUND_QUEUE_MAX:
            stats["background_dropped"] += 1
            return "queue_full"
        _pending.add(key)
        if _bg is None:
            _bg = ThreadPoolExecutor(max_workers=C.LLM_BACKGROUND_WORKERS, thread_name_prefix="llm")
    stats["background_scheduled"] += 1
    _bg.submit(_background, use_case, sheet, meta, key)
    return "pending"


def produce(use_case: str, sheet: FactSheet, meta: dict | None = None, mode: str = "nonblock",
            client: Provider | None = None, use_cache: bool = True) -> dict:
    client = client or get_client()
    pname = getattr(client, "name", "custom")
    attempts: list = []
    llm_status = "disabled"
    if client.enabled:
        key = cache_key(use_case, sheet, client)
        hit = cache.get(key) if use_cache else None
        if hit:
            rep, rendered = validate(use_case, hit.get("raw"), sheet)       # never serve an invalid cached text
            if rep.passed:
                return _result(use_case, sheet, "ok", "llm", hit["raw"], rendered, rep, pname, client.model,
                               llm_status="cached", cached=True)
            cache.drop(key)
        if mode == "sync":
            raw, rendered, attempts = _call_provider(use_case, sheet, client)
            if raw is not None:
                rep, _ = validate(use_case, raw, sheet)
                cache.set(key, {"raw": raw, "use_case": use_case, "provider": pname, "model": client.model,
                                "prompt_version": PROMPT_VERSION, "validator_version": VALIDATOR_VERSION}, meta)
                return _result(use_case, sheet, "ok", "llm", raw, rendered, rep, pname, client.model, attempts, "generated")
            llm_status = "failed"
        else:
            llm_status = _schedule(use_case, sheet, meta, key)

    raw = templates.render(use_case, sheet)
    rep, rendered = validate(use_case, raw, sheet) if raw else (None, None)
    if rendered:
        res = _result(use_case, sheet, "ok", "template", raw, rendered, rep, "template", None, attempts, llm_status)
        res["fallback_from"] = pname if attempts else None
        return res
    log.warning("template for %s failed validation: %s", use_case, rep.messages() if rep else "no variant")
    raw = safe.render(use_case, sheet)
    srep, rendered = validate(use_case, raw, safe.safe_sheet(sheet))
    if rendered:
        res = _result(use_case, sheet, "safe_fallback", "safe", raw, rendered, srep, "template", None, attempts, llm_status)
        res["template_validation"] = rep.to_dict() if rep else None
        return res
    return _result(use_case, sheet, "unavailable", None, None, None, srep, None, None, attempts, llm_status)


def produce_many(jobs: list[tuple[str, FactSheet, dict]], mode: str = "nonblock", use_cache: bool = True) -> list[dict]:
    client = get_client()
    if mode != "sync" or not client.enabled or len(jobs) <= 1:
        return [produce(u, s, m, mode, client, use_cache) for u, s, m in jobs]
    with ThreadPoolExecutor(max_workers=C.LLM_WORKERS) as ex:
        return list(ex.map(lambda j: produce(j[0], j[1], j[2], mode, client, use_cache), jobs))


def wait_background(timeout: float = 120.0):
    """For export/tests: wait until scheduled background generations are done."""
    import time
    t0 = time.time()
    while time.time() - t0 < timeout:
        with _lock:
            if not _pending:
                return True
        time.sleep(0.1)
    return False

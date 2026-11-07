"""python -m app.llm.evaluate   (from backend/)

Runs every use case on every finding / flat WITHOUT the cache, validates each LLM reply,
prints a pass-rate table and writes out/llm_eval.json (failures include the reply text).
Without ANTHROPIC_API_KEY it evaluates the templates instead (all should pass)."""
from __future__ import annotations

import json
import statistics
import sys

from .. import config as C
from ..state import AppState
from ..utils import jsonable
from . import prompts as LP
from .generate import generate, get_client
from .schemas import text_fields
from .validator import CHECKS


def _jobs(s: AppState):
    for f in s.findings:
        meta = {"flat_id": f["flat_id"], "finding_id": f["id"]}
        yield "finding_student", LP.payload_finding_student(f, s.llm_ctx), meta
        yield "finding_manager", LP.payload_finding_manager(f, s.llm_ctx), meta
    for fid in s.ds.flat_ids:
        sc = s.scores(fid, with_explainer=False)
        mine = [f for f in s.findings if f["flat_id"] == fid and f["status"] != "DISMISSED"]
        yield "weekly_digest", LP.payload_digest(sc, s.week_summary(fid), mine[0] if mine else None, s.llm_ctx), {"flat_id": fid}
        yield "score_explainer", LP.payload_score(sc), {"flat_id": fid}


def main() -> int:
    client = get_client()
    mode = "llm" if client.enabled else "template (no ANTHROPIC_API_KEY)"
    print(f"evaluating: {mode}, model={client.model}, prompt={LP.PROMPT_VERSION}")
    s = AppState()
    rows: dict[str, list] = {}
    failures = []
    for uc, payload, meta in _jobs(s):
        res = generate(uc, payload, meta, use_cache=False)
        first = res["llm_attempts"][0] if res["llm_attempts"] else None
        # judge the first LLM reply (before repair); templates are judged on their own output
        rep = first["validation"] if first else res["validation"]
        reply = (first or {}).get("reply") or res["output"]
        rows.setdefault(uc, []).append({
            "meta": meta, "source": res["source"], "first_passed": rep["passed"], "checks": rep["checks"],
            "attempts": len(res["llm_attempts"]),
            "latency_s": sum(a.get("latency_s", 0) for a in res["llm_attempts"]),
            "length": len(" ".join(text_fields(uc, reply).values())) if isinstance(reply, dict) else 0,
        })
        for a in res["llm_attempts"]:
            if not a["validation"]["passed"]:
                failures.append({"use_case": uc, **meta, "reply": a.get("reply"), "error": a.get("error"),
                                 "failures": a["validation"]["failures"]})
        print(".", end="", flush=True)
    print()

    summary = {}
    head = f"{'use case':<17}{'1st pass':>10}{'final llm':>11}" + "".join(f"{c[:8]:>10}" for c in CHECKS) + \
           f"{'fallback':>10}{'avg len':>9}{'avg s':>7}"
    print(head)
    for uc, rs in rows.items():
        n = len(rs)
        p1 = sum(r["first_passed"] for r in rs)
        llm = sum(r["source"] == "llm" for r in rs)
        fb = n - llm if client.enabled else 0
        checks = {c: 100 * sum(r["checks"].get(c, True) for r in rs) / n for c in CHECKS}
        lat = statistics.mean(r["latency_s"] for r in rs)
        ln = statistics.mean(r["length"] for r in rs)
        summary[uc] = {"n": n, "first_pass": p1, "final_llm": llm, "fallback": fb, "check_pass_pct": checks,
                       "avg_length_chars": ln, "avg_latency_s": lat}
        print(f"{uc:<17}{f'{p1}/{n}':>10}{f'{llm}/{n}':>11}" + "".join(f"{checks[c]:>9.0f}%" for c in CHECKS)
              + f"{fb:>10}{ln:>9.0f}{lat:>7.1f}")

    C.OUT_DIR.mkdir(exist_ok=True)
    out = C.OUT_DIR / "llm_eval.json"
    out.write_text(json.dumps(jsonable({"mode": mode, "model": client.model, "prompt_version": LP.PROMPT_VERSION,
                                        "summary": summary, "rows": rows, "failures": failures}),
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(failures)} rejected replies saved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

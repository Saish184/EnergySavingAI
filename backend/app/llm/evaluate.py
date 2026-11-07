"""python -m app.llm.evaluate   (from backend/)

Runs every use case on every real finding / flat / the portfolio WITHOUT the cache, validates each provider
reply, prints a pass-rate table and writes out/llm_eval.json (rejected replies are saved with their text).
Without a configured provider it evaluates our own wording (templates) the same way."""
from __future__ import annotations

import json
import statistics
import sys

from .. import config as C
from ..state import AppState
from ..utils import jsonable
from . import facts as FX
from .generate import get_client, produce
from .prompts import PROMPT_VERSION
from .validator import CHECKS


def jobs(s: AppState):
    for f in s.findings:
        meta = {"flat_id": f["flat_id"], "finding_id": f["id"]}
        yield "finding_student", FX.finding_sheet(f, "student"), meta
        yield "finding_manager", FX.finding_sheet(f, "manager"), meta
    for fid in s.ds.flat_ids:
        sc = s.scores(fid)
        yield "score_explainer", FX.score_sheet(sc), {"flat_id": fid}
        yield "weekly_digest", FX.overview_sheet(sc, s.flat_findings(fid), s.combined_potential(fid)), {"flat_id": fid}
    yield "portfolio_manager", FX.portfolio_sheet(s.portfolio()), {}


def main() -> int:
    C.LLM_BACKGROUND = False
    client = get_client()
    mode = f"{client.name}:{client.model}" if client.enabled else "template (no provider configured)"
    print(f"evaluating: {mode}, prompt={PROMPT_VERSION}")
    s = AppState()
    rows: dict[str, list] = {}
    failures = []
    for uc, sheet, meta in jobs(s):
        res = produce(uc, sheet, meta, mode="sync", use_cache=False)
        first = res["llm_attempts"][0] if res["llm_attempts"] else None
        rep = first["validation"] if first else res["validation"]
        rows.setdefault(uc, []).append({
            "meta": meta, "source": res["source"], "status": res["status"], "first_passed": bool(rep and rep["passed"]),
            "checks": (rep or {}).get("checks", {}), "attempts": len(res["llm_attempts"]),
            "latency_s": sum(a.get("latency_s", 0) for a in res["llm_attempts"]),
            "length": sum(len(v) if isinstance(v, str) else sum(len(x) for x in v) for k, v in (res["output"] or {}).items()
                          if k not in ("cta", "strongest_pillar", "weakest_pillar")),
        })
        for a in res["llm_attempts"]:
            if not a["validation"]["passed"]:
                failures.append({"use_case": uc, **meta, "reply": a.get("reply"), "error": a.get("error"),
                                 "failures": a["validation"]["failures"]})
        print(".", end="", flush=True)
    print()
    summary = {}
    print(f"{'use case':<18}{'n':>3}{'1st pass':>10}{'llm':>6}{'templ':>7}{'safe':>6}{'n/a':>5}{'avg s':>7}  failing checks (1st reply)")
    for uc, rs in rows.items():
        n = len(rs)
        by = {k: sum(r["source"] == k for r in rs) for k in ("llm", "template", "safe")}
        na = sum(r["status"] == "unavailable" for r in rs)
        p1 = sum(r["first_passed"] for r in rs)
        checks = {c: round(100 * sum(r["checks"].get(c, True) for r in rs) / n) for c in CHECKS}
        lat = statistics.mean(r["latency_s"] for r in rs)
        summary[uc] = {"n": n, "first_pass": p1, **by, "unavailable": na, "check_pass_pct": checks,
                       "avg_latency_s": lat, "avg_length_chars": statistics.mean(r["length"] for r in rs)}
        bad = ", ".join(f"{c} {v}%" for c, v in checks.items() if v < 100) or "-"
        print(f"{uc:<18}{n:>3}{f'{p1}/{n}':>10}{by['llm']:>6}{by['template']:>7}{by['safe']:>6}{na:>5}{lat:>7.1f}  {bad}")
    C.OUT_DIR.mkdir(exist_ok=True)
    out = C.OUT_DIR / "llm_eval.json"
    out.write_text(json.dumps(jsonable({"mode": mode, "prompt_version": PROMPT_VERSION, "summary": summary, "rows": rows,
                                        "failures": failures}), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(failures)} rejected replies saved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Static JSON fallback for the frontend.   python -m app.export   (from backend/)

With ANTHROPIC_API_KEY set, LLM texts are generated (or taken from out/llm_cache.json);
without it, template texts are written. Either way the demo never needs a live API call."""
from __future__ import annotations

import json

from . import config as C
from .services import tips
from .state import AppState
from .utils import jsonable


def main():
    s = AppState()
    C.OUT_DIR.mkdir(exist_ok=True)
    print("LLM texts:", s.warm_llm())
    flats = s.ds.flat_ids
    student = {f["id"]: f["student_text"] for fid in flats for f in s.flat_findings(fid)}
    manager = {f["id"]: f["manager_text"] for f in s.portfolio_findings()}
    findings = [{**f, "student_text": student[f["id"]], "manager_text": manager[f["id"]]} for f in s.findings]
    files = {
        "scores.json": {f: s.scores(f) for f in flats},
        "breakdown.json": {f: s.breakdown(f) for f in flats},
        "findings.json": findings,
        "portfolio.json": s.portfolio(),
        "tips.json": {f: {"tips": tips.tips_for_flat(s, f), "digest": s.digest(f),
                          "score_explainer": s.explainer(f)} for f in flats},
    }
    for name, data in files.items():
        (C.OUT_DIR / name).write_text(json.dumps(jsonable(data), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {C.OUT_DIR / name}")
    print(f"data source: {s.quality['data_source']}")


if __name__ == "__main__":
    main()

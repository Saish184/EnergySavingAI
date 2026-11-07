"""Static JSON fallback for the frontend.   python -m app.export   (from backend/)

With FEC_LLM_PROVIDER=gonka|anthropic and a key, every text is generated synchronously (validated, cached in
out/llm_cache.json, which is committed for the offline demo); otherwise our own wording is written."""
from __future__ import annotations

import json

from . import config as C
from .llm import service as LLM
from .state import AppState
from .utils import jsonable


def main():
    s = AppState()
    C.OUT_DIR.mkdir(exist_ok=True)
    print("texts:", LLM.warm(s))                 # sync: provider calls happen here, not in the API
    C.LLM_BACKGROUND = False                     # below: cached texts or our wording, no further provider calls
    flats = s.ds.flat_ids
    student = {x["id"]: x["student_text"] for fid in flats for x in LLM.student_findings(s, fid)}
    mgr = {x["id"]: x for x in LLM.manager_findings(s)}
    files = {
        "scores.json": {f: {**s.scores(f), "explainer": LLM.score_explainer(s, f)} for f in flats},
        "breakdown.json": {f: s.breakdown(f) for f in flats},
        "findings.json": [{**f, "student_text": student[f["id"]], "manager_text": mgr[f["id"]]["manager_text"],
                           "triage": mgr[f["id"]]["triage"]} for f in s.findings],
        "portfolio.json": {**s.portfolio(), "summary": LLM.portfolio_summary(s)},
        "tips.json": {f: {"tips": LLM.tips(s, f), "digest": LLM.overview(s, f)} for f in flats},
    }
    for name, data in files.items():
        (C.OUT_DIR / name).write_text(json.dumps(jsonable(data), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {C.OUT_DIR / name}")
    print(f"data source: {s.quality['data_source']}")


if __name__ == "__main__":
    main()

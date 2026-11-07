"""Static JSON fallback for the frontend.   python -m app.export   (from backend/)"""
from __future__ import annotations

import json

from . import config as C
from .services import tips
from .state import AppState
from .utils import jsonable


def main():
    s = AppState()
    C.OUT_DIR.mkdir(exist_ok=True)
    files = {
        "scores.json": {f: s.scores(f) for f in s.ds.flat_ids},
        "breakdown.json": {f: s.breakdown(f) for f in s.ds.flat_ids},
        "findings.json": s.findings,
        "portfolio.json": s.portfolio(),
        "tips.json": {f: tips.tips_for_flat(s.findings, f) for f in s.ds.flat_ids},
    }
    for name, data in files.items():
        (C.OUT_DIR / name).write_text(json.dumps(jsonable(data), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {C.OUT_DIR / name}")
    print(f"data source: {s.quality['data_source']}")


if __name__ == "__main__":
    main()

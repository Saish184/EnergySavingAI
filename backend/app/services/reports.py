"""Student 'report to manager' inbox (in-memory)."""
from __future__ import annotations

import itertools

import pandas as pd


class Reports:
    def __init__(self):
        self.items: list[dict] = []
        self._ids = itertools.count(1)

    def add(self, flat_id: str, finding_id: str, message: str | None) -> dict:
        r = {"id": f"RP{next(self._ids):03d}", "flat_id": flat_id, "finding_id": finding_id,
             "message": message, "created": pd.Timestamp.now(tz="UTC"), "status": "new"}
        self.items.append(r)
        return r

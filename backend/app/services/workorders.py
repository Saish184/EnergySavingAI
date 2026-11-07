"""In-memory work orders: open -> sent -> repaired. Verification is a separate step."""
from __future__ import annotations

import itertools

import pandas as pd

FLOW = {"open": {"sent", "closed_no_fault"}, "sent": {"repaired", "closed_no_fault"},
        "repaired": set(), "closed_no_fault": set()}


class WorkOrders:
    def __init__(self):
        self.items: dict[str, dict] = {}
        self._ids = itertools.count(1)

    def create(self, finding: dict, note: str | None = None) -> dict:
        for w in self.items.values():
            if w["finding_id"] == finding["id"]:
                raise ValueError(f"work order {w['id']} already exists for {finding['id']}")
        wid = f"WO{next(self._ids):03d}"
        now = pd.Timestamp.now(tz="UTC")
        w = {"id": wid, "finding_id": finding["id"], "flat_id": finding["flat_id"],
             "appliance_id": finding["appliance_id"], "status": "open", "note": note, "fault_found": None,
             "created": now, "history": [{"status": "open", "at": now}], "verification": None}
        self.items[wid] = w
        return w

    def get(self, wid: str) -> dict:
        if wid not in self.items:
            raise KeyError(wid)
        return self.items[wid]

    def advance(self, wid: str, status: str) -> dict:
        w = self.get(wid)
        if status not in FLOW[w["status"]]:
            raise ValueError(f"cannot go from {w['status']} to {status}")
        w["status"] = status
        w["history"].append({"status": status, "at": pd.Timestamp.now(tz="UTC")})
        return w

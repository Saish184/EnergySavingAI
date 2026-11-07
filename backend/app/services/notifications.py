"""In-app notification list, derived on the fly from findings, reports and work orders."""
from __future__ import annotations


def for_flat(flat_id: str, findings: list[dict], workorders: list[dict]) -> list[dict]:
    out = []
    for f in findings:
        if f["flat_id"] == flat_id:
            out.append({"kind": "finding", "finding_id": f["id"], "status": f["status"],
                        "text": f"{f['title']} ({f['wording']})", "responsibility": f["responsibility"]})
    for w in workorders:
        if w["flat_id"] == flat_id:
            out.append({"kind": "workorder", "workorder_id": w["id"], "finding_id": w["finding_id"],
                        "status": w["status"], "text": f"Work order {w['id']} is {w['status']}"})
    return out


def for_manager(reports: list[dict], workorders: list[dict]) -> list[dict]:
    out = [{"kind": "report", "report_id": r["id"], "flat_id": r["flat_id"], "finding_id": r["finding_id"],
            "text": f"Resident report from {r['flat_id']} on {r['finding_id']}"} for r in reports if r["status"] == "new"]
    out += [{"kind": "workorder", "workorder_id": w["id"], "status": w["status"],
             "text": f"{w['id']} ({w['flat_id']}) is {w['status']}"} for w in workorders if w["status"] != "repaired"
            or not w.get("verification")]
    return out

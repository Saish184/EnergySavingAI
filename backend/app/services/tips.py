"""Tip text. The LLM only rewords engine numbers; it never computes them.
Falls back to template text if there is no API key, the call fails, or the text contains a
number that isn't in the input."""
from __future__ import annotations

import json
import os
import re

from .. import config as C

SYSTEM = """You write short energy tips for students in a shared Swedish flat.
Rules:
- Use ONLY numbers that appear in the JSON. Never compute, round differently or invent numbers.
- Keep the status wording exactly as given in "wording" (e.g. "unusual pattern", "possible fault").
- Any annual figure must be called "projected".
- The appliance type is an assumption: say "-like" (e.g. "fridge-like") as given.
- If responsibility is "manager", tell the student to report it, not to fix it.
- At most 2 sentences, then one line starting "Action:". Plain text, no markdown."""

_cache: dict[str, dict] = {}


def _fmt(x, nd=0):
    return "?" if x is None else f"{x:,.{nd}f}"


def _proj_text(proj: dict) -> str:
    if proj.get("value") is None:
        return "not extrapolated to a year"
    return f"projected {_fmt(proj['low'], 0)}-{_fmt(proj['high'], 0)} SEK/year if it persists, spot price only"


def template(f: dict) -> str:
    proj = f["projection_annual"]["sek"]
    m = f["avoidable_28d"]
    days = m.get("window_days", 28)
    action = {
        "manager": "Action: report it to your building manager.",
        "resident": "Action: check the device and switch it off when nobody is home or run it later.",
        "unknown": "Action: check whether a portable heater is being used and ask your manager about radiators.",
    }[f["responsibility"]]
    if m.get("scenario") == "shift_flexible_load":
        return (f"{f['title']} on the {f['assumed_type']} channel ({f['wording']}). "
                f"Starting it after the peak hours would have saved about {_fmt(m['sek'], 1)} SEK and {_fmt(m['co2_kg'], 2)} kgCO2e "
                f"in {_fmt(days, 0)} days with the same kWh, if you pay hourly spot prices. "
                f"Action: start it after the evening peak (e.g. 21:00).")
    return (f"{f['title']} on the {f['assumed_type']} channel ({f['wording']}). "
            f"Over {_fmt(days, 0)} observed days this was about {_fmt(m['kwh'], 1)} kWh and {_fmt(m['sek'], 1)} SEK at spot prices "
            f"({_proj_text(proj)}). {action}")


def _llm_payload(f: dict) -> dict:
    return {k: f[k] for k in ("title", "assumed_type", "status", "wording", "responsibility",
                              "responsibility_note")} | {
        "measured_window": {k: round(f["avoidable_28d"][k], 2) for k in ("kwh", "sek", "co2_kg")} | {"days": f["avoidable_28d"]["window_days"]},
        "projected_annual_sek_range": (None if f["projection_annual"]["sek"]["value"] is None else
                                       [round(f["projection_annual"]["sek"]["low"]), round(f["projection_annual"]["sek"]["high"])]),
        "projection_note": "projected, spot price only, excludes network fee, energy tax, VAT",
    }


def _numbers_ok(text: str, payload: dict) -> bool:
    """Every number in the LLM text must appear in the payload."""
    allowed = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(payload).replace(",", "")))
    allowed |= {"1", "2", "28"}
    used = re.findall(r"\d+(?:\.\d+)?", text.replace(",", "").replace(" ", ""))
    return all(u in allowed for u in used)


def _llm(payload: dict) -> str | None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(timeout=20.0, max_retries=1)
        # no automatic model fallback after refusals (team decision); refusals and outages -> template text
        resp = client.messages.create(
            model=C.LLM_MODEL,
            max_tokens=1024,
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload)}],
            output_config={"effort": "low"},
        )
        if resp.stop_reason == "refusal":
            return None
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return text or None
    except Exception:  # network, auth, rate limit -> template
        return None


def tip_for(f: dict) -> dict:
    key = f"{f['id']}:{f['status']}"
    if key in _cache:
        return _cache[key]
    payload = _llm_payload(f)
    text = _llm(payload)
    source = "llm"
    if not text or not _numbers_ok(text, payload):
        text, source = template(f), "template"
    tip = {"finding_id": f["id"], "flat_id": f["flat_id"], "status": f["status"], "wording": f["wording"],
           "responsibility": f["responsibility"], "text": text, "source": source,
           "horizon": "28d measured + annual projection", "assumptions": f["assumptions"]}
    _cache[key] = tip
    return tip


def tips_for_flat(findings: list[dict], flat_id: str, limit: int = 3) -> list[dict]:
    mine = [f for f in findings if f["flat_id"] == flat_id]
    return [tip_for(f) for f in mine[:limit]]

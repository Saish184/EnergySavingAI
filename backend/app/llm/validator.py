"""Checks every LLM reply against the engine payload. Any failed check -> template fallback."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from . import schemas
from .prompts import REQUIRED_PHRASE

CHECKS = ("schema", "numbers", "wording", "projected", "shift", "blame", "appliance", "length", "logic")

SMALL_COUNTS = {1, 2, 3, 4, 5, 7, 12, 24, 28, 100}   # "4 weeks", "28 days", "out of 100", "3 things"
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
FORBIDDEN_UNCERTAIN = ["broken", "faulty", "definitely", "certainly", "confirmed"]
SHIFT_ENERGY_CLAIMS = ["less energy", "fewer kwh", "less kwh", "reduce energy", "reduces energy",
                       "save energy", "saves energy", "saving energy", "lower energy use", "use less electricity",
                       "uses less electricity", "less electricity", "reduce consumption", "reduces consumption"]
BLAME = ["you caused", "your fault", "you wasted", "you left", "because of you", "you broke", "you forgot"]
ANNUAL = re.compile(r"\b(year|yearly|annual|annually|per year|a year)\b|/\s?year|/yr", re.I)
TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")      # colon only: "12.31 SEK" is not a time
DATE_RES = [
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:T[\d:]+Z?)?"),                               # ISO
    re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", re.I),
    re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I),
]
NUM_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")


@dataclass
class ValidationReport:
    passed: bool = True
    failures: list[dict] = field(default_factory=list)
    checks: dict = field(default_factory=lambda: {c: True for c in CHECKS})

    def fail(self, check: str, detail: str):
        self.passed = False
        self.checks[check] = False
        self.failures.append({"check": check, "detail": detail})

    def to_dict(self):
        return asdict(self)

    def messages(self) -> list[str]:
        return [f"{f['check']}: {f['detail']}" for f in self.failures]


# ---------------- helpers ----------------

def _strings(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)
    elif isinstance(o, str):
        yield o


def _numbers(o):
    if isinstance(o, bool):
        return
    if isinstance(o, (int, float)):
        yield float(o)
    elif isinstance(o, dict):
        for v in o.values():
            yield from _numbers(v)
    elif isinstance(o, list):
        for v in o:
            yield from _numbers(v)


def _dates(text: str) -> set[tuple[int, int]]:
    out = set()
    for m in DATE_RES[0].finditer(text):
        out.add((int(m.group(2)), int(m.group(3))))
    for m in DATE_RES[1].finditer(text):
        out.add((MONTHS[m.group(2)[:3].lower()], int(m.group(1))))
    for m in DATE_RES[2].finditer(text):
        out.add((MONTHS[m.group(1)[:3].lower()], int(m.group(2))))
    return out


def allowed_numbers(payload: dict) -> set[float]:
    vals = set(_numbers(payload))
    for s in _strings(payload):                                   # numbers inside evidence text etc.
        vals |= {float(x) for x in NUM_RE.findall(s.replace(",", ""))}
    out = set()
    for v in vals:
        for x in (v, abs(v)) + ((abs(v) * 100,) if abs(v) <= 1 else ()):  # 0.92 -> 92 %
            out.add(x)
            for nd in (0, 1, 2):
                out.add(round(x, nd))
    return out


def _strip(text: str, payload_text: str, report: ValidationReport) -> str:
    """Remove dates/times that are in the input; flag ones that are not."""
    p_dates = _dates(payload_text)
    p_times = {(int(h), int(m)) for h, m in TIME_RE.findall(payload_text)}
    for rx in DATE_RES:
        for m in list(rx.finditer(text)):
            if not (_dates(m.group(0)) <= p_dates):
                report.fail("numbers", f"date '{m.group(0)}' not in input")
        text = rx.sub(" ", text)
    for m in list(TIME_RE.finditer(text)):
        if (int(m.group(1)), int(m.group(2))) not in p_times:
            report.fail("numbers", f"time '{m.group(0)}' not in input")
    return TIME_RE.sub(" ", text)


def _sentences(s: str) -> int:
    parts = [p for p in re.split(r"(?<=[.!?])\s+", s.strip()) if p.strip()]
    return len(parts)


def expected_priority(payload: dict) -> str:
    st = payload.get("status")
    if st in ("DETECTED", "DISMISSED"):
        return "low"
    if payload.get("is_largest_28d_sek_impact_in_portfolio"):
        return "high"
    return "medium"


# ---------------- main ----------------

def validate(use_case: str, output: dict | None, payload: dict) -> ValidationReport:
    r = ValidationReport()
    model = schemas.SCHEMAS[use_case]
    try:
        output = model(**(output or {})).model_dump()
    except Exception as e:  # noqa: BLE001
        r.fail("schema", f"does not match schema: {e}")
        return r

    fields = schemas.text_fields(use_case, output)
    text = " ".join(fields.values())
    low = text.lower()
    payload_text = json.dumps(payload, ensure_ascii=False)

    # 1. numbers
    allowed = allowed_numbers(payload)
    rest = _strip(text, payload_text, r)
    rest = re.sub(r"(?<=\d),(?=\d{3}\b)", "", rest)               # 1,234 -> 1234
    rest = re.sub(r"(?<=\d),(?=\d)", ".", rest)                   # 22,9 -> 22.9
    rest = re.sub(r"\b[A-Z]\d{2,3}(?:-[A-Z]\d{2})?\b", " ", rest)  # ids like F003, F003-A01, A07
    for n in NUM_RE.findall(rest):
        v = float(n)
        if v in allowed or (v.is_integer() and int(v) in SMALL_COUNTS):
            continue
        r.fail("numbers", f"number {n} is not in the engine input")

    # 2. wording
    status = payload.get("status")
    if status:
        need = REQUIRED_PHRASE[status]
        if need not in low:
            r.fail("wording", f"status {status} needs the phrase '{need}'")
        if status in ("DETECTED", "PLAUSIBLE"):
            for w in FORBIDDEN_UNCERTAIN:
                if re.search(rf"\b{w}\b", low):
                    r.fail("wording", f"'{w}' overstates a {status} finding")

    # 3. projected
    if ANNUAL.search(text) and "projected" not in low:
        r.fail("projected", "a yearly value is mentioned without 'projected'")

    # 4. shift saves money, not energy
    if "load shift" in payload_text or "shift_flexible_load" in payload_text:
        for w in SHIFT_ENERGY_CLAIMS:
            if w in low:
                r.fail("shift", f"load shift does not reduce energy ('{w}')")

    # 5. blame
    resp = payload.get("responsibility") or (payload.get("top_finding") or {}).get("responsibility")
    if resp in ("manager", "unknown"):
        for w in BLAME:
            if w in low:
                r.fail("blame", f"'{w}' blames residents for a {resp} finding")

    # 6. appliance types are assumptions
    for t in re.findall(r'"([a-z]+)-like', payload_text):
        if re.search(rf"\b(your|the)\s+{t}s?\b(?!-like)", low):
            r.fail("appliance", f"says '{t}' as fact; use '{t}-like appliance'")

    # 7. length limits
    for fname, lim in schemas.LIMITS[use_case].items():
        val = output[fname]
        if "items" in lim:
            lo, hi = lim["items"]
            if not lo <= len(val) <= hi:
                r.fail("length", f"{fname} must have {lo}-{hi} items, has {len(val)}")
            continue
        if "chars" in lim and len(val) > lim["chars"]:
            r.fail("length", f"{fname} is {len(val)} chars (max {lim['chars']})")
        if "sentences" in lim and _sentences(val) > lim["sentences"]:
            r.fail("length", f"{fname} has {_sentences(val)} sentences (max {lim['sentences']})")

    # 8. use-case logic that must match the engine
    if use_case == "finding_manager" and output["priority"] != expected_priority(payload):
        r.fail("logic", f"priority must be '{expected_priority(payload)}' by the rule")
    if use_case == "score_explainer":
        if output["strongest_pillar"] != payload["strongest_pillar"] or output["weakest_pillar"] != payload["weakest_pillar"]:
            r.fail("logic", "strongest/weakest pillar must match the engine")
        if "health" in low:
            r.fail("logic", "the Health pillar is not part of the resident score")
    if use_case == "finding_student" and output["cta"] != payload.get("suggested_cta", output["cta"]):
        if not (payload.get("responsibility") == "resident" and output["cta"] == "none"):
            r.fail("logic", f"cta should be '{payload.get('suggested_cta')}'")
    return r

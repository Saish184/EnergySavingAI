"""Checks every reply (LLM or template) against its FactSheet before anything is shown.

A reply is a dict of text fields containing {PLACEHOLDER}s. It is rejected if any check fails; nothing that
fails is ever served. Checks work on the raw reply (structure: which fact, which period, which category,
which wording) and on the rendered text (length).

The old v1 check ("every number in the text appears somewhere in the input, small numbers always OK")
accepted correct numbers with wrong units/periods and invented small numbers. v2 removes the allow-list:
replies may contain NO digits or number words at all; numbers enter only through facts, whose display
strings carry unit, period and tariff condition."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from . import schemas
from .facts import QUANTITY_CATEGORIES, FactSheet

VALIDATOR_VERSION = "v2"

CHECKS = ("schema", "placeholders", "raw_numbers", "units", "periods", "projection", "categories", "tariff",
          "wording", "overclaim", "fault_language", "blame", "appliance", "all_avoidable", "shift", "safety",
          "confidence", "synthetic", "required", "length", "logic")

PH = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")
NUMBER_WORDS = re.compile(r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
                          r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|hundred|hundreds|thousand|"
                          r"thousands|dozen|half|twice|double|triple|quarter|percent)\b", re.I)
UNIT_NEAR = re.compile(r"\}\s*(kwh|sek|kr|kronor|kg|co2|%|percent|days?|hours?|watts?|w)\b|"
                       r"\b(kwh|sek|kr|kronor|kg)\s*\{", re.I)
ANNUAL = re.compile(r"\b(year|years|yearly|annual|annually)\b", re.I)
OTHER_PERIOD = re.compile(r"\b(per|a|each|this|last|next) (day|week|month)\b|\b(daily|weekly|monthly|today|tonight|yesterday)\b", re.I)
CONDITIONAL = re.compile(r"\b(could|would|potential|potentially|if|up to|estimate|estimated|simulated|scenario|might|between)\b", re.I)
SAVE = re.compile(r"\bsav(e|es|ed|ing|ings)\b", re.I)
BILL = re.compile(r"\bbills?\b", re.I)
BILL_OK = re.compile(r"not (a|your|the)( electricity)? bill( saving)?|not on (your|the)( electricity)? bill", re.I)
OVERCLAIM = re.compile(r"\b(guarantee|guaranteed|guarantees|definitely|certainly|proves?|proof|for sure|without (a )?doubt|"
                       r"will save|you'll save|you will save|always saves?)\b", re.I)
VERIFIED_WORDS = re.compile(r"(?<!not )\b(verified|measured saving|saving measured)\b", re.I)
FAULT_ANY = re.compile(r"\b(fault|faults|faulty|broken|malfunction\w*|defect\w*|failure|failing|failed)\b", re.I)
FAULT_HARD = re.compile(r"\b(broken|faulty|defective|failed|failing|failure)\b", re.I)
BLAME = re.compile(r"you caused|your fault|you wasted|you left it|because of you|you broke|you forgot|blame", re.I)
ALL_AVOIDABLE = re.compile(r"\ball of (it|this|that|the (excess|extra|use))\b|\bentire (excess|amount)\b|"
                           r"\b(fully|completely|totally|entirely) avoidable\b|\ball avoidable\b|\bevery (kwh|bit) (is|of)\b", re.I)
SHIFT_ENERGY = re.compile(r"less energy|fewer kwh|less kwh|sav(e|es|ing) energy|reduc(e|es|ing) (energy|consumption|electricity use)|"
                          r"use less (energy|electricity)|uses less (energy|electricity)|lower (energy|electricity) use|"
                          r"cut (energy|consumption)|less electricity", re.I)
UNSAFE = [
    re.compile(r"\b(turn|switch|shut)(ing)? (off|out) (the |your |all )?(heat|heating|heaters?|radiators?)\b(?![^.]*\b(nobody|no one|away|leave|out)\b)", re.I),
    re.compile(r"\b(keep|leave) (the |your )?(heat|heating|heaters?|radiators?) off\b", re.I),
    re.compile(r"\bno heating\b|\bwithout heating\b", re.I),
    re.compile(r"\b(cover|block|tape)\w* (the |your )?(heater|radiator|vent)", re.I),
    re.compile(r"\bunplug\w*\b", re.I),
    re.compile(r"\b(open|repair|fix|dismantle|remove)\w* (it|the \w+(-like)? appliance|the back|the panel|the cover)\b[^.]*\byourself\b", re.I),
    re.compile(r"\byourself\b[^.]*\b(repair|fix|open|dismantle)\b", re.I),
    re.compile(r"\bunattended\b|\bwhile (you are |you're |everyone is )?(asleep|sleeping)\b|\bmiddle of the night\b|\bovernight\b", re.I),
    re.compile(r"\bwhile (you are |you're |everyone is )?(away|out)\b[^.]*\b(run|start)\b|\b(run|start)\b[^.]*\bwhile (you are |you're |everyone is )?(away|out)\b", re.I),
]
CONFIDENCE = re.compile(r"%|\bpercent|probabilit|\bchance\b|likelihood|\b\w+ sure\b|\bconfiden", re.I)
SYNTHETIC = re.compile(r"studies show|research shows|real students|most students|typical student|students in sweden|"
                       r"on average,? students|people like you|everyone in sweden|swedish students", re.I)
APPLIANCE_NOUNS = ["fridge", "freezer", "dishwasher", "heater", "washing machine", "washer", "lights", "lighting",
                   "electronics", "cooker", "stove", "oven", "standby"]
HEALTH = re.compile(r"\bhealth\b", re.I)
UNNECESSARY = re.compile(r"\bunnecessary\b", re.I)
HEDGE = re.compile(r"\b(potential|potentially|may|might|could|possibly|perhaps)\b", re.I)


@dataclass
class ValidationReport:
    passed: bool = True
    failures: list[dict] = field(default_factory=list)
    checks: dict = field(default_factory=lambda: {c: True for c in CHECKS})
    version: str = VALIDATOR_VERSION

    def fail(self, check: str, detail: str):
        self.passed = False
        self.checks[check] = False
        self.failures.append({"check": check, "detail": detail})

    def to_dict(self):
        return asdict(self)

    def messages(self) -> list[str]:
        return [f"{f['check']}: {f['detail']}" for f in self.failures]


def _sentences(s: str) -> list[str]:
    return [p for p in re.split(r"(?<=[.!?])\s+", s.strip()) if p.strip()]


def required_phrase(status: str | None, responsibility: str | None, wording: str | None) -> str | None:
    if not status:
        return None
    if status == "DETECTED":
        return "unusual pattern"
    if status == "PLAUSIBLE":
        if responsibility == "manager":
            return "possible fault"
        if responsibility == "unknown":
            return "heating opportunity"
        return "consistent pattern"
    return {"CONFIRMED": "confirmed", "REPAIRED": "repaired", "VERIFIED": "saving measured",
            "DISMISSED": "no fault found"}.get(status, wording)


def render(output: dict, sheet: FactSheet) -> dict:
    def sub(text):
        return PH.sub(lambda m: sheet.facts[m.group(1)].display if m.group(1) in sheet.facts else m.group(0), text)
    out = {}
    for k, v in output.items():
        if k in schemas.ENUM_FIELDS:
            out[k] = v
        elif isinstance(v, list):
            out[k] = [sub(str(x)) for x in v]
        else:
            out[k] = sub(str(v))
    return out


def validate(use_case: str, output: dict | None, sheet: FactSheet) -> tuple[ValidationReport, dict | None]:
    r = ValidationReport()
    try:
        output = schemas.SCHEMAS[use_case](**(output or {})).model_dump()
    except Exception as e:  # noqa: BLE001
        r.fail("schema", f"does not match schema: {str(e)[:200]}")
        return r, None

    fields = schemas.text_fields(output)
    rules, ctx = sheet.rules, sheet.context
    status = rules.get("status") or ctx.get("status")
    resp = rules.get("responsibility") or ctx.get("responsibility")
    facts = sheet.facts
    used_all: set[str] = set()

    for name, text in fields.items():
        used = PH.findall(text)
        used_all |= set(used)
        for u in used:
            if u not in facts:
                r.fail("placeholders", f"{name}: unknown placeholder {{{u}}}")
        if text.count("{") != text.count("}") or re.search(r"\{(?![A-Z][A-Z0-9_]*\})", text):
            r.fail("placeholders", f"{name}: malformed placeholder")
        bare = PH.sub(" ", text)
        bare_nounits = re.sub(r"CO2e?|CO₂e?", " ", bare)
        if re.search(r"\d", bare_nounits):
            r.fail("raw_numbers", f"{name}: contains a digit outside a placeholder")
        if NUMBER_WORDS.search(bare):
            r.fail("raw_numbers", f"{name}: number word '{NUMBER_WORDS.search(bare).group(0)}'")
        if UNIT_NEAR.search(text):
            r.fail("units", f"{name}: unit written next to a placeholder ('{UNIT_NEAR.search(text).group(0)}')")
        # periods: each quantity needs its period placeholder in the same field
        for u in used:
            f = facts.get(u)
            if f and f.period and f.period not in used:
                r.fail("periods", f"{name}: {{{u}}} needs its period {{{f.period}}} in the same text")
        if OTHER_PERIOD.search(bare) and not (re.search(r"\bevery week\b", bare, re.I) and "WEEKS" in facts):
            r.fail("periods", f"{name}: unsupported period '{OTHER_PERIOD.search(bare).group(0)}'")
        has_proj = any(facts[u].category == "projection" for u in used if u in facts)
        if ANNUAL.search(bare) and not has_proj:
            r.fail("projection", f"{name}: mentions a year without an engine projection")
        if has_proj and not re.search(r"\bprojected|projection\b", bare, re.I):
            r.fail("projection", f"{name}: projection must be called 'projected'")
        # categories, per sentence
        for sent in _sentences(text):
            su = [u for u in PH.findall(sent) if u in facts]
            cats = {facts[u].category for u in su}
            sb = PH.sub(" ", sent)
            if cats & {"simulated_saving", "avoidable_estimate"} and not CONDITIONAL.search(sb):
                r.fail("categories", f"{name}: a potential saving must be conditional ('could', 'potential', 'if')")
            if cats & {"unusual", "possible_waste", "observed"} and SAVE.search(sb) and not cats & {"simulated_saving", "avoidable_estimate"}:
                r.fail("categories", f"{name}: measured/observed use is presented as a saving")
            if "verified" in cats and "measured" not in sb.lower():
                r.fail("categories", f"{name}: a verified saving must be called measured")
            if "estimated_realized" in cats and "estimat" not in sb.lower():
                r.fail("categories", f"{name}: an estimated realised saving must be called estimated")
            tariffs = {facts[u].tariff for u in su if facts[u].tariff}
            if "hourly_spot" in tariffs and re.search(r"\b(fixed|monthly)\b", sb, re.I) and not tariffs - {"hourly_spot"}:
                r.fail("tariff", f"{name}: hourly-spot value attributed to another contract")
        for m in BILL.finditer(bare):
            win = bare[max(0, m.start() - 30): m.end() + 10]
            if not BILL_OK.search(win):
                r.fail("tariff", f"{name}: claims an electricity-bill saving")
                break

    text = " ".join(fields.values())
    bare = PH.sub(" ", text)
    low = bare.lower()

    need = required_phrase(status, resp, ctx.get("wording")) if sheet.use_case.startswith("finding") or \
        (sheet.use_case == "weekly_digest" and ctx.get("top_finding")) else None
    if need and need not in low:
        r.fail("wording", f"status {status} needs the phrase '{need}'")
    if resp == "unknown" and status in ("DETECTED", "PLAUSIBLE") and "confirm" not in low:
        r.fail("wording", "a heating opportunity must say it needs confirmation")
    if OVERCLAIM.search(bare):
        r.fail("overclaim", f"'{OVERCLAIM.search(bare).group(0)}' overstates the evidence")
    if VERIFIED_WORDS.search(bare) and status != "VERIFIED":
        r.fail("overclaim", "speaks of a verified/measured saving without post-change data")
    if re.search(r"\bconfirmed\b", low) and status not in ("CONFIRMED", "REPAIRED", "VERIFIED"):
        r.fail("overclaim", f"'confirmed' overstates a {status} finding")
    if resp and resp != "manager" and FAULT_ANY.search(bare):
        r.fail("fault_language", f"behaviour/heating finding described as a fault ('{FAULT_ANY.search(bare).group(0)}')")
    if resp == "manager" and status in ("DETECTED", "PLAUSIBLE"):
        if FAULT_HARD.search(bare):
            r.fail("fault_language", f"'{FAULT_HARD.search(bare).group(0)}' states a fault as fact")
        for m in re.finditer(r"\b(fault|malfunction\w*)\b", bare, re.I):
            if not re.search(r"(possible|possibly|may|might|could)\b[\w\s-]{0,25}$", bare[max(0, m.start() - 35): m.start()], re.I):
                r.fail("fault_language", "fault/malfunction must be qualified as possible")
                break
    if resp in ("manager", "unknown") and BLAME.search(bare):
        r.fail("blame", f"'{BLAME.search(bare).group(0)}' blames residents")
    for noun in APPLIANCE_NOUNS:
        if re.search(rf"\b(your|the|a|an|this)\s+{noun}s?\b(?!-like)(?!/)", low):
            r.fail("appliance", f"says '{noun}' as fact; appliance types are assumptions ('-like')")
            break
    if ALL_AVOIDABLE.search(bare):
        r.fail("all_avoidable", f"'{ALL_AVOIDABLE.search(bare).group(0)}' claims all excess is avoidable")
    if rules.get("shift_saves_money_not_energy") or rules.get("kind") == "shift":
        if SHIFT_ENERGY.search(bare):
            r.fail("shift", f"a load shift does not save energy ('{SHIFT_ENERGY.search(bare).group(0)}')")
    for rx in UNSAFE:
        if rx.search(bare):
            r.fail("safety", f"unsafe or disruptive advice ('{rx.search(bare).group(0)}')")
    if CONFIDENCE.search(bare):
        r.fail("confidence", f"probability/confidence language ('{CONFIDENCE.search(bare).group(0)}')")
    if SYNTHETIC.search(bare):
        r.fail("synthetic", f"generalises synthetic data to real people ('{SYNTHETIC.search(bare).group(0)}')")
    for req in sheet.required:
        if req not in used_all:
            r.fail("required", f"must use {{{req}}}")
    if rules.get("must_say_potentially_unnecessary") and not (UNNECESSARY.search(bare) and HEDGE.search(bare)):
        r.fail("required", "must describe it as potentially unnecessary consumption")
    if rules.get("must_ask_confirmation") and use_case == "finding_student":
        q = output.get("question", "")
        if not q.strip().endswith("?"):
            r.fail("required", "must ask the student to confirm the appliance / whether it can be switched off")

    # logic that must match the engine / deterministic rules
    if use_case == "finding_student" and output["cta"] != rules.get("suggested_cta"):
        r.fail("logic", f"cta must be '{rules.get('suggested_cta')}'")
    if use_case == "score_explainer":
        if output["strongest_pillar"] != rules["strongest_pillar"] or output["weakest_pillar"] != rules["weakest_pillar"]:
            r.fail("logic", "strongest/weakest pillar must match the engine")
        if HEALTH.search(bare):
            r.fail("logic", "the Health pillar is not part of the Resident Actions score")

    rendered = render(output, sheet)
    for fname, lim in schemas.LIMITS[use_case].items():
        val = rendered[fname]
        if "items" in lim:
            lo, hi = lim["items"]
            if not lo <= len(val) <= hi:
                r.fail("length", f"{fname} must have {lo}-{hi} items, has {len(val)}")
            continue
        if "chars" in lim and len(val) > lim["chars"]:
            r.fail("length", f"{fname} is {len(val)} chars (max {lim['chars']})")
        if "sentences" in lim and len(_sentences(output[fname])) > lim["sentences"]:
            r.fail("length", f"{fname} has {len(_sentences(output[fname]))} sentences (max {lim['sentences']})")
    if use_case == "finding_student" and not output["headline"].strip():
        r.fail("length", "headline is empty")
    if any("{" in str(v) for v in schemas.text_fields(rendered).values()):
        r.fail("placeholders", "unrendered placeholder left in the text")
    return r, (rendered if r.passed else None)


def quantity_facts_used(output: dict, sheet: FactSheet) -> list[dict]:
    """Structured claims behind a validated text: which engine field each number came from."""
    used = set()
    for t in schemas.text_fields(output).values():
        used |= set(PH.findall(t))
    return [{"placeholder": k, "value": sheet.facts[k].value, "unit": sheet.facts[k].unit, "category": sheet.facts[k].category,
             "period": sheet.facts[sheet.facts[k].period].display if sheet.facts[k].period in sheet.facts else None,
             "tariff": sheet.facts[k].tariff, "source": sheet.facts[k].source}
            for k in sorted(used) if k in sheet.facts and sheet.facts[k].category in QUANTITY_CATEGORIES | {"evidence", "score"}]

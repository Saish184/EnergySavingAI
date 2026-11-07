"""LLM layer v2 on Mina's validated findings. No paid provider calls: providers are fakes / mocked HTTP."""
import json
import logging
import os

import pytest
import requests

os.environ["FEC_LLM_PROVIDER"] = "template"
os.environ["GONKA_BROKER_API_KEY"] = ""

from app.llm import facts as FX  # noqa: E402
from app.llm import generate as G  # noqa: E402
from app.llm import safe, templates  # noqa: E402
from app.llm.cache import cache  # noqa: E402
from app.llm.providers import GonkaProvider, TemplateProvider, select_provider  # noqa: E402
from app.llm.providers import gonka as gonka_mod  # noqa: E402
from app.llm.validator import validate  # noqa: E402
from app.state import AppState  # noqa: E402

SECRET = "sk-test-SECRET-1234567890"


@pytest.fixture(scope="module")
def s():
    return AppState()


@pytest.fixture(autouse=True)
def _iso(tmp_path):
    cache.set_path(tmp_path / "cache.json")
    G.set_client(None)
    yield
    G.set_client(None)


class Fake:
    name, model, last_error, key_present = "fake", "fake-model", None, True

    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    @property
    def enabled(self):
        return True

    def call(self, system, tool, user):
        self.calls += 1
        r = self.replies[min(self.calls - 1, len(self.replies) - 1)]
        return (dict(r) if r else None), {"latency_s": 0.0, "error": None if r else "outage"}


def sheet(s, fid, aud="student"):
    return FX.finding_sheet(s.findings_by_id[fid], aud)


def good_fs():
    return {"headline": "Sudden lasting increase",
            "explanation": "The fridge-like appliance shows a possible fault since {SINCE}. Back at its earlier level it could use about {SAVE_KWH} less over {P_WINDOW}.",
            "action": "Report it to the building manager with the button below.", "question": "", "cta": "report"}


# ---------------- the five validated opportunity types, real engine numbers

def test_all_templates_and_safe_responses_pass_on_real_data(s):
    for f in s.findings:
        for aud in ("student", "manager"):
            sh = FX.finding_sheet(f, aud)
            rep, out = validate(f"finding_{aud}", templates.render(f"finding_{aud}", sh), sh)
            assert rep.passed, (f["id"], aud, rep.failures)
            srep, _ = validate(f"finding_{aud}", safe.render(f"finding_{aud}", sh), safe.safe_sheet(sh))
            assert srep.passed, (f["id"], aud, srep.failures)
    for fid in s.ds.flat_ids:
        sc = s.scores(fid)
        for uc, sh in (("score_explainer", FX.score_sheet(sc)),
                       ("weekly_digest", FX.overview_sheet(sc, s.flat_findings(fid), s.combined_potential(fid)))):
            assert validate(uc, templates.render(uc, sh), sh)[0].passed, (uc, fid)
    sh = FX.portfolio_sheet(s.portfolio())
    assert validate("portfolio_manager", templates.render("portfolio_manager", sh), sh)[0].passed


def test_F002_fridge_window_amount_and_wording(s):
    sh = sheet(s, "FS-F002-A01")
    assert sh.facts["P_WINDOW"].value == 14 and abs(sh.facts["SAVE_KWH"].value - 23.36) < 0.01
    out = validate("finding_student", templates.render("finding_student", sh), sh)[1]
    assert "14 observed days" in out["explanation"] and "23.4 kWh" in out["explanation"]
    assert "possible fault" in out["explanation"] and "hourly spot-price contract" in out["explanation"]


def test_F004_conditional_and_asks_confirmation(s):
    sh = sheet(s, "SB-F004-A05")
    assert abs(sh.facts["SAVE_KWH"].value - 14.30) < 0.01
    out = validate("finding_student", templates.render("finding_student", sh), sh)[1]
    assert "potentially unnecessary" in out["explanation"] and out["question"].endswith("?") and out["cta"] == "confirm"
    bad = {**templates.render("finding_student", sh), "question": ""}
    assert not validate("finding_student", bad, sh)[0].passed


def test_F005_excess_vs_avoidable_range(s):
    sh = sheet(s, "BL-F005-A06")
    assert abs(sh.facts["EXCESS_KWH"].value - 62.79) < 0.01 and sh.facts["RANGE_KWH"].category == "avoidable_estimate"
    raw = {**templates.render("finding_student", sh),
           "explanation": "The lighting/standby-like appliance shows a consistent pattern; you could save all of it: {EXCESS_KWH} over {P_WINDOW}."}
    rep = validate("finding_student", raw, sh)[0]
    assert not rep.checks["all_avoidable"] and not rep.checks["required"]


def test_F007_heating_no_projection_safe_and_needs_confirmation(s):
    sh = sheet(s, "HU-F007-A07")
    assert abs(sh.facts["SAVE_KWH"].value - 9.19) < 0.01 and "PROJ_SEK_RANGE" not in sh.facts
    base = templates.render("finding_student", sh)
    yearly = {**base, "explanation": base["explanation"] + " That is a lot per year."}
    assert not validate("finding_student", yearly, sh)[0].checks["projection"]
    unsafe = {**base, "action": "Switch off the heating completely."}
    assert not validate("finding_student", unsafe, sh)[0].checks["safety"]
    assert "needs confirmation" in validate("finding_student", base, sh)[1]["explanation"]


def test_dishwasher_shift_money_not_energy_and_tariff(s):
    sh = sheet(s, "PK-F002-A04")
    assert "SAVE_KWH" not in sh.facts and sh.facts["SAVE_SEK_HOURLY"].tariff == "hourly_spot"
    base = templates.render("finding_student", sh)
    bad = {**base, "explanation": base["explanation"].replace("for the same", "and uses less energy for the same")}
    assert not validate("finding_student", bad, sh)[0].checks["shift"]
    overnight = {**base, "action": "Run it overnight while you sleep."}
    assert not validate("finding_student", overnight, sh)[0].checks["safety"]


# ---------------- numerical grounding

@pytest.mark.parametrize("text,check", [
    ("A possible fault cost 999 SEK over {P_WINDOW}.", "raw_numbers"),                 # invented number
    ("A possible fault: {SAVE_KWH} SEK could be saved over {P_WINDOW}.", "units"),     # wrong unit
    ("A possible fault could save {SAVE_KWH} per month.", "periods"),                  # wrong period
    ("A possible fault could save {SAVE_KWH} over {P_WINDOW}, so a lot every year.", "projection"),
    ("A possible fault could cut your electricity bill by {SAVE_SEK_HOURLY} over {P_WINDOW}.", "tariff"),
    ("A possible fault: you will save {SAVE_KWH} over {P_WINDOW}, guaranteed.", "overclaim"),
    ("The pattern proves a possible fault: {SAVE_KWH} could be saved over {P_WINDOW}.", "overclaim"),
    ("Your fridge is broken.", "fault_language"),
    ("A possible fault, we are ninety percent sure.", "raw_numbers"),
    ("A possible fault with high probability.", "confidence"),
    ("A possible fault; studies show students waste energy.", "synthetic"),
    ("A possible fault; you caused it.", "blame"),
])
def test_fabricated_or_misleading_claims_rejected(s, text, check):
    sh = sheet(s, "FS-F002-A01")
    rep = validate("finding_student", {**good_fs(), "explanation": text}, sh)[0]
    assert not rep.checks[check], (check, rep.failures)


def test_good_reply_passes_and_records_claims(s):
    sh = sheet(s, "FS-F002-A01")
    rep, out = validate("finding_student", good_fs(), sh)
    assert rep.passed, rep.failures
    from app.llm.validator import quantity_facts_used
    c = {x["placeholder"]: x for x in quantity_facts_used(good_fs(), sh)}
    assert c["SAVE_KWH"]["source"] == "avoidable_28d.kwh" and c["SAVE_KWH"]["period"] == "the 14 observed days"


def test_missing_confidence_and_uncertain_appliance(s):
    f = s.findings_by_id["FS-F002-A01"]
    assert f["evidence"]["confidence"] is None
    sh = sheet(s, "FS-F002-A01")
    assert sh.context["appliance"] == "fridge-like appliance" and sh.context["appliance_type_is_assumption"]
    assert not validate("finding_student", {**good_fs(), "action": "Clean your fridge coils."}, sh)[0].checks["appliance"]


# ---------------- providers, fallback, cache

def test_llm_reply_used_cached_and_revalidated(s):
    sh, fake = sheet(s, "FS-F002-A01"), Fake([good_fs()])
    r1 = G.produce("finding_student", sh, {"flat_id": "F002", "finding_id": "FS-F002-A01"}, "sync", fake)
    assert r1["source"] == "llm" and r1["prompt_version"] == "v2" and r1["claims"]
    r2 = G.produce("finding_student", sh, None, "nonblock", fake)
    assert r2["cached"] and fake.calls == 1


def test_invalid_reply_and_outage_fall_back_to_validated_template(s):
    sh = sheet(s, "FS-F002-A01")
    for fake in (Fake([{**good_fs(), "explanation": "It is broken, 999 SEK."}]), Fake([None])):
        r = G.produce("finding_student", sh, None, "sync", fake)
        assert r["source"] == "template" and r["validation"]["passed"] and r["status"] == "ok"


def test_template_failure_serves_safe_response(s, monkeypatch):
    sh = sheet(s, "FS-F002-A01")
    monkeypatch.setattr(templates, "render", lambda uc, sh: {**good_fs(), "explanation": "Broken, 999 SEK."})
    r = G.produce("finding_student", sh, None, "sync", TemplateProvider())
    assert r["source"] == "safe" and r["status"] == "safe_fallback" and r["validation"]["passed"]


def test_nonblocking_request_never_calls_provider_synchronously(s, monkeypatch):
    from app import config as C
    monkeypatch.setattr(C, "LLM_BACKGROUND", False)
    fake = Fake([good_fs()])
    r = G.produce("finding_student", sheet(s, "FS-F002-A01"), None, "nonblock", fake)
    assert r["source"] == "template" and fake.calls == 0


def test_gonka_mocked_http_failures_and_key_redaction(s, monkeypatch, caplog):
    class R:
        def __init__(self, code, text):
            self.status_code, self.text = code, text

        def json(self):
            raise ValueError
    for resp in (R(401, f"bad token Bearer {SECRET}"), requests.Timeout("t")):
        def post(*a, _r=resp, **k):
            if isinstance(_r, Exception):
                raise _r
            return _r
        monkeypatch.setattr(gonka_mod.requests, "post", post)
        p = GonkaProvider(api_key=SECRET, base_url="https://broker.test/v1", model="m")
        with caplog.at_level(logging.DEBUG):
            r = G.produce("finding_student", sheet(s, "FS-F002-A01"), None, "sync", p)
        assert r["source"] == "template"
        assert SECRET not in caplog.text and SECRET not in json.dumps(r, default=str) and SECRET not in repr(p)


def test_provider_selection_and_no_auto_model_switch():
    assert isinstance(select_provider("template"), TemplateProvider)
    assert isinstance(select_provider("gonka"), TemplateProvider)        # no key -> template
    import inspect
    from app.llm.providers import anthropic as A
    assert "fallbacks" not in inspect.getsource(A)


# ---------------- API: roles, disclaimers, admin

def test_api_roles_texts_and_disclaimer():
    from fastapi.testclient import TestClient
    from app.api.main import app
    with TestClient(app) as c:
        fs = c.get("/flats/F002/findings").json()
        assert fs and all(f["student_text"]["status"] == "ok" and "manager_text" not in f for f in fs)
        assert all("Synthetic" in f["student_text"]["disclaimer"] for f in fs)
        for f in fs:
            assert all(x not in json.dumps(f["student_text"]["output"]) for x in ("F001", "F003", "F004", "F005"))
        assert c.get("/flats/F002/findings", headers={"X-Flat-Id": "F001"}).status_code == 403
        mf = c.get("/portfolio/findings").json()
        assert all("manager_text" in f and "triage" in f for f in mf)
        assert all(not f["triage"]["maintenance"] for f in mf if f["responsibility"] != "manager")
        for ep in ("/flats/F002/tips", "/flats/F002/digest", "/flats/F002/scores", "/portfolio/summary", "/llm/status"):
            assert c.get(ep).status_code == 200, ep
        t = c.get("/flats/F002/tips").json()[0]
        assert {"finding_id", "text", "source", "wording", "status"} <= set(t)
        assert c.get("/health").json()["demo_notice"]
        assert c.post("/llm/warm").status_code == 403 and c.post("/llm/regenerate", json={}).status_code == 403


def test_workorder_dismissed_excluded_from_health():
    s = AppState()
    f = next(x for x in s.findings if x["responsibility"] == "manager" and x["status"] == "PLAUSIBLE")
    before = s.ev["lenses"]["apartment"].loc[f["flat_id"], "health"]
    w = s.create_workorder(f["id"], None)
    assert s.findings_by_id[f["id"]]["status"] == "PLAUSIBLE"
    s.patch_workorder(w["id"], fault_found=False)
    assert s.findings_by_id[f["id"]]["status"] == "DISMISSED"
    assert s.ev["lenses"]["apartment"].loc[f["flat_id"], "health"] >= before
    assert s.ev["lenses"]["apartment"].loc[f["flat_id"], "health"] == pytest.approx(100.0)

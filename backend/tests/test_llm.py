"""LLM layer tests. No real API calls: a fake client returns canned tool inputs."""
import pytest

from app.core.claims import Status
from app.core.evaluate import evaluate
from app.llm import generate as G
from app.llm import prompts as LP
from app.llm import templates
from app.llm.cache import cache
from app.llm.validator import validate
from app.state import AppState


class FakeClient:
    model = "fake-model"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    @property
    def enabled(self):
        return True

    def call(self, system, tool, user):
        self.calls += 1
        r = self.replies[min(self.calls - 1, len(self.replies) - 1)]
        return (dict(r) if r is not None else None), {"latency_s": 0.0, "error": None if r else "boom"}


@pytest.fixture(scope="module")
def state():
    return AppState()


@pytest.fixture(autouse=True)
def _fresh_cache(tmp_path):
    cache.set_path(tmp_path / "cache.json")
    yield
    G.set_client(None)


def _find(state, typ):
    return next(f for f in state.findings if f["type"] == typ)


def _student_payload(state, typ="fault_step_change"):
    return LP.payload_finding_student(_find(state, typ), state.llm_ctx)


def _good_student(p):
    sek = p["measured_last_4_weeks"]["sek"]
    return {"title": "Fridge-like appliance check",
            "body": f"The fridge-like appliance shows a possible fault since {p['since']}, about {sek} SEK measured "
                    f"over the last 4 weeks. It is an equipment question, not something you did.",
            "action": "Check that the door closes, then report it.", "cta": "report"}


# ---------------- validator ----------------

def test_good_reply_accepted(state):
    p = _student_payload(state)
    assert p["status"] == "PLAUSIBLE"
    rep = validate("finding_student", _good_student(p), p)
    assert rep.passed, rep.failures


def test_invented_number_rejected_and_template_used(state):
    p = _student_payload(state)
    bad = _good_student(p) | {"body": "The fridge-like appliance shows a possible fault costing 999 SEK."}
    assert not validate("finding_student", bad, p).checks["numbers"]
    res = G.generate("finding_student", p, client=FakeClient([bad, bad]))
    assert res["source"] == "template"
    assert res["validation"]["passed"]
    assert res["llm_attempts"] and not res["llm_attempts"][0]["validation"]["passed"]


def test_broken_for_plausible_rejected(state):
    p = _student_payload(state)
    bad = _good_student(p) | {"body": "Your fridge is broken, a possible fault."}
    rep = validate("finding_student", bad, p)
    assert not rep.checks["wording"]                         # "broken" overstates PLAUSIBLE
    assert not rep.checks["appliance"]                       # "your fridge" instead of fridge-like


def test_annual_without_projected_rejected(state):
    p = _student_payload(state)
    hi = p["projected_per_year_sek"]["high"]
    bad = _good_student(p) | {"body": f"The fridge-like appliance shows a possible fault worth {hi:.0f} SEK per year."}
    assert not validate("finding_student", bad, p).checks["projected"]
    ok = _good_student(p) | {"body": f"The fridge-like appliance shows a possible fault, projected {hi:.0f} SEK per year."}
    assert validate("finding_student", ok, p).checks["projected"]


def test_shift_claiming_less_energy_rejected(state):
    p = _student_payload(state, "peak_usage")
    sek = p["measured_last_4_weeks"]["sek"]
    bad = {"title": "Run it later", "body": f"An unusual pattern: running the dishwasher-like appliance later uses less "
                                            f"energy and saves {sek} SEK.", "action": "Start it later.", "cta": "try"}
    assert not validate("finding_student", bad, p).checks["shift"]


def test_blame_rejected_for_manager_findings(state):
    p = _student_payload(state)
    bad = _good_student(p) | {"body": "The fridge-like appliance shows a possible fault. You wasted money."}
    assert not validate("finding_student", bad, p).checks["blame"]


def test_rounded_number_and_date_accepted(state):
    p = dict(_student_payload(state))
    p["measured_last_4_weeks"] = {**p["measured_last_4_weeks"], "sek": 22.9}
    p["since"] = "15 Oct"
    reply = _good_student(p) | {"body": "The fridge-like appliance shows a possible fault since 15 Oct, about 23 SEK "
                                        "measured over the last 4 weeks."}
    rep = validate("finding_student", reply, p)
    assert rep.passed, rep.failures
    wrong_date = reply | {"body": "The fridge-like appliance shows a possible fault since 3 Oct, about 23 SEK."}
    assert not validate("finding_student", wrong_date, p).checks["numbers"]


def test_length_limits(state):
    p = _student_payload(state)
    long_body = _good_student(p) | {"body": "A possible fault. Second sentence. Third sentence."}
    assert not validate("finding_student", long_body, p).checks["length"]
    assert not validate("finding_student", _good_student(p) | {"title": "x" * 61}, p).checks["length"]


def test_manager_priority_rule(state):
    f = _find(state, "fault_step_change")
    p = LP.payload_finding_manager(f, state.llm_ctx)
    out = templates.render("finding_manager", p)
    assert validate("finding_manager", out, p).passed
    wrong = out | {"priority": "high" if out["priority"] != "high" else "low"}
    assert not validate("finding_manager", wrong, p).checks["logic"]


def test_score_explainer_no_health_and_pillars_match(state):
    p = LP.payload_score(state.scores("F003", with_explainer=False))
    out = templates.render("score_explainer", p)
    assert validate("score_explainer", out, p).passed
    assert not validate("score_explainer", out | {"summary": "Your health pillar is fine."}, p).checks["logic"]
    other = next(k for k in ("use", "waste", "timing") if k != p["weakest_pillar"])
    assert not validate("score_explainer", out | {"weakest_pillar": other}, p).checks["logic"]


@pytest.mark.parametrize("status", [None, "DETECTED", "CONFIRMED", "REPAIRED", "VERIFIED", "DISMISSED"])
def test_every_phrase_variant_passes_validator(state, status):
    """Every variant in phrases.json, for every finding and status, must pass the checks."""
    for variant in range(templates.n_variants()):
        for f in state.findings:
            g = f if status is None else {**f, "status": status}
            for uc, p in (("finding_student", LP.payload_finding_student(g, state.llm_ctx)),
                          ("finding_manager", LP.payload_finding_manager(g, state.llm_ctx))):
                rep = validate(uc, templates.render(uc, p, variant), p)
                assert rep.passed, (uc, f["id"], status, variant, rep.failures)
        for fid in state.ds.flat_ids:
            sc = state.scores(fid, with_explainer=False)
            p = LP.payload_score(sc)
            rep = validate("score_explainer", templates.render("score_explainer", p, variant), p)
            assert rep.passed, (fid, variant, rep.failures)
            mine = [f for f in state.findings if f["flat_id"] == fid]
            p = LP.payload_digest(sc, state.week_summary(fid), mine[0] if mine else None, state.llm_ctx)
            rep = validate("weekly_digest", templates.render("weekly_digest", p, variant), p)
            assert rep.passed, (fid, variant, rep.failures)


def test_default_provider_makes_no_api_calls(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-would-be-used")
    G.set_client(None)
    assert not G.get_client().enabled                        # provider "none" ignores any key


# ---------------- generate / cache ----------------

def test_valid_llm_reply_used_and_cached(state):
    p = _student_payload(state)
    fake = FakeClient([_good_student(p)])
    r1 = G.generate("finding_student", p, {"flat_id": "F003", "finding_id": "AN001"}, client=fake)
    assert r1["source"] == "llm" and r1["prompt_version"] == LP.PROMPT_VERSION and not r1["cached"]
    r2 = G.generate("finding_student", p, client=fake)
    assert fake.calls == 1                                   # cache hit, client not called again
    assert r2["cached"] and r2["output"] == r1["output"]
    assert cache.clear(flat_id="F003") == 1
    G.generate("finding_student", p, client=fake)
    assert fake.calls == 2


def test_repair_attempt_can_fix_reply(state):
    p = _student_payload(state)
    bad = _good_student(p) | {"body": "A possible fault costing 999 SEK."}
    fake = FakeClient([bad, _good_student(p)])
    res = G.generate("finding_student", p, client=fake)
    assert res["source"] == "llm" and fake.calls == 2


def test_api_error_falls_back_without_retry(state):
    p = _student_payload(state)
    fake = FakeClient([None])
    res = G.generate("finding_student", p, client=fake)
    assert res["source"] == "template" and fake.calls == 1


def test_no_api_key_gives_template(state):
    from app.llm.client import LLMClient
    c = LLMClient(api_key="")
    assert not c.enabled
    res = G.generate("finding_student", _student_payload(state), client=c)
    assert res["source"] == "template" and res["prompt_version"] == LP.PROMPT_VERSION


def test_strict_tool_schema():
    from app.llm.schemas import SCHEMAS, tool_for
    for uc in SCHEMAS:
        t = tool_for(uc)
        assert t["strict"] is True
        sch = t["input_schema"]
        assert sch["additionalProperties"] is False and set(sch["required"]) == set(sch["properties"])
        assert set(sch["properties"]) == set(SCHEMAS[uc].model_fields)   # e.g. "title" not stripped


# ---------------- work-order fix ----------------

def test_workorder_create_keeps_status_and_outcomes():
    s = AppState()
    f = next(x for x in s.findings if x["responsibility"] == "manager" and x["status"] == "PLAUSIBLE")
    w = s.create_workorder(f["id"], None)
    assert s.findings_by_id[f["id"]]["status"] == "PLAUSIBLE"
    s.patch_workorder(w["id"], fault_found=True)
    assert s.findings_by_id[f["id"]]["status"] == "CONFIRMED"


def test_no_fault_found_dismisses_and_health_ignores_it():
    s = AppState()
    f = next(x for x in s.findings if x["responsibility"] == "manager" and x["status"] == "PLAUSIBLE")
    flat = f["flat_id"]
    without = s.ds.copy(anomalies=[a for a in s.ds.anomalies if a["id"] != f["id"]])
    health_without = evaluate(without, with_sensitivity=False)["lenses"]["apartment"].loc[flat, "health"]
    health_before = s.ev["lenses"]["apartment"].loc[flat, "health"]
    assert health_before < health_without                    # the PLAUSIBLE fault lowered HEALTH
    w = s.create_workorder(f["id"], None)
    s.patch_workorder(w["id"], fault_found=False)
    assert s.ds.anomaly(f["id"])["status"] == Status.DISMISSED
    assert s.findings_by_id[f["id"]]["status"] == "DISMISSED"
    assert s.ev["lenses"]["apartment"].loc[flat, "health"] == pytest.approx(health_without)

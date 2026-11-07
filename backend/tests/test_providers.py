"""Provider tests with mocked HTTP. No real network calls."""
import json
import logging

import pytest
import requests

from app.llm import generate as G
from app.llm import prompts as LP
from app.llm.cache import cache
from app.llm.providers import GonkaProvider, TemplateProvider, select_provider
from app.llm.providers import gonka as gonka_mod
from app.llm.schemas import tool_for
from app.state import AppState

SECRET = "sk-test-SECRET-1234567890"


class FakeResp:
    def __init__(self, status=200, body=None, text=None):
        self.status_code = status
        self._body = body
        self.text = text if text is not None else json.dumps(body)

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def tool_reply(name, args, as_string=True):
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
        {"id": "c1", "type": "function",
         "function": {"name": name, "arguments": json.dumps(args) if as_string else args}}]}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


@pytest.fixture(scope="module")
def state():
    return AppState()


@pytest.fixture(autouse=True)
def _iso(tmp_path):
    cache.set_path(tmp_path / "cache.json")
    yield
    G.set_client(None)


@pytest.fixture()
def payload(state):
    f = next(x for x in state.findings if x["type"] == "fault_step_change" and x["status"] == "PLAUSIBLE")
    return LP.payload_finding_student(f, state.llm_ctx)


def good(p):
    return {"title": "Fridge-like appliance check",
            "body": f"The fridge-like appliance shows a possible fault since {p['since']}, about "
                    f"{p['measured_last_4_weeks']['sek']} SEK measured over the last 4 weeks.",
            "action": "Check that the door closes, then report it.", "cta": "report"}


def provider():
    return GonkaProvider(api_key=SECRET, base_url="https://broker.test/v1", model="test-model")


def mock_post(monkeypatch, *responses):
    calls = []

    def post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        r = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(gonka_mod.requests, "post", post)
    return calls


def test_valid_tool_call_parsed_and_used(monkeypatch, payload):
    name = tool_for("finding_student")["name"]
    calls = mock_post(monkeypatch, FakeResp(200, tool_reply(name, good(payload))))
    p = provider()
    out = p.generate(LP.STUDENT_PROMPT, "x", tool_for("finding_student"))
    assert out == good(payload)
    body = calls[0]["json"]
    assert calls[0]["url"] == "https://broker.test/v1/chat/completions"
    assert body["tool_choice"]["function"]["name"] == name and body["tools"][0]["type"] == "function"
    assert calls[0]["timeout"] == 30.0
    res = G.generate("finding_student", payload, client=p)
    assert res["source"] == "llm" and res["provider"] == "gonka" and res["model"] == "test-model"
    assert res["prompt_version"] == LP.PROMPT_VERSION


def test_arguments_as_object_also_ok(monkeypatch, payload):
    name = tool_for("finding_student")["name"]
    mock_post(monkeypatch, FakeResp(200, tool_reply(name, good(payload), as_string=False)))
    assert provider().generate("s", "u", tool_for("finding_student")) == good(payload)


@pytest.mark.parametrize("resp", [
    FakeResp(200, {"choices": [{"message": {"content": "here you go", "tool_calls": []}}]}),   # no tool call
    FakeResp(200, {"choices": [{"message": {"tool_calls": [{"function": {
        "name": "write_finding_student", "arguments": "{not json"}}]}}]}),                      # bad JSON
    requests.Timeout("timed out"),                                                              # timeout
    FakeResp(401, {"error": "invalid or expired token"}),                                       # auth
    FakeResp(200, None, text="<html>oops</html>"),                                              # not JSON
])
def test_failures_return_none_and_template_is_used(monkeypatch, payload, resp):
    mock_post(monkeypatch, resp)
    p = provider()
    assert p.generate("s", "u", tool_for("finding_student")) is None
    assert p.last_error
    res = G.generate("finding_student", payload, client=p)
    assert res["source"] == "template" and res["provider"] == "template" and res["fallback_from"] == "gonka"
    assert res["validation"]["passed"]


def test_retry_once_on_5xx_and_network_error(monkeypatch, payload):
    name = tool_for("finding_student")["name"]
    calls = mock_post(monkeypatch, FakeResp(503, {"error": "busy"}), FakeResp(200, tool_reply(name, good(payload))))
    assert provider().generate("s", "u", tool_for("finding_student")) == good(payload)
    assert len(calls) == 2
    calls = mock_post(monkeypatch, requests.ConnectionError("down"), requests.ConnectionError("down"))
    assert provider().generate("s", "u", tool_for("finding_student")) is None
    assert len(calls) == 2                                    # 1 try + 1 retry, then give up
    calls = mock_post(monkeypatch, FakeResp(401, {"error": "nope"}))
    provider().generate("s", "u", tool_for("finding_student"))
    assert len(calls) == 1                                    # no retry on 4xx


def test_template_provider_makes_no_http_call(monkeypatch, payload):
    calls = mock_post(monkeypatch, FakeResp(500, {}))
    p = select_provider("template")
    assert isinstance(p, TemplateProvider) and not p.enabled
    res = G.generate("finding_student", payload, client=p)
    assert res["source"] == "template" and calls == []


def test_missing_key_or_unknown_provider_falls_back(monkeypatch, caplog):
    monkeypatch.setenv("GONKA_BROKER_API_KEY", "")
    with caplog.at_level(logging.WARNING, logger="fec.llm"):
        assert isinstance(select_provider("gonka"), TemplateProvider)
        assert isinstance(select_provider("banana"), TemplateProvider)
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2


def test_key_never_in_logs_or_responses(monkeypatch, payload, caplog):
    # broker echoes the key back in its error body
    mock_post(monkeypatch, FakeResp(401, {"error": f"bad token {SECRET}"}, text=f"bad token Bearer {SECRET}"))
    p = provider()
    with caplog.at_level(logging.DEBUG):
        res = G.generate("finding_student", payload, client=p)
    assert SECRET not in caplog.text
    assert SECRET not in json.dumps(res, default=str)
    assert SECRET not in (p.last_error or "") and SECRET not in repr(p)
    assert "[REDACTED]" in p.last_error


def test_endpoints_200_when_gonka_fails(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.main import app
    mock_post(monkeypatch, FakeResp(401, {"error": "invalid or expired token"}))
    G.set_client(provider())
    with TestClient(app) as c:
        for ep in ("/flats/F003/findings", "/flats/F003/digest", "/flats/F003/scores", "/flats/F003/tips",
                   "/portfolio/findings"):
            r = c.get(ep)
            assert r.status_code == 200, ep
            assert SECRET not in r.text
        f = c.get("/flats/F003/findings").json()[0]
        assert f["student_text"]["source"] == "template"
        st = c.get("/llm/status").json()
        assert st["provider"] == "gonka" and st["key_present"] is True and st["last_error"]
        assert SECRET not in json.dumps(st)


def test_status_endpoint_template_mode():
    from fastapi.testclient import TestClient
    from app.api.main import app
    with TestClient(app) as c:
        st = c.get("/llm/status").json()
        assert st["provider"] == "template" and st["llm_enabled"] is False and st["key_present"] is False

"""Gonka broker: OpenAI-compatible /chat/completions with function tools, over plain HTTP
(the openai package is broken in this environment). Forced tool_choice works on this broker."""
from __future__ import annotations

import json
import time

import requests

from ... import config as C
from .base import Provider, log, redact

RETRY_STATUS = {500, 502, 503, 504}


class GonkaProvider(Provider):
    name = "gonka"

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        super().__init__(model=model or C.GONKA_MODEL)
        self._key = api_key if api_key is not None else C.env("GONKA_BROKER_API_KEY")
        self.base_url = (base_url or C.GONKA_BROKER_URL).rstrip("/")

    @property
    def key_present(self) -> bool:
        return bool(self._key)

    @property
    def enabled(self) -> bool:
        return bool(self._key and self.base_url and self.model)

    def __repr__(self):                                # never show the key
        return f"GonkaProvider(base_url={self.base_url!r}, model={self.model!r}, key_present={self.key_present})"

    def _body(self, system: str, tool: dict, user: str) -> dict:
        fn = {"name": tool["name"], "description": tool["description"], "parameters": tool["input_schema"]}
        return {
            "model": self.model,
            "max_tokens": C.GONKA_MAX_TOKENS,
            "temperature": C.GONKA_TEMPERATURE,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "tools": [{"type": "function", "function": fn}],
            "tool_choice": {"type": "function", "function": {"name": tool["name"]}},
        }

    def call(self, system: str, tool: dict, user: str) -> tuple[dict | None, dict]:
        info = {"provider": self.name, "model": self.model, "latency_s": 0.0, "error": None, "usage": None}
        if not self.enabled:
            return self._fail(info, "gonka not configured (key, url or model missing)")
        self.calls += 1
        t0 = time.time()
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        body = self._body(system, tool, user)
        resp = None
        try:
            for attempt in range(1 + C.GONKA_RETRIES):
                try:
                    resp = requests.post(url, json=body, headers=headers, timeout=C.GONKA_TIMEOUT_S)
                except (requests.ConnectionError, requests.Timeout) as e:
                    if attempt < C.GONKA_RETRIES:
                        log.info("gonka network error, retrying: %s", type(e).__name__)
                        continue
                    return self._fail(info, f"{type(e).__name__}: network error/timeout", self._key)
                if resp.status_code in RETRY_STATUS and attempt < C.GONKA_RETRIES:
                    log.info("gonka HTTP %s, retrying", resp.status_code)
                    continue
                break
            if resp.status_code != 200:
                return self._fail(info, f"HTTP {resp.status_code}: {resp.text[:200]}", self._key)
            try:
                data = resp.json()
                msg = data["choices"][0]["message"]
            except (ValueError, KeyError, IndexError, TypeError):
                return self._fail(info, "unexpected response shape", self._key)
            info["usage"] = data.get("usage")
            calls = msg.get("tool_calls") or []
            call = next((c for c in calls if c.get("function", {}).get("name") == tool["name"]), None)
            if call is None:
                return self._fail(info, "model did not call the tool")
            try:
                args = call["function"]["arguments"]
                out = json.loads(args) if isinstance(args, str) else args
            except (ValueError, TypeError):
                return self._fail(info, "tool arguments are not valid JSON")
            if not isinstance(out, dict):
                return self._fail(info, "tool arguments are not an object")
            self.last_error = None
            return out, info
        except Exception as e:  # noqa: BLE001  never raise into the app
            return self._fail(info, f"{type(e).__name__}: {e}", self._key)
        finally:
            info["latency_s"] = round(time.time() - t0, 3)

"""Claude via the Anthropic SDK (optional; used when FEC_LLM_PROVIDER=anthropic and a key is set).

Claude Sonnet 5.5 rejects a forced tool_choice (400), so tool_choice is "auto" + strict schema +
the prompt asks for exactly one tool call. A reply without that tool call counts as a failure."""
from __future__ import annotations

import time

from ... import config as C
from .base import Provider


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        super().__init__(model=model or C.LLM_MODEL)
        self._key = api_key if api_key is not None else C.env("ANTHROPIC_API_KEY")
        self._client = None

    @property
    def key_present(self) -> bool:
        return bool(self._key)

    @property
    def enabled(self) -> bool:
        return bool(self._key)

    def __repr__(self):
        return f"AnthropicProvider(model={self.model!r}, key_present={self.key_present})"

    def _sdk(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._key, timeout=C.LLM_TIMEOUT_S,
                                               max_retries=C.LLM_MAX_RETRIES)
        return self._client

    def call(self, system: str, tool: dict, user: str) -> tuple[dict | None, dict]:
        info = {"provider": self.name, "model": self.model, "latency_s": 0.0, "error": None,
                "stop_reason": None, "usage": None}
        if not self.enabled:
            return self._fail(info, "no API key")
        self.calls += 1
        t0 = time.time()
        try:
            import anthropic
            sdk = self._sdk()
            kwargs = dict(
                model=self.model,
                max_tokens=C.LLM_MAX_TOKENS,
                # cache breakpoint on the system prompt (tools render before it, so both are cached)
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                tools=[tool],
                tool_choice={"type": "auto"},
                messages=[{"role": "user", "content": user}],
            )
            body = {"output_config": {"effort": C.LLM_EFFORT}}
            resp = None
            if C.LLM_REFUSAL_FALLBACK:
                try:
                    resp = sdk.beta.messages.create(**kwargs, betas=["server-side-fallback-2026-07-01"],
                                                    extra_body={**body, "fallbacks": "default"})
                except anthropic.BadRequestError:
                    resp = None                       # fallback param not accepted -> plain request
            if resp is None:
                resp = sdk.messages.create(**kwargs, extra_body=body)
            info["stop_reason"] = resp.stop_reason
            info["usage"] = {k: getattr(resp.usage, k, None) for k in
                             ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
            if resp.stop_reason == "refusal":
                return self._fail(info, "refusal")
            for block in resp.content:
                if block.type == "tool_use" and block.name == tool["name"]:
                    self.last_error = None
                    return dict(block.input), info
            return self._fail(info, "model did not call the tool")
        except Exception as e:  # noqa: BLE001  network, auth, rate limit, timeout -> template
            return self._fail(info, f"{type(e).__name__}: {e}", self._key)
        finally:
            info["latency_s"] = round(time.time() - t0, 3)

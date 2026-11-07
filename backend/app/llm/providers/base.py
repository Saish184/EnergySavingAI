"""Provider interface. A provider only rewords engine JSON; it never computes numbers.

    call(system, user, tool)     -> (tool_input dict | None, info dict)   used by generate.py
    generate(system, user, tool) -> tool_input dict | None                convenience

`tool` is the provider-neutral tool definition from schemas.tool_for(): {name, description,
input_schema, strict}. Providers convert it to their own wire format. They never raise."""
from __future__ import annotations

import logging
import re

log = logging.getLogger("fec.llm")


def redact(text: str | None, *secrets: str | None) -> str | None:
    """Remove secrets and bearer tokens from any text before it is logged or returned."""
    if text is None:
        return None
    for s in secrets:
        if s:
            text = text.replace(s, "[REDACTED]")
    return re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+", r"\1[REDACTED]", text)


class Provider:
    name = "base"

    def __init__(self, model: str | None = None):
        self.model = model
        self.calls = 0
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return False

    @property
    def key_present(self) -> bool:
        return False

    def call(self, system: str, tool: dict, user: str) -> tuple[dict | None, dict]:
        return None, {"provider": self.name, "model": self.model, "latency_s": 0.0, "error": "disabled"}

    def generate(self, system: str, user: str, tool: dict) -> dict | None:
        return self.call(system, tool, user)[0]

    def _fail(self, info: dict, error: str, *secrets) -> tuple[None, dict]:
        info["error"] = redact(error, *secrets)[:300]
        self.last_error = info["error"]
        log.warning("%s call failed: %s", self.name, info["error"])
        return None, info

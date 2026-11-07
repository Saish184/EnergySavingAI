"""Provider selection from FEC_LLM_PROVIDER = gonka | anthropic | template (default).
Unknown provider or missing key -> template, with one warning line."""
from __future__ import annotations

from ... import config as C
from .anthropic import AnthropicProvider
from .base import Provider, log, redact
from .gonka import GonkaProvider
from .template import TemplateProvider

__all__ = ["Provider", "GonkaProvider", "AnthropicProvider", "TemplateProvider", "select_provider", "redact"]


def select_provider(name: str | None = None) -> Provider:
    name = (name or C.LLM_PROVIDER or "template").strip().lower()
    if name in ("template", "none", ""):
        return TemplateProvider()
    if name == "gonka":
        p = GonkaProvider()
        if p.enabled:
            return p
        log.warning("FEC_LLM_PROVIDER=gonka but GONKA_BROKER_API_KEY/URL/MODEL missing -> using template texts")
        return TemplateProvider()
    if name == "anthropic":
        p = AnthropicProvider()
        if p.enabled:
            return p
        log.warning("FEC_LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY missing -> using template texts")
        return TemplateProvider()
    log.warning("unknown FEC_LLM_PROVIDER=%r -> using template texts", name)
    return TemplateProvider()

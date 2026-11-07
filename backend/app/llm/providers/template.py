"""Our own wording (phrases.json). No network, no key. Default provider."""
from __future__ import annotations

from .. import templates
from .base import Provider


class TemplateProvider(Provider):
    name = "template"

    def __init__(self):
        super().__init__(model=None)

    def render(self, use_case: str, payload: dict) -> dict:
        return templates.render(use_case, payload)

"""Backward-compatible alias; the providers live in app/llm/providers/."""
from .providers.anthropic import AnthropicProvider as LLMClient  # noqa: F401

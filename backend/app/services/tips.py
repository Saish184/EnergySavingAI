"""Tips = the student texts of a flat's top findings. Thin wrapper: the single LLM integration layer is
app/llm/ (facts -> provider/template -> validator -> renderer). Kept for import compatibility."""
from __future__ import annotations


def tips_for_flat(state, flat_id: str, limit: int = 3) -> list[dict]:
    from ..llm import service
    return service.tips(state, flat_id, limit)

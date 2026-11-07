"""Cache of validated LLM outputs (raw placeholder text): key = hash(use_case + fact sheet + prompt/validator
version + provider/model). Entries are re-validated before they are served (generate.produce).
Persisted to out/llm_cache.json so the demo never depends on a live API call.
Templates are not cached (deterministic and free)."""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from .. import config as C


class LLMCache:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._data: dict | None = None
        self._lock = threading.Lock()

    @staticmethod
    def key(use_case: str, payload: dict, prompt_version: str, model: str) -> str:
        raw = json.dumps([use_case, payload, prompt_version, model], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _load(self) -> dict:
        if self._data is None:
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                self._data = {}
        return self._data

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, key: str) -> dict | None:
        with self._lock:
            return self._load().get(key)

    def set(self, key: str, value: dict, meta: dict | None = None):
        with self._lock:
            self._load()[key] = {**value, "meta": meta or {}}
            self._save()

    def drop(self, key: str):
        with self._lock:
            if self._load().pop(key, None) is not None:
                self._save()

    def clear(self, flat_id: str | None = None, finding_id: str | None = None) -> int:
        with self._lock:
            data = self._load()
            drop = [k for k, v in data.items()
                    if (flat_id is None or v.get("meta", {}).get("flat_id") == flat_id)
                    and (finding_id is None or v.get("meta", {}).get("finding_id") == finding_id)]
            for k in drop:
                del data[k]
            self._save()
            return len(drop)

    def entries(self) -> dict:
        with self._lock:
            return dict(self._load())

    def set_path(self, path: Path):
        with self._lock:
            self.path, self._data = Path(path), None


cache = LLMCache(C.LLM_CACHE_PATH)

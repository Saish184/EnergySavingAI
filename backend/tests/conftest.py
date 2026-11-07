import os
import sys
from pathlib import Path

os.environ["FEC_DATA_SOURCE"] = "mock"          # tests never depend on the teammate's files
os.environ["ANTHROPIC_API_KEY"] = ""            # tests never call an LLM (empty values also block .env)
os.environ["GONKA_BROKER_API_KEY"] = ""
os.environ["FEC_LLM_PROVIDER"] = "template"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile  # noqa: E402
os.environ["FEC_LLM_CACHE"] = str(Path(tempfile.mkdtemp()) / "llm_cache.json")  # never touch out/

import pytest  # noqa: E402

from app.core.evaluate import evaluate  # noqa: E402
from app.loader import load  # noqa: E402


@pytest.fixture(scope="session")
def loaded():
    ds, _ = load()
    return ds


@pytest.fixture()
def ds(loaded):
    return loaded.copy()


@pytest.fixture(scope="session")
def ev(loaded):
    return evaluate(loaded)

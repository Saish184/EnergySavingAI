import os
import sys
from pathlib import Path

os.environ["FEC_DATA_SOURCE"] = "mock"          # tests never depend on the teammate's files
os.environ["ANTHROPIC_API_KEY"] = ""            # tests never call the LLM (empty also blocks .env)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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

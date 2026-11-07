import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT / "analysis" / "score_audit"))

from mathcore import load_flats  # noqa: E402


@pytest.fixture(scope="session")
def flats():
    return load_flats()


@pytest.fixture(scope="session")
def opportunities():
    return {o["id"]: o for o in json.loads((ROOT / "reports" / "opportunities.json").read_text())["opportunities"]}


@pytest.fixture(scope="session")
def root():
    return ROOT

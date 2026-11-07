import os
import sys
from pathlib import Path

os.environ.setdefault("FEC_DATA_SOURCE", "processed")   # validated pipeline output (data/processed/analytical_table.csv)
os.environ["ANTHROPIC_API_KEY"] = ""                     # tests never call the LLM (empty also blocks .env)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.core.evaluate import evaluate, prepare  # noqa: E402
from app.loader import load  # noqa: E402


@pytest.fixture(scope="session")
def loaded():
    ds, _ = load()
    return prepare(ds)


@pytest.fixture()
def ds(loaded):
    return loaded.copy()          # anomalies (statuses) are copied; baseline flats and frozen references are shared, read-only


@pytest.fixture(scope="session")
def ev(loaded):
    return evaluate(loaded)


@pytest.fixture(scope="session")
def opportunities():
    """Validated reference values from reports/opportunities.json (the independent research pipeline)."""
    import json
    J = {o["id"][:2]: o for o in json.loads((Path(__file__).resolve().parents[2] / "reports" / "opportunities.json").read_text())["opportunities"]}
    sc = lambda oid, role: next(s for s in J[oid]["scenarios"] if s["role"] == role)  # noqa: E731
    return {"O1": {"central_kwh": sc("O1", "central")["kwh"], "upper_kwh": sc("O1", "upper_measured")["kwh"]},
            "O5": {"central_sek": sc("O5", "central")["value_spot_hourly_sek"]}, "raw": J}

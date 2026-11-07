"""The mock fallback still loads and evaluates (used when no pipeline output exists)."""
from app import config as C
from app.core.evaluate import evaluate, prepare
from app import loader


def test_mock_source_loads_and_evaluates(monkeypatch):
    monkeypatch.setattr(C, "DATA_SOURCE", "mock")
    ds, q = loader.load()
    assert q["data_source"] == "mock" and len(ds.flats) == 8
    ev = evaluate(prepare(ds), with_sensitivity=False)
    for lens, t in ev["lenses"].items():
        assert ((t["score"] > 0) & (t["score"] <= 100)).all()


def test_processed_source_is_the_validated_pipeline_output():
    src, path = loader.resolve_source()
    assert src == "processed" and path.endswith("analytical_table.csv")

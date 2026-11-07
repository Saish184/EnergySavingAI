import numpy as np
import pandas as pd

from app import config as C
from app.core.claims import Status
from app.core.evaluate import evaluate
from app.core.score import arithmetic, band, geometric
from app.core.sensitivity import sensitivity


def _with_injected_fault(loaded, flat="F003", ch="A01", add=0.06, from_hour=360):
    """A lasting step on an equipment channel: the engine must DETECT it (no hand-made anomaly)."""
    from app.core.dataset import Dataset
    flats = dict(loaded.flats)
    k = flats[flat].kwh.copy()
    k.loc[from_hour:, ch] = k.loc[from_hour:, ch] + add
    flats[flat] = flats[flat].with_kwh(k)
    from app.core.evaluate import prepare
    return prepare(Dataset(flats=flats, meta=loaded.meta))


def test_manager_excess_lowers_apartment_not_resident(loaded, ev):
    ds2 = _with_injected_fault(loaded)
    assert any(a["id"] == "FS-F003-A01" and a["responsibility"] == "manager" for a in ds2.anomalies)
    ev2 = evaluate(ds2, with_sensitivity=False)
    ap1, ap2 = ev["lenses"]["apartment"].loc["F003", "score"], ev2["lenses"]["apartment"].loc["F003", "score"]
    rs1, rs2 = ev["lenses"]["resident"], ev2["lenses"]["resident"]
    assert ap2 < ap1
    assert ev2["lenses"]["apartment"].loc["F003", "health"] < ev["lenses"]["apartment"].loc["F003", "health"]
    for col in ["score", *C.LENSES["resident"]]:                       # resident lens unchanged for every flat
        np.testing.assert_allclose(rs2[col].to_numpy(), rs1[col].to_numpy(), atol=1e-6)


def test_geometric_le_arithmetic():
    rng = np.random.default_rng(0)
    for lens, w in C.LENSES.items():
        for _ in range(2000):
            vals = rng.choice([0.0, 0.5, 1.0, 37.0, 99.0, 100.0], size=len(w)) if rng.random() < 0.3 \
                else rng.uniform(0, 100, size=len(w))
            p = dict(zip(w, vals))
            assert geometric(p, w) <= arithmetic(p, w) + 1e-9


def test_geometric_le_arithmetic_on_data(ev):
    for t in ev["lenses"].values():
        assert (t["score"] <= t["arithmetic_mean"] + 1e-9).all()


def test_bands():
    assert band(95) == "A" and band(90) == "A" and band(89.9) == "B" and band(55) == "D"
    assert band(19.9) == "G" and band(0) == "G"


def test_sensitivity_brackets_score(ev):
    for lens, t in ev["lenses"].items():
        s = ev["sensitivity"][lens]
        assert (s["score_p5"] <= s["score_p95"]).all()
        assert (s["rank_p5"] <= s["rank_p95"]).all()
        assert ((s["rank_p5"] >= 1) & (s["rank_p95"] <= len(t))).all()


def test_sensitivity_reproducible(ev):
    t = ev["lenses"]["apartment"]
    a = sensitivity(t, C.LENSES["apartment"])
    b = sensitivity(t, C.LENSES["apartment"])
    pd.testing.assert_frame_equal(a, b)

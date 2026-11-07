import numpy as np
import pandas as pd

from app import config as C
from app.core.claims import Status
from app.core.evaluate import evaluate
from app.core.score import arithmetic, band, geometric
from app.core.sensitivity import sensitivity


def _add_manager_excess(ds, app="F001-A05", delta=0.25, start="2026-10-10", end="2026-10-20"):
    r = ds.readings.copy()
    s, e = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    m = (r["appliance_id"] == app) & (r["timestamp_utc"] >= s) & (r["timestamp_utc"] < e)
    r.loc[m, "kwh"] = r.loc[m, "kwh"] + delta
    base = float(ds.readings.loc[m, "kwh"].mean())
    a = {"id": "TEST1", "flat_id": app[:4], "appliance_id": app, "channel": app[-3:], "type": "fault_step_change",
         "start": s, "end": e, "excess_kwh": float(delta * r.loc[m, "kwh"].notna().sum()),
         "baseline_kwh_per_h": base, "observed_kwh_per_h": base + delta, "confidence": 0.9,
         "status": Status.PLAUSIBLE, "responsibility": "manager", "evidence": "test"}
    return ds.copy(readings=r, anomalies=ds.anomalies + [a])


def test_manager_excess_lowers_apartment_not_resident(ds, ev):
    ev2 = evaluate(_add_manager_excess(ds), with_sensitivity=False)
    ap1, ap2 = ev["lenses"]["apartment"].loc["F001", "score"], ev2["lenses"]["apartment"].loc["F001", "score"]
    rs1, rs2 = ev["lenses"]["resident"], ev2["lenses"]["resident"]
    assert ap2 < ap1
    assert ev2["lenses"]["apartment"].loc["F001", "health"] < ev["lenses"]["apartment"].loc["F001", "health"]
    # resident lens unchanged for every flat (incl. pillars)
    for col in ["score", *C.LENSES["resident"]]:
        np.testing.assert_allclose(rs2[col].to_numpy(), rs1[col].to_numpy(), atol=1e-9)


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

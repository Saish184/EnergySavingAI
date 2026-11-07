import numpy as np
import pandas as pd
import pytest

from app.core.claims import Status, human_transition, verification_transition
from app.core.verification import simulate_post_repair, verify


def _post(days, rate, seed=0):
    ts = pd.date_range("2026-10-29", periods=int(days * 24), freq="h", tz="UTC")
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"timestamp_utc": ts, "kwh": np.maximum(0, rate + 0.005 * rng.standard_normal(len(ts)))})


def test_no_verified_with_less_than_7_days():
    for days in (0, 1, 3, 6.9):
        r = verify(0.18, _post(days, 0.07), Status.REPAIRED)
        assert r["status"] == "REPAIRED", days
        assert r["saving_kwh"] is None


def test_missing_hours_do_not_count_as_days():
    p = _post(10, 0.07)
    p.loc[p.index[: 24 * 4], "kwh"] = np.nan              # 10 days of rows, only 6 with data
    assert verify(0.18, p, Status.REPAIRED)["status"] == "REPAIRED"


def test_verified_with_7_days_and_real_saving():
    r = verify(0.18, _post(7, 0.07), Status.REPAIRED)
    assert r["status"] == "VERIFIED"
    assert r["interval_90"][0] > 0
    assert abs(r["saving_kwh"] - (0.18 - 0.07) * 7 * 24) < 2


def test_no_saving_stays_repaired():
    r = verify(0.07, _post(10, 0.07), Status.REPAIRED)
    assert r["status"] == "REPAIRED"


def test_only_verification_sets_verified():
    with pytest.raises(ValueError):
        human_transition(Status.REPAIRED, Status.VERIFIED)
    with pytest.raises(ValueError):
        verification_transition(Status.CONFIRMED, True)


def test_simulated_flag():
    a = {"baseline_kwh_per_h": 0.07, "observed_kwh_per_h": 0.18}
    post = simulate_post_repair(a)
    assert post["simulated"].all()
    r = verify(0.18, post, Status.REPAIRED, simulated=True)
    assert r["simulated"] is True and "SIMULATED" in r["reason"]

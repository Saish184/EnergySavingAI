import numpy as np
import pandas as pd
import pytest

from app import config as C
from app.core.dataset import Dataset
from app.core.detect import unoccupied_cells
from app.core.evaluate import evaluate, prepare
from app.core.pillars import pillars
from app.loader import parse_utc


def _all_pillars(ev):
    for lens, t in ev["lenses"].items():
        for k in C.LENSES[lens]:
            yield lens, k, t[k]


def test_pillars_between_0_and_100(ev):
    for lens, k, s in _all_pillars(ev):
        assert s.notna().all(), (lens, k)
        assert ((s >= 0) & (s <= 100)).all(), (lens, k, s.tolist())


def test_pillars_bounded_under_extreme_data(loaded):
    flats = dict(loaded.flats)
    flats["F001"] = flats["F001"].with_kwh(flats["F001"].kwh * 50)       # absurdly high flat
    flats["F002"] = flats["F002"].with_kwh(flats["F002"].kwh * 0.0)      # flat that uses nothing
    ev = evaluate(prepare(Dataset(flats=flats, meta=loaded.meta)), with_sensitivity=False)
    for lens, k, s in _all_pillars(ev):
        v = s.dropna()
        assert ((v >= 0) & (v <= 100)).all(), (lens, k)


def test_flat_at_or_below_benchmark_gets_use_100(loaded):
    R = loaded.refs
    fd = loaded.flats["F001"]
    eq, days = R.eq["F001"], C.PERIOD_DAYS
    base = {"resident_excess_kwh": 0.0, "fault_kwh": 0.0, "peak_flexible_kwh": 0.0}
    at = pillars(fd, {**base, "explained_apartment": R.use_bench["apartment"] * eq * days,
                      "explained_resident": R.use_bench["resident"] * eq * days}, R)
    above = pillars(fd, {**base, "explained_apartment": 2 * R.use_bench["apartment"] * eq * days,
                         "explained_resident": 2 * R.use_bench["resident"] * eq * days}, R)
    assert at["apartment"]["use"] == pytest.approx(100.0) and at["resident"]["use"] == pytest.approx(100.0)
    assert abs(above["apartment"]["use"] - 50.0) < 1e-9
    for k in ("waste", "health", "timing"):
        assert at["apartment"][k] == pytest.approx(100.0)


def test_missing_readings_not_treated_as_zero(loaded, ev):
    rng = np.random.default_rng(1)
    fd = loaded.flats["F001"]
    k = fd.kwh.copy()
    k[rng.random(k.shape) < 0.3] = np.nan
    from app.core.pillars import partition
    p1 = partition(fd, None, loaded.anomalies, loaded.refs)
    p2 = partition(fd.with_kwh(k), None, loaded.anomalies, loaded.refs)
    assert abs(p2["total_kwh"] / p1["total_kwh"] - 1) < 0.05            # 30 % zeros would give ~0.70


def test_nan_is_not_zero_in_sums():
    r = pd.DataFrame({"kwh": [1.0, np.nan, 2.0]})
    assert r["kwh"].sum(min_count=1) == 3.0 and r["kwh"].count() == 2


def test_unknown_occupancy_is_not_away(loaded):
    fd = loaded.flats["F007"]
    from app.core.hourly import FlatData
    blind = FlatData(fd.flat_id, fd.residents, fd.floor_area_m2, fd.kwh, fd.price, fd.carbon,
                     fd.occupants * np.nan, fd.outdoor, fd.local_hour)
    assert not unoccupied_cells(blind, 1).any()


def test_heater_excess_only_in_unoccupied_hours(loaded):
    a = loaded.anomaly("HU-F007-A07")
    occ = loaded.flats["F007"].occupants.to_numpy()
    assert (occ[a["cells"]] == 0).all()
    assert abs(a["excess_kwh"] - 9.19) < 0.01


def test_dst_25_october_no_lost_or_duplicated_hours(loaded):
    fd = loaded.flats["F001"]
    assert len(fd.kwh) == C.PERIOD_HOURS and fd.kwh.index.is_unique
    local = (pd.Timestamp(C.PERIOD_START) + pd.to_timedelta(range(C.PERIOD_HOURS), unit="h")).tz_convert(C.TZ_LOCAL)
    oct25 = local[local.strftime("%Y-%m-%d") == "2026-10-25"]
    assert len(oct25) == 25 and (oct25.hour == 2).sum() == 2           # the repeated 02:00 hour is a real hour
    assert (fd.local_hour.to_numpy() == local.hour).all()
    assert fd.carbon.notna().all()


def test_legacy_timestamp_format_is_utc():
    s = parse_utc(pd.Series(["2026-10-25T01:00:00Z", "2026/10/25 01:00"]))
    assert s.iloc[0] == s.iloc[1]


def test_peak_hours_are_data_driven(loaded):
    fd = loaded.flats["F001"]
    by = pd.Series(fd.price.to_numpy()).groupby(fd.local_hour.to_numpy()).mean()
    assert loaded.refs.peak_hours == {h for h, v in by.items() if v > fd.price.mean()} == {7, 8, 9, 17, 18, 19, 20}

import numpy as np
import pandas as pd

from app import config as C
from app.core import metrics, pillars as P
from app.core.evaluate import evaluate
from app.loader import parse_utc


def _all_pillars(ev):
    for lens, t in ev["lenses"].items():
        for k in C.LENSES[lens]:
            yield lens, k, t[k]


def test_pillars_between_0_and_100(ev):
    for lens, k, s in _all_pillars(ev):
        assert s.notna().all(), (lens, k)
        assert ((s >= 0) & (s <= 100)).all(), (lens, k, s.tolist())


def test_pillars_bounded_under_extreme_data(ds):
    r = ds.readings.copy()
    r.loc[r["flat_id"] == "F001", "kwh"] *= 50        # absurdly high flat
    r.loc[r["flat_id"] == "F002", "kwh"] = 0.0        # flat that uses nothing
    ev = evaluate(ds.copy(readings=r), with_sensitivity=False)
    for lens, k, s in _all_pillars(ev):
        v = s.dropna()
        assert ((v >= 0) & (v <= 100)).all(), (lens, k)


def test_flat_at_benchmark_gets_use_100():
    kwh = pd.Series([100.0, 120.0, 150.0, 200.0, 250.0], index=list("ABCDE"))
    residents = pd.Series([1, 1, 1, 1, 1], index=list("ABCDE"))
    x, use, bench = P.use_pillar(kwh, residents, days=1, percentile=0)   # P0 -> bench = A's own x
    assert bench == x["A"]
    assert use["A"] == 100.0
    assert (use.drop("A") < 100).all()
    x, use, bench = P.use_pillar(kwh, residents, days=1, percentile=20)
    assert (use[x <= bench] == 100).all()


def test_missing_readings_not_treated_as_zero(ds, ev):
    rng = np.random.default_rng(1)
    r = ds.readings.copy()
    m = (r["flat_id"] == "F001") & (rng.random(len(r)) < 0.3)
    r.loc[m, "kwh"] = np.nan
    ev2 = evaluate(ds.copy(readings=r), with_sensitivity=False)
    x1 = ev["detail"]["apartment"]["use_x"]["F001"]
    x2 = ev2["detail"]["apartment"]["use_x"]["F001"]
    assert abs(x2 / x1 - 1) < 0.05                    # 30% zeros would give ~0.70
    assert ev2["totals"].loc["F001", "coverage"] < 0.75


def test_nan_is_not_zero_in_sums():
    r = pd.DataFrame({"kwh": [1.0, np.nan, 2.0]})
    assert r["kwh"].sum(min_count=1) == 3.0 and r["kwh"].count() == 2


def test_unknown_occupancy_is_not_away(ds):
    ctx = ds.context.copy()
    ctx.loc[ctx["flat_id"] == "F002", "occupants_home"] = np.nan
    d = ds.copy()
    d.context = ctx
    e = metrics.enrich(d.readings, d.flats, d.prices, d.context)
    assert P.avoidable_away_kwh(e, set())["F002"] == 0


def test_heater_not_waste_unless_confirmed(ds):
    from app.core.claims import Status
    e = metrics.enrich(ds.readings, ds.flats, ds.prices, ds.context)
    before = P.avoidable_away_kwh(e, P.heater_confirmed_flats(ds.anomalies))["F006"]
    for a in ds.anomalies:
        if a["type"] == "heater_pattern":
            a["status"] = Status.CONFIRMED
    after = P.avoidable_away_kwh(e, P.heater_confirmed_flats(ds.anomalies))["F006"]
    assert after >= before


def test_dst_25_october_no_lost_or_duplicated_hours(ds):
    e = metrics.enrich(ds.readings, ds.flats, ds.prices, ds.context)
    per_app = e.groupby("appliance_id")["timestamp_utc"].agg(["count", "nunique"])
    assert (per_app["nunique"] == C.PERIOD_HOURS).all()
    assert (per_app["count"] == per_app["nunique"]).all()
    one = e[e["appliance_id"] == "F001-A01"].copy()
    local = one["timestamp_utc"].dt.tz_convert(C.TZ_LOCAL)
    oct25 = one[local.dt.strftime("%Y-%m-%d") == "2026-10-25"]
    assert len(oct25) == 25                            # the repeated 02:00 hour is a real hour
    assert (local[local.dt.strftime("%Y-%m-%d") == "2026-10-25"].dt.hour == 2).sum() == 2
    assert one["is_peak"].sum() == 28 * len(C.PEAK_HOURS_LOCAL)
    # every reading still joins to exactly one price
    assert e["carbon"].notna().all()


def test_legacy_timestamp_format_is_utc():
    s = parse_utc(pd.Series(["2026-10-25T01:00:00Z", "2026/10/25 01:00"]))
    assert s.iloc[0] == s.iloc[1]

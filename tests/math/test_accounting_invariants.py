"""UNIVERSAL accounting invariants of the quantitative engine (no score formula involved).

Each test names the requirement in docs/math/requirements_spec.md. These must hold for any implementation.
"""
import numpy as np
import pandas as pd
import pytest

from mathcore import (CHANNELS, Op, Trajectory, combine, difference, op_O1_heater_off_unoccupied, op_O2_always_on,
                      op_O3_fridge_repair, op_O4_daytime_electronics, op_O5_dishwasher_shift, op_S1b_heater_setback,
                      per_resident_average, totals)

TOL = 0.006  # values in opportunities.json are rounded to 2 dp (kWh, SEK) / 3 dp (kg)


def central(opps, oid):
    return next(s for s in opps[oid]["scenarios"] if s["role"] == "central")


# ---------------------------------------------------------------- R1 dimensional consistency
def test_R1_units_sek_and_co2_are_kwh_weighted_sums(flats):
    fd = flats["F002"]
    t = totals(fd)
    x, p, c = fd.kwh, fd.price, fd.carbon
    sek = sum(x.loc[h, ch] * p.loc[h] for h in x.index for ch in CHANNELS if pd.notna(x.loc[h, ch]) and pd.notna(p.loc[h]))
    co2 = sum(x.loc[h, ch] * c.loc[h] for h in x.index for ch in CHANNELS if pd.notna(x.loc[h, ch])) / 1000
    assert t["sek_spot_hourly"] == pytest.approx(sek, abs=1e-9)          # [kWh]*[SEK/kWh] = [SEK]
    assert t["co2e_kg"] == pytest.approx(co2, abs=1e-12)                 # [kWh]*[g/kWh]/1000 = [kg]
    assert t["sek_spot_timeavg_proxy"] == pytest.approx(t["kwh"] * fd.price.mean())


# ---------------------------------------------------------------- golden reproduction of validated cases
@pytest.mark.parametrize("oid,flat,make,window", [
    ("O1_F007_heating_unoccupied", "F007", lambda F: [op_O1_heater_off_unoccupied(F["F007"])], (0, 672)),
    ("O2_F005_elevated_base_load", "F005", lambda F: [op_O2_always_on(F["F005"], theta=0.5)], (0, 672)),
    ("O3_F002_refrigerator_step", "F002", lambda F: [op_O3_fridge_repair(F["F002"])], (336, 672)),
    ("O4_F004_daytime_electronics", "F004", lambda F: [op_O4_daytime_electronics(F["F004"], F)], (0, 672)),
])
def test_validated_reduction_cases_reproduce(flats, opportunities, oid, flat, make, window):
    fd = flats[flat]
    cf, _ = combine(fd.kwh, make(flats))
    d = difference(fd, fd.kwh, cf, window=window)
    c = central(opportunities, oid)
    assert d["kwh"] == pytest.approx(c["kwh"], abs=TOL)
    assert d["sek_spot_hourly"] == pytest.approx(c["value_spot_hourly_sek"], abs=TOL)
    assert d["co2e_kg"] == pytest.approx(c["co2e_kg"], abs=0.0006)
    assert d["sek_spot_timeavg_proxy"] == pytest.approx(c["value_spot_timeavg_sek"], abs=TOL)


def test_validated_dishwasher_shift_reproduces_fleet_and_per_flat(flats, opportunities):
    c = central(opportunities, "O5_dishwasher_price_timing")
    per_flat = opportunities["O5_dishwasher_price_timing"]["observed_evidence"]["central_saving_per_flat_spot_sek_28d"]
    sek = co2 = 0.0
    for fl, fd in flats.items():
        cf, _ = combine(fd.kwh, [op_O5_dishwasher_shift(fd)])
        d = difference(fd, fd.kwh, cf)
        assert d["sek_spot_hourly"] == pytest.approx(per_flat[fl], abs=TOL)
        sek += d["sek_spot_hourly"]; co2 += d["co2e_kg"]
    assert sek == pytest.approx(c["value_spot_hourly_sek"], abs=TOL)
    assert co2 == pytest.approx(c["co2e_kg"], abs=0.0006)


# ---------------------------------------------------------------- R9 load shifting
def test_R9_shift_conserves_energy_per_channel_and_total(flats):
    for fl, fd in flats.items():
        cf, logs = combine(fd.kwh, [op_O5_dishwasher_shift(fd)])
        assert np.nansum(cf.delta.values) == pytest.approx(0.0, abs=1e-12)
        assert totals(fd, cf)["kwh"] == pytest.approx(totals(fd)["kwh"], abs=1e-12)
        for ch in CHANNELS:
            assert cf.delta[ch].sum() == pytest.approx(0.0, abs=1e-12)


def test_R9_shift_value_equals_price_difference_and_tariff_rules(flats):
    fd = flats["F002"]
    op = op_O5_dishwasher_shift(fd)
    cf, _ = combine(fd.kwh, [op])
    expected = sum(fd.kwh.A04[h0] * (fd.price[h0] - fd.price[h1]) for h0, h1 in op.moves)
    d = difference(fd, fd.kwh, cf)
    assert d["sek_spot_hourly"] == pytest.approx(expected, abs=1e-12)
    assert d["kwh"] == pytest.approx(0.0, abs=1e-12)
    assert d["sek_spot_timeavg_proxy"] == pytest.approx(0.0, abs=1e-12)  # non-hourly tariff: shifting is worth 0


def test_R9_R3_shift_into_missing_hour_neither_loses_nor_invents_energy(flats):
    fd = flats["F007"]  # two F007 runs move into hours whose A04 reading is missing
    cf, logs = combine(fd.kwh, [op_O5_dishwasher_shift(fd)])
    assert logs[0]["moved_into_missing_hour"] == 2
    assert cf.base.isna().equals(fd.kwh.isna())                    # no missing reading was filled
    assert totals(fd, cf)["kwh"] == pytest.approx(totals(fd)["kwh"], abs=1e-12)
    view = fd.with_trajectory(cf)                                  # what a score model receives
    assert view.kwh.isna().equals(fd.kwh.isna())
    assert float(view.extra.values.sum()) > 0
    assert totals(view)["kwh"] == pytest.approx(totals(fd)["kwh"], abs=1e-12)


# ---------------------------------------------------------------- R3 missing observations
def test_R3_reductions_never_touch_missing_cells(flats):
    fd = flats["F002"]
    cf, logs = combine(fd.kwh, [op_O3_fridge_repair(fd)])
    miss = fd.kwh.A01.loc[336:].isna()
    assert logs[0]["skipped_missing"] == int(miss.sum()) == 4
    assert (cf.delta.A01.loc[336:][miss] == 0).all()


def test_R3_totals_exclude_missing_rather_than_zero_fill_window_vs_observed(flats):
    fd = flats["F002"]
    obs = totals(fd, window=(336, 672), channels=["A01"])
    assert obs["observed_cells"] == 332 and obs["window_hours"] == 336


# ---------------------------------------------------------------- R5 no double counting
def test_R5_disjoint_interventions_add_exactly(flats):
    fd = flats["F002"]
    ops = [op_O3_fridge_repair(fd), op_O5_dishwasher_shift(fd)]
    both = difference(fd, fd.kwh, combine(fd.kwh, ops)[0])
    parts = [difference(fd, fd.kwh, combine(fd.kwh, [o])[0]) for o in ops]
    for k in ("kwh", "sek_spot_hourly", "co2e_kg"):
        assert both[k] == pytest.approx(sum(p[k] for p in parts), abs=1e-9)


def test_R5_overlapping_interventions_do_not_double_count(flats):
    fd = flats["F007"]
    a, b = op_O1_heater_off_unoccupied(fd), op_S1b_heater_setback(fd)
    both = difference(fd, fd.kwh, combine(fd.kwh, [a, b])[0])["kwh"]
    naive = sum(difference(fd, fd.kwh, combine(fd.kwh, [o])[0])["kwh"] for o in (a, b))
    assert both < naive
    assert naive - both == pytest.approx(2.54, abs=0.01)          # overlap measured in math_review (22 shared cells)
    assert both <= totals(fd, channels=["A07"])["kwh"]              # cannot save more than was used


def test_R5_combination_order_is_fixed_and_proportional_ops_commute(flats):
    fd = flats["F002"]
    ops = [op_O5_dishwasher_shift(fd), op_O3_fridge_repair(fd)]
    a = combine(fd.kwh, ops)[0].delta
    b = combine(fd.kwh, list(reversed(ops)))[0].delta
    pd.testing.assert_frame_equal(a, b)
    f1 = Op("10%", "fraction", "A06", list(range(672)), phi=0.10)
    f2 = Op("20%", "fraction", "A06", list(range(672)), phi=0.20)
    x = combine(fd.kwh, [f1, f2])[0].delta.A06
    y = combine(fd.kwh, [f2, f1])[0].delta.A06
    assert np.allclose(x, y)
    obs = fd.kwh.A06.notna()
    assert np.allclose(-x[obs], fd.kwh.A06[obs] * (1 - 0.9 * 0.8))  # combined = 1 - prod(1 - phi_i), not sum


def test_R5_counterfactual_never_negative(flats):
    for fl, fd in flats.items():
        cf, _ = combine(fd.kwh, [Op(f"all {c}", "fraction", c, list(range(672)), phi=1.0) for c in CHANNELS])
        assert (cf.effective().fillna(0) >= -1e-12).all().all()


# ---------------------------------------------------------------- R2 quantity ladder E >= A >= S >= 0
def test_R2_measured_excess_ge_avoidable_ge_counterfactual(flats):
    fd = flats["F007"]
    E = difference(fd, fd.kwh, combine(fd.kwh, [op_O1_heater_off_unoccupied(fd, min_absence_h=1)])[0])["kwh"]
    A = difference(fd, fd.kwh, combine(fd.kwh, [op_O1_heater_off_unoccupied(fd, min_absence_h=2)])[0])["kwh"]
    S = difference(fd, fd.kwh, combine(fd.kwh, [op_O1_heater_off_unoccupied(fd, min_absence_h=2, rebound=0.25)])[0])["kwh"]
    assert E >= A >= S >= 0
    assert (round(E, 2), round(A, 2), round(S, 2)) == (23.27, 9.19, 6.89)
    fd = flats["F005"]
    E = difference(fd, fd.kwh, combine(fd.kwh, [op_O2_always_on(fd, theta=1.0)])[0])["kwh"]
    A = difference(fd, fd.kwh, combine(fd.kwh, [op_O2_always_on(fd, theta=0.5)])[0])["kwh"]
    assert E >= A >= 0 and A == pytest.approx(E / 2)


# ---------------------------------------------------------------- R8 per-flat and per-resident
def test_R8_average_per_resident_is_labelled_and_reconstructs_flat_total(flats):
    for fl, fd in flats.items():
        t = totals(fd)["kwh"]
        avg = per_resident_average(t, fd.residents)
        assert avg["value"] * fd.residents == pytest.approx(t)
        assert "not measured per person" in avg["label"]


# ---------------------------------------------------------------- R10 explicit periods / R11 determinism
def test_R10_window_restricts_accounting(flats):
    fd = flats["F002"]
    cf, _ = combine(fd.kwh, [op_O3_fridge_repair(fd)])
    assert difference(fd, fd.kwh, cf, window=(0, 336))["kwh"] == pytest.approx(0.0, abs=1e-12)
    assert difference(fd, fd.kwh, cf, window=(336, 672))["kwh"] == pytest.approx(difference(fd, fd.kwh, cf)["kwh"])


def test_R11_deterministic(flats):
    fd = flats["F004"]
    a = combine(fd.kwh, [op_O4_daytime_electronics(fd, flats)])[0].delta
    b = combine(fd.kwh, [op_O4_daytime_electronics(fd, flats)])[0].delta
    pd.testing.assert_frame_equal(a, b)
    assert Trajectory.of(fd.kwh).delta.abs().sum().sum() == 0

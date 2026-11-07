"""Money and carbon for a change in hourly energy, per tariff. Spot energy component only (excl. VAT, network fee,
energy tax, markup, fixed fees) - never a bill saving.

  hourly_spot           sum_h dkWh_h * spot_h                (exact, time-specific; unpriced hours reported)
  monthly_average_spot  dkWh * time-average spot              (reductions only; a shift is worth 0)
  fixed_price           dkWh * student's own price            (reductions only; needs the price; a shift is worth 0)
  included_in_rent      0 SEK to the student (the provider pays; provider's tariff unknown -> kWh only)
  unknown               SEK not stated; 'if hourly spot' value given separately
kgCO2e = sum_h dkWh_h * g_h / 1000 with the synthetic hourly operational factor (average, not marginal).
"""
from __future__ import annotations

TARIFFS = ("hourly_spot", "monthly_average_spot", "fixed_price", "included_in_rent", "unknown")
MONEY_LABEL = "spot-energy component only (excl. VAT, network fee, energy tax, markup, fixed fees); not a bill saving"


def value(delta: dict, kind: str, tariff: dict | None = None) -> dict:
    """delta: saving = baseline - counterfactual (kwh, sek_spot_hourly, sek_spot_timeavg_proxy, co2e_kg)."""
    tariff = tariff or {"type": "unknown"}
    t = tariff.get("type", "unknown")
    if t not in TARIFFS:
        raise ValueError(f"tariff type must be one of {TARIFFS}")
    shift = kind == "shift"
    fixed = tariff.get("fixed_price_sek_per_kwh")
    by = {
        "hourly_spot": delta["sek_spot_hourly"],
        "monthly_average_spot": 0.0 if shift else delta["sek_spot_timeavg_proxy"],
        "fixed_price": 0.0 if shift else (delta["kwh"] * fixed if fixed is not None else None),
        "included_in_rent": 0.0,
    }
    if t == "fixed_price" and fixed is None:
        raise ValueError("fixed_price tariff needs fixed_price_sek_per_kwh")
    return {
        "tariff": t, "sek": None if t == "unknown" else by[t], "sek_if_hourly_spot": delta["sek_spot_hourly"],
        "sek_by_tariff": by, "label": MONEY_LABEL,
        "note": ("load shifting changes cost only on an hourly spot contract" if shift else
                 "electricity included in rent: the student saves 0 SEK; the provider's saving depends on its contract"),
    }

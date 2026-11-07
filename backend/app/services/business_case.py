"""Business-case calculator. Every input is explicit; price per flat is a hypothesis."""
from __future__ import annotations

from ..core.claims import Status


def calculate(flats: int, price_per_flat_sek_per_year: float, faults_per_flat_per_year: float,
              avg_fault_kwh: float, marginal_tariff_sek_per_kwh: float, who_pays_electricity: str) -> dict:
    if who_pays_electricity not in ("landlord", "tenant"):
        raise ValueError("who_pays_electricity must be 'landlord' or 'tenant'")
    cost = flats * price_per_flat_sek_per_year
    avoided_kwh = flats * faults_per_flat_per_year * avg_fault_kwh
    avoided_sek = avoided_kwh * marginal_tariff_sek_per_kwh
    landlord_gain = avoided_sek if who_pays_electricity == "landlord" else 0.0
    tenant_gain = avoided_sek - landlord_gain
    return {
        "label": "projection",
        "horizon": "annual",
        "inputs": {
            "flats": flats,
            "price_per_flat_sek_per_year": {"value": price_per_flat_sek_per_year, "label": "hypothesis"},
            "faults_per_flat_per_year": faults_per_flat_per_year,
            "avg_fault_kwh": avg_fault_kwh,
            "marginal_tariff_sek_per_kwh": marginal_tariff_sek_per_kwh,
            "who_pays_electricity": who_pays_electricity,
        },
        "yearly_cost_sek": cost,
        "avoided_kwh": avoided_kwh,
        "avoided_cost_sek": avoided_sek,
        "landlord_net_sek": landlord_gain - cost,
        "tenant_gain_sek": tenant_gain,
        "break_even_price_per_flat_sek": avoided_sek / flats if flats else None,
        "assumptions": [
            "price per flat is a hypothesis, not a quote",
            "fault rate and size are user inputs; engine reference values come from 28 days of synthetic data",
            "marginal tariff should include all variable parts (spot, network, tax, VAT) the payer avoids",
            "fixed fees do not change",
        ],
    }


def engine_reference(findings: list[dict], n_flats: int) -> dict:
    """Reference values measured by the engine, shown NEXT to the inputs (never auto-filled)."""
    faults = [f for f in findings if f["responsibility"] == "manager" and f["status_level"] >= Status.PLAUSIBLE]
    kwh = [f["projection_annual"]["kwh"]["value"] for f in faults]
    return {
        "label": "engine reference (synthetic data)",
        "plausible_faults_in_28d": len(faults),
        "flats": n_flats,
        "faults_per_flat_28d": len(faults) / n_flats if n_flats else None,
        "avg_projected_fault_kwh_per_year": sum(kwh) / len(kwh) if kwh else None,
        "assumptions": ["28 days of October synthetic data", "fault kWh projected as if not repaired for a year"],
    }

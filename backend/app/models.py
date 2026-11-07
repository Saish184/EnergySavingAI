"""Request bodies (Pydantic). Responses are plain JSON built by app.state (see docs/data_contract.md)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ScenarioRequest(BaseModel):
    scenario: Literal["return_to_baseline", "shift_flexible_load", "reduce_away_usage"]
    params: dict = Field(default_factory=dict,
                         examples=[{"anomaly_id": "AN001"}, {"channel": "A04"}, {"fraction": 0.5}])


class ReportRequest(BaseModel):
    message: str | None = None


class WorkOrderCreate(BaseModel):
    finding_id: str
    note: str | None = None


class WorkOrderPatch(BaseModel):
    status: Literal["sent", "repaired"] | None = None
    fault_found: bool | None = Field(None, description="technician outcome: true -> CONFIRMED, false -> dismissed")


class PostReading(BaseModel):
    timestamp_utc: str
    kwh: float | None


class VerifyRequest(BaseModel):
    post_readings: list[PostReading] | None = None
    simulate: bool = False


class BusinessCaseInput(BaseModel):
    flats: int = Field(gt=0)
    price_per_flat_sek_per_year: float = Field(ge=0, description="HYPOTHESIS")
    faults_per_flat_per_year: float = Field(ge=0)
    avg_fault_kwh: float = Field(ge=0)
    marginal_tariff_sek_per_kwh: float = Field(ge=0)
    who_pays_electricity: Literal["landlord", "tenant"]

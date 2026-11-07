from __future__ import annotations

from fastapi import APIRouter

from ..services.live_prices import today_prices

router = APIRouter(tags=["prices"])


@router.get("/prices/today")
def prices_today(hourly_contract: bool = False):
    """Live SE3 prices, only when the user says they have an hourly contract."""
    return today_prices(hourly_contract)

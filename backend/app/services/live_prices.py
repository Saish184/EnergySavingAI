"""Today's SE3 spot prices from elprisetjustnu.se. Only shown for hourly/spot contracts.
Never substitutes October dataset prices for 'today'."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import requests

from .. import config as C

_cache: dict[str, dict] = {}
UNAVAILABLE = "live prices unavailable"


def today_prices(hourly_contract: bool, today: dt.date | None = None) -> dict:
    if not hourly_contract:
        return {"shown": False, "message": "Live prices only matter on an hourly (spot) contract. "
                                           "On a fixed or monthly contract, timing does not change your bill."}
    today = today or dt.datetime.now(ZoneInfo(C.TZ_LOCAL)).date()
    key = today.isoformat()
    if key in _cache:
        return _cache[key]
    url = C.LIVE_PRICE_URL.format(y=today.year, m=f"{today.month:02d}", d=f"{today.day:02d}")
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        rows = r.json()
        prices = [{"start": p["time_start"], "end": p["time_end"], "sek_per_kwh": p["SEK_per_kWh"]} for p in rows]
        if not prices:
            raise ValueError("empty")
        cheapest = min(prices, key=lambda p: p["sek_per_kwh"])
        out = {"shown": True, "date": key, "area": "SE3", "source": "elprisetjustnu.se", "label": "live",
               "prices": prices, "cheapest": cheapest,
               "note": "spot price excl. VAT, network fee and energy tax"}
        _cache[key] = out
        return out
    except Exception:
        return {"shown": False, "date": key, "message": UNAVAILABLE}

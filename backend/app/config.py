"""All tunable numbers in one place. Change here, never inline."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # repo root
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
MOCK_DIR = ROOT / "data" / "mock"
OUT_DIR = ROOT / "out"

# minimal .env support (no extra dependency); real environment variables win
_env = ROOT / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        if "=" in _line and not _line.lstrip().startswith("#"):
            _k, _v = _line.split("=", 1)
            if _v.strip():
                os.environ.setdefault(_k.strip(), _v.strip().strip('"'))

# "auto" = teammate's processed/ files if both exist, else mock. Or force "mock" / "processed".
DATA_SOURCE = os.getenv("FEC_DATA_SOURCE", "auto")

TZ_LOCAL = "Europe/Stockholm"
PERIOD_START = "2026-10-01T00:00:00Z"
PERIOD_END = "2026-10-29T00:00:00Z"                  # exclusive
PERIOD_HOURS = 672
PERIOD_DAYS = 28

CHANNELS = [f"A{i:02d}" for i in range(1, 8)]

# ASSUMPTIONS: channels are unlabelled in the dataset. These labels are guesses from load shape.
ASSUMED_TYPES = {
    "A01": "fridge-like",
    "A04": "dishwasher-like",
    "A07": "heater-like",
}
ASSUMED_TYPE_DEFAULT = "unlabelled channel"
HEATER_CHANNELS = {"A07"}
FLEXIBLE_CHANNELS = {"A04"}                          # default channels offered for load shifting

# Local peak hours (hour-of-day start, Europe/Stockholm): 07-09 and 17-20
PEAK_HOURS_LOCAL = {7, 8, 17, 18, 19}
NIGHT_HOURS_LOCAL = {0, 1, 2, 3, 4, 5}

# Claims
PLAUSIBLE_MIN_CONFIDENCE = 0.7
PLAUSIBLE_MIN_DAYS = 3.0

# Pillars
USE_BENCH_PERCENTILE = 20
BASELOAD_PERCENTILE = 10
WASTE_FULL_PENALTY_SHARE = 0.5                       # avoidable/total of 50% -> WASTE 0
HEALTH_FAULT_MULTIPLIER = 2.0                        # fault share of 50% -> HEALTH 0

# Score lenses (weights sum to 1)
LENSES = {
    "apartment": {"use": 0.40, "waste": 0.25, "timing": 0.20, "health": 0.15},
    "resident": {"use": 0.50, "waste": 0.30, "timing": 0.20},
}
LENS_LABELS = {
    "apartment": "Apartment Performance",
    "resident": "Resident Actions",
}
BANDS = [(90, "A"), (80, "B"), (70, "C"), (55, "D"), (40, "E"), (20, "F"), (0, "G")]

# Sensitivity
SENS_DRAWS = 2000
SENS_CONCENTRATION = 20
SENS_SEED = 0

# Scenarios
SHIFT_WINDOW_HOURS = 12
AWAY_REDUCTION_DEFAULT = 0.5

# Projection
ANNUAL_FACTOR = 365 / 28
ANNUAL_FACTOR_HEATER = 182 / 28                      # heating season only
PROJECTION_BAND = 0.30
BOOTSTRAP_DRAWS = 1000
BOOTSTRAP_SEED = 0
PROJECTION_BASE_ASSUMPTIONS = [
    "October data only",
    "spot price only, excludes network fee, energy tax, VAT",
    "synthetic dataset; not evidence of real-world savings",
]

# Verification
VERIFY_MIN_DAYS = 7
VERIFY_INTERVAL = (5, 95)                           # 90% interval

# LLM
LLM_MODEL = "claude-sonnet-5-5"

# Live prices
LIVE_PRICE_URL = "https://www.elprisetjustnu.se/api/v1/prices/{y}/{m}-{d}_SE3.json"

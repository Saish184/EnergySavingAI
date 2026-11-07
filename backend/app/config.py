"""All tunable numbers in one place, each with its justification. Change here, never inline.

Constants removed in the mathematical revision (and why) are listed in docs/engine_changes.md:
WASTE_FULL_PENALTY_SHARE, HEALTH_FAULT_MULTIPLIER, BASELOAD_PERCENTILE, PEAK_HOURS_LOCAL (now data-driven),
PROJECTION_BAND.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # repo root
RAW_DIR = ROOT                                       # organiser files stay at the repo root (preserved, hash-checked)
PROCESSED_DIR = ROOT / "data" / "processed"          # validated pipeline output (analysis/clean_data.py)
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

# "auto" = validated pipeline output if present, else mock. Or force "mock" / "processed".
DATA_SOURCE = os.getenv("FEC_DATA_SOURCE", "auto")

TZ_LOCAL = "Europe/Stockholm"
PERIOD_START = "2026-10-01T00:00:00Z"
PERIOD_END = "2026-10-29T00:00:00Z"                  # exclusive
PERIOD_HOURS = 672
PERIOD_DAYS = 28

CHANNELS = [f"A{i:02d}" for i in range(1, 8)]

# ---------------------------------------------------------------- appliance assumptions (student-confirmable)
# Channels are unlabelled in the dataset; labels are inferred from load shape (reports/opportunity_report.md §3).
ASSUMED_TYPES = {
    "A01": "fridge-like", "A02": "cooking-like", "A03": "washing-machine-like", "A04": "dishwasher-like",
    "A05": "electronics-like", "A06": "lighting/standby-like", "A07": "heater-like",
}
ASSUMED_TYPE_DEFAULT = "unlabelled channel"
HEATER_CHANNELS = {"A07"}            # weather-driven (hourly r with outdoor temperature -0.88 / -1.00)
EQUIPMENT_CHANNELS = {"A01"}         # cold appliance: a lasting step change is treated as possible equipment fault
FLEXIBLE_CHANNELS = {"A03", "A04"}   # discrete one-hour runs whose start time a person chooses (washer, dishwasher)

# A channel is "continuous" (always-on) if it is non-zero in most hours across the fleet. The data are bimodal
# (0 % zero hours for A01/A05/A06 vs 78-97 % for the others), so any cut between 0.05 and 0.75 gives the same split.
CONTINUOUS_MAX_ZERO_SHARE = 0.5

# ---------------------------------------------------------------- peak hours (data-driven)
# Peak = local hours whose mean spot price exceeds the period's time-average spot price. On this dataset that is
# {7, 8, 9, 17, 18, 19, 20} (0.83-0.93 SEK/kWh vs <= 0.32 otherwise). Used only if prices are missing:
PEAK_HOURS_FALLBACK = {7, 8, 9, 17, 18, 19, 20}
NIGHT_HOURS_LOCAL = {0, 1, 2, 3, 4, 5}

# ---------------------------------------------------------------- detection (statistical criteria)
DETECTION_ALPHA = 0.01               # family-wise error for the step-change permutation test (all splits)
PERMUTATIONS = 999                   # p resolution 0.001; seeded below
PERMUTATION_SEED = 0
MIN_SEGMENT_DAYS = 3                 # shortest pre/post segment; also the persistence needed for PLAUSIBLE
MIN_HOURS_PER_DAY = 12               # a day mean needs >= half the day observed
MIN_ABSENCE_HOURS = 2                # heater: shortest absence a person can realistically act on (1 h = upper bound)
MIN_EVIDENCE_DAYS = 3                # behaviour patterns must occur on >= 3 distinct days

# Claims (engine can only assign DETECTED or PLAUSIBLE; people confirm)
PLAUSIBLE_MIN_DAYS = 3.0

# ---------------------------------------------------------------- scores
USE_BENCH_PERCENTILE = 20            # USE benchmark = P20 of the flats at BASELINE (frozen)
EQUIVALENCE_EXPONENT = 0.5           # OECD square-root equivalence scale (external convention; data elasticity 0.24-0.33)
LENSES = {
    "apartment": {"use": 0.40, "waste": 0.25, "timing": 0.20, "health": 0.15},
    "resident": {"use": 0.50, "waste": 0.30, "timing": 0.20},
}
LENS_LABELS = {"apartment": "Apartment Performance", "resident": "Resident Actions"}
BANDS = [(90, "A"), (80, "B"), (70, "C"), (55, "D"), (40, "E"), (20, "F"), (0, "G")]

# Sensitivity of the composite to the (policy) weights
SENS_DRAWS = 2000
SENS_CONCENTRATION = 20
SENS_SEED = 0

# ---------------------------------------------------------------- scenarios
SHIFT_WINDOW_HOURS = 12              # a run may be delayed at most 12 h
QUIET_HOURS_LOCAL: set[int] = set()  # student preference; empty = no restriction (validated default: start 21:00)
AWAY_REDUCTION_DEFAULT = 0.5

# ---------------------------------------------------------------- uncertainty / projection
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 0
ANNUAL_DAYS = 365
PROJECTION_BASE_ASSUMPTIONS = [
    "extrapolation of 4 October weeks: assumes the pattern persists unchanged",
    "spot price only, excludes network fee, energy tax, VAT",
    "synthetic dataset; not evidence of real-world savings",
]
# Only persistent, weather-independent patterns are extrapolated; heating and timing are not (weather / price).
PROJECTABLE_TYPES = {"fault_step_change", "base_load_outlier", "scheduled_block"}

# Verification
VERIFY_MIN_DAYS = 7
VERIFY_INTERVAL = (5, 95)            # 90% interval

# LLM
LLM_MODEL = "claude-sonnet-5-5"

# Live prices
LIVE_PRICE_URL = "https://www.elprisetjustnu.se/api/v1/prices/{y}/{m}-{d}_SE3.json"

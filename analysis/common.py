"""Shared paths, constants and appliance-label assumptions for the analysis pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = {
    "readings": ROOT / "energy_readings.csv",
    "flats": ROOT / "flats.csv",
    "context": ROOT / "hourly_context.csv",
    "prices": ROOT / "hourly_prices.csv",
}
ORIGINAL_FILES = [
    "energy_readings.csv", "flats.csv", "hourly_context.csv",
    "hourly_prices.csv", "README.md", "DATA_DICTIONARY.md",
]
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"

TZ_LOCAL = "Europe/Stockholm"
PERIOD_START_UTC = "2026-10-01T00:00:00Z"   # inclusive
N_HOURS = 672                              # 28 days; end 2026-10-29T00:00Z exclusive
N_FLATS = 8
N_CHANNELS = 7

# Physical plausibility ceiling for a single appliance/circuit in one hour.
# Largest credible observed value is 1.30 kWh; the smallest rejected value is 10.8 kWh.
SPIKE_THRESHOLD_KWH = 5.0

# Appliance categories are NOT supplied by the dataset. These labels are inferred
# from load signatures (see reports/data_quality_report.md section "Appliance inference")
# and must be presented as assumptions.
APPLIANCE_LABELS = {
    "A01": "Cold appliance (fridge/freezer)",
    "A02": "Cooking (hob/oven)",
    "A03": "Washing machine",
    "A04": "Dishwasher",
    "A05": "Personal electronics & charging",
    "A06": "Lighting & entertainment",
    "A07": "Portable electric heater",
}
APPLIANCE_EVIDENCE = {
    "A01": "Never zero; flat ~50-60 W around the clock with no daily cycle.",
    "A02": "~0.77 kWh single-hour events clustered at 07, 12 and 18-19 local (meal times); more on weekends.",
    "A03": "~0.67 kWh isolated single-hour events at varied daytime/evening hours, ~1 per 2-3 days per flat.",
    "A04": "~0.89 kWh single-hour events; all 108 valid events start at exactly 20:00 local (scheduled programme).",
    "A05": "4 W standby 08:00-16:59 local in 7 of 8 flats; ~35 W 17-20 and ~65 W 21:00-07:59; scales with occupants home (0 home: 0.010, 5 home: 0.085 kWh/h).",
    "A06": "33 W always-on floor plus 110-120 W evening peak 17:00-23:00 local.",
    "A07": "Only F001/F007 use it; hourly correlation with outdoor temperature r = -0.88 (F001) and -1.00 (F007); 39-46 % of its energy falls 00:00-05:59.",
}
SHIFTABLE = {"A03", "A04"}  # assumption: delay-start possible; others treated as not shiftable

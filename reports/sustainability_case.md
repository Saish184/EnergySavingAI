# Sustainability case (generated from the engine)

_`python analysis/sustainability_case.py`, references hash `a0b4475d31be9674`. Synthetic data: the figures demonstrate the method, not real-world savings._

## 1. Observed (measured, 28 days)

8 flats, 25 residents, 2026-10-01..2026-10-28 (28 days, UTC): **1,904.5 kWh**, **1,010.71 SEK** (spot-energy component only, not a bill), **73.06 kg CO₂e** (synthetic average factors).

## 2. What acting on the findings could change (simulated by the engine)

Each group is applied together on each flat's hourly data (no double counting); flats are then summed. Windows: 28 observed days, except the F002 fault (14 days, from its start).

| Group | Who acts | kWh avoided | SEK if hourly spot | SEK if monthly average | kg CO₂e |
|---|---|---:|---:|---:|---:|
| Equipment repair | building manager | 23.36 | 11.54 | 11.16 | 0.771 |
| Behaviour: always-on, fixed-hour, heating while away | residents | 86.28 | 40.40 | 41.22 | 3.205 |
| Timing: washer/dishwasher after the peak | residents | 0.00 (shift: same kWh) | 83.19 | 0.00 | 2.336 |
| **All findings** | | **109.65** | **135.13** | 52.38 | **6.313** |

kWh avoided = 5.8 % of observed portfolio use (windows of 14–28 days, so this is indicative). Shifting saves money only on an hourly spot contract and saves **0 kWh**; its CO₂e effect comes from the destination hours' factors. With electricity included in rent a student saves 0 SEK.

## 3. Per finding

| Finding | Flat | Who | Kind | Window | kWh avoided | kWh moved | SEK hourly spot (95 % range) | kg CO₂e | Annual |
|---|---|---|---|---:|---:|---:|---|---:|---|
| Always-on load above other flats (lighting/standby-like (inferred)) | F005 | residents (behaviour) | reduction | 28 d | 62.79 | 0.00 | 29.46 (26.72–32.22) | 2.338 | 819 kWh (814–824), 384 SEK |
| Sudden lasting increase (fridge-like (inferred)) | F002 | building manager (equipment) | reduction | 14 d | 23.36 | 0.00 | 11.54 (9.95–13.11) | 0.771 | 609 kWh (601–618), 301 SEK |
| Runs in expensive peak hours (dishwasher-like (inferred)) | F001 | residents (behaviour) | shift | 28 d | 0.00 | 13.60 | 9.86 (5.38–15.78) | 0.238 | not extrapolated |
| Runs in expensive peak hours (dishwasher-like (inferred)) | F007 | residents (behaviour) | shift | 28 d | 0.00 | 12.21 | 8.70 (4.87–13.54) | 0.213 | not extrapolated |
| Runs in expensive peak hours (dishwasher-like (inferred)) | F005 | residents (behaviour) | shift | 28 d | 0.00 | 12.00 | 8.53 (4.77–13.27) | 0.207 | not extrapolated |
| Runs in expensive peak hours (dishwasher-like (inferred)) | F003 | residents (behaviour) | shift | 28 d | 0.00 | 11.15 | 7.80 (4.16–12.23) | 0.197 | not extrapolated |
| Runs in expensive peak hours (washing-machine-like (inferred)) | F005 | residents (behaviour) | shift | 28 d | 0.00 | 9.44 | 6.70 (3.24–11.61) | 0.182 | not extrapolated |
| Runs in expensive peak hours (dishwasher-like (inferred)) | F002 | residents (behaviour) | shift | 28 d | 0.00 | 12.94 | 6.48 (3.94–9.02) | 0.212 | not extrapolated |
| Runs in expensive peak hours (dishwasher-like (inferred)) | F008 | residents (behaviour) | shift | 28 d | 0.00 | 12.28 | 6.09 (3.68–8.47) | 0.203 | not extrapolated |
| Runs in expensive peak hours (dishwasher-like (inferred)) | F004 | residents (behaviour) | shift | 28 d | 0.00 | 12.06 | 5.98 (3.63–8.38) | 0.205 | not extrapolated |
| Runs in expensive peak hours (dishwasher-like (inferred)) | F006 | residents (behaviour) | shift | 28 d | 0.00 | 11.39 | 5.79 (3.42–8.23) | 0.182 | not extrapolated |
| Runs in expensive peak hours (washing-machine-like (inferred)) | F003 | residents (behaviour) | shift | 28 d | 0.00 | 7.80 | 5.78 (2.53–9.80) | 0.154 | not extrapolated |
| Heater-like use while nobody is home (heater-like (inferred)) | F007 | needs confirmation (heating) | reduction | 28 d | 9.19 | 0.00 | 5.65 (1.68–10.32) | 0.375 | not extrapolated |
| Device running at fixed hours, also when nobody is home (electronics-like (inferred)) | F004 | residents (behaviour) | reduction | 28 d | 14.30 | 0.00 | 5.29 (4.83–5.78) | 0.492 | 186 kWh (183–189), 69 SEK |
| Runs in expensive peak hours (washing-machine-like (inferred)) | F001 | residents (behaviour) | shift | 28 d | 0.00 | 6.09 | 4.60 (1.87–8.47) | 0.126 | not extrapolated |
| Runs in expensive peak hours (washing-machine-like (inferred)) | F008 | residents (behaviour) | shift | 28 d | 0.00 | 6.62 | 3.70 (1.73–5.77) | 0.123 | not extrapolated |
| Runs in expensive peak hours (washing-machine-like (inferred)) | F002 | residents (behaviour) | shift | 28 d | 0.00 | 6.33 | 3.18 (1.46–5.04) | 0.094 | not extrapolated |

## 4. Annual projections (only where the data supports one)

Supported for persistent equipment / always-on / fixed-hour patterns only: BL-F005-A06, FS-F002-A01, SB-F004-A05. Central values sum to **1,614 kWh**, **754 SEK** (hourly spot) and **57.0 kg CO₂e** per year, assuming the October pattern persists unchanged; sum of central projections for persistent patterns only; the per-item p5-p95 ranges are not additive.

Not extrapolated: heating while away (weather-dependent) and timing shifts (price-dependent). Four autumn weeks cannot establish their annual effect; rebound effects are only covered by the stated scenario ranges.

## 5. Per resident (defensible allocation)

Resident-controlled actions are shared household actions. The table shows each flat's combined resident-controlled potential and its average per resident of **that flat**. It is not divided across all 25 students, and equipment repairs are not attributed to residents.

| Flat | Residents | kWh (flat) | SEK hourly spot (flat) | kg CO₂e (flat) | kWh per resident (avg) | SEK per resident (avg) |
|---|---:|---:|---:|---:|---:|---:|
| F001 | 2 | 0.00 | 14.45 | 0.365 | 0.00 | 7.23 |
| F002 | 3 | 0.00 | 9.66 | 0.306 | 0.00 | 3.22 |
| F003 | 4 | 0.00 | 13.58 | 0.351 | 0.00 | 3.40 |
| F004 | 2 | 14.30 | 11.27 | 0.697 | 7.15 | 5.63 |
| F005 | 5 | 62.79 | 44.68 | 2.727 | 12.56 | 8.94 |
| F006 | 3 | 0.00 | 5.79 | 0.182 | 0.00 | 1.93 |
| F007 | 4 | 9.19 | 14.35 | 0.588 | 2.30 | 3.59 |
| F008 | 2 | 0.00 | 9.80 | 0.326 | 0.00 | 4.90 |

## 6. Assumptions and uncertainty

- Appliance identities are inferred from load shapes (no labels in the data).
- “Avoidable” is a simulation if the household acts fully (adoption 1); each finding also has an assumption range (e.g. F005 15.7–62.8 kWh) and a 95 % day-bootstrap range.
- Findings are statistical patterns (PLAUSIBLE), not confirmed faults or confirmed waste; a technician or resident confirms.
- SEK is the spot-energy component only (excl. VAT, network fees, energy tax, markup, fixed fees), conditional on the contract.
- Carbon uses the synthetic operational hourly factor (not marginal or lifecycle).
- Occupancy is a simulated sensor estimate; missing readings are excluded, never treated as zero.

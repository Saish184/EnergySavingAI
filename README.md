# AI for Energy Saving — participant dataset

Entirely synthetic, fictional Swedish student flats. No personal data. Created for this hackathon; free to use, modify and redistribute. Not real meter, Nord Pool, weather or emissions observations and not calibrated to a representative Swedish population.

## Included files

| File | Contents | Rows |
|---|---|---:|
| energy_readings.csv | Hourly appliance/circuit energy readings | 37,715 |
| flats.csv | Resident counts, floor areas and price areas | 8 |
| hourly_context.csv | Weather, indoor temperature and estimated occupancy | 5,376 |
| hourly_prices.csv | Synthetic spot prices and carbon factors | 672 |

See DATA_DICTIONARY.md for column definitions. The four CSV files contain 43,771 rows in total.

## Start here
1. Open energy_readings.csv and flats.csv. Choose one flat or appliance_id first.
2. Profile missing values, units, identifiers and duplicated records before calculating totals. Zero can mean an appliance was off; missing does not mean zero.
3. Join readings to flats on flat_id, context on flat_id + timestamp_utc, and prices on timestamp_utc + the flat's price_area. Check join cardinality and identifier consistency before aggregating.
4. Build an actionable recommendation and explain its estimated kWh, SEK and CO2e effects and uncertainty.

There are eight flats, 25 residents, 56 appliances and 672 hourly intervals, from 2026-10-01 00:00 UTC inclusive to 2026-10-29 00:00 UTC exclusive. Rows are intentionally imperfect and not sorted. UTF-8 comma-separated CSV with quoted fields where needed. Do not let an importer silently replace invalid data with zeros.

Each energy reading is energy consumed in the one-hour interval beginning at timestamp_utc, not instantaneous power or a cumulative register. Seven mutually exclusive appliance/circuit channels cover the modeled electricity of each flat. No appliance lookup is included, so appliance_id is an identifier without a supplied type, rated power or shiftability label. Any inferred appliance type or scheduling constraint must be stated as an assumption. No total-meter channel is included: do not invent one as independent validation.

Main district heating and hot water are excluded, as are campus rooms, EV charging, bills/images and nudge experiments. Portable heaters are supplementary electricity. Hourly data supports energy coaching and load timing, but not high-frequency appliance identification. Occupancy is a simulated sensor estimate, not personal tracking.

## Time and prices
Canonical timestamps are UTC. A legacy export may use YYYY/MM/DD HH:MM (still UTC). Local timestamps include offsets for Europe/Stockholm; the repeated clock hour on 25 October is legitimate. Join and measure elapsed time using UTC.

Prices are synthetic hourly scenario inputs, not the format or granularity of a live market feed. Negative spot prices are valid. spot_sek_per_kwh excludes VAT. No tariff table is included; tariff_id in flats.csv is a retained reference with no matching lookup in this package.

Spot-energy cost (SEK, excluding VAT) = kWh × spot_sek_per_kwh, summed across intervals after cleaning and unit conversion. This is only the spot-price component, not a full electricity bill. Retailer markup, network fees, energy tax, VAT and fixed fees are not supplied; any full-bill estimate needs separately stated assumptions or sources. Fixed fees do not disappear when consumption is reduced.

Carbon kgCO2e = kWh × carbon_gco2e_per_kwh / 1000; this is a synthetic operational factor, not lifecycle or marginal emissions.

Moving a load can reduce cost without reducing kWh. Carbon savings depend on the destination hour's factor. Respect practical schedules and appliance constraints. Comparing flats requires resident counts, floor areas and occupancy context. Four autumn weeks do not establish annual savings: state seasonal assumptions, uncertainty and rebound effects explicitly. Synthetic factors are suitable for a demo, not evidence for real-world savings claims.

Suggested starting questions: Which flat has potentially avoidable overnight electricity use? Which consumption peaks coincide with expensive hours? Which changes appear to be equipment faults rather than corrupt readings? How should a recommendation handle missing occupancy or price information?

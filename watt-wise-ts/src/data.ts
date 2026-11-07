import type {
  ChannelDef,
  DataSourceRow,
  Flat,
  Limitation,
  MaintenanceAlert,
  Recommendation,
  ScoreComponent,
} from './types';

/**
 * PLACEHOLDER DATA. Replace with output from the CSV analysis.
 * Hours are UTC, matching the dataset. Prices and carbon are approximate
 * hour-of-day averages in the style of hourly_prices.csv.
 */
export const DAYS = 28; // 2026-10-01 to 2026-10-28 inclusive

/** kWh per hour for a 2-resident flat (placeholder). */
export const BASE_PROFILE: readonly number[] = [
  0.14, 0.12, 0.12, 0.11, 0.13, 0.28, 0.38, 0.3, 0.22, 0.2, 0.19, 0.21, 0.24, 0.22, 0.23, 0.34,
  0.52, 0.66, 0.58, 0.46, 0.38, 0.3, 0.22, 0.17,
];

/** SEK/kWh, excluding VAT. */
export const PRICE: readonly number[] = [
  0.35, 0.37, 0.38, 0.38, 0.38, 0.85, 0.88, 0.85, 0.35, 0.3, 0.3, 0.25, 0.3, 0.3, 0.3, 0.88, 0.95,
  0.9, 0.88, 0.33, 0.33, 0.33, 0.3, 0.38,
];

/** gCO2e/kWh, synthetic operational factor. */
export const CARBON: readonly number[] = [
  33, 32, 31, 32, 33, 52, 53, 52, 33, 31, 31, 31, 30, 31, 31, 50, 52, 48, 50, 34, 35, 34, 33, 32,
];

/** Resident counts and areas are from flats.csv. nightExtraKwh is a placeholder. */
export const FLATS: readonly Flat[] = [
  { id: 'F001', residents: 2, areaM2: 56, priceArea: 'SE3', tariffId: 'T01', nightExtraKwh: 0.0 },
  { id: 'F002', residents: 3, areaM2: 69, priceArea: 'SE3', tariffId: 'T01', nightExtraKwh: 0.03 },
  { id: 'F003', residents: 4, areaM2: 82, priceArea: 'SE3', tariffId: 'T01', nightExtraKwh: 0.1 },
  { id: 'F004', residents: 2, areaM2: 56, priceArea: 'SE3', tariffId: 'T01', nightExtraKwh: 0.02 },
  { id: 'F005', residents: 5, areaM2: 95, priceArea: 'SE3', tariffId: 'T01', nightExtraKwh: 0.04 },
  { id: 'F006', residents: 3, areaM2: 69, priceArea: 'SE3', tariffId: 'T01', nightExtraKwh: 0.0 },
  { id: 'F007', residents: 4, areaM2: 82, priceArea: 'SE3', tariffId: 'T01', nightExtraKwh: 0.05 },
  { id: 'F008', residents: 2, areaM2: 56, priceArea: 'SE3', tariffId: 'T01', nightExtraKwh: 0.01 },
];

/** Seven channels per flat. The data has no appliance type, so labels stay generic. */
export const CHANNELS: readonly ChannelDef[] = [
  { id: 'ch-1', label: 'Channel 1', share: 0.24 },
  { id: 'ch-2', label: 'Channel 2', share: 0.18 },
  { id: 'ch-3', label: 'Channel 3', share: 0.16 },
  { id: 'ch-4', label: 'Channel 4', share: 0.14 },
  { id: 'ch-5', label: 'Channel 5', share: 0.12 },
  { id: 'ch-6', label: 'Channel 6', share: 0.1 },
  { id: 'ch-7', label: 'Channel 7', share: 0.06 },
];

export const RECOMMENDATIONS: readonly Recommendation[] = [
  {
    id: 'rec-shift',
    tag: 'shift',
    title: 'Run movable appliances after 19:00 UTC',
    body: 'The late-afternoon price peak is among the costliest windows of the day. Moving a laundry or dishwasher cycle later keeps the same kWh but can cost less.',
    confidence: 'medium',
    evidence: [
      {
        kind: 'from-data',
        source: 'hourly_prices.csv',
        claim:
          'Spot prices peak twice a day, around 05–07 UTC and 15–18 UTC. On most days the 15–18 UTC window is among the costliest.',
      },
      {
        kind: 'from-data',
        source: 'hourly_prices.csv',
        claim:
          'On 20 Oct 2026 the 15–18 UTC prices were about 2.6–2.7 SEK/kWh, far above the usual evening level.',
      },
      {
        kind: 'placeholder',
        source: 'energy_readings.csv',
        claim: 'This flat’s own load in 15–18 UTC: [to be computed from cleaned readings].',
      },
    ],
    assumptions: [
      'Appliance types are not labelled, so which channels can move is an assumption.',
      'The moved load keeps the same kWh; only timing changes.',
    ],
  },
  {
    id: 'rec-waste',
    tag: 'waste',
    title: 'Check what keeps running overnight',
    body: 'A steady draw while the flat sleeps can mean standby devices, a heater left on or a fridge working hard. A smart plug or a quick walk-round would tell.',
    confidence: 'medium',
    evidence: [
      {
        kind: 'placeholder',
        source: 'energy_readings.csv',
        claim: 'Overnight (00–04 UTC) load per channel: [pending analysis].',
      },
      {
        kind: 'placeholder',
        source: 'hourly_context.csv',
        claim: 'Load while occupants_home is low: [pending analysis].',
      },
    ],
    assumptions: [
      'Overnight use is treated as avoidable only until someone checks it on site.',
      'Occupancy is a simulated estimate, not a measurement of people.',
    ],
  },
  {
    id: 'rec-check',
    tag: 'check',
    title: 'One channel may have changed its pattern',
    body: 'If a channel steps to a new level and stays there, it may be equipment rather than bad data. We flag it for a person to look at, never as a diagnosis.',
    confidence: 'low',
    evidence: [
      {
        kind: 'placeholder',
        source: 'energy_readings.csv',
        claim: 'Step change that persists across days: [pending analysis].',
      },
    ],
    assumptions: [
      'A persistent change could be equipment or behaviour. Only an inspection can tell.',
      'Unit mix-ups (Wh vs kWh) and duplicate records must be ruled out first.',
    ],
  },
];

export const SCORE_COMPONENTS: readonly ScoreComponent[] = [
  { id: 'sc-night', label: 'Overnight baseload', note: 'Definition pending' },
  { id: 'sc-peak', label: 'Peak-hour exposure', note: 'Definition pending' },
  { id: 'sc-per-person', label: 'Load per resident', note: 'Definition pending' },
  { id: 'sc-data', label: 'Data completeness', note: 'Definition pending' },
];

export const LIMITATIONS: readonly Limitation[] = [
  {
    title: 'Spot price only',
    body: 'Costs use spot_sek_per_kwh excluding VAT. Retailer markup, network fees, energy tax, VAT and fixed fees are not in the data, so these figures are not a bill.',
  },
  {
    title: 'No tariff table',
    body: 'flats.csv keeps a tariff_id (T01) but no lookup comes with the data, so tariff-specific advice cannot be given.',
  },
  {
    title: 'No whole-flat meter',
    body: 'Seven channels per flat make up the modelled electricity. There is no total meter to cross-check against.',
  },
  {
    title: 'Appliance types unknown',
    body: 'appliance_id has no type, rated power or shiftability label. Ideas like "this looks like a dishwasher" are assumptions.',
  },
  {
    title: 'Short, synthetic window',
    body: 'Four autumn weeks (1–28 Oct 2026) of synthetic data. No annual claims, and rebound effects are not modelled.',
  },
  {
    title: 'Heating and hot water excluded',
    body: 'District heating and hot water are outside the electricity scope. Portable heaters count as supplementary electricity.',
  },
  {
    title: 'Occupancy is simulated',
    body: 'occupants_home is a simulated sensor estimate, used as context only, not as ground truth about people.',
  },
  {
    title: 'Times are UTC',
    body: 'Stockholm local time is UTC+2 until the clocks change on 25 October, then UTC+1. The repeated clock hour that night is legitimate.',
  },
];

/** Sample alerts. Flats and channels are arbitrary placeholders, not findings. */
export const ALERTS: readonly MaintenanceAlert[] = [
  {
    id: 'al-1',
    flatId: 'F003',
    channelId: 'ch-4',
    title: 'Persistent overnight draw',
    hypothesis:
      'Hypothesis: equipment left on, stuck or faulty. Could also be a standby load that is simply normal.',
    checks: [
      'Confirm the draw persists across weeks, not single nights',
      'Cross-check against occupants_home',
      'Rule out data errors (units, duplicate records)',
      'Inspect the appliance on site',
    ],
    owner: 'Data team validates · Property manager inspects',
    evidence: [
      {
        kind: 'placeholder',
        source: 'energy_readings.csv',
        claim: 'Overnight level of this channel versus its own history: [pending analysis].',
      },
    ],
  },
  {
    id: 'al-2',
    flatId: 'F005',
    channelId: 'ch-2',
    title: 'Step change in level',
    hypothesis:
      'Hypothesis: a change in equipment or use that stays at a new level. Not proven to be a fault.',
    checks: [
      'Find the date of the step and check it is real',
      'Ask the residents whether something changed',
      'Inspect only if the level stays high',
    ],
    owner: 'Data team validates · Property manager follows up',
    evidence: [
      {
        kind: 'placeholder',
        source: 'energy_readings.csv',
        claim: 'Date and size of the step: [pending analysis].',
      },
    ],
  },
  {
    id: 'al-3',
    flatId: 'F001',
    channelId: 'ch-6',
    title: 'Load while nobody seems to be home',
    hypothesis:
      'Hypothesis: something runs while the flat is empty. Occupancy is simulated, so this may be a false alarm.',
    checks: [
      'Compare with occupants_home over several days',
      'Treat occupancy as a hint only',
      'Check with residents before anyone enters the flat',
    ],
    owner: 'Data team validates · Resident confirms',
    evidence: [
      {
        kind: 'placeholder',
        source: 'hourly_context.csv',
        claim: 'Hours with occupants_home = 0 and load above baseline: [pending analysis].',
      },
    ],
  },
];

export const DATA_SOURCES: readonly DataSourceRow[] = [
  {
    file: 'energy_readings.csv',
    issues: 'Repeated reading_id, mixed Wh and kWh, a legacy timestamp format, possible missing values.',
    handling: 'Deduplicate, convert to kWh, parse to UTC, keep gaps as gaps (missing is not zero).',
    owner: 'Data team',
    status: 'Audit pending',
  },
  {
    file: 'hourly_prices.csv',
    issues: 'Some hours have no spot price. Negative prices are valid.',
    handling: 'Never fill with zero. Flag affected hours and mark their costs as incomplete.',
    owner: 'Data team',
    status: 'Gaps seen in file, count pending',
  },
  {
    file: 'hourly_context.csv',
    issues: 'Occupancy is a simulated sensor estimate.',
    handling: 'Use as context only. Never present it as tracking of people.',
    owner: 'Data team',
    status: 'Audit pending',
  },
  {
    file: 'flats.csv',
    issues: 'tariff_id has no lookup. No whole-flat meter channel.',
    handling: 'Spot cost only. No full-bill estimate without a supplied tariff.',
    owner: 'Property manager supplies tariff',
    status: 'Limitation, not a defect',
  },
];

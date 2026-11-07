/**
 * Response and request types of the FastAPI backend (mina). Hand-written from the real responses in
 * fixtures/ and docs/api_examples/ and from backend/app/state.py. The backend is the only source of numbers:
 * these types describe what it sends; the UI only formats them.
 *
 * Units: energy kWh, money SEK (spot energy component only, never a bill), carbon kg CO2e.
 * Timestamps: ISO strings in UTC. Local presentation uses Europe/Stockholm (see format.ts).
 * Nullable fields are null when the backend does not state a value (e.g. a projection that is not extrapolated).
 */

export type Lens = 'apartment' | 'resident';
export type Tariff = 'hourly_spot' | 'monthly_average_spot' | 'fixed_price' | 'included_in_rent' | 'unknown';
export type FindingType =
  | 'fault_step_change'
  | 'base_load_outlier'
  | 'scheduled_block'
  | 'heater_pattern'
  | 'peak_usage';
export type FindingStatus = 'DETECTED' | 'PLAUSIBLE' | 'CONFIRMED' | 'REPAIRED' | 'VERIFIED' | (string & {});
export type Responsibility = 'manager' | 'resident' | 'unknown';
export type ScenarioName = 'return_to_baseline' | 'shift_flexible_load' | 'reduce_away_usage' | 'apply_interventions';
export type SavingKind = 'reduction' | 'shift' | 'mixed';

export interface FlatMeta {
  flat_id: string;
  residents: number;
  floor_area_m2: number;
  price_area: string;
}

export interface Health {
  ok: boolean;
  data_source: string;
  flats: number;
  findings: number;
  data_quality: Record<string, unknown>;
}

/* ---------- breakdown ---------- */
export interface BreakdownTotals {
  kwh: number;
  sek: number;
  co2_kg: number;
  kwh_per_resident: number;
  sek_per_resident: number;
  co2_kg_per_resident: number;
  kwh_per_m2: number;
  peak_share: number | null;
  coverage: number;
  price_coverage: number | null;
  residents: number;
  floor_area_m2: number;
  kwh_coverage_adjusted: number | null;
}

export interface ChannelRow {
  appliance_id: string;
  channel: string;
  kwh: number;
  sek: number;
  co2_kg: number;
  hours_observed: number;
  coverage: number;
  share_of_flat: number | null;
  peak_share: number | null;
  assumed_type: string;
  assumed_type_is_assumption: boolean;
  flexible: boolean;
  heater_like: boolean;
}

export interface Breakdown {
  flat_id: string;
  horizon: string;
  status: string;
  totals: BreakdownTotals;
  per_resident_label: string;
  channels: ChannelRow[];
  /** UTC days. Prefer Profile.daily (local dates) for display. */
  daily: { day: string; kwh: number; sek: number; co2_kg: number }[];
  assumptions: string[];
  uncertainty: { coverage: number; price_coverage: number | null; note: string };
}

/* ---------- local profile (additive endpoint GET /flats/{id}/profile) ---------- */
export interface ProfileHour {
  local_hour: number;
  hours_in_period: number;
  mean_kwh: number | null;
  mean_kwh_by_channel: Record<string, number | null>;
  observed_share: number | null;
  mean_spot_sek_per_kwh: number | null;
  mean_carbon_g_per_kwh: number | null;
  is_peak: boolean;
}

export interface ProfileDay {
  local_date: string;
  hours_in_period: number;
  complete_day: boolean;
  kwh: number;
  sek: number;
  co2_kg: number;
  observed_share: number;
}

export interface Profile {
  flat_id: string;
  timezone: string;
  peak_hours_local: number[];
  time_avg_price_sek_per_kwh: number;
  period_utc: { start: string; end_exclusive: string };
  hour_of_day: ProfileHour[];
  daily: ProfileDay[];
  assumptions: string[];
}

/* ---------- scores ---------- */
export interface Pillars {
  use: number;
  waste: number;
  timing: number;
  health?: number;
}

export interface LensView {
  label: string;
  score: number;
  band: string;
  arithmetic_mean: number;
  rank: number;
  of: number;
  pillars: Pillars;
  weights: Record<string, number>;
  sensitivity: { score_p5: number; score_p95: number; rank_p5: number; rank_p95: number; draws: number };
  responsibility: string;
  excludes: string[];
}

export interface Scores {
  flat_id: string;
  horizon: string;
  status: string;
  lenses: Record<Lens, LensView>;
  benchmark: {
    metric: string;
    flat_value: number;
    benchmark_value: number;
    flat_value_resident_lens: number;
    benchmark_value_resident_lens: number;
    percentile: number;
    frozen: boolean;
    references_hash: string;
  };
  partition_kwh: Record<string, number>;
  pillar_detail: { possible_avoidable_kwh: number; possible_fault_kwh: number; peak_flexible_kwh: number };
  assumptions: string[];
  uncertainty: { method: string; data_coverage: number };
}

/* ---------- findings ---------- */
export interface ProjectionItem {
  label: string;
  horizon: string;
  unit: string;
  assumptions: string[];
  value: number | null;
  low: number | null;
  high: number | null;
  factor: string | null;
  reason?: string | null;
  range_method?: string;
}
export interface ProjectionTriplet {
  kwh: ProjectionItem;
  sek: ProjectionItem;
  co2_kg: ProjectionItem;
}

export interface Valuation {
  tariff: Tariff;
  sek: number | null;
  sek_if_hourly_spot: number;
  sek_by_tariff: Partial<Record<Tariff, number | null>>;
  label: string;
  note: string;
}

export interface LadderItem {
  kind: 'reduction' | 'shift';
  anomaly_id: string;
  params: Record<string, unknown>;
  window_hours: number;
  observed_hours: number;
  observed_kwh: number;
  expected_baseline_kwh: number;
  unexplained_excess_kwh: number;
  avoidable_estimate_kwh: number;
  counterfactual_kwh: number;
  kwh_moved: number;
  unexplained_excess_upper_kwh?: number;
  labels: Record<string, string>;
}

/** Saving ranges. Positive = saving. Keys follow the engine (sek_spot_hourly, co2e_kg). */
export interface SavingRange {
  kwh: [number, number];
  sek_spot_hourly: [number, number];
  co2e_kg: [number, number];
}

export interface Uncertainty {
  sampling_ci95: SavingRange & { method: string };
  scenario_range: SavingRange | null;
  scenario_method: string;
  evidence: Record<string, { status: string; stats: Record<string, unknown> }>;
  not_included: string[];
}

export interface Finding {
  id: string;
  flat_id: string;
  appliance_id: string;
  channel: string;
  assumed_type: string;
  assumed_type_is_assumption: boolean;
  type: FindingType;
  title: string;
  status: FindingStatus;
  status_level: number;
  wording: string;
  responsibility: Responsibility;
  responsibility_note: string;
  counts_as: string;
  window: { start: string; end: string; days: number };
  evidence: {
    text: string;
    statistics: Record<string, unknown>;
    confidence: null;
    confidence_note: string;
    baseline_kwh_per_h: number | null;
    observed_kwh_per_h: number | null;
    reported_excess_kwh: number | null;
  };
  quantities: LadderItem;
  avoidable_28d: {
    kwh: number;
    sek: number;
    co2_kg: number;
    horizon: string;
    window_days: number;
    label: string;
    scenario: string;
    method: string;
    kind: 'reduction' | 'shift';
  };
  valuation: Valuation;
  score_if_fixed: Record<Lens, { before: number; after: number }>;
  projection_annual: ProjectionTriplet;
  assumptions: string[];
  uncertainty: Uncertainty & { detector_confidence: null; projection_range_sek: [number | null, number | null] };
  tiers: {
    potential: { kwh: number; sek_if_hourly_spot: number; co2_kg: number };
    estimated_realized: unknown;
    estimated_realized_reason: string;
    verified: number | null;
    verified_reason: string;
  };
  verification: Verification | null;
  simulated: boolean;
}

export interface Tip {
  finding_id: string;
  flat_id: string;
  status: string;
  wording: string;
  responsibility: Responsibility;
  text: string;
  source: 'llm' | 'template' | (string & {});
  horizon: string;
  assumptions: string[];
}

/* ---------- scenarios ---------- */
export interface ScoreSnapshot {
  score: number;
  band: string;
  rank: number;
  pillars: Pillars;
}

export interface ScenarioResponse {
  scenario: ScenarioName;
  params: Record<string, unknown>;
  flat_id: string;
  label: string;
  horizon: string;
  /** Change in the flat's consumption: NEGATIVE = saving. kWh is 0 for a pure shift. */
  delta_28d: { kwh: number; sek: number; co2_kg: number };
  before: Record<Lens, ScoreSnapshot>;
  after: Record<Lens, ScoreSnapshot>;
  score_change: Record<Lens, number>;
  projection_annual: ProjectionTriplet;
  assumptions: string[];
  items: { anomaly_id: string; type: FindingType; params: Record<string, unknown> }[];
  /** Absent when the scenario had nothing to apply (see assumptions for the reason). */
  kind?: SavingKind;
  window?: { start_utc: string; end_utc_exclusive: string; days: number };
  ladder?: LadderItem[];
  valuation?: Valuation;
  uncertainty?: Uncertainty;
  overlap?: { kwh: number; sek_spot_hourly: number; sek_spot_timeavg_proxy: number; co2e_kg: number };
  missing_hour_moves?: number;
}

export interface TariffSpec {
  type: Tariff;
  fixed_price_sek_per_kwh?: number;
}

export interface InterventionOptions {
  scenarios: ScenarioName[];
  tariffs: Tariff[];
  tariff_requirements: Record<string, string[]>;
  parameters: Record<FindingType, Record<string, { default: unknown; grid: unknown[] }>>;
  common_parameters: Record<string, unknown>;
  kind: Record<FindingType, 'reduction' | 'shift'>;
}

/* ---------- portfolio ---------- */
export interface CombinedPotential {
  findings: string[];
  kwh: number;
  sek_if_hourly_spot: number;
  co2_kg: number;
  overlap_kwh: number;
  score_after: Record<Lens, ScoreSnapshot>;
  label: string;
}

export interface PortfolioFlat {
  flat_id: string;
  residents: number;
  floor_area_m2: number;
  apartment_score: number;
  apartment_band: string;
  apartment_rank: number;
  resident_score: number;
  resident_band: string;
  health: number;
  open_findings: number;
  open_manager_findings: number;
  kwh_28d: number;
  sek_28d: number;
  co2_kg_28d: number;
  coverage: number;
  comparison: {
    explained_kwh_per_eq_resident_day: number;
    kwh_per_m2: number;
    heater_kwh: number;
    possible_fault_kwh: number;
    possible_avoidable_kwh: number;
  };
  combined_potential: CombinedPotential | null;
}

export interface Portfolio {
  horizon: string;
  status: string;
  data_source: string;
  flats: PortfolioFlat[];
  totals: { kwh: number; sek: number; co2_kg: number };
  potential: { kwh: number; sek_if_hourly_spot: number; co2_kg: number; label: string };
  maintenance: {
    finding_id: string;
    flat_id: string;
    status: string;
    wording: string;
    evidence: string;
    excess_kwh_per_day: number;
    potential_kwh: number;
    window_days: number;
  }[];
  data_quality: {
    coverage_by_flat: Record<string, number>;
    data_source: string;
    readings_missing_kwh?: number;
    readings_rows?: number;
    prices_missing_spot_hours?: number;
    context_occupancy_missing?: number;
    context_outdoor_missing?: number;
    [k: string]: unknown;
  };
  evidence_quality: { findings_by_status: Record<string, number>; note: string };
  references: References;
  assumptions: string[];
}

export interface References {
  peak_hours_local: number[];
  equivalence_exponent: number;
  eq_residents: Record<string, number>;
  use_bench_kwh_per_eq_resident_day: Record<Lens, number>;
  K_kwh_per_eq_resident_day: number;
  K_T_kwh_per_eq_resident_day: number;
  use_bench_percentile: number;
  time_avg_price_sek_per_kwh: number;
  hash: string;
}

/* ---------- work orders, reports, notifications ---------- */
export interface Verification {
  simulated: boolean;
  status: string;
  saving_kwh: number | null;
  saving_kwh_per_day?: number;
  interval_90: [number, number] | null;
  post_hours: number;
  post_days: number;
  reason?: string;
  [k: string]: unknown;
}

export interface WorkOrderRaw {
  id: string;
  finding_id: string;
  flat_id: string;
  appliance_id: string;
  status: string;
  note: string | null;
  verification: Verification | null;
  [k: string]: unknown;
}

export interface ReportRaw {
  id: string;
  flat_id: string;
  finding_id: string;
  message: string | null;
  status: string;
}

export interface NotificationRaw {
  kind: string;
  text: string;
  status?: string;
  finding_id?: string;
  workorder_id?: string;
  report_id?: string;
  flat_id?: string;
}

export interface VerifyResponse {
  workorder: WorkOrderRaw;
  verification: Verification;
  finding: Finding;
}

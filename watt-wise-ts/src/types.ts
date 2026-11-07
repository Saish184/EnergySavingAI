export type ViewId = 'student' | 'manager';

/** Who is signed in. Students are identified by flat only; managers by email. */
export type Session = { role: 'student'; flatId: string } | { role: 'manager'; email: string };

export type Tariff = 'hourly_spot' | 'monthly_average_spot' | 'included_in_rent';

/* ---------- shapes returned by the backend (docs/api_for_frontend.md). The UI only displays them. ---------- */

export interface Claim {
  placeholder: string;
  value: number | number[] | string;
  unit: string;
  category: string;
  period: string | null;
  tariff: string | null;
  source: string;
}

export interface Text<O = unknown> {
  status: 'ok' | 'safe_fallback' | 'unavailable';
  source: 'llm' | 'template' | 'safe' | null;
  provider: string | null;
  model: string | null;
  prompt_version: string;
  output: O | null;
  claims: Claim[];
  validation: { passed: boolean } | null;
  llm_status: string;
  disclaimer: string;
}

export interface StudentOut { headline: string; explanation: string; action: string; question: string; cta: 'report' | 'try' | 'confirm' | 'none' }
export interface ManagerOut { headline: string; summary: string; evidence_points: string[]; suggested_check: string }
export interface DigestOut { headline: string; bullets: string[]; encouragement: string }
export interface ExplainerOut { summary: string; strongest_pillar: string; weakest_pillar: string; next_step: string }
export interface PortfolioOut { headline: string; bullets: string[]; maintenance_note: string }

export interface Lens {
  label: string;
  score: number;
  band: string;
  rank: number;
  of: number;
  pillars: Record<string, number>;
  sensitivity: { score_p5: number; score_p95: number; rank_p5: number; rank_p95: number };
  excludes: string[];
}

export interface Scores {
  flat_id: string;
  lenses: { apartment: Lens; resident: Lens };
  benchmark: { flat_value_resident_lens: number; benchmark_value_resident_lens: number };
  explainer?: Text<ExplainerOut>;
}

export interface Finding {
  id: string;
  flat_id: string;
  appliance_id: string;
  assumed_type: string;
  type: string;
  title: string;
  status: string;
  wording: string;
  responsibility: 'manager' | 'resident' | 'unknown';
  responsibility_note: string;
  counts_as: string;
  window: { start: string; end: string; days: number };
  evidence: { text: string; statistics: Record<string, unknown>; confidence: null };
  quantities: { kind: string; observed_kwh: number; unexplained_excess_kwh: number; avoidable_estimate_kwh: number; kwh_moved: number };
  avoidable_28d: { kwh: number; sek: number; co2_kg: number; window_days: number; label: string; kind: 'reduction' | 'shift'; horizon: string };
  valuation: { sek_by_tariff: Record<string, number | null>; label: string; note?: string };
  uncertainty: { sampling_ci95: Record<string, number[] | string>; scenario_range: Record<string, number[]> };
  projection_annual: { sek: { value: number | null; low: number | null; high: number | null; reason?: string } };
  score_if_fixed: Record<string, { before: number; after: number }>;
  tiers: { estimated_realized: unknown; estimated_realized_reason: string; verified: number | null; verified_reason: string };
  simulated: boolean;
  student_text?: Text<StudentOut>;
  manager_text?: Text<ManagerOut>;
  triage?: { maintenance: boolean; priority: string; action_owner: string; reason: string };
}

export interface Breakdown {
  totals: { kwh: number; sek: number; co2_kg: number; kwh_per_resident: number; peak_share: number; coverage: number; residents: number; floor_area_m2: number };
  channels: { channel: string; assumed_type: string; kwh: number; sek: number; share_of_flat: number }[];
  daily: { day: string; kwh: number; sek: number }[];
  per_resident_label: string;
}

export interface PortfolioFlat {
  flat_id: string; residents: number; floor_area_m2: number; apartment_score: number; apartment_band: string; apartment_rank: number;
  resident_score: number; resident_band: string; health: number; open_findings: number; open_manager_findings: number;
  kwh_28d: number; sek_28d: number; co2_kg_28d: number; coverage: number;
  comparison: { kwh_per_m2: number; possible_fault_kwh: number; possible_avoidable_kwh: number };
  combined_potential: { kwh: number; sek_if_hourly_spot: number } | null;
}

export interface Portfolio {
  flats: PortfolioFlat[];
  totals: { kwh: number; sek: number; co2_kg: number };
  potential: { kwh: number; sek_if_hourly_spot: number; co2_kg: number; label: string };
  evidence_quality: { findings_by_status: Record<string, number>; note: string };
}

export interface WorkOrder { id: string; finding_id: string; flat_id: string; status: string; fault_found: boolean | null }

export interface ScenarioResult {
  delta_28d: { kwh: number; sek: number; co2_kg: number };
  valuation: { tariff: string; sek: number | null; sek_by_tariff: Record<string, number | null> };
  before: Record<string, { score: number; band: string }>;
  after: Record<string, { score: number; band: string }>;
  kind: string;
  window: { days: number };
}

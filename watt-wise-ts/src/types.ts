export type ViewId = 'student' | 'manager';

/** Who is signed in. Students are identified by flat only; managers by email. */
export type Session = { role: 'student'; flatId: string } | { role: 'manager'; email: string };
export type ScenarioId = 'shift-evening' | 'trim-overnight';
export type AlertStatus = 'open' | 'inspection-scheduled' | 'confirmed' | 'dismissed';

/** Where a piece of evidence comes from. Placeholders must never look like findings. */
export type EvidenceKind = 'from-data' | 'placeholder';

export interface Flat {
  id: string;
  residents: number;
  areaM2: number;
  priceArea: string;
  tariffId: string;
  /** Placeholder extra overnight load (kWh/hour) so flats differ in the demo. */
  nightExtraKwh: number;
}

export interface ChannelDef {
  id: string;
  label: string;
  /** Placeholder share of a flat's total load. */
  share: number;
}

export interface Totals {
  kwh: number;
  sek: number;
  co2kg: number;
}

/** `low` and `high` are changes (after minus before); negative means a reduction. */
export interface Projection {
  before: Totals;
  low: Totals;
  high: Totals;
}

export interface ScenarioState {
  id: ScenarioId;
  sharePct: number;
}

export interface EvidenceItem {
  kind: EvidenceKind;
  source: string;
  claim: string;
}

export interface Recommendation {
  id: string;
  tag: 'shift' | 'waste' | 'check';
  title: string;
  body: string;
  confidence: 'low' | 'medium';
  evidence: EvidenceItem[];
  assumptions: string[];
}

export interface MaintenanceAlert {
  id: string;
  flatId: string;
  channelId: string;
  title: string;
  hypothesis: string;
  checks: string[];
  owner: string;
  evidence: EvidenceItem[];
}

export interface ScoreComponent {
  id: string;
  label: string;
  note: string;
}

export interface DataSourceRow {
  file: string;
  issues: string;
  handling: string;
  owner: string;
  status: string;
}

export interface Limitation {
  title: string;
  body: string;
}

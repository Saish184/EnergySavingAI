import type { AlertStatus, ScenarioState, Session } from './types';

export interface AppState {
  session: Session | null;
  /** The flat the student view shows. Set from the student session at sign-in. */
  flatId: string;
  scenario: ScenarioState;
  /** Share of flats that adopt the scenario in the manager's portfolio estimate. */
  adoptionPct: number;
  alertStatus: Record<string, AlertStatus>;
}

export const state: AppState = {
  session: null,
  flatId: 'F001',
  scenario: { id: 'shift-evening', sharePct: 30 },
  adoptionPct: 50,
  alertStatus: {},
};

export function alertStatusOf(id: string): AlertStatus {
  return state.alertStatus[id] ?? 'open';
}

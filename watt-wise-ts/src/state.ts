import type { Session, Tariff } from './types';

export interface AppState {
  session: Session | null;
  /** The flat the student view shows. Set from the student session at sign-in. */
  flatId: string;
  /** The student's contract: only selects which engine-computed value is shown. */
  tariff: Tariff;
}

export const state: AppState = {
  session: null,
  flatId: 'F001',
  tariff: 'hourly_spot',
};

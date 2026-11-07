import type { Api } from './api/client';
import type { TariffSpec } from './api/contracts';
import type { AppConfig } from './config';
import type { Session } from './types';

export interface AppState {
  session: Session | null;
  config: AppConfig | null;
  api: Api | null;
  /** The student's electricity contract: a condition on money figures (never changes kWh or CO2e). */
  tariff: TariffSpec;
}

const TARIFF_KEY = 'wattwise.tariff';

export const state: AppState = {
  session: null,
  config: null,
  api: null,
  tariff: loadTariff(),
};

function loadTariff(): TariffSpec {
  try {
    const raw = typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(TARIFF_KEY);
    const t = raw ? (JSON.parse(raw) as TariffSpec) : null;
    if (t && typeof t.type === 'string') return t;
  } catch {
    /* storage blocked: default below */
  }
  return { type: 'unknown' };
}

export function setTariff(t: TariffSpec): void {
  state.tariff = t;
  try {
    sessionStorage.setItem(TARIFF_KEY, JSON.stringify(t));
  } catch {
    /* ignore */
  }
}

export function api(): Api {
  if (!state.api) throw new Error('API not initialised');
  return state.api;
}

import type { AppConfig } from '../config';
import { LiveApi, type Api } from './client';
import { browserLoader, MockApi } from './mock';

export * from './client';
export type * from './contracts';

/** The single place where live or mock data is chosen. Screens receive an Api and never know which. */
export function createApi(config: AppConfig, flatHeader: () => string | null): Api {
  if (config.mode === 'mock') return new MockApi(browserLoader(config.fixturesBase));
  return new LiveApi({ baseUrl: config.apiBase, timeoutMs: config.timeoutMs, flatHeader });
}

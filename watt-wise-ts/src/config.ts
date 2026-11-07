/**
 * Runtime configuration. Defaults come from config.js (window.WATTWISE_CONFIG); the URL can override them
 * for a demo: ?mode=mock  or  ?mode=live&api=http://localhost:8000
 * There is no automatic fallback from live to mock: if the backend is down, the app says so.
 */
export type DataMode = 'live' | 'mock';

export interface AppConfig {
  mode: DataMode;
  apiBase: string;
  fixturesBase: string;
  timeoutMs: number;
}

export const DEFAULT_CONFIG: AppConfig = {
  mode: 'live',
  apiBase: 'http://localhost:8000',
  fixturesBase: 'fixtures',
  timeoutMs: 20000,
};

export function resolveConfig(fromWindow: Partial<AppConfig> | undefined, search: string): AppConfig {
  const c: AppConfig = { ...DEFAULT_CONFIG, ...(fromWindow ?? {}) };
  const q = new URLSearchParams(search);
  const mode = q.get('mode');
  if (mode === 'live' || mode === 'mock') c.mode = mode;
  const api = q.get('api');
  if (api && /^https?:\/\/[^\s]+$/.test(api)) c.apiBase = api;
  if (c.mode !== 'live' && c.mode !== 'mock') c.mode = 'live';
  return c;
}

declare global {
  interface Window {
    WATTWISE_CONFIG?: Partial<AppConfig>;
  }
}

import type { Breakdown, Finding, Portfolio, ScenarioResult, Scores, Tariff, Text, WorkOrder, DigestOut, PortfolioOut } from './types';

/**
 * Every number shown in Watt Wise comes from the backend engine (Mina's validated maths).
 * The frontend never calculates savings, scores or projections; it only displays them.
 */
declare global {
  interface Window { WATT_API?: string }
}

export const API_BASE: string =
  window.WATT_API ?? (location.protocol.startsWith('http') && location.port === '8000' ? location.origin : 'http://localhost:8000');

async function req<T>(path: string, init: RequestInit = {}, flatId?: string): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (flatId) headers['X-Flat-Id'] = flatId;
  const r = await fetch(API_BASE + path, { ...init, headers });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* not json */ }
    throw new Error(`${r.status}: ${detail}`);
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () => req<{ data_source: string; demo_notice: string }>('/health'),
  llmStatus: () => req<{ provider: string; llm_enabled: boolean; model: string | null }>('/llm/status'),
  scores: (f: string) => req<Scores>(`/flats/${f}/scores`, {}, f),
  breakdown: (f: string) => req<Breakdown>(`/flats/${f}/breakdown`, {}, f),
  findings: (f: string) => req<Finding[]>(`/flats/${f}/findings`, {}, f),
  digest: (f: string) => req<Text<DigestOut>>(`/flats/${f}/digest`, {}, f),
  report: (f: string, fid: string) =>
    req(`/flats/${f}/findings/${fid}/report`, { method: 'POST', body: JSON.stringify({ message: 'Reported from Watt Wise' }) }, f),
  scenario: (f: string, anomalyId: string, adoption: number, tariff: Tariff) =>
    req<ScenarioResult>(`/flats/${f}/scenarios`, {
      method: 'POST',
      body: JSON.stringify({ scenario: 'apply_interventions',
        params: { items: [{ anomaly_id: anomalyId, params: { adoption } }], tariff: { type: tariff } } }),
    }, f),
  portfolio: () => req<Portfolio>('/portfolio'),
  portfolioFindings: () => req<Finding[]>('/portfolio/findings'),
  portfolioSummary: () => req<Text<PortfolioOut>>('/portfolio/summary'),
  workorders: () => req<WorkOrder[]>('/workorders'),
  openWorkorder: (fid: string) => req<WorkOrder>('/workorders', { method: 'POST', body: JSON.stringify({ finding_id: fid }) }),
  patchWorkorder: (id: string, body: { status?: string; fault_found?: boolean }) =>
    req<WorkOrder>(`/workorders/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  verify: (id: string) =>
    req<{ verification: { status: string; reason: string } }>(`/workorders/${id}/verify`, { method: 'POST', body: JSON.stringify({ simulate: true }) }),
};

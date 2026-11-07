/**
 * Builds scenario requests exactly as the backend accepts them, and the canonical key the offline fixtures are
 * recorded under (must match scenario_key() in backend/scripts/frontend_fixtures.py).
 * No numbers are computed here: parameters are passed through from the backend's /interventions grid.
 */
import type { ScenarioName, TariffSpec } from './contracts';

export interface ScenarioRequest {
  scenario: ScenarioName;
  params: Record<string, unknown>;
}

/** Only parameters that differ from the documented default are sent (the backend fills in defaults). */
export function nonDefault(
  chosen: Record<string, unknown>,
  defaults: Record<string, { default: unknown }>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(chosen)) {
    if (k === 'adoption') {
      if (v !== 1 && v !== undefined) out[k] = v;
      continue;
    }
    if (!(k in defaults)) throw new Error(`unknown parameter ${k}`);
    if (v !== defaults[k].default) out[k] = v;
  }
  return out;
}

export function returnToBaseline(anomalyId: string, tariff: TariffSpec, params: Record<string, unknown> = {}): ScenarioRequest {
  const p: Record<string, unknown> = { anomaly_id: anomalyId, tariff };
  if (Object.keys(params).length) p.params = params;
  return { scenario: 'return_to_baseline', params: p };
}

export function applyInterventions(anomalyIds: string[], tariff: TariffSpec): ScenarioRequest {
  return { scenario: 'apply_interventions', params: { items: anomalyIds.map((id) => ({ anomaly_id: id })), tariff } };
}

export function shiftFlexibleLoad(channel: string, tariff: TariffSpec): ScenarioRequest {
  return { scenario: 'shift_flexible_load', params: { channel, tariff } };
}

export function reduceAwayUsage(fraction: number, tariff: TariffSpec): ScenarioRequest {
  return { scenario: 'reduce_away_usage', params: { fraction, tariff } };
}

function sortDeep(o: unknown): unknown {
  if (Array.isArray(o)) return o.map(sortDeep);
  if (o && typeof o === 'object') {
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(o as Record<string, unknown>).sort()) out[k] = sortDeep((o as Record<string, unknown>)[k]);
    return out;
  }
  return o;
}

/** Same text as Python json.dumps(canon(x), sort_keys=True, separators=(",", ":"), ensure_ascii=False). */
export function scenarioKey(flatId: string, req: ScenarioRequest): string {
  return JSON.stringify(sortDeep({ flat_id: flatId, scenario: req.scenario, params: req.params }));
}

/**
 * Offline mode: serves REAL backend responses recorded by backend/scripts/frontend_fixtures.py (fixtures/).
 * Same interface as LiveApi. It never computes or approximates a number: a request that was not recorded
 * (e.g. a fixed-price tariff with your own price) fails with 'offline_unsupported', and actions that change
 * backend state (work orders, reports) are not available offline.
 */
import type { Api } from './client';
import { ApiError } from './client';
import type {
  DigestText,
  LlmStatus,
  PortfolioSummaryText,
  TextObject,
  Breakdown,
  Finding,
  FlatMeta,
  Health,
  InterventionOptions,
  NotificationRaw,
  Portfolio,
  Profile,
  References,
  ReportRaw,
  ScenarioResponse,
  Scores,
  Tip,
  VerifyResponse,
  WorkOrderRaw,
} from './contracts';
import { scenarioKey, type ScenarioRequest } from './scenarioRequest';

export interface FixtureIndex {
  get: Record<string, string>;
  scenarios: Record<string, string>;
  meta: { references_hash: string; data_source: string; recorded_from: string; tariffs_recorded: string[] };
}

type Loader = (relPath: string) => Promise<unknown>;

export function browserLoader(baseUrl: string): Loader {
  const base = baseUrl.replace(/\/+$/, '');
  return async (rel) => {
    let res: Response;
    try {
      res = await fetch(`${base}/${rel}`);
    } catch (e) {
      throw new ApiError('network', 'Offline fixtures could not be loaded. Serve the app over http (npm run serve).', undefined, String(e));
    }
    if (!res.ok) throw new ApiError('http', `Fixture file missing: ${rel}`, res.status);
    return res.json();
  };
}

const OFFLINE_ACTION = 'This action changes data on the backend and is not available in offline (mock) mode. Start the backend and use live mode.';

export class MockApi implements Api {
  readonly mode = 'mock' as const;
  readonly describe = 'offline fixtures recorded from the real backend';
  private index: Promise<FixtureIndex> | null = null;

  constructor(private readonly load: Loader) {}

  private idx(): Promise<FixtureIndex> {
    this.index ??= this.load('index.json') as Promise<FixtureIndex>;
    return this.index;
  }

  async meta(): Promise<FixtureIndex['meta']> {
    return (await this.idx()).meta;
  }

  private async get<T>(path: string): Promise<T> {
    const i = await this.idx();
    const rel = i.get[path];
    if (!rel) {
      if (/^\/flats\/[^/]+\//.test(path)) throw new ApiError('http', 'Not found: unknown flat.', 404);
      throw new ApiError('offline_unsupported', `No recorded response for ${path} in offline mode.`);
    }
    return (await this.load(rel)) as T;
  }

  health() { return this.get<Health>('/health'); }
  flats() { return this.get<FlatMeta[]>('/flats'); }
  references() { return this.get<{ references: References; detectors: unknown[] }>('/references'); }
  interventions() { return this.get<InterventionOptions>('/interventions'); }
  scores(f: string) { return this.get<Scores>(`/flats/${f}/scores`); }
  breakdown(f: string) { return this.get<Breakdown>(`/flats/${f}/breakdown`); }
  profile(f: string) { return this.get<Profile>(`/flats/${f}/profile`); }
  findings(f: string) { return this.get<Finding[]>(`/flats/${f}/findings`); }
  tips(f: string) { return this.get<Tip[]>(`/flats/${f}/tips`); }
  flatNotifications(f: string) { return this.get<NotificationRaw[]>(`/flats/${f}/notifications`); }

  async scenario(f: string, req: ScenarioRequest): Promise<ScenarioResponse> {
    const i = await this.idx();
    const rel = i.scenarios[scenarioKey(f, req)];
    if (!rel) {
      throw new ApiError(
        'offline_unsupported',
        'This combination was not recorded for offline mode. Start the backend (live mode) to calculate it.',
      );
    }
    return (await this.load(rel)) as ScenarioResponse;
  }

  digest(f: string) { return this.get<TextObject<DigestText> & { flat_id: string; horizon: string }>(`/flats/${f}/digest`); }
  llmStatus() { return this.get<LlmStatus>('/llm/status'); }
  portfolioSummary() { return this.get<TextObject<PortfolioSummaryText>>('/portfolio/summary'); }
  portfolio() { return this.get<Portfolio>('/portfolio'); }
  portfolioFindings(filter: { responsibility?: string; status?: string } = {}) {
    if (filter.status) return Promise.reject(new ApiError('offline_unsupported', 'Status filters need live mode.'));
    return this.get<Finding[]>(filter.responsibility ? `/portfolio/findings?responsibility=${filter.responsibility}` : '/portfolio/findings');
  }
  workorders() { return this.get<WorkOrderRaw[]>('/workorders'); }
  reports() { return this.get<ReportRaw[]>('/reports'); }
  managerNotifications() { return this.get<NotificationRaw[]>('/notifications'); }

  report(): Promise<ReportRaw> { return Promise.reject(new ApiError('offline_unsupported', OFFLINE_ACTION)); }
  createWorkorder(): Promise<WorkOrderRaw> { return Promise.reject(new ApiError('offline_unsupported', OFFLINE_ACTION)); }
  patchWorkorder(): Promise<WorkOrderRaw> { return Promise.reject(new ApiError('offline_unsupported', OFFLINE_ACTION)); }
  verifyWorkorder(): Promise<VerifyResponse> { return Promise.reject(new ApiError('offline_unsupported', OFFLINE_ACTION)); }
}

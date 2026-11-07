/**
 * One typed interface for every backend call. Screens only use `Api`; whether it is the live FastAPI backend
 * (LiveApi) or recorded real responses (MockApi, mock.ts) is decided once in api/index.ts.
 *
 * Failure policy: a failed call throws ApiError. Nothing here ever substitutes a value.
 */
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
import type { ScenarioRequest } from './scenarioRequest';

export type ApiErrorKind = 'network' | 'timeout' | 'http' | 'bad_response' | 'offline_unsupported';

export class ApiError extends Error {
  constructor(
    readonly kind: ApiErrorKind,
    message: string,
    readonly status?: number,
    readonly detail?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface Api {
  readonly mode: 'live' | 'mock';
  readonly describe: string;
  health(): Promise<Health>;
  flats(): Promise<FlatMeta[]>;
  references(): Promise<{ references: References; detectors: unknown[] }>;
  interventions(): Promise<InterventionOptions>;
  // student (one flat)
  scores(flatId: string): Promise<Scores>;
  breakdown(flatId: string): Promise<Breakdown>;
  profile(flatId: string): Promise<Profile>;
  findings(flatId: string): Promise<Finding[]>;
  tips(flatId: string): Promise<Tip[]>;
  flatNotifications(flatId: string): Promise<NotificationRaw[]>;
  scenario(flatId: string, req: ScenarioRequest): Promise<ScenarioResponse>;
  report(flatId: string, findingId: string, message: string | null): Promise<ReportRaw>;
  digest(flatId: string): Promise<TextObject<DigestText> & { flat_id: string; horizon: string }>;
  llmStatus(): Promise<LlmStatus>;
  portfolioSummary(): Promise<TextObject<PortfolioSummaryText>>;
  // manager
  portfolio(): Promise<Portfolio>;
  portfolioFindings(filter?: { responsibility?: string; status?: string }): Promise<Finding[]>;
  workorders(): Promise<WorkOrderRaw[]>;
  createWorkorder(findingId: string, note: string | null): Promise<WorkOrderRaw>;
  /** status: 'sent' | 'repaired'; fault_found: technician outcome (true -> CONFIRMED, false -> DISMISSED). */
  patchWorkorder(id: string, body: WorkOrderPatch): Promise<WorkOrderRaw>;
  verifyWorkorder(id: string, simulate: boolean): Promise<VerifyResponse>;
  reports(): Promise<ReportRaw[]>;
  managerNotifications(): Promise<NotificationRaw[]>;
}

export interface WorkOrderPatch {
  status?: 'sent' | 'repaired';
  fault_found?: boolean;
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface LiveOptions {
  baseUrl: string;
  timeoutMs: number;
  /** Student session flat: sent as X-Flat-Id (a demo guard on the backend, NOT authentication). */
  flatHeader?: () => string | null;
  fetchImpl?: FetchLike;
}

export class LiveApi implements Api {
  readonly mode = 'live' as const;
  readonly describe: string;
  private readonly base: string;
  private readonly fetchImpl: FetchLike;

  constructor(private readonly opts: LiveOptions) {
    this.base = opts.baseUrl.replace(/\/+$/, '');
    this.describe = `live backend at ${this.base}`;
    this.fetchImpl = opts.fetchImpl ?? ((i, init) => fetch(i, init));
  }

  private async call<T>(method: 'GET' | 'POST' | 'PATCH', path: string, body?: unknown, studentFlat?: string): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const flat = studentFlat ?? null;
    if (flat) headers['X-Flat-Id'] = flat;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.opts.timeoutMs);
    let res: Response;
    try {
      res = await this.fetchImpl(this.base + path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: ctrl.signal,
      });
    } catch (e) {
      if (ctrl.signal.aborted) throw new ApiError('timeout', `The data service did not answer within ${Math.round(this.opts.timeoutMs / 1000)} s.`);
      throw new ApiError('network', `Cannot reach the data service at ${this.base}.`, undefined, String(e));
    } finally {
      clearTimeout(timer);
    }
    let data: unknown;
    try {
      data = await res.json();
    } catch {
      throw new ApiError('bad_response', `The data service sent an unreadable response (HTTP ${res.status}).`, res.status);
    }
    if (!res.ok) {
      const detail = typeof data === 'object' && data && 'detail' in data ? String((data as { detail: unknown }).detail) : '';
      throw new ApiError('http', httpMessage(res.status, detail), res.status, detail);
    }
    return data as T;
  }

  private student<T>(flatId: string, path: string, method: 'GET' | 'POST' = 'GET', body?: unknown): Promise<T> {
    const flat = this.opts.flatHeader?.() ?? null;
    return this.call<T>(method, `/flats/${encodeURIComponent(flatId)}${path}`, body, flat ?? undefined);
  }

  health() { return this.call<Health>('GET', '/health'); }
  flats() { return this.call<FlatMeta[]>('GET', '/flats'); }
  references() { return this.call<{ references: References; detectors: unknown[] }>('GET', '/references'); }
  interventions() { return this.call<InterventionOptions>('GET', '/interventions'); }
  scores(f: string) { return this.student<Scores>(f, '/scores'); }
  breakdown(f: string) { return this.student<Breakdown>(f, '/breakdown'); }
  profile(f: string) { return this.student<Profile>(f, '/profile'); }
  findings(f: string) { return this.student<Finding[]>(f, '/findings'); }
  tips(f: string) { return this.student<Tip[]>(f, '/tips'); }
  flatNotifications(f: string) { return this.student<NotificationRaw[]>(f, '/notifications'); }
  scenario(f: string, req: ScenarioRequest) { return this.student<ScenarioResponse>(f, '/scenarios', 'POST', req); }
  report(f: string, findingId: string, message: string | null) {
    return this.student<ReportRaw>(f, `/findings/${encodeURIComponent(findingId)}/report`, 'POST', { message });
  }
  digest(f: string) { return this.student<TextObject<DigestText> & { flat_id: string; horizon: string }>(f, '/digest'); }
  llmStatus() { return this.call<LlmStatus>('GET', '/llm/status'); }
  portfolioSummary() { return this.call<TextObject<PortfolioSummaryText>>('GET', '/portfolio/summary'); }
  portfolio() { return this.call<Portfolio>('GET', '/portfolio'); }
  portfolioFindings(filter: { responsibility?: string; status?: string } = {}) {
    const q = new URLSearchParams();
    if (filter.responsibility) q.set('responsibility', filter.responsibility);
    if (filter.status) q.set('status', filter.status);
    const s = q.toString();
    return this.call<Finding[]>('GET', `/portfolio/findings${s ? `?${s}` : ''}`);
  }
  workorders() { return this.call<WorkOrderRaw[]>('GET', '/workorders'); }
  createWorkorder(findingId: string, note: string | null) {
    return this.call<WorkOrderRaw>('POST', '/workorders', { finding_id: findingId, note });
  }
  patchWorkorder(id: string, body: WorkOrderPatch) {
    return this.call<WorkOrderRaw>('PATCH', `/workorders/${encodeURIComponent(id)}`, body);
  }
  verifyWorkorder(id: string, simulate: boolean) {
    return this.call<VerifyResponse>('POST', `/workorders/${encodeURIComponent(id)}/verify`, { simulate });
  }
  reports() { return this.call<ReportRaw[]>('GET', '/reports'); }
  managerNotifications() { return this.call<NotificationRaw[]>('GET', '/notifications'); }
}

export function httpMessage(status: number, detail: string): string {
  if (status === 403) return 'This flat is not available for your sign-in.';
  if (status === 404) return detail ? `Not found: ${detail}.` : 'Not found.';
  if (status === 400) return detail ? `The request was not accepted: ${detail}` : 'The request was not accepted.';
  if (status === 422) return 'The request had an invalid format.';
  return `The data service returned an error (HTTP ${status}).`;
}

/** Shared UI pieces (string templates, as in Hugo's original). Every number shown comes from the backend. */
import { ApiError } from './api/client';
import { esc } from './dom';

export type BadgeKind =
  | 'projected'
  | 'provisional'
  | 'placeholder'
  | 'data'
  | 'hypothesis'
  | 'owner'
  | 'simulated'
  | 'verified'
  | 'measured';

export function badge(kind: BadgeKind, text: string): string {
  return `<span class="badge ${kind}">${esc(text)}</span>`;
}

export function plainList(items: readonly string[]): string {
  return `<ul class="plain">${items.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>`;
}

/** Expandable panel (native <details>, keyboard accessible). */
export function details(summary: string, bodyHtml: string, open = false): string {
  return `<details class="more"${open ? ' open' : ''}><summary>${esc(summary)}</summary><div class="more-body">${bodyHtml}</div></details>`;
}

export function loadingHtml(what: string): string {
  return `<p class="loading" role="status"><span class="spinner" aria-hidden="true"></span>Loading ${esc(what)}…</p>`;
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  return 'Something went wrong while showing this part of the page.';
}

export function errorHtml(e: unknown, what: string): string {
  const offline = e instanceof ApiError && e.kind === 'offline_unsupported';
  return `<div class="error-box" role="alert"><strong>${esc(offline ? `${what}: not available offline.` : `Could not load ${what}.`)}</strong> ${esc(
    errorMessage(e),
  )} <span class="note">No numbers are shown instead.</span></div>`;
}

export function emptyHtml(text: string): string {
  return `<p class="empty">${esc(text)}</p>`;
}

/**
 * Loads data into an element with explicit loading and error states. On failure nothing numeric is rendered.
 * Returns the data (or null on error) so callers can wire events after rendering.
 */
export async function loadInto<T>(
  el: HTMLElement,
  what: string,
  load: () => Promise<T>,
  render: (data: T) => string,
): Promise<T | null> {
  el.setAttribute('aria-busy', 'true');
  el.innerHTML = loadingHtml(what);
  try {
    const data = await load();
    el.innerHTML = render(data);
    return data;
  } catch (e) {
    el.innerHTML = errorHtml(e, what);
    return null;
  } finally {
    el.removeAttribute('aria-busy');
  }
}

export function kv(rows: [string, string][]): string {
  return `<dl class="kv">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join('')}</dl>`;
}

/** Status of a finding: wording is shown verbatim from the backend, never upgraded. */
export function statusBadge(status: string, wording: string): string {
  const kind: BadgeKind = status === 'VERIFIED' ? 'verified' : status === 'DETECTED' || status === 'PLAUSIBLE' ? 'hypothesis' : 'owner';
  return `<span class="badge ${kind}" title="Status ${esc(status)}">${esc(wording)}</span>`;
}

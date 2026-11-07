import { esc, fmt } from './dom';
import type { Finding, Tariff, Text } from './types';

export type BadgeKind = 'projected' | 'provisional' | 'placeholder' | 'data' | 'hypothesis' | 'owner' | 'ai' | 'ok' | 'muted';

export function badge(kind: BadgeKind, text: string, title = ''): string {
  return `<span class="badge ${kind}"${title ? ` title="${esc(title)}"` : ''}>${esc(text)}</span>`;
}

export const TARIFF_LABEL: Record<Tariff, string> = {
  hourly_spot: 'Hourly spot price',
  monthly_average_spot: 'Monthly average price',
  included_in_rent: 'Included in rent',
};

/** Which evidence level a finding has, in the engine's own words. */
export function statusChip(f: Finding): string {
  const cls = f.status === 'VERIFIED' ? 'ok' : f.status === 'DISMISSED' ? 'muted' : f.responsibility === 'manager' ? 'hypothesis' : 'projected';
  return badge(cls as BadgeKind, f.wording, `status ${f.status}`);
}

export const RESP_LABEL: Record<Finding['responsibility'], string> = {
  manager: 'Building manager',
  resident: 'Residents',
  unknown: 'Needs confirmation',
};

/** Where the text came from, and that it passed the checks. */
export function textMeta(t?: Text | null): string {
  if (!t) return '';
  const src = t.source === 'llm' ? badge('ai', `AI · ${t.provider ?? ''}`) : t.source === 'template' ? badge('muted', 'Watt Wise wording')
    : t.source === 'safe' ? badge('provisional', 'Short version') : badge('placeholder', 'Text unavailable');
  const ok = t.validation?.passed ? badge('data', '✓ Numbers checked against the engine') : '';
  return `<div class="meta">${src}${ok}</div>`;
}

export function claimsDetails(t?: Text | null): string {
  if (!t?.claims?.length) return '';
  const rows = t.claims.map((c) => {
    const v = Array.isArray(c.value) ? c.value.map((x) => fmt.num(Number(x), 2)).join(' – ') : typeof c.value === 'number' ? fmt.num(c.value, 2) : esc(String(c.value));
    return `<tr><td class="num">${v} <span class="unit">${esc(c.unit)}</span></td><td>${esc(c.category.replace(/_/g, ' '))}</td><td>${esc(c.period ?? '')}</td><td><code>${esc(c.source)}</code></td></tr>`;
  }).join('');
  return `<details class="claims"><summary>Where these numbers come from</summary>
    <div class="table-wrap"><table class="data mini"><thead><tr><th>Value</th><th>Kind</th><th>Period</th><th>Engine field</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
}

/** Score ring: SVG arc for a 0-100 value from the engine. */
export function scoreRing(score: number, band: string, size = 148): string {
  const r = 58, c = 2 * Math.PI * r, p = Math.max(0, Math.min(100, score)) / 100;
  return `<div class="ring" style="width:${size}px;height:${size}px" role="img" aria-label="Score ${fmt.num(score)} of 100, band ${esc(band)}">
    <svg viewBox="0 0 140 140" width="${size}" height="${size}">
      <circle cx="70" cy="70" r="${r}" class="ring-bg"/>
      <circle cx="70" cy="70" r="${r}" class="ring-fg" stroke-dasharray="${(c * p).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 70 70)"/>
    </svg>
    <div class="ring-txt"><b>${fmt.num(score)}</b><span class="band band-${esc(band)}">${esc(band)}</span></div></div>`;
}

const PILLAR_LABEL: Record<string, string> = { use: 'Use', waste: 'Waste', timing: 'Timing', health: 'Health' };
const PILLAR_HINT: Record<string, string> = {
  use: 'electricity compared with the most efficient flats',
  waste: 'possible avoidable use the engine found',
  timing: 'flexible appliances in peak-price hours',
  health: 'possible equipment faults (not your score)',
};

export function pillarRows(p: Record<string, number>): string {
  return Object.entries(p).map(([k, v]) => `<div class="pillar">
      <div class="pillar-name">${esc(PILLAR_LABEL[k] ?? k)}<span>${esc(PILLAR_HINT[k] ?? '')}</span></div>
      <div class="track"><i style="width:${Math.max(2, v)}%" class="${v >= 80 ? 'hi' : v >= 55 ? 'mid' : 'lo'}"></i></div>
      <div class="pillar-val">${fmt.num(v)}</div></div>`).join('');
}

export function kpi(label: string, value: string, sub = '', tone = ''): string {
  return `<div class="kpi ${tone}"><div class="kpi-label">${esc(label)}</div><div class="kpi-val">${value}</div>${sub ? `<div class="kpi-sub">${sub}</div>` : ''}</div>`;
}

/** Daily kWh bars straight from the engine's daily series. */
export function dailyBars(daily: { day: string; kwh: number }[]): string {
  const max = Math.max(...daily.map((d) => d.kwh), 1e-9);
  const bars = daily.map((d) => {
    const dt = new Date(d.day + 'T12:00:00Z');
    const we = dt.getUTCDay() === 0 || dt.getUTCDay() === 6;
    return `<div class="dbar${we ? ' we' : ''}" style="height:${Math.max(3, (d.kwh / max) * 100)}%" title="${esc(d.day)}: ${fmt.num(d.kwh, 1)} kWh"></div>`;
  }).join('');
  return `<div class="dbars" role="img" aria-label="Electricity per day">${bars}</div>
    <div class="dlabels"><span>${esc(daily[0]?.day ?? '')}</span><span>${esc(daily[daily.length - 1]?.day ?? '')}</span></div>`;
}

/** The engine's SEK value for the chosen tariff; never computed here. */
export function moneyFor(f: Finding, tariff: Tariff): string {
  const v = f.valuation.sek_by_tariff[tariff];
  if (v == null) return '–';
  return `${fmt.num(v, 1)} SEK`;
}

export function skeleton(): string {
  return `<div class="skel"><div></div><div></div><div></div></div>`;
}

export function errorBox(e: unknown): string {
  return `<div class="panel errbox"><h2>Can’t reach the Watt Wise engine</h2><p>${esc(String((e as Error)?.message ?? e))}</p>
    <p class="note">Start it with <code>cd backend &amp;&amp; uvicorn app.api.main:app --port 8000</code>, then reload.</p></div>`;
}

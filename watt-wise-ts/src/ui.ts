import { $, esc, fmt } from './dom';
import { state } from './state';
import type { EvidenceItem, Projection, ScenarioId, Totals } from './types';

export type BadgeKind = 'projected' | 'provisional' | 'placeholder' | 'data' | 'hypothesis' | 'owner';

export function badge(kind: BadgeKind, text: string): string {
  return `<span class="badge ${kind}">${esc(text)}</span>`;
}

export function evidenceList(items: readonly EvidenceItem[]): string {
  const rows = items
    .map((e) => {
      const b =
        e.kind === 'from-data'
          ? badge('data', 'Read from the data file')
          : badge('placeholder', 'Placeholder · analysis pending');
      return `<li class="ev"><span class="ev-src">${esc(e.source)}</span> ${esc(e.claim)} ${b}</li>`;
    })
    .join('');
  return `<ul class="evidence">${rows}</ul>`;
}

export function plainList(items: readonly string[]): string {
  return `<ul class="plain">${items.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>`;
}

/* ---------- scenario controls shared by both views ---------- */

export function scenarioControlsHtml(prefix: string): string {
  const s = state.scenario;
  const radio = (id: ScenarioId, label: string): string =>
    `<label class="radio"><input type="radio" name="${prefix}-scn" value="${id}" ${
      s.id === id ? 'checked' : ''
    }> ${esc(label)}</label>`;
  return `
    <fieldset class="scenario">
      <legend>Scenario</legend>
      ${radio('shift-evening', 'Move evening use (15–18 UTC) to overnight (22–04 UTC)')}
      ${radio('trim-overnight', 'Trim overnight use (00–04 UTC), assuming it is avoidable')}
    </fieldset>
    <label for="${prefix}-share" id="${prefix}-share-label" class="range-label">Share of the load changed: ${s.sharePct}%</label>
    <input id="${prefix}-share" type="range" min="0" max="60" step="5" value="${s.sharePct}">
    <p class="note">The ranges below assume that between 50% and 100% of the planned change really happens.</p>`;
}

export function bindScenarioControls(prefix: string, onChange: () => void): void {
  document.querySelectorAll<HTMLInputElement>(`input[name="${prefix}-scn"]`).forEach((radio) => {
    radio.addEventListener('change', () => {
      state.scenario.id = radio.value as ScenarioId;
      onChange();
    });
  });
  const range = $<HTMLInputElement>(`#${prefix}-share`);
  range.addEventListener('input', () => {
    state.scenario.sharePct = Number(range.value);
    $(`#${prefix}-share-label`).textContent = `Share of the load changed: ${state.scenario.sharePct}%`;
    onChange();
  });
}

/* ---------- before / after table ---------- */

interface Row {
  label: string;
  unit: string;
  key: keyof Totals;
  digits: number;
}

const ROWS: readonly Row[] = [
  { label: 'Electricity', unit: 'kWh', key: 'kwh', digits: 1 },
  { label: 'Spot cost, excl. VAT', unit: 'SEK', key: 'sek', digits: 1 },
  { label: 'Carbon', unit: 'kg CO₂e', key: 'co2kg', digits: 2 },
];

export function projectionTable(p: Projection, caption: string): string {
  const body = ROWS.map((r) => {
    const before = p.before[r.key];
    const lo = p.low[r.key];
    const hi = p.high[r.key];
    const afterHigh = before + hi; // full adherence gives the larger change
    const afterLow = before + lo;
    const flat = Math.abs(hi) < 0.05 && Math.abs(lo) < 0.05;
    const after = flat
      ? `${fmt.num(before, r.digits)} (unchanged)`
      : `${fmt.num(afterHigh, r.digits)} – ${fmt.num(afterLow, r.digits)}`;
    const change = flat ? fmt.num(0, r.digits) : `${fmt.signed(lo, r.digits)} to ${fmt.signed(hi, r.digits)}`;
    return `<tr>
      <th scope="row">${esc(r.label)} <span class="unit">${r.unit}</span></th>
      <td>${fmt.num(before, r.digits)}</td>
      <td>${after}</td>
      <td>${change}</td>
    </tr>`;
  }).join('');
  return `<div class="table-wrap"><table class="data">
    <caption>${esc(caption)}</caption>
    <thead><tr><th scope="col">Measure</th><th scope="col">Before</th><th scope="col">After (projected)</th><th scope="col">Change (projected)</th></tr></thead>
    <tbody>${body}</tbody>
  </table></div>`;
}

/** Shown wherever a saving appears. Nothing in this app can verify a saving. */
export function unverifiedNote(): string {
  return `<p class="warn">${badge('projected', 'Projected · not verified')} These are model estimates from sample data. A saving only counts once a real before/after measurement confirms it.</p>`;
}

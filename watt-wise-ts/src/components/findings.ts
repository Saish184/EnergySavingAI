/**
 * Finding cards. Everything numeric is a backend field; this file only selects and formats.
 * Energy avoided (reduction) and electricity moved (shift) are never presented as the same thing.
 */
import type { Finding, FindingType, TariffSpec } from '../api/contracts';
import type { TextView } from '../api/texts';
import { esc } from '../dom';
import * as F from '../format';
import { badge, details, kv, plainList, statusBadge } from '../ui';
import { moneyFor } from './tariff';
import { textCard } from './textCard';

/** Practical, safety-aware next steps per pattern type (static guidance, no numbers). */
export const NEXT_STEP: Record<FindingType, string> = {
  fault_step_change:
    'Report it to your building manager. It looks like an equipment change (for example a fridge door seal or thermostat); residents are not scored on it.',
  base_load_outlier:
    'Walk round the flat for things that stay on day and night (standby electronics, chargers, extra lighting) and switch off what is not needed.',
  scheduled_block:
    'Check what runs at the same hours every day, also when nobody is home (a timer, a computer or a screen left on), and turn it off when it is not used.',
  heater_pattern:
    'Check whether a portable heater is left on while nobody is home. Keep rooms safely warm: do not switch heating off completely, and tell the manager if rooms feel cold.',
  peak_usage:
    'Start the machine after the evening peak instead of during it. Avoid unattended night runs; a later evening start is enough.',
};

export const TYPE_PILL: Record<FindingType, { cls: string; label: string }> = {
  fault_step_change: { cls: 'check', label: 'Possible equipment issue' },
  base_load_outlier: { cls: 'waste', label: 'Always-on use' },
  scheduled_block: { cls: 'waste', label: 'Fixed-hour use' },
  heater_pattern: { cls: 'waste', label: 'Heating while away' },
  peak_usage: { cls: 'shift', label: 'Timing (shift, same kWh)' },
};

function statsTable(stats: Record<string, unknown>): string {
  const rows = Object.entries(stats)
    .filter(([, v]) => v !== null && typeof v !== 'object')
    .map(([k, v]) => `<tr><th scope="row">${esc(k.replace(/_/g, ' '))}</th><td>${esc(typeof v === 'number' ? String(v) : String(v))}</td></tr>`)
    .join('');
  return `<div class="table-wrap"><table class="data compact"><tbody>${rows}</tbody></table></div>`;
}

export function savingsBlock(f: Finding, tariff: TariffSpec): string {
  const a = f.avoidable_28d;
  const q = f.quantities;
  const shift = a.kind === 'shift';
  const money = moneyFor(f.valuation, tariff, a.kind);
  const energyLine = shift
    ? `<div class="kpi"><span class="kpi-label">Electricity moved to other hours</span><span class="kpi-val">${esc(F.kwh(q.kwh_moved))}</span><span class="note">Same total use: 0 kWh saved. Only the timing changes.</span></div>`
    : `<div class="kpi"><span class="kpi-label">Energy that could be avoided</span><span class="kpi-val">${esc(F.kwh(a.kwh))}</span><span class="note">Simulated, if acted on fully.</span></div>`;
  return `<div class="kpis small">
      ${energyLine}
      <div class="kpi"><span class="kpi-label">Money (conditional on your contract)</span><span class="kpi-val">${esc(money.text)}</span><span class="note">${esc(money.note)}</span></div>
      <div class="kpi"><span class="kpi-label">Emissions avoided</span><span class="kpi-val">${esc(F.co2(a.co2_kg))}</span><span class="note">Synthetic average hourly factors.</span></div>
    </div>
    <p class="note">${badge('simulated', 'Simulated')} Over ${esc(F.days(a.window_days))} of observed data (${esc(a.horizon)}). ${esc(a.method)}.</p>`;
}

export function uncertaintyBlock(f: Finding): string {
  const u = f.uncertainty;
  const ci = u.sampling_ci95;
  const sr = u.scenario_range;
  return kv([
    ['Sampling range (95 %)', `${esc(F.range(ci.kwh[0], ci.kwh[1], 'kWh'))}; ${esc(F.range(ci.sek_spot_hourly[0], ci.sek_spot_hourly[1], 'SEK if hourly spot', 2))}<br><span class="note">${esc(ci.method)}</span>`],
    [
      'Assumption range',
      sr
        ? `${esc(F.range(sr.kwh[0], sr.kwh[1], 'kWh'))}; ${esc(F.range(sr.sek_spot_hourly[0], sr.sek_spot_hourly[1], 'SEK if hourly spot', 2))}<br><span class="note">${esc(u.scenario_method)}</span>`
        : esc(F.NA),
    ],
    ['Evidence strength', `${esc(f.evidence.confidence_note)}`],
  ]);
}

export function projectionBlock(f: Finding): string {
  const p = f.projection_annual;
  if (p.sek.value == null) {
    return `<p class="note">${badge('placeholder', 'No yearly figure')} ${esc(p.sek.reason ?? 'Not extrapolated.')}</p>`;
  }
  return `<p class="note">${badge('projected', 'Projection, not a promise')} If the pattern continued unchanged for a year: ${esc(F.kwh(p.kwh.value, 0))} (${esc(
    F.range(p.kwh.low, p.kwh.high, 'kWh', 0),
  )}), ${esc(F.sek(p.sek.value, 0))} if hourly spot (${esc(F.range(p.sek.low, p.sek.high, 'SEK', 0))}). ${esc(p.sek.range_method ?? '')}. ${esc(p.sek.assumptions.join('; '))}.</p>`;
}

export function tiersBlock(f: Finding): string {
  const t = f.tiers;
  const verified =
    t.verified != null
      ? `${esc(F.kwh(t.verified))} measured after the change${f.simulated ? ` ${badge('simulated', 'SIMULATED post-repair data')}` : ''}`
      : esc(t.verified_reason);
  return kv([
    ['Potential (simulated)', `${esc(F.kwh(t.potential.kwh))} · ${esc(F.sek(t.potential.sek_if_hourly_spot))} if hourly spot`],
    ['Estimated realised', esc(t.estimated_realized_reason)],
    ['Verified', verified],
  ]);
}

export function ladderBlock(f: Finding): string {
  const q = f.quantities;
  const rows: [string, number, string][] = [
    ['Observed use in the pattern’s hours', q.observed_kwh, q.labels.observed_kwh],
    ['Expected without the pattern', q.expected_baseline_kwh, q.labels.expected_baseline_kwh],
    ['Unexplained excess', q.unexplained_excess_kwh, q.labels.unexplained_excess_kwh],
    ['Avoidable estimate', q.avoidable_estimate_kwh, q.labels.avoidable_estimate_kwh],
    ['Use after the change', q.counterfactual_kwh, q.labels.counterfactual_kwh],
  ];
  if (q.kind === 'shift') rows.push(['Moved to later hours', q.kwh_moved, 'simulated (same kWh)']);
  return `<div class="table-wrap"><table class="data compact"><thead><tr><th scope="col">Quantity</th><th scope="col">kWh</th><th scope="col">Kind</th></tr></thead><tbody>${rows
    .map(([l, v, k]) => `<tr><th scope="row">${esc(l)}</th><td>${esc(F.num(v, 2))}</td><td>${esc(k)}</td></tr>`)
    .join('')}</tbody></table></div><p class="note">${esc(String(q.observed_hours))} of ${esc(String(q.window_hours))} pattern hours observed.</p>`;
}

export function evidenceBlock(f: Finding): string {
  const e = f.evidence;
  return `<p>${esc(e.text)}</p>
    ${kv([
      ['Reference level', e.baseline_kwh_per_h == null ? F.NA : `${esc(F.num(e.baseline_kwh_per_h, 4))} kWh per hour`],
      ['Observed level', e.observed_kwh_per_h == null ? F.NA : `${esc(F.num(e.observed_kwh_per_h, 4))} kWh per hour`],
      ['Excess vs reference', esc(F.kwh(e.reported_excess_kwh, 2))],
    ])}
    <div class="subhead">Test statistics</div>${statsTable(e.statistics)}
    <p class="note">${esc(e.confidence_note)}.</p>`;
}

function scoreIfFixed(f: Finding, lenses: ('resident' | 'apartment')[]): string {
  return lenses
    .map((l) => {
      const s = f.score_if_fixed[l];
      return `${l === 'resident' ? 'Resident score' : 'Apartment score'}: ${esc(F.score(s.before))} → ${esc(F.score(s.after))}`;
    })
    .join(' · ');
}

export function windowText(f: Finding): string {
  return `${F.localDate(f.window.start)} – ${F.localDate(new Date(F.parseUtc(f.window.end).getTime() - 1).toISOString())} (${F.days(f.window.days)})`;
}

export interface CardOptions {
  audience: 'student' | 'manager';
  tariff: TariffSpec;
  text?: TextView;
  /** extra HTML for actions (report button, work-order panel) */
  actionsHtml?: string;
}

export function findingCard(f: Finding, o: CardOptions): string {
  const pill = TYPE_PILL[f.type] ?? { cls: 'check', label: f.type };
  const lenses: ('resident' | 'apartment')[] = o.audience === 'student' ? ['resident', 'apartment'] : ['apartment', 'resident'];
  return `<article class="card finding" id="finding-${esc(f.id)}" data-finding="${esc(f.id)}">
    <div class="alert-head"><span class="pill ${pill.cls}">${esc(pill.label)}</span>${statusBadge(f.status, f.wording)}</div>
    <h3>${esc(f.title)}</h3>
    <p class="meta">${esc(o.audience === 'manager' ? `${f.flat_id} · ` : '')}${esc(f.channel)} · ${esc(F.appliance(f.assumed_type))}${
      f.assumed_type_is_assumption ? ' <span class="note">(type inferred from the load shape)</span>' : ''
    }<br>${esc(windowText(f))}</p>
    <p class="owner">${badge('owner', f.responsibility_note)}</p>
    ${o.text && o.text.state === 'ok' ? textCard(o.text) : `<div class="subhead">What you can do</div><p>${esc(NEXT_STEP[f.type] ?? '')}</p>`}
    ${savingsBlock(f, o.tariff)}
    ${projectionBlock(f)}
    <p class="note">Score if fixed: ${scoreIfFixed(f, lenses)}. Counts as: ${esc(f.counts_as)}.</p>
    ${details('Evidence', evidenceBlock(f))}
    ${details('Uncertainty', uncertaintyBlock(f))}
    ${details('How the saving is built', ladderBlock(f) + tiersBlock(f))}
    ${details('Assumptions', plainList(f.assumptions))}
    ${o.actionsHtml ?? ''}
  </article>`;
}

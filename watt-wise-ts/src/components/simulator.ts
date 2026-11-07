/**
 * What-if simulator. Every option is a parameter the backend documents (GET /interventions); every result is the
 * backend's POST /flats/{id}/scenarios response. Nothing is calculated in the browser.
 */
import type { Api } from '../api/client';
import type { Finding, InterventionOptions, Lens, ScenarioResponse, TariffSpec } from '../api/contracts';
import * as R from '../api/scenarioRequest';
import { esc } from '../dom';
import * as F from '../format';
import { badge, details, errorHtml, kv, loadingHtml, plainList } from '../ui';
import { moneyFor, tariffForRequest } from './tariff';

const PARAM_LABEL: Record<string, string> = {
  fix_fraction: 'Share of the extra use that the repair removes',
  repair_after_days: 'Repair happens after (days)',
  post_level: 'Level after the repair',
  avoidable_fraction: 'Share of the extra use that is avoidable',
  only_when_unoccupied: 'Only in hours with nobody home',
  min_absence_hours: 'Count absences of at least (hours)',
  rebound: 'Extra heating needed on return (rebound)',
  share_moved: 'Share of peak-hour runs moved',
  max_delay_hours: 'Latest start (hours after the original)',
};

function valueLabel(v: unknown): string {
  if (v === true) return 'yes';
  if (v === false) return 'no';
  if (v === 'pre_step_mean') return 'level before the step';
  if (v === 'peer_mean') return 'other flats’ level';
  if (typeof v === 'number' && v > 0 && v < 1) return `${Math.round(v * 100)} %`;
  return String(v);
}

type Mode = 'one' | 'all' | 'shift' | 'away';

export interface SimulatorDeps {
  api: Api;
  flatId: string;
  findings: Finding[];
  options: InterventionOptions;
  tariff: () => TariffSpec;
}

export function simulatorHtml(d: SimulatorDeps): string {
  const flexChannels = [...new Set(d.findings.filter((f) => f.type === 'peak_usage').map((f) => f.channel))];
  const away = d.findings.some((f) => f.type === 'scheduled_block' || f.type === 'heater_pattern');
  const adoption = d.api.mode === 'mock' ? [1, 0.5] : [1, 0.75, 0.5, 0.25];
  const findingOpts = d.findings.map((f) => `<option value="${esc(f.id)}">${esc(`${f.title} · ${f.channel} ${f.assumed_type}`)}</option>`).join('');
  const modeRadio = (m: Mode, label: string, disabled = false) =>
    `<label class="radio"><input type="radio" name="sim-mode" value="${m}" ${m === 'one' ? 'checked' : ''} ${disabled ? 'disabled' : ''}> ${esc(label)}${
      disabled ? ' <span class="note">(no such pattern in this flat)</span>' : ''
    }</label>`;
  if (!d.findings.length) return `<p class="empty">No patterns were detected for this flat, so there is nothing to simulate.</p>`;
  return `<form id="sim-form" class="sim" novalidate>
      <fieldset class="scenario"><legend>What do you want to try?</legend>
        ${modeRadio('one', 'Act on one finding')}
        ${modeRadio('all', 'Act on all findings together (no double counting)')}
        ${modeRadio('shift', 'Run a flexible appliance after the peak', !flexChannels.length)}
        ${modeRadio('away', 'Use less while nobody is home', !away)}
      </fieldset>
      <div data-show="one">
        <label class="range-label" for="sim-finding">Finding</label>
        <select id="sim-finding">${findingOpts}</select>
        <div id="sim-params"></div>
        <label class="range-label" for="sim-adoption">How much of it you would actually do</label>
        <select id="sim-adoption">${adoption.map((a) => `<option value="${a}">${a === 1 ? 'All of it' : valueLabel(a)}</option>`).join('')}</select>
      </div>
      <div data-show="shift" hidden>
        <label class="range-label" for="sim-channel">Appliance</label>
        <select id="sim-channel">${flexChannels
          .map((c) => `<option value="${esc(c)}">${esc(`${c} ${d.findings.find((f) => f.channel === c)?.assumed_type ?? ''}`)}</option>`)
          .join('')}</select>
      </div>
      <div data-show="away" hidden>
        <label class="range-label" for="sim-fraction">Share of that use you would cut</label>
        <select id="sim-fraction"><option value="0.5">50 %</option><option value="1">100 %</option></select>
      </div>
      <button class="btn inline" type="submit" id="sim-run">Run simulation</button>
      ${d.api.mode === 'mock' ? '<p class="note">Offline mode: only recorded combinations are available. Start the backend for any combination and for your own fixed price.</p>' : ''}
    </form>
    <div id="sim-result" aria-live="polite"></div>`;
}

function paramsHtml(f: Finding, o: InterventionOptions): string {
  const spec = o.parameters[f.type] ?? {};
  return Object.entries(spec)
    .map(
      ([k, s]) => `<label class="range-label" for="sim-p-${esc(k)}">${esc(PARAM_LABEL[k] ?? k)}</label>
      <select id="sim-p-${esc(k)}" data-param="${esc(k)}">${s.grid
        .map(
          (v, i) =>
            `<option value="${i}" ${JSON.stringify(v) === JSON.stringify(s.default) ? 'selected' : ''}>${esc(valueLabel(v))}${
              JSON.stringify(v) === JSON.stringify(s.default) ? ' (default)' : ''
            }</option>`,
        )
        .join('')}</select>`,
    )
    .join('');
}

export function buildRequest(
  mode: Mode,
  form: ParentNode,
  d: Pick<SimulatorDeps, 'findings' | 'options'>,
  tariff: TariffSpec,
): R.ScenarioRequest {
  const t = tariffForRequest(tariff);
  if (mode === 'all') return R.applyInterventions(d.findings.map((f) => f.id), t);
  if (mode === 'shift') return R.shiftFlexibleLoad(form.querySelector<HTMLSelectElement>('#sim-channel')?.value ?? 'A04', t);
  if (mode === 'away') return R.reduceAwayUsage(Number(form.querySelector<HTMLSelectElement>('#sim-fraction')?.value ?? 0.5), t);
  const id = form.querySelector<HTMLSelectElement>('#sim-finding')?.value ?? '';
  const f = d.findings.find((x) => x.id === id);
  if (!f) throw new Error('choose a finding');
  const spec = d.options.parameters[f.type] ?? {};
  const chosen: Record<string, unknown> = {};
  form.querySelectorAll<HTMLSelectElement>('select[data-param]').forEach((s) => {
    const k = s.dataset.param ?? '';
    chosen[k] = spec[k]?.grid[Number(s.value)];
  });
  chosen.adoption = Number(form.querySelector<HTMLSelectElement>('#sim-adoption')?.value ?? 1);
  return R.returnToBaseline(f.id, t, R.nonDefault(chosen, spec));
}

function scoreTable(r: ScenarioResponse): string {
  const lenses: Lens[] = ['resident', 'apartment'];
  const rows = lenses
    .map((l) => {
      const b = r.before[l];
      const a = r.after[l];
      const pillars = Object.keys(a.pillars)
        .map((k) => `${k} ${F.score((b.pillars as unknown as Record<string, number>)[k])} → ${F.score((a.pillars as unknown as Record<string, number>)[k])}`)
        .join(', ');
      return `<tr><th scope="row">${l === 'resident' ? 'Resident score' : 'Apartment score'}</th><td>${esc(F.score(b.score))} (${esc(b.band)}, rank ${esc(F.num(b.rank, 0))})</td><td>${esc(
        F.score(a.score),
      )} (${esc(a.band)}, rank ${esc(F.num(a.rank, 0))})</td><td>${esc(F.signed(r.score_change[l], 1))}</td><td class="note">${esc(pillars)}</td></tr>`;
    })
    .join('');
  return `<div class="table-wrap"><table class="data"><caption>Scores before and after (frozen references: other flats unchanged)</caption><thead><tr><th scope="col">Score</th><th scope="col">Before</th><th scope="col">After</th><th scope="col">Change</th><th scope="col">Pillars</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

export function resultHtml(r: ScenarioResponse, tariff: TariffSpec): string {
  if (!r.kind || !r.valuation || !r.uncertainty || !r.window) {
    return `<div class="sim-out"><p>${badge('placeholder', 'Nothing to simulate')} ${esc(r.assumptions.join('; '))}</p></div>`;
  }
  const money = moneyFor(r.valuation, tariff, r.kind);
  const moved = (r.ladder ?? []).filter((l) => l.kind === 'shift');
  const kindLabel = r.kind === 'shift' ? 'Timing shift (same kWh)' : r.kind === 'reduction' ? 'Energy reduction' : 'Reduction + timing shift';
  const u = r.uncertainty;
  const ci = u.sampling_ci95;
  const sr = u.scenario_range;
  const p = r.projection_annual;
  const ladderRows = (r.ladder ?? [])
    .map(
      (l) =>
        `<tr><th scope="row">${esc(l.anomaly_id)}</th><td>${esc(l.kind)}</td><td>${esc(F.num(l.observed_kwh, 2))}</td><td>${esc(F.num(l.avoidable_estimate_kwh, 2))}</td><td>${esc(
          F.num(l.kwh_moved, 2),
        )}</td><td>${esc(F.num(l.counterfactual_kwh, 2))}</td></tr>`,
    )
    .join('');
  return `<div class="sim-out">
    <div class="panel-head"><h3>Result</h3><span>${badge('simulated', 'Simulated, not measured')} ${badge('data', kindLabel)}</span></div>
    <p class="note">Window: ${esc(F.localDate(r.window.start_utc))} – ${esc(F.localDate(new Date(F.parseUtc(r.window.end_utc_exclusive).getTime() - 1).toISOString()))} (${esc(F.days(r.window.days))} of observed data).</p>
    <div class="kpis small">
      <div class="kpi"><span class="kpi-label">Change in electricity use</span><span class="kpi-val">${esc(F.signed(r.delta_28d.kwh, 2))} kWh</span><span class="note">${
        r.kind === 'shift' ? 'A shift keeps the same kWh.' : 'Negative = less electricity used.'
      }</span></div>
      ${
        moved.length
          ? `<div class="kpi"><span class="kpi-label">Electricity moved to later hours</span><span class="kpi-val">${moved.map((m) => esc(F.kwh(m.kwh_moved, 2))).join(' + ')}</span><span class="note">Moved, not saved.</span></div>`
          : ''
      }
      <div class="kpi"><span class="kpi-label">Money (your contract)</span><span class="kpi-val">${esc(money.text)}</span><span class="note">${esc(money.note)}</span></div>
      <div class="kpi"><span class="kpi-label">Change in emissions</span><span class="kpi-val">${esc(F.signed(r.delta_28d.co2_kg, 3))} kg CO₂e</span><span class="note">Synthetic average hourly factors.</span></div>
    </div>
    ${scoreTable(r)}
    ${kv([
      ['Sampling range (95 %) of the saving', `${esc(F.range(ci.kwh[0], ci.kwh[1], 'kWh', 2))}; ${esc(F.range(ci.sek_spot_hourly[0], ci.sek_spot_hourly[1], 'SEK if hourly spot', 2))}`],
      ['Assumption range of the saving', sr ? `${esc(F.range(sr.kwh[0], sr.kwh[1], 'kWh', 2))}; ${esc(F.range(sr.sek_spot_hourly[0], sr.sek_spot_hourly[1], 'SEK if hourly spot', 2))}` : esc(F.NA)],
      [
        'Yearly',
        p.sek.value == null
          ? esc(p.sek.reason ?? 'not extrapolated')
          : `${badge('projected', 'Projection')} ${esc(F.sek(p.sek.value, 0))} if hourly spot (${esc(F.range(p.sek.low, p.sek.high, 'SEK', 0))}), ${esc(F.kwh(p.kwh.value, 0))}`,
      ],
      ['Counted twice across items', `${esc(F.kwh(r.overlap?.kwh ?? null, 2))} (combined effects are calculated together)`],
      ['Shifts into hours with no reading', esc(String(r.missing_hour_moves ?? 0))],
    ])}
    ${details(
      'Per finding',
      `<div class="table-wrap"><table class="data compact"><thead><tr><th scope="col">Finding</th><th scope="col">Kind</th><th scope="col">Observed kWh</th><th scope="col">Avoided kWh</th><th scope="col">Moved kWh</th><th scope="col">kWh after</th></tr></thead><tbody>${ladderRows}</tbody></table></div>`,
    )}
    ${details('Assumptions of this simulation', plainList([...r.assumptions, ...u.not_included.map((n) => `not included: ${n}`)]))}
  </div>`;
}

export function bindSimulator(root: HTMLElement, d: SimulatorDeps): { select: (findingId: string) => void } {
  const form = root.querySelector<HTMLFormElement>('#sim-form');
  const out = root.querySelector<HTMLElement>('#sim-result');
  if (!form || !out) return { select: () => undefined };
  const mode = (): Mode => (form.querySelector<HTMLInputElement>('input[name="sim-mode"]:checked')?.value ?? 'one') as Mode;
  const refreshParams = () => {
    const f = d.findings.find((x) => x.id === form.querySelector<HTMLSelectElement>('#sim-finding')?.value);
    const box = form.querySelector<HTMLElement>('#sim-params');
    if (box && f) box.innerHTML = paramsHtml(f, d.options);
  };
  const showMode = () => {
    form.querySelectorAll<HTMLElement>('[data-show]').forEach((el) => {
      el.hidden = el.dataset.show !== mode();
    });
  };
  form.addEventListener('change', (e) => {
    const t = e.target as HTMLElement;
    if (t.id === 'sim-finding') refreshParams();
    if ((t as HTMLInputElement).name === 'sim-mode') showMode();
  });
  const run = form.querySelector<HTMLButtonElement>('#sim-run');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!run || run.disabled) return;
    run.disabled = true;
    run.textContent = 'Calculating…';
    out.innerHTML = loadingHtml('the simulation');
    try {
      const tariff = d.tariff();
      const req = buildRequest(mode(), form, d, tariff);
      const r = await d.api.scenario(d.flatId, req);
      out.innerHTML = resultHtml(r, tariff);
    } catch (err) {
      out.innerHTML = errorHtml(err, 'the simulation');
    } finally {
      run.disabled = false;
      run.textContent = 'Run simulation';
    }
  });
  refreshParams();
  showMode();
  return {
    select(findingId: string) {
      const one = form.querySelector<HTMLInputElement>('input[name="sim-mode"][value="one"]');
      if (one) one.checked = true;
      const sel = form.querySelector<HTMLSelectElement>('#sim-finding');
      if (sel) sel.value = findingId;
      refreshParams();
      showMode();
      form.scrollIntoView({ behavior: 'smooth', block: 'start' });
      form.querySelector<HTMLButtonElement>('#sim-run')?.focus({ preventScroll: true });
    },
  };
}

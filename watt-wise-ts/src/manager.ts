import { ALERTS, DATA_SOURCES, FLATS, SCORE_COMPONENTS } from './data';
import { flatProfile, portfolioProjection, totals } from './calc';
import { $, esc, fmt } from './dom';
import { alertStatusOf, state } from './state';
import type { AlertStatus, MaintenanceAlert } from './types';
import {
  badge,
  bindScenarioControls,
  evidenceList,
  plainList,
  projectionTable,
  scenarioControlsHtml,
  unverifiedNote,
} from './ui';

const STATUS_LABEL: Record<AlertStatus, string> = {
  open: 'Open',
  'inspection-scheduled': 'Inspection scheduled',
  confirmed: 'Fault confirmed on site',
  dismissed: 'Dismissed',
};

const STATUS_ORDER: readonly AlertStatus[] = ['open', 'inspection-scheduled', 'confirmed', 'dismissed'];

function alertCard(a: MaintenanceAlert): string {
  const options = STATUS_ORDER.map(
    (s) => `<option value="${s}" ${alertStatusOf(a.id) === s ? 'selected' : ''}>${STATUS_LABEL[s]}</option>`,
  ).join('');
  return `<article class="card">
    <div class="alert-head">
      <span class="pill check">${esc(a.flatId)} · ${esc(a.channelId.replace('ch-', 'Channel '))}</span>
      ${badge('hypothesis', 'Hypothesis · needs inspection')}
    </div>
    <h3>${esc(a.title)}</h3>
    <p>${esc(a.hypothesis)}</p>
    <div class="subhead">Evidence</div>
    ${evidenceList(a.evidence)}
    <div class="subhead">Checks before acting</div>
    ${plainList(a.checks)}
    <div class="owner">${badge('owner', a.owner)}</div>
    <label class="status-label" for="m-status-${a.id}">Status</label>
    <select id="m-status-${a.id}" data-alert="${a.id}">${options}</select>
    <p class="note">Any saving linked to this alert stays projected, even after a fault is confirmed, until a real before/after measurement exists.</p>
  </article>`;
}

export function mountManager(root: HTMLElement): void {
  const rows = FLATS.map((f) => {
    const kwh = totals(flatProfile(f)).kwh;
    return { flat: f, kwh };
  });
  const maxKwh = Math.max(...rows.map((r) => r.kwh));

  root.innerHTML = `
  <section class="hero">
    <div class="hero-text">
      <div class="eyebrow">Manager view</div>
      <h1>The whole portfolio, with its caveats.</h1>
      <p>Compare flats, follow up possible equipment issues and see what savings could look like, without mistaking a projection for a result.</p>
    </div>
  </section>

  <section class="panel" aria-labelledby="m-h-hist">
    <div class="panel-head"><h2 id="m-h-hist">Historical consumption across flats</h2>${badge('placeholder', 'Sample figures')}</div>
    <p class="lead">Four weeks per flat. Compare per resident and per m², not just totals.</p>
    <div class="table-wrap"><table class="data">
      <caption>Consumption by flat, 1–28 Oct 2026 (placeholder values)</caption>
      <thead><tr><th scope="col">Flat</th><th scope="col">Residents</th><th scope="col">Area</th><th scope="col">Total</th><th scope="col">Per resident</th><th scope="col">Per m²</th></tr></thead>
      <tbody>${rows
        .map(
          (r) => `<tr>
        <th scope="row">${r.flat.id}</th>
        <td>${r.flat.residents}</td>
        <td>${r.flat.areaM2} m²</td>
        <td><div class="inline-bar"><span style="width:${Math.round((r.kwh / maxKwh) * 100)}%"></span></div> ${fmt.num(r.kwh, 0)} kWh</td>
        <td>${fmt.num(r.kwh / r.flat.residents, 0)} kWh</td>
        <td>${fmt.num(r.kwh / r.flat.areaM2, 1)} kWh</td>
      </tr>`,
        )
        .join('')}</tbody>
    </table></div>
  </section>

  <section class="panel" aria-labelledby="m-h-opp">
    <div class="panel-head"><h2 id="m-h-opp">Maintenance and efficiency opportunities</h2>${badge('projected', 'Not verified')}</div>
    <div class="two-col">
      <div>
        <h3 class="col-title">Efficiency, mostly resident action</h3>
        <ul class="plain">
          <li><strong>Evening peak exposure.</strong> Flats with load concentrated in 15–18 UTC are candidates for timing nudges.</li>
          <li><strong>Overnight baseload.</strong> Flats with a high quiet-hour level are candidates for a walk-round.</li>
        </ul>
        <div class="owner">${badge('owner', 'Resident acts · manager sends the nudge')}</div>
      </div>
      <div>
        <h3 class="col-title">Maintenance, manager action</h3>
        <ul class="plain">
          <li><strong>Persistent draws.</strong> A channel that stays high may be equipment left on or faulty.</li>
          <li><strong>Step changes.</strong> A channel that jumps and stays may need an inspection.</li>
        </ul>
        <div class="owner">${badge('owner', 'Data team validates · manager inspects')}</div>
      </div>
    </div>
    <p class="note">Which flats and channels qualify is still to be computed. See the alerts below for the placeholder cases.</p>
  </section>

  <h2 class="section-title" id="m-h-al">Evidence-backed maintenance alerts</h2>
  <p class="lead">Alerts are hypotheses. Each one lists its evidence, the checks to do first and who is responsible. Nothing is a confirmed fault until someone has looked.</p>
  <p class="status-summary" id="m-alert-summary" aria-live="polite"></p>
  <section class="cards" aria-labelledby="m-h-al">${ALERTS.map(alertCard).join('')}</section>

  <section class="panel" aria-labelledby="m-h-port">
    <div class="panel-head"><h2 id="m-h-port">Portfolio-level conditional savings</h2>${badge('projected', 'Conditional · not verified')}</div>
    <p class="lead">What the portfolio might save <em>if</em> the chosen share of flats adopts the change.</p>
    ${scenarioControlsHtml('m')}
    <label for="m-adopt" id="m-adopt-label" class="range-label">Flats that adopt the change: ${state.adoptionPct}%</label>
    <input id="m-adopt" type="range" min="0" max="100" step="10" value="${state.adoptionPct}">
    <div id="m-port"></div>
  </section>

  <section class="panel" aria-labelledby="m-h-score">
    <div class="panel-head"><h2 id="m-h-score">Score comparison</h2>${badge('provisional', 'Provisional · not audited')}</div>
    <p class="lead">Placeholders only. The score stays provisional until the implementation has been audited, so no ranking is shown.</p>
    <div class="table-wrap"><table class="data">
      <caption>Score components by flat (no values yet)</caption>
      <thead><tr><th scope="col">Flat</th>${SCORE_COMPONENTS.map((c) => `<th scope="col">${esc(c.label)}</th>`).join('')}<th scope="col">Overall</th></tr></thead>
      <tbody>${FLATS.map(
        (f) =>
          `<tr><th scope="row">${f.id}</th>${SCORE_COMPONENTS.map(() => '<td class="dash">–</td>').join('')}<td class="dash">–</td></tr>`,
      ).join('')}</tbody>
    </table></div>
  </section>

  <section class="panel" aria-labelledby="m-h-dq">
    <div class="panel-head"><h2 id="m-h-dq">Data quality and responsibility</h2></div>
    <p class="lead">What is known to be imperfect in each source, how it is handled and who owns the follow-up.</p>
    <div class="table-wrap"><table class="data">
      <caption>Data sources, known issues and owners</caption>
      <thead><tr><th scope="col">Source</th><th scope="col">Known issues</th><th scope="col">Handling</th><th scope="col">Responsible</th><th scope="col">Status</th></tr></thead>
      <tbody>${DATA_SOURCES.map(
        (d) => `<tr>
        <th scope="row">${esc(d.file)}</th>
        <td>${esc(d.issues)}</td>
        <td>${esc(d.handling)}</td>
        <td>${badge('owner', d.owner)}</td>
        <td>${esc(d.status)}</td>
      </tr>`,
      ).join('')}</tbody>
    </table></div>
  </section>`;

  document.querySelectorAll<HTMLSelectElement>('select[data-alert]').forEach((sel) => {
    sel.addEventListener('change', () => {
      state.alertStatus[sel.dataset.alert ?? ''] = sel.value as AlertStatus;
      renderAlertSummary();
    });
  });
  bindScenarioControls('m', refreshPortfolio);
  const adopt = $<HTMLInputElement>('#m-adopt');
  adopt.addEventListener('input', () => {
    state.adoptionPct = Number(adopt.value);
    $('#m-adopt-label').textContent = `Flats that adopt the change: ${state.adoptionPct}%`;
    refreshPortfolio();
  });
  renderAlertSummary();
  refreshPortfolio();
}

function renderAlertSummary(): void {
  const counts: Record<AlertStatus, number> = { open: 0, 'inspection-scheduled': 0, confirmed: 0, dismissed: 0 };
  ALERTS.forEach((a) => {
    counts[alertStatusOf(a.id)] += 1;
  });
  $('#m-alert-summary').textContent = STATUS_ORDER.map((s) => `${STATUS_LABEL[s]}: ${counts[s]}`).join(' · ');
}

function refreshPortfolio(): void {
  const p = portfolioProjection(FLATS, state.scenario.id, state.scenario.sharePct, state.adoptionPct);
  $('#m-port').innerHTML =
    projectionTable(
      p,
      `All ${FLATS.length} flats, ${state.adoptionPct}% adopting, scenario at ${state.scenario.sharePct}%`,
    ) + unverifiedNote();
}

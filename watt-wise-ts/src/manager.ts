/** Manager view: all flats. Every number from GET /portfolio, /portfolio/findings, /workorders. */
import type { Finding, Portfolio } from './api/contracts';
import { byFinding, type WorkOrderView } from './api/workorders';
import { findingCard } from './components/findings';
import { textCard } from './components/textCard';
import { unavailable } from './api/texts';
import { $, esc } from './dom';
import * as F from './format';
import { api, state } from './state';
import { badge, details, emptyHtml, errorHtml, errorMessage, kv, loadInto, loadingHtml, plainList, statusBadge } from './ui';

function kpi(label: string, value: string, note = ''): string {
  return `<div class="kpi"><span class="kpi-label">${esc(label)}</span><span class="kpi-val">${esc(value)}</span>${note ? `<span class="note">${esc(note)}</span>` : ''}</div>`;
}

function overview(p: Portfolio): string {
  const t = p.totals;
  const pot = p.potential;
  return `<div class="kpis">
      ${kpi('Electricity, 8 flats', F.kwh(t.kwh, 1), '1–28 Oct 2026, measured')}
      ${kpi('Spot-price cost', F.sek(t.sek, 2), 'Energy part only, not a bill')}
      ${kpi('Emissions', F.co2(t.co2_kg, 2), 'Synthetic average factors')}
      ${kpi('Combined potential', F.kwh(pot.kwh, 1), `${F.sek(pot.sek_if_hourly_spot, 2)} if hourly spot · ${F.co2(pot.co2_kg, 2)}`)}
    </div>
    <p class="note">${badge('simulated', 'Simulated')} ${esc(pot.label)}. Each flat's findings are applied together on its hourly data, so nothing is counted twice.</p>`;
}

function flatTable(p: Portfolio): string {
  const max = Math.max(...p.flats.map((f) => f.kwh_28d), 1e-9);
  const rows = p.flats
    .map(
      (f) => `<tr>
      <th scope="row">${esc(f.flat_id)}</th>
      <td>${esc(String(f.residents))} · ${esc(String(f.floor_area_m2))} m²</td>
      <td><div class="inline-bar"><span style="width:${Math.round((f.kwh_28d / max) * 100)}%"></span></div>${esc(F.num(f.kwh_28d, 1))}</td>
      <td>${esc(F.num(f.sek_28d, 2))}</td>
      <td>${esc(F.num(f.co2_kg_28d, 2))}</td>
      <td>${esc(F.num(f.comparison.kwh_per_m2, 2))}</td>
      <td>${esc(F.num(f.comparison.explained_kwh_per_eq_resident_day, 2))}</td>
      <td><strong>${esc(F.score(f.apartment_score))}</strong> ${esc(f.apartment_band)} <span class="unit">#${esc(F.num(f.apartment_rank, 0))}</span></td>
      <td>${esc(F.score(f.resident_score))} ${esc(f.resident_band)}</td>
      <td>${esc(F.score(f.health))}</td>
      <td>${esc(F.num(f.comparison.possible_fault_kwh, 1))} / ${esc(F.num(f.comparison.possible_avoidable_kwh, 1))}</td>
      <td>${esc(String(f.open_manager_findings))} / ${esc(String(f.open_findings))}</td>
      <td>${esc(F.pct(f.coverage, 1))}</td>
    </tr>`,
    )
    .join('');
  return `<div class="table-wrap"><table class="data">
    <caption>Measured 1–28 Oct 2026. Context-adjusted: explained use per equivalent resident (√residents) per day.</caption>
    <thead><tr><th scope="col">Flat</th><th scope="col">Size</th><th scope="col">kWh</th><th scope="col">SEK spot</th><th scope="col">kg CO₂e</th><th scope="col">kWh/m²</th><th scope="col">kWh/eq. res./day</th><th scope="col">Apartment score</th><th scope="col">Resident score</th><th scope="col">Health</th><th scope="col">Possible fault / avoidable kWh</th><th scope="col">Open (manager / all)</th><th scope="col">Readings</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

function potentialTable(p: Portfolio): string {
  const rows = p.flats
    .map((f) => {
      const c = f.combined_potential;
      if (!c) return `<tr><th scope="row">${esc(f.flat_id)}</th><td colspan="5" class="dash">no findings</td></tr>`;
      return `<tr><th scope="row">${esc(f.flat_id)}</th><td>${esc(F.num(c.kwh, 2))}</td><td>${esc(F.num(c.sek_if_hourly_spot, 2))}</td><td>${esc(F.num(c.co2_kg, 3))}</td><td>${esc(
        F.score(f.apartment_score),
      )} → ${esc(F.score(c.score_after.apartment.score))}</td><td class="note">${esc(c.findings.join(', '))}</td></tr>`;
    })
    .join('');
  return `<div class="table-wrap"><table class="data compact"><thead><tr><th scope="col">Flat</th><th scope="col">kWh avoided</th><th scope="col">SEK if hourly spot</th><th scope="col">kg CO₂e</th><th scope="col">Apartment score</th><th scope="col">Findings applied</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function dataQuality(p: Portfolio): string {
  const q = p.data_quality;
  const ev = p.evidence_quality;
  return kv([
    ['Data source', esc(String(q.data_source))],
    ['Readings', `${esc(F.num(q.readings_rows ?? null, 0))} rows, ${esc(F.num(q.readings_missing_kwh ?? null, 0))} missing (kept missing, never 0)`],
    ['Hours without a spot price', esc(F.num(q.prices_missing_spot_hours ?? null, 0))],
    ['Occupancy / outdoor gaps', `${esc(F.num(q.context_occupancy_missing ?? null, 0))} / ${esc(F.num(q.context_outdoor_missing ?? null, 0))} hours`],
    ['Coverage by flat', Object.entries(q.coverage_by_flat).map(([k, v]) => `${esc(k)} ${esc(F.pct(v, 1))}`).join(' · ')],
    ['Findings by evidence level', Object.entries(ev.findings_by_status).map(([k, v]) => `${esc(k)}: ${esc(String(v))}`).join(' · ') + `<br><span class="note">${esc(ev.note)}</span>`],
    ['Peak hours (local)', esc(F.hourRanges(p.references.peak_hours_local))],
    ['Frozen references', `hash ${esc(p.references.hash)}`],
  ]);
}

function workOrderPanel(f: Finding, w: WorkOrderView | undefined, live: boolean): string {
  if (!live) return `<div class="wo"><div class="subhead">Work order</div><p class="note">Work orders change data on the backend and need live mode.</p></div>`;
  if (!w) {
    return `<div class="wo"><div class="subhead">Work order</div><p class="note">Opening a work order records the manager's confirmation of this finding.</p>
      <button class="btn inline" type="button" data-wo-create="${esc(f.id)}">Open work order</button><p class="form-status" role="status" aria-live="polite"></p></div>`;
  }
  const v = w.verification;
  return `<div class="wo"><div class="subhead">Work order ${esc(w.id)}</div><p><strong>${esc(w.statusLabel)}</strong>${w.simulated ? ` ${badge('simulated', 'SIMULATED post-repair data')}` : ''}</p>
    ${v ? `<p class="note">Verification: ${esc(v.status)}${v.saving_kwh != null ? `, saving ${esc(F.kwh(v.saving_kwh, 2))}` : ''}${v.reason ? ` (${esc(String(v.reason))})` : ''}</p>` : ''}
    <div class="row">${w.actions
      .map((a) =>
        a.kind === 'patch'
          ? `<button class="btn inline secondary" type="button" data-wo="${esc(w.id)}" data-wo-status="${esc(a.status)}">${esc(a.label)}</button>`
          : `<button class="btn inline secondary" type="button" data-wo-verify="${esc(w.id)}">${esc(a.label)}</button>`,
      )
      .join('')}</div><p class="form-status" role="status" aria-live="polite"></p></div>`;
}

export function mountManager(root: HTMLElement): void {
  root.innerHTML = `
  <section class="hero">
    <div class="hero-text">
      <div class="eyebrow">Manager view</div>
      <h1>The whole portfolio, with its caveats.</h1>
      <p>Compare flats, follow up possible equipment issues and see what acting on the findings could change, without mistaking a simulation for a result.</p>
    </div>
  </section>
  <nav class="jump" aria-label="On this page"><a href="#m-h-over">Overview</a><a href="#m-h-flats">Flats</a><a href="#m-h-maint">Maintenance</a><a href="#m-h-res">Resident actions</a><a href="#m-h-dq">Data quality</a></nav>

  <section class="panel" aria-labelledby="m-h-over">
    <div class="panel-head"><h2 id="m-h-over">Portfolio</h2>${badge('measured', 'Measured')}</div>
    <div id="m-over"></div>
  </section>

  <section class="panel" aria-labelledby="m-h-flats">
    <div class="panel-head"><h2 id="m-h-flats">Eight flats compared</h2>${badge('measured', 'From the engine')}</div>
    <div id="m-flats"></div>
    ${details('Combined potential per flat (simulated)', '<div id="m-pot"></div>')}
  </section>

  <h2 class="section-title" id="m-h-maint">Possible equipment issues</h2>
  <p class="lead">Findings the building manager is responsible for. “Possible fault” means a statistical test was met; it becomes confirmed only when someone checks it.</p>
  ${textCard(unavailable('finding_summary', 'manager'))}
  <section class="cards" id="m-maint" aria-labelledby="m-h-maint"></section>

  <section class="panel" aria-labelledby="m-h-res">
    <div class="panel-head"><h2 id="m-h-res">Resident-controlled opportunities</h2>${badge('owner', 'Residents act')}</div>
    <p class="lead">Behaviour patterns. Residents see these in their own view; no technician is needed.</p>
    <div id="m-res"></div>
  </section>

  <section class="panel" aria-labelledby="m-h-rep">
    <div class="panel-head"><h2 id="m-h-rep">Resident reports and notifications</h2></div>
    <div id="m-rep"></div>
  </section>

  <section class="panel" aria-labelledby="m-h-dq">
    <div class="panel-head"><h2 id="m-h-dq">Data quality and evidence</h2></div>
    <div id="m-dq"></div>
  </section>`;

  const A = api();
  const live = A.mode === 'live';

  void (async () => {
    const els = ['#m-over', '#m-flats', '#m-pot', '#m-dq'].map((s) => $(s));
    els.forEach((e) => (e.innerHTML = loadingHtml('portfolio')));
    try {
      const p = await A.portfolio();
      $('#m-over').innerHTML = overview(p);
      $('#m-flats').innerHTML = flatTable(p);
      $('#m-pot').innerHTML = potentialTable(p);
      $('#m-dq').innerHTML = dataQuality(p) + details('Assumptions', plainList(p.assumptions));
    } catch (e) {
      els.forEach((el) => (el.innerHTML = errorHtml(e, 'the portfolio')));
    }
  })();

  const maint = $('#m-maint');
  const renderMaint = async () => {
    maint.innerHTML = loadingHtml('maintenance findings');
    try {
      const [fs, wos] = await Promise.all([A.portfolioFindings({ responsibility: 'manager' }), A.workorders()]);
      const map = byFinding(wos);
      maint.innerHTML = fs.length
        ? fs.map((f) => findingCard(f, { audience: 'manager', tariff: { type: 'hourly_spot' }, actionsHtml: workOrderPanel(f, map.get(f.id), live) })).join('')
        : emptyHtml('No possible equipment issues were found.');
    } catch (e) {
      maint.innerHTML = errorHtml(e, 'maintenance findings');
    }
  };
  void renderMaint();

  void loadInto($('#m-res'), 'resident findings', async () => {
    const [r, u] = await Promise.all([A.portfolioFindings({ responsibility: 'resident' }), A.portfolioFindings({ responsibility: 'unknown' })]);
    return [...u, ...r];
  }, (fs) =>
    fs.length
      ? `<div class="table-wrap"><table class="data compact"><thead><tr><th scope="col">Flat</th><th scope="col">Finding</th><th scope="col">Status</th><th scope="col">kWh avoided</th><th scope="col">kWh moved</th><th scope="col">SEK if hourly spot</th><th scope="col">Window</th></tr></thead><tbody>${fs
          .map(
            (f) => `<tr><th scope="row">${esc(f.flat_id)}</th><td>${esc(f.title)}<br><span class="note">${esc(f.channel)} ${esc(f.assumed_type)}</span></td><td>${statusBadge(f.status, f.wording)}</td><td>${esc(
              f.avoidable_28d.kind === 'shift' ? '0 (shift)' : F.num(f.avoidable_28d.kwh, 2),
            )}</td><td>${esc(f.avoidable_28d.kind === 'shift' ? F.num(f.quantities.kwh_moved, 2) : '–')}</td><td>${esc(F.num(f.valuation.sek_if_hourly_spot, 2))}</td><td>${esc(F.days(f.avoidable_28d.window_days))}</td></tr>`,
          )
          .join('')}</tbody></table></div><p class="note">${badge('simulated', 'Simulated')} Potential if acted on fully. Shifts move electricity to other hours and save 0 kWh; their money value exists only on an hourly spot contract.</p>`
      : emptyHtml('No resident-controlled patterns.'),
  );

  void loadInto($('#m-rep'), 'reports', async () => ({ reports: await A.reports(), notes: await A.managerNotifications() }), ({ reports, notes }) =>
    (reports.length ? `<ul class="plain">${reports.map((r) => `<li>${esc(`${r.id} from ${r.flat_id} on ${r.finding_id}: ${r.message ?? '(no message)'}`)}</li>`).join('')}</ul>` : emptyHtml('No resident reports yet.')) +
    (notes.length ? `<div class="subhead">Notifications</div><ul class="plain">${notes.map((n) => `<li>${esc(n.text)}</li>`).join('')}</ul>` : ''),
  );

  root.addEventListener('click', async (e) => {
    const t = (e.target as HTMLElement).closest<HTMLButtonElement>('[data-wo-create],[data-wo],[data-wo-verify]');
    if (!t) return;
    const status = t.closest('.wo')?.querySelector<HTMLElement>('.form-status');
    t.disabled = true;
    if (status) status.textContent = 'Saving…';
    try {
      if (t.dataset.woCreate) await A.createWorkorder(t.dataset.woCreate, null);
      else if (t.dataset.wo) await A.patchWorkorder(t.dataset.wo, t.dataset.woStatus ?? '');
      else if (t.dataset.woVerify) await A.verifyWorkorder(t.dataset.woVerify, true);
      await renderMaint();
    } catch (err) {
      t.disabled = false;
      if (status) status.textContent = `Not saved: ${errorMessage(err)}`;
    }
  });
  void state;
}

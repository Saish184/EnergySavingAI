import { api } from './api';
import { $, esc, fmt } from './dom';
import type { Finding, Portfolio, PortfolioFlat, Text, WorkOrder, PortfolioOut } from './types';
import { RESP_LABEL, badge, claimsDetails, errorBox, kpi, skeleton, statusChip, textMeta } from './ui';

type Filter = 'maintenance' | 'all' | 'behaviour';
let filter: Filter = 'maintenance';

function bandPill(score: number, band: string): string {
  return `<span class="sc"><b>${fmt.num(score)}</b><span class="band band-${esc(band)}">${esc(band)}</span></span>`;
}

function flatsTable(p: Portfolio): string {
  const max = Math.max(...p.flats.map((r) => r.kwh_28d));
  const row = (r: PortfolioFlat) => `<tr>
    <th scope="row">${esc(r.flat_id)}<span class="unit"> · ${r.residents} res · ${r.floor_area_m2} m²</span></th>
    <td>${bandPill(r.apartment_score, r.apartment_band)}</td>
    <td>${bandPill(r.resident_score, r.resident_band)}</td>
    <td><div class="inline-bar"><span style="width:${Math.max(2, r.health)}%" class="${r.health < 90 ? 'warnbar' : ''}"></span></div>${fmt.num(r.health)}</td>
    <td><div class="inline-bar"><span style="width:${(r.kwh_28d / max) * 100}%"></span></div>${fmt.num(r.kwh_28d)} kWh</td>
    <td>${fmt.num(r.comparison.kwh_per_m2, 2)}</td>
    <td>${r.open_findings}${r.open_manager_findings ? ` <span class="badge hypothesis">${r.open_manager_findings} equipment</span>` : ''}</td>
    <td>${r.combined_potential ? `${fmt.num(r.combined_potential.kwh, 1)} kWh` : '–'}</td></tr>`;
  return `<div class="table-wrap"><table class="data">
    <caption>Apartment Performance includes possible equipment faults; Resident Actions does not. Bands A–G.</caption>
    <thead><tr><th>Flat</th><th>Apartment</th><th>Resident</th><th>Health</th><th>Use · 28 d</th><th>kWh / m²</th><th>Open findings</th><th>Combined potential</th></tr></thead>
    <tbody>${[...p.flats].sort((a, b) => a.apartment_rank - b.apartment_rank).map(row).join('')}</tbody></table></div>`;
}

function woControls(f: Finding, w?: WorkOrder): string {
  if (!f.triage?.maintenance) return `<span class="note">No technician needed: ${esc(f.triage?.reason ?? '')}</span>`;
  if (!w) return `<button class="btn-sm primary" data-open="${esc(f.id)}">Open work order</button>`;
  const steps = ['open', 'sent', 'repaired'];
  const prog = `<ol class="steps">${steps.map((s) => `<li class="${steps.indexOf(w.status) >= steps.indexOf(s) ? 'done' : ''}">${s}</li>`).join('')}</ol>`;
  const btn = (label: string, body: object, cls = '') => `<button class="btn-sm ${cls}" data-wo="${esc(w.id)}" data-body='${esc(JSON.stringify(body))}'>${label}</button>`;
  let b = '';
  if (w.status === 'closed_no_fault') return `${badge('muted', 'Closed: no fault found')}`;
  if (w.status === 'open') b += btn('Mark sent', { status: 'sent' });
  if ((w.status === 'open' || w.status === 'sent') && w.fault_found == null)
    b += btn('Technician: fault found', { fault_found: true }, 'primary') + btn('No fault', { fault_found: false });
  if (w.status === 'sent') b += btn('Mark repaired', { status: 'repaired' });
  if (w.status === 'repaired') b += `<button class="btn-sm primary" data-verify="${esc(w.id)}">Verify (simulated data)</button>`;
  return `<div class="wo"><span class="badge owner">${esc(w.id)}</span>${prog}${b}</div>`;
}

function mCard(f: Finding, w?: WorkOrder): string {
  const t = f.manager_text, o = t?.output;
  const a = f.avoidable_28d;
  return `<article class="fcard resp-${f.responsibility}">
    <div class="fcard-top"><div><h3>${esc(o?.headline ?? `${f.flat_id} · ${f.title}`)}</h3>
      <div class="chips">${statusChip(f)}${badge('owner', RESP_LABEL[f.responsibility])}
      ${f.triage?.maintenance ? badge('hypothesis', `maintenance · ${f.triage.priority}`) : badge('muted', 'not maintenance')}</div></div>
      <div class="fig-mini">${a.kind === 'shift' ? `${fmt.num(f.quantities.kwh_moved, 1)} kWh moved` : `${fmt.num(a.kwh, 1)} kWh`}<span>${fmt.num(a.sek, 1)} SEK if hourly · ${fmt.num(a.window_days)} d</span></div></div>
    <p class="fbody">${esc(o?.summary ?? '')}</p>
    ${o?.evidence_points?.length ? `<ul class="evidence">${o.evidence_points.map((e) => `<li>${esc(e)}</li>`).join('')}</ul>` : ''}
    ${o?.suggested_check ? `<p class="faction"><b>Check:</b> ${esc(o.suggested_check)}</p>` : ''}
    <div class="factions">${woControls(f, w)}${textMeta(t)}</div>
    ${claimsDetails(t)}
  </article>`;
}

function summaryPanel(p: Portfolio, s: Text<PortfolioOut>): string {
  const o = s.output, st = p.evidence_quality.findings_by_status;
  return `<section class="hero-grid">
    <div class="panel"><div class="eyebrow">Portfolio · 28 days</div><h2>${esc(o?.headline ?? 'Portfolio')}</h2>
      <ul class="digest-list">${(o?.bullets ?? []).map((b) => `<li>${esc(b)}</li>`).join('')}</ul>
      <p class="encourage">${esc(o?.maintenance_note ?? '')}</p>${textMeta(s)}</div>
    <div class="panel"><div class="kpis col2">
      ${kpi('Measured use', `${fmt.num(p.totals.kwh)} kWh`, `${fmt.num(p.totals.sek)} SEK spot · ${fmt.num(p.totals.co2_kg)} kg CO₂e`)}
      ${kpi('Simulated potential', `${fmt.num(p.potential.kwh, 1)} kWh`, `${fmt.num(p.potential.sek_if_hourly_spot)} SEK if hourly spot · not verified`, 'good')}
      ${Object.entries(st).map(([k, v]) => kpi(k.toLowerCase(), String(v), 'findings')).join('')}
    </div><p class="note">${esc(p.evidence_quality.note)}</p></div></section>`;
}

export async function mountManager(root: HTMLElement): Promise<void> {
  root.innerHTML = `<section class="hero"><div class="hero-text"><div class="eyebrow">Manager view</div>
    <h1>The whole portfolio, with its caveats.</h1><p>Which flats perform, which equipment needs a technician, and what is only a behaviour pattern for residents.</p></div></section>
    <div id="m-body">${skeleton()}</div>`;
  await refresh();
}

async function refresh(): Promise<void> {
  const body = $('#m-body');
  try {
    const [p, fs, s, wo] = await Promise.all([api.portfolio(), api.portfolioFindings(), api.portfolioSummary(), api.workorders()]);
    const shown = fs.filter((f) => filter === 'all' || (filter === 'maintenance' ? f.triage?.maintenance : !f.triage?.maintenance));
    const tab = (id: Filter, label: string, n: number) => `<button class="tab" data-filter="${id}" aria-pressed="${filter === id}">${label} <span class="count">${n}</span></button>`;
    body.innerHTML = `${summaryPanel(p, s)}
      <section class="panel"><div class="panel-head"><h2>Flats</h2>${badge('data', 'Engine scores · frozen references')}</div>${flatsTable(p)}</section>
      <div class="section-head"><h2 class="section-title">Findings</h2><div class="seg">
        ${tab('maintenance', 'Maintenance', fs.filter((f) => f.triage?.maintenance).length)}
        ${tab('behaviour', 'Residents', fs.filter((f) => !f.triage?.maintenance).length)}${tab('all', 'All', fs.length)}</div></div>
      <section class="fcards">${shown.map((f) => mCard(f, wo.find((w) => w.finding_id === f.id))).join('') || '<div class="panel">None.</div>'}</section>
      <p class="disclaimer">${esc(fs[0]?.manager_text?.disclaimer ?? '')}</p>`;
    body.querySelectorAll<HTMLButtonElement>('[data-filter]').forEach((b) => b.addEventListener('click', () => { filter = b.dataset.filter as Filter; void refresh(); }));
    body.querySelectorAll<HTMLButtonElement>('[data-open]').forEach((b) => b.addEventListener('click', () => act(b, () => api.openWorkorder(b.dataset.open!))));
    body.querySelectorAll<HTMLButtonElement>('[data-wo]').forEach((b) => b.addEventListener('click', () =>
      act(b, () => api.patchWorkorder(b.dataset.wo!, JSON.parse(b.dataset.body!)))));
    body.querySelectorAll<HTMLButtonElement>('[data-verify]').forEach((b) => b.addEventListener('click', () => act(b, async () => {
      const r = await api.verify(b.dataset.verify!);
      alert(`Verification with SIMULATED data: ${r.verification.status}\n${r.verification.reason}`);
    })));
  } catch (e) {
    body.innerHTML = errorBox(e);
  }
}

async function act(b: HTMLButtonElement, fn: () => Promise<unknown>): Promise<void> {
  b.disabled = true;
  try { await fn(); await refresh(); } catch (e) { alert(String((e as Error).message)); b.disabled = false; }
}

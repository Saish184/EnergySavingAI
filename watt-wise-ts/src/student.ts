/** Student view: one flat, every number from the backend (GET /flats/{id}/..., POST /flats/{id}/scenarios). */
import type { Breakdown, Finding, InterventionOptions, Profile, Scores } from './api/contracts';
import { studentFindingTexts, scoreExplanation, type TextView } from './api/texts';
import { channelBars, dailyChart, hourOfDayChart } from './components/charts';
import { findingCard } from './components/findings';
import { lensPanel, scoreDetails } from './components/score';
import { bindSimulator, simulatorHtml } from './components/simulator';
import { bindTariffSelector, tariffSelectorHtml } from './components/tariff';
import { textCard } from './components/textCard';
import { LIMITATIONS } from './data';
import { $, esc } from './dom';
import * as F from './format';
import { api, setTariff, state } from './state';
import { badge, details, emptyHtml, errorHtml, errorMessage, kv, loadInto, loadingHtml } from './ui';

function kpi(label: string, value: string, note = ''): string {
  return `<div class="kpi"><span class="kpi-label">${esc(label)}</span><span class="kpi-val">${esc(value)}</span>${note ? `<span class="note">${esc(note)}</span>` : ''}</div>`;
}

function overviewHtml(b: Breakdown): string {
  const t = b.totals;
  return `<div class="kpis">
      ${kpi('Electricity used', F.kwh(t.kwh, 1), `${F.kwh(t.kwh_per_m2, 2)} per m²`)}
      ${kpi('Spot-price cost', F.sek(t.sek, 2), 'Energy part only, not your bill')}
      ${kpi('Emissions', F.co2(t.co2_kg, 2), 'Synthetic average factors')}
      ${kpi('Readings observed', F.pct(t.coverage, 1), `${F.pct(t.price_coverage, 1)} of kWh has a spot price`)}
    </div>
    <p class="note">Measured over 1–28 Oct 2026 (28 days). Per resident: ${esc(F.kwh(t.kwh_per_resident, 1))}, ${esc(F.sek(t.sek_per_resident, 2))}, ${esc(
      F.co2(t.co2_kg_per_resident, 2),
    )} (${esc(b.per_resident_label)}). ${esc(F.pct(t.peak_share, 0))} of your electricity was used in peak-price hours.</p>
    ${details('How these numbers are measured', `<ul class="plain">${b.assumptions.map((a) => `<li>${esc(a)}</li>`).join('')}<li>${esc(b.uncertainty.note)}</li></ul>`)}`;
}

function reportForm(f: Finding): string {
  return `<form class="report" data-report="${esc(f.id)}" novalidate>
      <label for="rep-${esc(f.id)}">Tell the building manager (optional message)</label>
      <textarea id="rep-${esc(f.id)}" maxlength="500" rows="2" placeholder="e.g. the fridge door does not close properly"></textarea>
      <div class="row"><button class="btn inline secondary" type="submit">Report to the building manager</button>
      <button class="btn inline" type="button" data-sim="${esc(f.id)}">Simulate this</button></div>
      <p class="form-status" role="status" aria-live="polite"></p>
    </form>`;
}

export function mountStudent(root: HTMLElement, flatId: string): void {
  root.innerHTML = `
  <section class="hero">
    <div class="hero-text">
      <div class="eyebrow">Student view</div>
      <h1>Your flat, in plain numbers.</h1>
      <p>See when your flat uses electricity, what the data says could change, and how much to trust each number.</p>
    </div>
    <div class="picker"><span class="picker-label">Signed in for</span><strong class="flat-chip">${esc(flatId)}</strong></div>
  </section>
  <div class="viewing" id="s-meta"></div>
  <nav class="jump" aria-label="On this page"><a href="#s-h-over">Overview</a><a href="#s-h-find">Findings</a><a href="#s-h-sim">What if</a><a href="#s-h-score">Score</a><a href="#s-h-lim">Limits</a></nav>

  <section class="panel" aria-labelledby="s-h-over">
    <div class="panel-head"><h2 id="s-h-over">Your flat in numbers</h2>${badge('measured', 'Measured')}</div>
    <div id="s-over"></div>
  </section>

  <section class="panel" aria-labelledby="s-h-hist">
    <div class="panel-head"><h2 id="s-h-hist">When your flat uses electricity</h2>${badge('measured', 'Measured')}</div>
    <p class="lead">Average use per hour of the day (Stockholm time), with the expensive peak hours marked.</p>
    <div id="s-hours"></div>
    <div class="subhead big">Day by day</div>
    <div id="s-days"></div>
  </section>

  <section class="panel" aria-labelledby="s-h-ch">
    <div class="panel-head"><h2 id="s-h-ch">By appliance channel</h2>${badge('measured', 'Measured')}</div>
    <p class="lead">Seven channels per flat. The appliance names are inferred from how each channel uses power (*).</p>
    <div id="s-channels"></div>
  </section>

  <section class="panel" aria-labelledby="s-h-tariff">
    <div class="panel-head"><h2 id="s-h-tariff">Your electricity contract</h2></div>
    <p class="lead">The contract changes what a saving is worth in SEK. It never changes kWh or emissions.</p>
    ${tariffSelectorHtml('s', state.tariff)}
  </section>

  <h2 class="section-title" id="s-h-find">What the data found</h2>
  <p class="lead">Each finding states its evidence, who can act on it, and what acting on it could change. “Possible” and “consistent pattern” mean a statistical test was met. Nothing here is confirmed until a person checks it.</p>
  <div id="s-digest"></div>
  <section class="cards" id="s-findings" aria-labelledby="s-h-find"></section>

  <section class="panel" aria-labelledby="s-h-sim">
    <div class="panel-head"><h2 id="s-h-sim">What if…</h2>${badge('simulated', 'Simulated by the engine')}</div>
    <p class="lead">Pick a change. The engine recalculates your flat hour by hour and returns the result, including your score.</p>
    <div id="s-sim"></div>
  </section>

  <section class="panel" aria-labelledby="s-h-score">
    <div class="panel-head"><h2 id="s-h-score">Your sustainability score</h2>${badge('measured', 'From the engine')}</div>
    <div id="s-score"></div>
  </section>

  <section class="panel" aria-labelledby="s-h-notes">
    <div class="panel-head"><h2 id="s-h-notes">Notifications</h2></div>
    <div id="s-notes"></div>
  </section>

  <section class="panel" aria-labelledby="s-h-lim">
    <div class="panel-head"><h2 id="s-h-lim">Before you rely on a number</h2></div>
    <div class="limits">${LIMITATIONS.map((l) => `<div class="limit"><h3>${esc(l.title)}</h3><p>${esc(l.body)}</p></div>`).join('')}</div>
  </section>`;

  const A = api();
  let findings: Finding[] = [];
  let texts = new Map<string, TextView>();
  let sim: { select: (id: string) => void } | null = null;

  void loadInto($('#s-meta'), 'flat details', () => A.flats(), (fl) => {
    const f = fl.find((x) => x.flat_id === flatId);
    return f
      ? `Viewing <b>${esc(f.flat_id)}</b> · ${esc(String(f.residents))} residents · ${esc(String(f.floor_area_m2))} m² · price area ${esc(f.price_area)} · 1–28 Oct 2026 (synthetic data)`
      : errorHtml(new Error('unknown flat'), 'this flat');
  });
  void loadInto($('#s-over'), 'consumption', () => A.breakdown(flatId), overviewHtml);
  void loadInto($('#s-channels'), 'the channel breakdown', () => A.breakdown(flatId), (b) => channelBars(b.channels) + '<p class="note">* Inferred, not measured: the dataset has no appliance labels. Missing readings are shown per channel.</p>');
  void loadInto($('#s-hours'), 'the hourly profile', () => A.profile(flatId), (p: Profile) => hourOfDayChart(p));
  void loadInto($('#s-days'), 'daily use', () => A.profile(flatId), (p: Profile) => dailyChart(p));
  void loadInto($('#s-score'), 'your score', () => A.scores(flatId), (s: Scores) => scoreHtml(s));
  void loadInto($('#s-notes'), 'notifications', () => A.flatNotifications(flatId), (n) =>
    n.length ? `<ul class="plain">${n.map((x) => `<li>${esc(x.text)}</li>`).join('')}</ul>` : emptyHtml('No notifications.'),
  );
  $('#s-digest').innerHTML = '';

  const findingsEl = $('#s-findings');
  const renderFindings = () => {
    findingsEl.innerHTML = findings.length
      ? findings.map((f) => findingCard(f, { audience: 'student', tariff: state.tariff, text: texts.get(f.id), actionsHtml: reportForm(f) })).join('')
      : emptyHtml('No patterns were detected for your flat. That is good news.');
  };

  void (async () => {
    findingsEl.innerHTML = loadingHtml('findings');
    const simEl = $('#s-sim');
    simEl.innerHTML = loadingHtml('the simulator');
    try {
      findings = await A.findings(flatId);
    } catch (e) {
      findingsEl.innerHTML = errorHtml(e, 'findings');
      simEl.innerHTML = errorHtml(e, 'the simulator');
      return;
    }
    try {
      texts = await studentFindingTexts(A, flatId);
    } catch {
      texts = new Map(); // text is optional: cards still show every engine figure
    }
    renderFindings();
    let options: InterventionOptions;
    try {
      options = await A.interventions();
    } catch (e) {
      simEl.innerHTML = errorHtml(e, 'the simulator');
      return;
    }
    const deps = { api: A, flatId, findings, options, tariff: () => state.tariff };
    simEl.innerHTML = simulatorHtml(deps);
    sim = bindSimulator(simEl, deps);
  })();

  bindTariffSelector('s', root, (t) => {
    setTariff(t);
    if (findings.length) renderFindings();
  });

  root.addEventListener('click', (e) => {
    const b = (e.target as HTMLElement).closest<HTMLElement>('[data-sim]');
    if (b && sim) sim.select(b.dataset.sim ?? '');
  });

  root.addEventListener('submit', async (e) => {
    const form = (e.target as HTMLElement).closest<HTMLFormElement>('form[data-report]');
    if (!form) return;
    e.preventDefault();
    const id = form.dataset.report ?? '';
    const status = form.querySelector<HTMLElement>('.form-status');
    const btn = form.querySelector<HTMLButtonElement>('button[type=submit]');
    const msg = form.querySelector<HTMLTextAreaElement>('textarea')?.value.trim() || null;
    if (btn) btn.disabled = true;
    if (status) status.textContent = 'Sending…';
    try {
      const r = await A.report(flatId, id, msg);
      if (status) status.textContent = `Sent to the building manager (report ${r.id}).`;
    } catch (err) {
      if (status) status.textContent = `Not sent: ${errorMessage(err)}`;
    } finally {
      if (btn) btn.disabled = false;
    }
  });
}

function scoreHtml(s: Scores): string {
  return `${lensPanel(s.lenses.resident, 'resident')}
    <div id="s-score-text">${textCard({ kind: 'score_explanation', audience: 'student', state: 'unavailable', source: 'none', text: '', note: 'AI explanations of the score are not connected yet. The pillar notes above describe how each part is calculated.' })}</div>
    ${details('Apartment score (includes possible equipment faults you are not scored on)', lensPanel(s.lenses.apartment, 'apartment'))}
    ${scoreDetails(s)}
    ${kv([['Measured over', esc(s.horizon)]])}`;
}

// keep the adapter's async API referenced so future wiring is a one-line change
void scoreExplanation;

import { api } from './api';
import { $, esc, fmt } from './dom';
import { state } from './state';
import type { Breakdown, Finding, Scores, Tariff, Text, DigestOut } from './types';
import {
  RESP_LABEL, TARIFF_LABEL, badge, claimsDetails, dailyBars, errorBox, kpi, moneyFor, pillarRows, scoreRing, skeleton,
  statusChip, textMeta,
} from './ui';

const TYPE_ICON: Record<string, string> = {
  fault_step_change: '❄', base_load_outlier: '⏻', scheduled_block: '⏱', heater_pattern: '♨', peak_usage: '⇥',
};

function findingCard(f: Finding): string {
  const t = f.student_text, o = t?.output;
  const a = f.avoidable_28d, shift = a.kind === 'shift';
  const proj = f.projection_annual.sek;
  const cta = o?.cta === 'report' ? `<button class="btn-sm primary" data-report="${esc(f.id)}">Report to manager</button>`
    : o?.cta === 'confirm' ? `<button class="btn-sm" data-confirm="${esc(f.id)}">Confirm what it is</button>`
    : o?.cta === 'try' ? `<button class="btn-sm" data-try="${esc(f.id)}">Try it in the calculator</button>` : '';
  return `<article class="fcard resp-${f.responsibility}">
    <div class="fcard-top"><span class="ficon" aria-hidden="true">${TYPE_ICON[f.type] ?? '•'}</span>
      <div><h3>${esc(o?.headline ?? f.title)}</h3>
      <div class="chips">${statusChip(f)}${badge('placeholder', `${f.assumed_type} (assumed)`)}${badge('owner', RESP_LABEL[f.responsibility])}</div></div></div>
    <p class="fbody">${esc(o?.explanation ?? '')}</p>
    ${o?.action ? `<p class="faction"><b>Try this:</b> ${esc(o.action)}</p>` : ''}
    ${o?.question ? `<p class="fq">${esc(o.question)}</p>` : ''}
    <div class="figures">
      ${shift ? kpi('Moved to cheaper hours', `${fmt.num(f.quantities.kwh_moved, 1)} kWh`, 'same energy, other time')
        : kpi('Could be saved', `${fmt.num(a.kwh, 1)} kWh`, `over ${fmt.num(a.window_days)} days · if followed fully`)}
      ${kpi(TARIFF_LABEL[state.tariff], moneyFor(f, state.tariff), 'spot-energy part only')}
      ${kpi('CO₂e', `${fmt.num(a.co2_kg, 2)} kg`, 'synthetic factor')}
      ${kpi('Yearly', proj.value != null ? `${fmt.num(proj.low ?? 0)}–${fmt.num(proj.high ?? 0)} SEK` : 'not projected',
        proj.value != null ? 'projection, if hourly spot' : 'depends on weather / prices')}
    </div>
    <div class="factions">${cta}${textMeta(t)}</div>
    ${claimsDetails(t)}
    <details class="claims"><summary>Evidence</summary><p class="note">${esc(f.evidence.text)}</p><p class="note">${esc(f.counts_as)} · ${esc(f.valuation.label)}</p></details>
  </article>`;
}

function hero(sc: Scores, ex: Text | undefined, dg: Text<DigestOut>): string {
  const r = sc.lenses.resident, a = sc.lenses.apartment;
  const e = ex?.output as { summary?: string; next_step?: string } | undefined, d = dg.output;
  return `<section class="hero-grid">
    <div class="panel score-panel">
      <div class="eyebrow">Resident Actions score</div>
      <div class="score-row-top">${scoreRing(r.score, r.band)}
        <div class="score-side"><p class="score-sum">${esc(e?.summary ?? '')}</p>
        ${e?.next_step ? `<p class="next"><b>Next step:</b> ${esc(e.next_step)}</p>` : ''}
        <p class="note">Rank ${fmt.num(r.rank)} of ${r.of} · ${fmt.num(r.sensitivity.score_p5)}–${fmt.num(r.sensitivity.score_p95)} with other weightings</p></div></div>
      <div class="pillars">${pillarRows(r.pillars)}</div>
      <p class="note">Not counted for you: ${esc(r.excludes.join('; '))}. Whole-flat score incl. equipment: <b>${fmt.num(a.score)} ${esc(a.band)}</b>.</p>
      ${textMeta(ex)}
    </div>
    <div class="panel digest">
      <div class="eyebrow">Your 28 days</div>
      <h2>${esc(d?.headline ?? 'Overview')}</h2>
      <ol class="digest-list">${(d?.bullets ?? []).map((b) => `<li>${esc(b)}</li>`).join('')}</ol>
      <p class="encourage">${esc(d?.encouragement ?? '')}</p>
      ${textMeta(dg)}
    </div>
  </section>`;
}

function usage(b: Breakdown): string {
  const max = Math.max(...b.channels.map((c) => c.kwh));
  return `<section class="panel">
    <div class="panel-head"><h2>Where your electricity went</h2>${badge('data', 'Measured · 1–28 Oct')}</div>
    <div class="kpis">${kpi('Electricity', `${fmt.num(b.totals.kwh)} kWh`, '28 days')}${kpi('Spot cost', `${fmt.num(b.totals.sek)} SEK`, 'excl. VAT and fees')}
      ${kpi('CO₂e', `${fmt.num(b.totals.co2_kg, 1)} kg`)}${kpi('In peak hours', `${fmt.num(b.totals.peak_share * 100)} %`, 'share of kWh')}
      ${kpi('Per resident', `${fmt.num(b.totals.kwh_per_resident)} kWh`, 'flat average')}</div>
    <div class="two-col">
      <div><div class="subhead">Per day</div>${dailyBars(b.daily)}<p class="note">Darker bars are weekends.</p></div>
      <div><div class="subhead">By appliance (types are assumptions)</div>
        ${b.channels.map((c) => `<div class="chrow"><span>${esc(c.assumed_type)}</span><div class="chtrack"><div class="chfill" style="width:${(c.kwh / max) * 100}%"></div></div><span class="chval">${fmt.num(c.kwh, 1)} kWh</span></div>`).join('')}</div>
    </div></section>`;
}

function calculator(fs: Finding[]): string {
  if (!fs.length) return '';
  return `<section class="panel calc" id="calc">
    <div class="panel-head"><h2>What if?</h2>${badge('projected', 'Simulated by the engine · not verified')}</div>
    <p class="lead">Pick a finding and how much of the change you would really do. The engine re-runs the numbers; nothing here is calculated in the browser.</p>
    <div class="calc-row">
      <label class="field-inline">Finding<select id="c-f">${fs.map((f) => `<option value="${esc(f.id)}">${esc(f.title)} · ${esc(f.assumed_type)}</option>`).join('')}</select></label>
      <label class="field-inline">How much you’d do: <b id="c-a-l">100 %</b><input id="c-a" type="range" min="10" max="100" step="10" value="100"></label>
    </div>
    <div id="c-out" class="calc-out">${skeleton()}</div></section>`;
}

async function runCalc(): Promise<void> {
  const out = $('#c-out');
  const fid = $<HTMLSelectElement>('#c-f').value, adoption = Number($<HTMLInputElement>('#c-a').value) / 100;
  out.classList.add('busy');
  try {
    const r = await api.scenario(state.flatId, fid, adoption, state.tariff);
    const d = r.delta_28d, sek = r.valuation.sek_by_tariff[state.tariff];
    const b = r.before.resident.score, a = r.after.resident.score;
    out.innerHTML = `<div class="kpis">
      ${r.kind === 'shift' ? kpi('Energy', 'unchanged', 'a shift moves use, it does not cut it') : kpi('Energy', `${fmt.num(-d.kwh, 1)} kWh less`, `over ${fmt.num(r.window.days)} days`, 'good')}
      ${kpi(TARIFF_LABEL[state.tariff], sek == null ? '–' : `${fmt.num(sek, 1)} SEK`, 'spot-energy part only', 'good')}
      ${kpi('CO₂e', `${fmt.num(-d.co2_kg, 2)} kg less`)}
      ${kpi('Your score', `${fmt.num(b)} → <b>${fmt.num(a)}</b>`, `${esc(r.before.resident.band)} → ${esc(r.after.resident.band)}`, a > b ? 'good' : '')}
    </div><p class="note">Potential if you do ${fmt.num(adoption * 100)} % of it. A real saving needs measured data afterwards.</p>`;
  } catch (e) {
    out.innerHTML = `<p class="error">${esc(String((e as Error).message))}</p>`;
  } finally {
    out.classList.remove('busy');
  }
}

export async function mountStudent(root: HTMLElement): Promise<void> {
  const f = state.flatId;
  root.innerHTML = `<section class="hero"><div class="hero-text"><div class="eyebrow">Student view · ${esc(f)}</div>
    <h1>Your flat, in plain numbers.</h1><p>What your flat used, what the engine noticed, and what a small change could do. Every number is checked.</p></div>
    <div class="picker"><label class="picker-label" for="s-tariff">Your electricity contract</label>
    <select id="s-tariff">${(Object.keys(TARIFF_LABEL) as Tariff[]).map((t) => `<option value="${t}" ${t === state.tariff ? 'selected' : ''}>${TARIFF_LABEL[t]}</option>`).join('')}</select></div></section>
    <div id="s-body">${skeleton()}</div>`;
  $('#s-tariff').addEventListener('change', (e) => { state.tariff = (e.target as HTMLSelectElement).value as Tariff; void mountStudent(root); });
  try {
    const [sc, fs, dg, bd] = await Promise.all([api.scores(f), api.findings(f), api.digest(f), api.breakdown(f)]);
    $('#s-body').innerHTML = `${hero(sc, sc.explainer, dg)}
      <h2 class="section-title">What the engine noticed <span class="count">${fs.length}</span></h2>
      <p class="lead">Each card says how sure we are, who can act, and what it could be worth on <b>your</b> contract.</p>
      <section class="fcards">${fs.length ? fs.map(findingCard).join('') : '<div class="panel">Nothing unusual found for your flat. Nice.</div>'}</section>
      ${calculator(fs)}${usage(bd)}
      <p class="disclaimer">${esc(fs[0]?.student_text?.disclaimer ?? '')}</p>`;
    root.querySelectorAll<HTMLButtonElement>('[data-report]').forEach((b) => b.addEventListener('click', async () => {
      b.disabled = true;
      try { await api.report(f, b.dataset.report!); b.textContent = 'Reported ✓'; } catch { b.textContent = 'Could not report'; }
    }));
    root.querySelectorAll<HTMLButtonElement>('[data-confirm]').forEach((b) => b.addEventListener('click', () => {
      b.textContent = 'Thanks, noted'; b.disabled = true;
    }));
    root.querySelectorAll<HTMLButtonElement>('[data-try]').forEach((b) => b.addEventListener('click', () => {
      $<HTMLSelectElement>('#c-f').value = b.dataset.try!; void runCalc(); $('#calc').scrollIntoView({ behavior: 'smooth' });
    }));
    if (fs.length) {
      $('#c-f').addEventListener('change', () => void runCalc());
      let t = 0;
      $<HTMLInputElement>('#c-a').addEventListener('input', (e) => {
        $('#c-a-l').textContent = `${(e.target as HTMLInputElement).value} %`;
        clearTimeout(t); t = window.setTimeout(() => void runCalc(), 250);
      });
      void runCalc();
    }
  } catch (e) {
    $('#s-body').innerHTML = errorBox(e);
  }
}

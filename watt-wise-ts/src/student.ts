import { CHANNELS, FLATS, LIMITATIONS, PRICE, RECOMMENDATIONS, SCORE_COMPONENTS } from './data';
import { flatProfile, project, totals } from './calc';
import { $, esc, fmt, priceColor } from './dom';
import { state } from './state';
import type { Flat, Recommendation } from './types';
import {
  badge,
  bindScenarioControls,
  evidenceList,
  plainList,
  projectionTable,
  scenarioControlsHtml,
  unverifiedNote,
} from './ui';

const TAG_LABEL: Record<Recommendation['tag'], string> = {
  shift: 'Shift load',
  waste: 'Cut waste',
  check: 'Check equipment',
};

function currentFlat(): Flat {
  return FLATS.find((f) => f.id === state.flatId) ?? FLATS[0];
}

function recCard(r: Recommendation): string {
  return `<article class="card">
    <span class="pill ${r.tag}">${TAG_LABEL[r.tag]}</span>
    <h3>${esc(r.title)}</h3>
    <p>${esc(r.body)}</p>
    <div class="subhead">Evidence</div>
    ${evidenceList(r.evidence)}
    <div class="subhead">Assumptions</div>
    ${plainList(r.assumptions)}
    <div class="conf">Confidence: ${r.confidence === 'medium' ? 'medium' : 'low, needs a check'}</div>
  </article>`;
}

export function mountStudent(root: HTMLElement): void {
  root.innerHTML = `
  <section class="hero">
    <div class="hero-text">
      <div class="eyebrow">Student view</div>
      <h1>Your flat, in plain numbers.</h1>
      <p>See when your flat uses electricity, what small changes could do, and how much to trust each number.</p>
    </div>
    <div class="picker">
      <span class="picker-label">Signed in for</span>
      <strong class="flat-chip">${esc(state.flatId)}</strong>
    </div>
  </section>
  <p class="viewing" id="s-meta"></p>

  <section class="panel" aria-labelledby="s-h-hist">
    <div class="panel-head">
      <h2 id="s-h-hist">Historical consumption by channel</h2>
      ${badge('placeholder', 'Sample figures')}
    </div>
    <p class="lead">Average electricity per hour of the day, coloured by spot price. Times are UTC.</p>
    <div class="legend">
      <span><i class="swatch" style="background:var(--orange)"></i>Expensive hour</span>
      <span><i class="swatch" style="background:var(--mint)"></i>Normal</span>
      <span><i class="swatch" style="background:var(--green)"></i>Cheap hour</span>
    </div>
    <div class="bars" id="s-bars" role="img" aria-label="Average electricity use per hour of the day, coloured by price"></div>
    <div class="bar-labels" id="s-bar-labels" aria-hidden="true"></div>
    <div class="subhead big">Four weeks by channel</div>
    <div id="s-channels"></div>
    <p class="note">Channel names are generic because the data has no appliance types. The split between channels is a placeholder until the real readings are cleaned and summed.</p>
  </section>

  <section class="panel" aria-labelledby="s-h-scn">
    <div class="panel-head"><h2 id="s-h-scn">Potential savings scenarios</h2>${badge('projected', 'Projected')}</div>
    <p class="lead">Pick a change and see what it could do. Nothing here has been measured.</p>
    ${scenarioControlsHtml('s')}
  </section>

  <h2 class="section-title" id="s-h-rec">Recommendations and the evidence behind them</h2>
  <p class="lead">Each suggestion lists what supports it and what it assumes. Items marked as placeholders still wait for the real analysis.</p>
  <section class="cards" aria-labelledby="s-h-rec">${RECOMMENDATIONS.map(recCard).join('')}</section>

  <section class="panel" aria-labelledby="s-h-ba">
    <div class="panel-head"><h2 id="s-h-ba">Before and after: kWh, SEK, CO₂e</h2>${badge('projected', 'Projected · not verified')}</div>
    <div id="s-ba"></div>
  </section>

  <section class="panel" aria-labelledby="s-h-score">
    <div class="panel-head"><h2 id="s-h-score">Score components</h2>${badge('provisional', 'Provisional · not audited')}</div>
    <p class="lead">The score stays provisional until the implementation has been audited. These are placeholders for the components it might use.</p>
    <div class="score-list">${SCORE_COMPONENTS.map(
      (c) => `<div class="score-row">
        <div><strong>${esc(c.label)}</strong><div class="note">${esc(c.note)} · weight to be decided</div></div>
        <div class="hatch" aria-hidden="true"></div>
        <div class="score-val">– / 100</div>
      </div>`,
    ).join('')}</div>
  </section>

  <section class="panel" aria-labelledby="s-h-lim">
    <div class="panel-head"><h2 id="s-h-lim">Tariff and data limitations</h2></div>
    <p class="lead">Read these before relying on any number above.</p>
    <div class="limits">${LIMITATIONS.map(
      (l) => `<div class="limit"><h3>${esc(l.title)}</h3><p>${esc(l.body)}</p></div>`,
    ).join('')}</div>
  </section>`;

  bindScenarioControls('s', refreshProjection);
  refresh();
}

function refresh(): void {
  const flat = currentFlat();
  const profile = flatProfile(flat);
  const max = Math.max(...profile);

  $('#s-meta').innerHTML = `Viewing <b>${flat.id}</b> · ${flat.residents} residents · ${flat.areaM2} m² · 1–28 Oct 2026 · sample figures, not real results`;

  $('#s-bars').innerHTML = profile
    .map(
      (v, h) =>
        `<div class="bar" style="height:${Math.round((v / max) * 190)}px;background:${priceColor(PRICE[h])}" title="${fmt.hour(h)}:00 UTC, ${fmt.num(v, 2)} kWh, ${fmt.num(PRICE[h], 2)} SEK/kWh"></div>`,
    )
    .join('');
  $('#s-bar-labels').innerHTML = profile.map((_, h) => `<span>${h % 3 === 0 ? fmt.hour(h) : ''}</span>`).join('');

  const total = totals(profile).kwh;
  $('#s-channels').innerHTML = CHANNELS.map((c) => {
    const kwh = total * c.share;
    return `<div class="chrow">
      <span class="chname">${esc(c.label)}</span>
      <div class="chtrack"><div class="chfill" style="width:${Math.round((c.share / CHANNELS[0].share) * 100)}%"></div></div>
      <span class="chval">${fmt.num(kwh, 0)} kWh</span>
    </div>`;
  }).join('');

  refreshProjection();
}

function refreshProjection(): void {
  const profile = flatProfile(currentFlat());
  const p = project(profile, state.scenario.id, state.scenario.sharePct);
  $('#s-ba').innerHTML =
    projectionTable(p, `Typical four weeks for ${state.flatId}, scenario at ${state.scenario.sharePct}%`) +
    unverifiedNote() +
    (state.scenario.id === 'shift-evening'
      ? '<p class="note">Moving load keeps the same kWh. Only cost and, depending on the hour, carbon change.</p>'
      : '');
}

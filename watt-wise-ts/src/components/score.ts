/** Score panels. Scores, pillars, ranks and ranges are backend values; texts explain the documented method. */
import type { Lens, LensView, Scores } from '../api/contracts';
import { esc } from '../dom';
import * as F from '../format';
import { details, kv, plainList } from '../ui';

export const PILLAR_TEXT: Record<string, { name: string; text: string }> = {
  use: {
    name: 'Use',
    text: 'Explained electricity per equivalent resident per day, compared with a frozen benchmark (the 20th percentile of the 8 flats at baseline). 100 = at or below the benchmark.',
  },
  waste: {
    name: 'Waste',
    text: 'Possible avoidable use found by the detectors (always-on load, fixed-hour use while nobody is home, heating while away). 100 = none found; 50 = as much as a typical flat uses in total.',
  },
  timing: {
    name: 'Timing',
    text: 'Washing-machine-like and dishwasher-like runs in peak-price hours. Moving them later raises this pillar without changing kWh.',
  },
  health: {
    name: 'Health',
    text: 'Possible equipment faults (apartment score only). Residents are not scored on it.',
  },
};

function pillarRows(v: LensView): string {
  return Object.entries(v.pillars)
    .map(([k, val]) => {
      const p = PILLAR_TEXT[k] ?? { name: k, text: '' };
      const w = v.weights[k];
      return `<div class="score-row">
        <div><strong>${esc(p.name)}</strong> <span class="unit">weight ${esc(F.num((w ?? 0) * 100, 0))} %</span><div class="note">${esc(p.text)}</div></div>
        <div class="meter" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${esc(F.num(val, 1))}" aria-label="${esc(p.name)} pillar"><span style="width:${Math.max(0, Math.min(100, val))}%"></span></div>
        <div class="score-val">${esc(F.score(val))}</div>
      </div>`;
    })
    .join('');
}

export function lensPanel(v: LensView, lens: Lens): string {
  const s = v.sensitivity;
  return `<div class="score-head">
      <div class="big-score"><span class="score-num">${esc(F.score(v.score))}</span><span class="band band-${esc(v.band)}">${esc(v.band)}</span></div>
      <div>
        <strong>${esc(v.label)}</strong>
        <p class="note">Rank ${esc(F.num(v.rank, 0))} of ${esc(String(v.of))}. With other reasonable weights: score ${esc(F.range(s.score_p5, s.score_p95, '', 1))}, rank ${esc(F.num(s.rank_p5, 0))}–${esc(F.num(s.rank_p95, 0))}.</p>
        <p class="note">${lens === 'resident' ? 'Counts only what residents control.' : 'How the flat performs, including possible equipment faults.'}${
          v.excludes.length ? ` Excludes: ${esc(v.excludes.join('; '))}.` : ''
        }</p>
      </div>
    </div>
    <div class="score-list">${pillarRows(v)}</div>`;
}

export function scoreDetails(s: Scores): string {
  const b = s.benchmark;
  const d = s.pillar_detail;
  return (
    details(
      'What the score is built from',
      kv([
        ['Your explained use', `${esc(F.num(b.flat_value_resident_lens, 3))} kWh per equivalent resident per day (resident score)`],
        ['Benchmark', `${esc(F.num(b.benchmark_value_resident_lens, 3))} kWh (frozen ${esc(String(b.percentile))}th percentile of the 8 flats)`],
        ['Possible avoidable use', esc(F.kwh(d.possible_avoidable_kwh, 1))],
        ['Possible equipment fault', `${esc(F.kwh(d.possible_fault_kwh, 1))} (apartment score only)`],
        ['Flexible runs in peak hours', esc(F.kwh(d.peak_flexible_kwh, 1))],
        ['Data coverage', esc(F.pct(s.uncertainty.data_coverage, 1))],
      ]) + `<p class="note">${esc(s.uncertainty.method)}. References hash ${esc(b.references_hash)}.</p>`,
    ) + details('Score assumptions', plainList(s.assumptions))
  );
}

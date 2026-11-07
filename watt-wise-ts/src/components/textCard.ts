/** Explanatory text card for AI-worded or template text (see api/texts.ts). Shows its source and never a number of its own. */
import type { TextView } from '../api/texts';
import { esc } from '../dom';
import { badge } from '../ui';

const TITLE: Record<TextView['kind'], string> = {
  finding: 'In plain words',
  finding_summary: 'Summary for the manager',
  digest: 'Your week in brief',
  score_explanation: 'What your score means',
};

export function textCard(t: TextView): string {
  if (t.state === 'unavailable') {
    return `<div class="textcard unavailable"><div class="textcard-head"><strong>${esc(TITLE[t.kind])}</strong>${badge('placeholder', 'Not connected yet')}</div><p class="note">${esc(t.note)}</p></div>`;
  }
  const b = t.source === 'llm' ? badge('data', 'AI-worded · numbers from the engine') : badge('placeholder', 'Standard wording');
  return `<div class="textcard"><div class="textcard-head"><strong>${esc(TITLE[t.kind])}</strong>${b}</div><p>${esc(t.text)}</p><p class="note">${esc(t.note)}</p></div>`;
}

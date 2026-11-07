/** Explanatory text card for validated AI or standard wording (see api/texts.ts). Shows its source; adds no numbers. */
import type { TextView } from '../api/texts';
import { esc } from '../dom';
import { badge, details } from '../ui';

const TITLE: Record<TextView['kind'], string> = {
  finding: 'In plain words',
  finding_summary: 'Summary for the manager',
  digest: 'Your 28 days in brief',
  score_explanation: 'What your score means',
  portfolio_summary: 'Portfolio in brief',
};

function sourceBadge(t: TextView): string {
  if (t.source === 'llm') return badge('data', 'AI explanation · checked');
  if (t.source === 'safe') return badge('placeholder', 'Safe short wording');
  return badge('placeholder', 'Standard explanation');
}

export function textCard(t: TextView, opts: { heading?: string; showClaims?: boolean } = {}): string {
  const heading = opts.heading ?? TITLE[t.kind];
  if (t.state === 'unavailable') {
    return `<div class="textcard unavailable"><div class="textcard-head"><strong>${esc(heading)}</strong>${badge('placeholder', 'No text available')}</div><p class="note">${esc(t.note)}</p></div>`;
  }
  const claims = opts.showClaims && t.claims.length
    ? details(
        'Where the numbers in this text come from',
        `<ul class="plain">${t.claims
          .map((c) => `<li><code>${esc(c.source)}</code>: ${esc(String(c.value ?? ''))} ${esc(c.unit ?? '')}${c.period ? `, ${esc(c.period)}` : ''}${c.tariff ? `, ${esc(c.tariff)}` : ''} (${esc(c.category)})</li>`)
          .join('')}</ul>`,
      )
    : '';
  return `<div class="textcard">
    <div class="textcard-head"><strong>${esc(heading)}</strong>${sourceBadge(t)}</div>
    ${t.title && t.kind !== 'finding' ? `<p class="textcard-title">${esc(t.title)}</p>` : ''}
    ${t.paragraphs.map((p) => `<p>${esc(p)}</p>`).join('')}
    ${t.bullets.length ? `<ul class="plain">${t.bullets.map((b) => `<li>${esc(b)}</li>`).join('')}</ul>` : ''}
    ${t.action ? `<p><strong>${t.audience === 'manager' ? 'Suggested check:' : 'Next step:'}</strong> ${esc(t.action)}</p>` : ''}
    ${t.question ? `<p class="question"><strong>Question for you:</strong> ${esc(t.question)}</p>` : ''}
    <p class="note">${esc(t.note)}${t.pending ? ' An AI version is being prepared and will appear on a later visit.' : ''}</p>
    ${claims}
  </div>`;
}

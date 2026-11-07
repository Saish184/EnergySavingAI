/**
 * Explanatory-text adapter (the seam for Saish's LLM layer).
 *
 * Today the backend (mina) offers one text endpoint: GET /flats/{id}/tips (an LLM rewording when a key is set,
 * otherwise a deterministic template; `source` says which). Manager summaries, digests and score explanations
 * have NO backend endpoint yet, so they resolve to an explicit 'unavailable' state - never to invented text.
 *
 * When Saish's contract is final (e.g. finding.student_text / manager_text, scores.explainer, /digest), map it in
 * the functions below; the TextCard component and the screens stay unchanged.
 */
import type { Api } from './client';
import type { Tip } from './contracts';

export type TextAudience = 'student' | 'manager';
export type TextKind = 'finding' | 'finding_summary' | 'digest' | 'score_explanation';

export interface TextView {
  kind: TextKind;
  audience: TextAudience;
  state: 'ok' | 'unavailable';
  /** 'llm' = AI-worded from engine numbers; 'template' = fixed wording from engine numbers. */
  source: 'llm' | 'template' | 'none';
  text: string;
  note: string;
}

export function fromTip(t: Tip): TextView {
  const src = t.source === 'llm' ? 'llm' : 'template';
  return {
    kind: 'finding',
    audience: 'student',
    state: 'ok',
    source: src,
    text: t.text,
    note: src === 'llm' ? 'AI-worded text. Every number in it comes from the engine.' : 'Standard wording filled with engine numbers.',
  };
}

export function unavailable(kind: TextKind, audience: TextAudience): TextView {
  return {
    kind,
    audience,
    state: 'unavailable',
    source: 'none',
    text: '',
    note: 'AI explanations for this view are not connected yet. The figures below come directly from the engine.',
  };
}

/** Student finding texts keyed by finding id (backend returns them for the flat's top findings only). */
export async function studentFindingTexts(api: Api, flatId: string): Promise<Map<string, TextView>> {
  const tips = await api.tips(flatId);
  return new Map(tips.map((t) => [t.finding_id, fromTip(t)]));
}

export async function managerFindingSummary(): Promise<TextView> {
  return unavailable('finding_summary', 'manager');
}

export async function studentDigest(): Promise<TextView> {
  return unavailable('digest', 'student');
}

export async function scoreExplanation(): Promise<TextView> {
  return unavailable('score_explanation', 'student');
}

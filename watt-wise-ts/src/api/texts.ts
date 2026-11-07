/**
 * Explanatory-text adapter for Saish's LLM layer (backend/app/llm, prompt v2).
 *
 * The backend returns validated text objects: student_text on each finding, explainer on /scores,
 * /flats/{id}/digest, manager_text (+ triage) on /portfolio/findings and /portfolio/summary. Every number inside
 * them was inserted by the backend from engine fields (`claims`); the model never writes digits. `source` says
 * whether the wording is AI-written (llm), our validated standard wording (template) or a safe fallback.
 *
 * This file only maps those objects to one view model for TextCard. A missing or unavailable text becomes an
 * explicit 'unavailable' state; nothing is invented and no page waits on a provider.
 */
import type {
  DigestText,
  FindingManagerText,
  FindingStudentText,
  PortfolioSummaryText,
  ScoreExplainerText,
  TextClaim,
  TextObject,
} from './contracts';

export type TextAudience = 'student' | 'manager';
export type TextKind = 'finding' | 'finding_summary' | 'digest' | 'score_explanation' | 'portfolio_summary';

export interface TextView {
  kind: TextKind;
  audience: TextAudience;
  state: 'ok' | 'unavailable';
  source: 'llm' | 'template' | 'safe' | 'none';
  /** Short heading (may be empty) */
  title: string;
  paragraphs: string[];
  bullets: string[];
  action: string;
  question: string;
  claims: TextClaim[];
  /** pending: an AI version is being generated in the background; the standard wording is shown meanwhile */
  pending: boolean;
  disclaimer: string;
  note: string;
}

function base(kind: TextKind, audience: TextAudience, t: TextObject<unknown> | undefined | null): TextView | null {
  if (!t || !t.output || t.status === 'unavailable') return null;
  const src = t.source === 'llm' ? 'llm' : t.source === 'safe' ? 'safe' : 'template';
  return {
    kind,
    audience,
    state: 'ok',
    source: src,
    title: '',
    paragraphs: [],
    bullets: [],
    action: '',
    question: '',
    claims: t.claims ?? [],
    pending: t.llm_status === 'pending',
    disclaimer: t.disclaimer ?? '',
    note:
      src === 'llm'
        ? 'Written by the AI layer and checked by the validator. Every number in it was inserted from the engine.'
        : src === 'safe'
          ? 'Short safe wording: the detailed text could not be validated.'
          : 'Standard wording filled in with the engine’s numbers.',
  };
}

export function unavailable(kind: TextKind, audience: TextAudience, why = 'No explanation is available for this right now.'): TextView {
  return {
    kind, audience, state: 'unavailable', source: 'none', title: '', paragraphs: [], bullets: [], action: '', question: '',
    claims: [], pending: false, disclaimer: '', note: `${why} The figures shown come directly from the engine.`,
  };
}

export function studentFinding(t: TextObject<FindingStudentText> | undefined): TextView {
  const v = base('finding', 'student', t);
  if (!v || !t?.output) return unavailable('finding', 'student');
  const o = t.output;
  return { ...v, title: o.headline, paragraphs: [o.explanation].filter(Boolean), action: o.action, question: o.question };
}

export function managerFinding(t: TextObject<FindingManagerText> | undefined): TextView {
  const v = base('finding_summary', 'manager', t);
  if (!v || !t?.output) return unavailable('finding_summary', 'manager');
  const o = t.output;
  return { ...v, title: o.headline, paragraphs: [o.summary].filter(Boolean), bullets: o.evidence_points ?? [], action: o.suggested_check };
}

export function scoreExplainer(t: TextObject<ScoreExplainerText> | undefined): TextView {
  const v = base('score_explanation', 'student', t);
  if (!v || !t?.output) return unavailable('score_explanation', 'student');
  const o = t.output;
  return { ...v, paragraphs: [o.summary].filter(Boolean), action: o.next_step };
}

export function digest(t: TextObject<DigestText> | undefined): TextView {
  const v = base('digest', 'student', t);
  if (!v || !t?.output) return unavailable('digest', 'student');
  const o = t.output;
  return { ...v, title: o.headline, bullets: o.bullets ?? [], paragraphs: [o.encouragement].filter(Boolean) };
}

export function portfolioSummary(t: TextObject<PortfolioSummaryText> | undefined): TextView {
  const v = base('portfolio_summary', 'manager', t);
  if (!v || !t?.output) return unavailable('portfolio_summary', 'manager');
  const o = t.output;
  return { ...v, title: o.headline, bullets: o.bullets ?? [], paragraphs: [o.maintenance_note].filter(Boolean) };
}

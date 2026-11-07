import type { Session } from './types';

/**
 * DEMO AUTH. This runs in the browser, so it cannot protect anything.
 * Before real use, replace loginManager with a call to a server that checks
 * the password and returns a signed session, and enforce roles on the server.
 */
export const DEMO_MODE = true;

const STORAGE_KEY = 'wattwise.session';
export const MIN_PASSWORD_LENGTH = 8;

export type StudentResult = { ok: true; session: Session } | { ok: false; message: string };
export type ManagerResult =
  | { ok: true; session: Session }
  | { ok: false; field: 'email' | 'password'; message: string };

/** Accepts "3", "03", "F3", "f003" and returns "F003" if it is one of `known` (from GET /flats), else null. */
export function parseFlatNumber(input: string, known: readonly string[]): string | null {
  const m = /^\s*f?\s*0*(\d{1,3})\s*$/i.exec(input);
  if (!m) return null;
  const id = `F${m[1].padStart(3, '0')}`;
  return known.includes(id) ? id : null;
}

export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export function loginStudent(input: string, known: readonly string[]): StudentResult {
  if (input.trim() === '') return { ok: false, message: 'Enter your flat number.' };
  const flatId = parseFlatNumber(input, known);
  if (!flatId) {
    const range = known.length ? ` (${known[0]} to ${known[known.length - 1]})` : '';
    return { ok: false, message: `We could not find that flat. Try a number like 3 or F003${range}.` };
  }
  return { ok: true, session: { role: 'student', flatId } };
}

/** Demo only: accepts any well-formed email and a password of at least 8 characters. */
export async function loginManager(email: string, password: string): Promise<ManagerResult> {
  const cleanEmail = email.trim().toLowerCase();
  if (cleanEmail === '') return { ok: false, field: 'email', message: 'Enter your email address.' };
  if (!isValidEmail(cleanEmail)) {
    return { ok: false, field: 'email', message: 'That does not look like an email address.' };
  }
  if (password === '') return { ok: false, field: 'password', message: 'Enter your password.' };
  if (password.length < MIN_PASSWORD_LENGTH) {
    return {
      ok: false,
      field: 'password',
      message: `Passwords have at least ${MIN_PASSWORD_LENGTH} characters.`,
    };
  }
  return { ok: true, session: { role: 'manager', email: cleanEmail } };
}

/* ---------- session storage (cleared when the tab closes) ---------- */

export function saveSession(session: Session): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    /* storage can be blocked; the user just has to sign in again after a reload */
  }
}

export function clearSession(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export function loadSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data: unknown = JSON.parse(raw);
    if (typeof data !== 'object' || data === null) return null;
    const d = data as Record<string, unknown>;
    if (d.role === 'student' && typeof d.flatId === 'string' && /^F\d{3}$/.test(d.flatId)) {
      return { role: 'student', flatId: d.flatId };
    }
    if (d.role === 'manager' && typeof d.email === 'string' && isValidEmail(d.email)) {
      return { role: 'manager', email: d.email };
    }
    return null;
  } catch {
    return null;
  }
}

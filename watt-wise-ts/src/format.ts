/**
 * The only place for units, rounding and time-zone presentation. Rounding is presentation only:
 * every value comes from the backend. null/undefined/NaN is shown as "not available", never as 0.
 */
import type { Tariff } from './api/contracts';

export const TZ = 'Europe/Stockholm';
export const NA = 'not available';

function ok(n: number | null | undefined): n is number {
  return typeof n === 'number' && Number.isFinite(n);
}

export function num(n: number | null | undefined, digits = 0): string {
  if (!ok(n)) return NA;
  const r = Number(n.toFixed(digits));
  return (Object.is(r, -0) ? 0 : r).toLocaleString('en-GB', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Signed with a real minus sign; −0.0 is shown as 0. */
export function signed(n: number | null | undefined, digits = 1): string {
  if (!ok(n)) return NA;
  const r = Number(n.toFixed(digits));
  if (r === 0) return num(0, digits);
  return (r > 0 ? '+' : '−') + num(Math.abs(r), digits);
}

export const kwh = (n: number | null | undefined, d = 1) => (ok(n) ? `${num(n, d)} kWh` : NA);
export const sek = (n: number | null | undefined, d = 2) => (ok(n) ? `${num(n, d)} SEK` : NA);
export const co2 = (n: number | null | undefined, d = 2) => (ok(n) ? `${num(n, d)} kg CO₂e` : NA);
export const pct = (fraction: number | null | undefined, d = 0) => (ok(fraction) ? `${num(fraction * 100, d)} %` : NA);
export const score = (n: number | null | undefined) => (ok(n) ? num(n, 1) : NA);

export function range(lo: number | null | undefined, hi: number | null | undefined, unit: string, d = 1): string {
  if (!ok(lo) || !ok(hi)) return NA;
  return `${num(lo, d)}–${num(hi, d)} ${unit}`;
}

/** Backend timestamps are UTC ISO strings, sometimes "2026-10-15 00:00:00+00:00". */
export function parseUtc(s: string): Date {
  const t = s.includes('T') ? s : s.replace(' ', 'T');
  const d = new Date(t);
  if (Number.isNaN(d.getTime())) throw new Error(`bad timestamp ${s}`);
  return d;
}

export function localDateTime(isoUtc: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: TZ,
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(parseUtc(isoUtc));
}

export function localDate(isoUtc: string): string {
  return new Intl.DateTimeFormat('en-GB', { timeZone: TZ, day: 'numeric', month: 'short', year: 'numeric' }).format(parseUtc(isoUtc));
}

/** A plain calendar date "2026-10-25" (already local) -> "Sun 25 Oct". */
export function calendarDate(ymd: string): string {
  const [y, m, d] = ymd.split('-').map(Number);
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short' }).format(
    new Date(Date.UTC(y, m - 1, d)),
  );
}

export const hour = (h: number) => `${String(h).padStart(2, '0')}:00`;

/** [7,8,9,17,18,19,20] -> "07:00–10:00 and 17:00–21:00" (local clock time). */
export function hourRanges(hours: readonly number[]): string {
  const s = [...hours].sort((a, b) => a - b);
  const runs: [number, number][] = [];
  for (const h of s) {
    const last = runs[runs.length - 1];
    if (last && h === last[1] + 1) last[1] = h;
    else runs.push([h, h]);
  }
  const parts = runs.map(([a, b]) => `${hour(a)}–${hour((b + 1) % 24)}`);
  return parts.length <= 1 ? (parts[0] ?? 'none') : `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
}

export const TARIFF_LABEL: Record<Tariff, string> = {
  hourly_spot: 'Hourly spot price',
  monthly_average_spot: 'Monthly average spot price',
  fixed_price: 'Fixed price',
  included_in_rent: 'Electricity included in rent',
  unknown: 'I don’t know my contract',
};

export const MONEY_NOTE = 'Spot-energy component only (excl. VAT, network fee, energy tax, markup and fixed fees). Not a bill.';

/** "fridge-like" -> "fridge-like appliance (assumed)". Identities are inferred, never measured. */
export function appliance(assumedType: string): string {
  return assumedType.endsWith('-like') ? `${assumedType} appliance` : assumedType;
}

export function days(n: number | null | undefined): string {
  if (!ok(n)) return NA;
  return `${num(n, Number.isInteger(n) ? 0 : 1)} day${n === 1 ? '' : 's'}`;
}

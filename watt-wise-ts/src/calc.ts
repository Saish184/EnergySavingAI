import { BASE_PROFILE, CARBON, DAYS, PRICE } from './data';
import type { Flat, Projection, ScenarioId, Totals } from './types';

/** Share of the planned change that really happens. A stated assumption, shown to the user. */
export const ADHERENCE_LOW = 0.5;
export const ADHERENCE_HIGH = 1.0;

const SOURCE_HOURS = [15, 16, 17];
const DEST_HOURS = [22, 23, 0, 1, 2, 3];
const NIGHT_HOURS = [0, 1, 2, 3, 4];

/** Typical-day kWh per hour for a flat (placeholder model). */
export function flatProfile(flat: Flat): number[] {
  return BASE_PROFILE.map((v, h) => v * (flat.residents / 2) + (NIGHT_HOURS.includes(h) ? flat.nightExtraKwh : 0));
}

/** Totals over the whole window, from a typical-day profile. Spot cost excludes VAT. */
export function totals(profile: readonly number[]): Totals {
  let kwh = 0;
  let sek = 0;
  let co2kg = 0;
  profile.forEach((v, h) => {
    kwh += v * DAYS;
    sek += v * DAYS * PRICE[h];
    co2kg += (v * DAYS * CARBON[h]) / 1000;
  });
  return { kwh, sek, co2kg };
}

function applyScenario(profile: readonly number[], id: ScenarioId, sharePct: number, adherence: number): number[] {
  const out = [...profile];
  const f = (sharePct / 100) * adherence;
  if (id === 'shift-evening') {
    let moved = 0;
    for (const h of SOURCE_HOURS) {
      const delta = profile[h] * f;
      out[h] -= delta;
      moved += delta;
    }
    for (const h of DEST_HOURS) out[h] += moved / DEST_HOURS.length;
  } else {
    for (const h of NIGHT_HOURS) out[h] -= profile[h] * f;
  }
  return out;
}

function diff(after: Totals, before: Totals): Totals {
  return { kwh: after.kwh - before.kwh, sek: after.sek - before.sek, co2kg: after.co2kg - before.co2kg };
}

function scale(t: Totals, k: number): Totals {
  return { kwh: t.kwh * k, sek: t.sek * k, co2kg: t.co2kg * k };
}

function add(a: Totals, b: Totals): Totals {
  return { kwh: a.kwh + b.kwh, sek: a.sek + b.sek, co2kg: a.co2kg + b.co2kg };
}

const ZERO: Totals = { kwh: 0, sek: 0, co2kg: 0 };

/** Projected change for one flat. Always a projection, never a measurement. */
export function project(profile: readonly number[], id: ScenarioId, sharePct: number): Projection {
  const before = totals(profile);
  return {
    before,
    low: diff(totals(applyScenario(profile, id, sharePct, ADHERENCE_LOW)), before),
    high: diff(totals(applyScenario(profile, id, sharePct, ADHERENCE_HIGH)), before),
  };
}

/** Conditional portfolio estimate: "if adoptionPct of flats adopt the scenario". */
export function portfolioProjection(
  flats: readonly Flat[],
  id: ScenarioId,
  sharePct: number,
  adoptionPct: number,
): Projection {
  let before = ZERO;
  let low = ZERO;
  let high = ZERO;
  for (const flat of flats) {
    const p = project(flatProfile(flat), id, sharePct);
    before = add(before, p.before);
    low = add(low, p.low);
    high = add(high, p.high);
  }
  const k = adoptionPct / 100;
  return { before, low: scale(low, k), high: scale(high, k) };
}

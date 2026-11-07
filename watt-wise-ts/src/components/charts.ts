/** Charts built from measured backend data (no values are derived here; bar heights are geometry only). */
import type { ChannelRow, Profile } from '../api/contracts';
import { esc } from '../dom';
import * as F from '../format';

/** Average kWh per local clock hour, coloured by the backend's peak-price flag. */
export function hourOfDayChart(p: Profile): string {
  const vals = p.hour_of_day.map((h) => h.mean_kwh ?? 0);
  const max = Math.max(...vals, 1e-9);
  const bars = p.hour_of_day
    .map((h) => {
      const cls = h.mean_kwh == null ? 'nodata' : h.is_peak ? 'peak' : 'offpeak';
      const height = h.mean_kwh == null ? 190 : Math.max(2, Math.round((h.mean_kwh / max) * 190));
      const tip = `${F.hour(h.local_hour)} local: ${h.mean_kwh == null ? 'no complete reading' : F.kwh(h.mean_kwh, 3)} on average · mean spot ${
        h.mean_spot_sek_per_kwh == null ? F.NA : `${F.num(h.mean_spot_sek_per_kwh, 2)} SEK/kWh`
      }${h.is_peak ? ' · peak-price hour' : ''} · ${h.hours_in_period} hours in period`;
      return `<div class="bar ${cls}" style="height:${height}px" title="${esc(tip)}"><span class="sr-only">${esc(tip)}</span></div>`;
    })
    .join('');
  const labels = p.hour_of_day.map((h) => `<span>${h.local_hour % 3 === 0 ? String(h.local_hour).padStart(2, '0') : ''}</span>`).join('');
  return `
    <div class="legend">
      <span><i class="swatch" style="background:var(--orange)"></i>Peak-price hour (${esc(F.hourRanges(p.peak_hours_local))})</span>
      <span><i class="swatch" style="background:var(--mint)"></i>Other hours</span>
    </div>
    <div class="bars" role="img" aria-label="Average electricity use per local hour of the day">${bars}</div>
    <div class="bar-labels" aria-hidden="true">${labels}</div>
    <p class="note">Average of observed readings per Stockholm clock hour, 1–28 Oct 2026. Peak hours are the local hours whose mean spot price is above the period average (${esc(
      F.num(p.time_avg_price_sek_per_kwh, 3),
    )} SEK/kWh). Hover a bar for the exact value.</p>`;
}

/** Measured kWh per local date. Partial first/last days and the 25-hour DST day are labelled. */
export function dailyChart(p: Profile): string {
  const max = Math.max(...p.daily.map((d) => d.kwh), 1e-9);
  const bars = p.daily
    .map((d) => {
      const flag = !d.complete_day ? ` (partial day: ${d.hours_in_period} h)` : d.hours_in_period === 25 ? ' (25-hour day: clocks went back)' : '';
      const tip = `${F.calendarDate(d.local_date)}: ${F.kwh(d.kwh, 2)}, ${F.sek(d.sek)}, ${F.co2(d.co2_kg)}${flag}; ${F.pct(d.observed_share)} of readings observed`;
      return `<div class="bar day ${d.complete_day ? '' : 'partial'}" style="height:${Math.max(2, Math.round((d.kwh / max) * 160))}px" title="${esc(tip)}"><span class="sr-only">${esc(tip)}</span></div>`;
    })
    .join('');
  const labels = p.daily.map((d, i) => `<span>${i % 7 === 0 || d.local_date.endsWith('-25') ? esc(d.local_date.slice(8)) : ''}</span>`).join('');
  return `
    <div class="bars short" role="img" aria-label="Electricity use per day, Stockholm dates">${bars}</div>
    <div class="bar-labels" aria-hidden="true">${labels}</div>
    <p class="note">Measured kWh per Stockholm date (day of month shown). 1 Oct starts at 02:00 and 29 Oct has one hour because the dataset is defined in UTC (shown lighter). 25 Oct has 25 hours because the clocks went back. Missing readings are left out, not counted as zero.</p>`;
}

export function channelBars(channels: ChannelRow[]): string {
  const max = Math.max(...channels.map((c) => c.share_of_flat ?? 0), 1e-9);
  return channels
    .map((c) => {
      const missing = c.coverage < 1 ? `<span class="miss" title="${esc(`${c.hours_observed} of 672 hours observed`)}">${esc(F.pct(1 - c.coverage, 1))} missing</span>` : '';
      return `<div class="chrow">
        <span class="chname"><strong>${esc(c.channel)}</strong> ${esc(c.assumed_type)}${c.assumed_type_is_assumption ? '<sup title="Inferred from the load shape: the data has no appliance labels">*</sup>' : ''}</span>
        <div class="chtrack" aria-hidden="true"><div class="chfill" style="width:${Math.round(((c.share_of_flat ?? 0) / max) * 100)}%"></div></div>
        <span class="chval">${esc(F.kwh(c.kwh, 1))}<br><span class="unit">${esc(F.pct(c.share_of_flat, 0))} · ${esc(F.sek(c.sek, 1))}</span>${missing ? `<br>${missing}` : ''}</span>
      </div>`;
    })
    .join('');
}

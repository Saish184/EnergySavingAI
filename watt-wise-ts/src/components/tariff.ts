/**
 * Tariff selector. The tariff is a CONDITION on the money figures, never a calculation here: the backend returns
 * valuation.sek_by_tariff (hourly spot, monthly average, included in rent) and, for a fixed price, values it when
 * the scenario is run with the student's price. Shifting has no supported benefit outside hourly spot.
 */
import type { Tariff, TariffSpec, Valuation } from '../api/contracts';
import { esc } from '../dom';
import * as F from '../format';

export const TARIFFS: Tariff[] = ['unknown', 'hourly_spot', 'monthly_average_spot', 'fixed_price', 'included_in_rent'];

export function tariffSelectorHtml(prefix: string, current: TariffSpec): string {
  const radios = TARIFFS.map(
    (t) => `<label class="radio"><input type="radio" name="${prefix}-tariff" value="${t}" ${current.type === t ? 'checked' : ''}> ${esc(F.TARIFF_LABEL[t])}</label>`,
  ).join('');
  const price = current.fixed_price_sek_per_kwh ?? '';
  return `<fieldset class="scenario" id="${prefix}-tariff-box">
      <legend>Your electricity contract</legend>
      ${radios}
      <div class="fixed-price" ${current.type === 'fixed_price' ? '' : 'hidden'}>
        <label for="${prefix}-fixed" class="range-label">Your fixed energy price (SEK per kWh, excl. VAT)</label>
        <input id="${prefix}-fixed" type="number" inputmode="decimal" min="0" max="20" step="0.01" value="${esc(String(price))}">
        <p class="note">Fixed-price values are calculated by the backend when you run a simulation with your price.</p>
      </div>
      <p class="note">${esc(F.MONEY_NOTE)}</p>
    </fieldset>`;
}

export function bindTariffSelector(prefix: string, root: ParentNode, onChange: (t: TariffSpec) => void): void {
  const box = root.querySelector<HTMLElement>(`#${prefix}-tariff-box`);
  if (!box) return;
  const fixedWrap = box.querySelector<HTMLElement>('.fixed-price');
  const fixed = box.querySelector<HTMLInputElement>(`#${prefix}-fixed`);
  const emit = () => {
    const t = (box.querySelector<HTMLInputElement>(`input[name="${prefix}-tariff"]:checked`)?.value ?? 'unknown') as Tariff;
    if (fixedWrap) fixedWrap.hidden = t !== 'fixed_price';
    const spec: TariffSpec = { type: t };
    if (t === 'fixed_price') {
      const v = fixed?.value.trim() ? Number(fixed.value) : NaN;
      if (Number.isFinite(v) && v >= 0) spec.fixed_price_sek_per_kwh = v;
    }
    onChange(spec);
  };
  box.addEventListener('change', emit);
  fixed?.addEventListener('input', emit);
}

/** The backend's request object for a tariff; a fixed price without a valid price falls back to 'unknown'. */
export function tariffForRequest(t: TariffSpec): TariffSpec {
  if (t.type === 'fixed_price') {
    return t.fixed_price_sek_per_kwh != null ? { type: 'fixed_price', fixed_price_sek_per_kwh: t.fixed_price_sek_per_kwh } : { type: 'unknown' };
  }
  return { type: t.type };
}

/**
 * Money line for a backend valuation under the chosen tariff. Selection only: the value is the backend's
 * sek_by_tariff entry (or valuation.sek when the backend was asked with that tariff).
 */
export function moneyFor(v: Valuation, t: TariffSpec, kind: 'reduction' | 'shift' | 'mixed'): { text: string; note: string } {
  const spot = `${F.sek(v.sek_if_hourly_spot)} if you pay hourly spot prices`;
  if (t.type === 'unknown') {
    return { text: spot, note: 'Choose your contract above to see what applies to you.' };
  }
  if (t.type === 'fixed_price') {
    if (v.tariff === 'fixed_price' && v.sek != null) return { text: F.sek(v.sek), note: 'At your fixed price, calculated by the backend.' };
    const zero = v.sek_by_tariff.fixed_price;
    if (zero === 0 && kind === 'shift') return { text: F.sek(0), note: 'Moving use to other hours does not change a fixed-price bill.' };
    return { text: 'run the simulation with your price', note: 'The backend values a fixed price once you enter it and run the simulation.' };
  }
  const val = v.tariff === t.type && v.sek != null ? v.sek : v.sek_by_tariff[t.type];
  const note =
    t.type === 'included_in_rent'
      ? 'Electricity is included in your rent, so you save 0 SEK; the landlord’s saving depends on its own contract.'
      : t.type === 'monthly_average_spot' && kind === 'shift'
        ? 'With a monthly average price, moving use to other hours does not change your cost.'
        : t.type === 'monthly_average_spot'
          ? 'Valued at the period’s average spot price.'
          : 'Valued at each hour’s spot price.';
  return { text: val == null ? F.NA : F.sek(val), note };
}

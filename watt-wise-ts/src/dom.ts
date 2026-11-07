const ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};

export function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ESCAPES[c] ?? c);
}

/** Typed querySelector that throws instead of returning null. */
export function $<T extends HTMLElement = HTMLElement>(selector: string, root: ParentNode = document): T {
  const el = root.querySelector<T>(selector);
  if (!el) throw new Error(`Missing element: ${selector}`);
  return el;
}

export const fmt = {
  num(n: number, digits = 0): string {
    return n.toLocaleString('en-GB', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  },
  /** Signed number with a real minus sign. Rounds -0.0 to 0.0. */
  signed(n: number, digits = 1): string {
    const r = Number(n.toFixed(digits));
    if (r === 0) return fmt.num(0, digits);
    return (r > 0 ? '+' : '−') + fmt.num(Math.abs(r), digits);
  },
  hour(h: number): string {
    return String(h).padStart(2, '0');
  },
};

export function priceColor(pricePerKwh: number): string {
  if (pricePerKwh > 0.7) return 'var(--orange)';
  if (pricePerKwh < 0.3) return 'var(--green)';
  return 'var(--mint)';
}

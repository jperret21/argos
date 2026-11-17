/**
 * Number formatting for controls (BRAND 5): fixed decimals per quantity,
 * U+2212 for negatives (Intl gives a hyphen-minus), thousands grouped with
 * U+202F NARROW NO-BREAK SPACE ("1 305"): the grouping recommended to the
 * owner for BRAND 5 by the lab synthesis (web/lab/PROPOSAL.md), shared by
 * every lab. It lives in GROUP only.
 */

export const MINUS = '−';
export const GROUP = ' ';

/** toFixed with a true minus sign and no "-0". */
export function fixed(v: number, decimals: number): string {
  if (!Number.isFinite(v)) return '—';
  const s = v.toFixed(decimals);
  if (/^-0(\.0+)?$/.test(s)) return s.slice(1);
  return s.startsWith('-') ? MINUS + s.slice(1) : s;
}

/** Always signed: "+0.83", "−0.12" (declinations, offsets, deltas). */
export function signed(v: number, decimals: number): string {
  const s = fixed(v, decimals);
  if (s === '—') return s;
  return s.startsWith(MINUS) ? s : `+${s}`;
}

/** Integer with thousands grouping: 12450 -> "12 450", -1250 -> "−1 250" (U+202F). */
export function grouped(v: number): string {
  if (!Number.isFinite(v)) return '—';
  const n = Math.round(v);
  const digits = Math.abs(n).toString();
  const out = digits.replace(/\B(?=(\d{3})+(?!\d))/g, GROUP);
  return n < 0 ? MINUS + out : out;
}

/** Signed grouped integer for step deltas: "+300", "−1 000". */
export function signedGrouped(v: number): string {
  const s = grouped(v);
  return s === '—' || s.startsWith(MINUS) ? s : `+${s}`;
}

/** Exposure in seconds with the precision its size needs: 0.01, 0.5, 2.0, 120. */
export function exposure(s: number): string {
  if (!Number.isFinite(s)) return '—';
  if (s < 0.1) return s.toFixed(3);
  if (s < 10) return s.toFixed(s < 1 ? 2 : 1);
  return s.toFixed(0);
}

/** Parse what an observer types: comma or point decimal, U+2212 or "-", spaces and group marks ignored. */
export function parseNumber(text: string): number | null {
  const t = text.trim().replace(/[\s  ]/g, '').replace(MINUS, '-');
  // "12,450" (grouped) vs "0,5" (decimal comma): a comma followed by exactly three digits groups.
  const normal = /^[-+]?\d{1,3}(,\d{3})+(\.\d*)?$/.test(t) ? t.replace(/,/g, '') : t.replace(',', '.');
  if (!/^[-+]?(\d+\.?\d*|\.\d+)$/.test(normal)) return null;
  return Number(normal);
}

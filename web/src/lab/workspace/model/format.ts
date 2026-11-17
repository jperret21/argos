/**
 * Formatters for the workspace (BRAND 5). Hot paths use toFixed + a manual
 * minus sign (Intl gives U+002D, BRAND wants U+2212). Thousands use U+202F
 * NARROW NO-BREAK SPACE, the BRAND 5 grouping the lab synthesis recommends
 * (web/lab/PROPOSAL.md) and every lab now shares; one constant here, so the
 * owner's choice is a one-line change.
 */

export { formatRA, formatDec, MINUS, PRIME, DOUBLE_PRIME } from '../../../lib/format/astro';
import { MINUS } from '../../../lib/format/astro';

/** Thousands separator (U+202F, kept under its old name for the imports). */
export const THIN = ' ';
export const PM = '±';

/** Fixed decimals, U+2212 for negatives. */
export function fixed(v: number, digits: number): string {
  if (!Number.isFinite(v)) return '—';
  const s = Math.abs(v).toFixed(digits);
  // "-0.000" is a zero: no sign.
  return v < 0 && Number(s) !== 0 ? MINUS + s : s;
}

/** Always signed (Δ values, declinations): "+0.10", "−0.04". */
export function signed(v: number, digits: number): string {
  if (!Number.isFinite(v)) return '—';
  const s = Math.abs(v).toFixed(digits);
  return (v < 0 && Number(s) !== 0 ? MINUS : '+') + s;
}

/** Integer with grouped thousands (U+202F): 58824 -> "58 824". */
export function int(v: number): string {
  if (!Number.isFinite(v)) return '—';
  const n = Math.round(Math.abs(v)).toString();
  const out = n.replace(/\B(?=(\d{3})+(?!\d))/g, THIN);
  return v < 0 ? MINUS + out : out;
}

/** "22:24:42" from unix seconds, UTC. */
export function utc(t: number, seconds = true): string {
  const iso = new Date(Math.round(t) * 1000).toISOString();
  return seconds ? iso.slice(11, 19) : iso.slice(11, 16);
}

/** "2026-09-25" from unix seconds, UTC. */
export function utcDate(t: number): string {
  return new Date(Math.round(t) * 1000).toISOString().slice(0, 10);
}

/** BRAND durations: "1h 05m", "12m 30s", "45 s". */
export function duration(s: number): string {
  if (!Number.isFinite(s) || s < 0) return '—';
  const r = Math.round(s);
  if (r < 60) return `${r} s`;
  const h = Math.floor(r / 3600);
  const m = Math.floor((r % 3600) / 60);
  const sec = r % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
  return `${m}m ${String(sec).padStart(2, '0')}s`;
}

/** Age of the last frame, as a clock reads it: "12 s", "1m 05s". */
export function age(s: number): string {
  return duration(Math.max(0, s));
}

/** Magnitude with uncertainty, 3 decimals: "7.692 ± 0.035". */
export function mag(m: number, err?: number): string {
  if (err === undefined) return fixed(m, 3);
  return `${fixed(m, 3)} ${PM} ${fixed(err, 3)}`;
}

/** Arcminutes with the prime: "6.2′". */
export function arcmin(v: number, digits = 1): string {
  return `${fixed(v, digits)}′`;
}

/** Julian date (5 decimals, BRAND 5) from unix seconds. */
export function jd(t: number): string {
  return (t / 86400 + 2440587.5).toFixed(5);
}

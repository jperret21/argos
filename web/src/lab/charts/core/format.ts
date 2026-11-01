/**
 * Number and time formats for charts (BRAND 5): one decimal convention per
 * quantity, U+2212 for negatives, explicit units, UTC named.
 *
 * Hot paths (tick labels, cursor readouts) use toFixed and string ops, not
 * Intl (stack-capabilities 11: 4x cheaper, and Intl gives a hyphen-minus).
 * Thousands are grouped with U+202F NARROW NO-BREAK SPACE, the grouping the
 * lab synthesis recommends for BRAND 5 (web/lab/PROPOSAL.md), shared by every
 * lab (it never breaks a number across lines; one cell wide in Plex Mono).
 */

export const MINUS = '−';
export const PLUS_MINUS = '±';
export const EN_DASH = '–';
export const THIN = ' ';
/** Grouping separator: U+202F (recommended for BRAND 5, see the header). */
export const GROUP = ' ';

/** toFixed with U+2212 for negatives; "−0.000" is printed "0.000". */
export function fixed(v: number, digits: number): string {
  if (!Number.isFinite(v)) return '—';
  const s = v.toFixed(digits);
  if (s[0] !== '-') return s;
  return /[1-9]/.test(s) ? MINUS + s.slice(1) : s.slice(1);
}

/** Always signed: "+0.004", "−0.012", "0.000" stays unsigned. */
export function signed(v: number, digits: number): string {
  const s = fixed(v, digits);
  if (s === '—' || s[0] === MINUS || !/[1-9]/.test(s)) return s;
  return `+${s}`;
}

/** Integer with grouped thousands: 65535 -> "65 535". */
export function grouped(v: number): string {
  if (!Number.isFinite(v)) return '—';
  const neg = v < 0;
  const s = Math.round(Math.abs(v)).toString();
  let out = '';
  for (let i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 === 0) out += GROUP;
    out += s[i];
  }
  return neg ? MINUS + out : out;
}

/** Compact counts for log axes: 1, 10, 100, 1k, 10k, 1M. */
export function compactCount(v: number): string {
  if (v >= 1e6) return `${+(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${+(v / 1e3).toFixed(1)}k`;
  return String(Math.round(v));
}

/** Magnitude with uncertainty, 3 decimals (BRAND 5): "12.345 ± 0.012". */
export function mag(v: number, err?: number): string {
  return err === undefined ? fixed(v, 3) : `${fixed(v, 3)} ${PLUS_MINUS} ${fixed(err, 3)}`;
}

const pad2 = (n: number) => (n < 10 ? `0${n}` : String(n));

/** "21:34:05" from unix seconds (UTC), rounded to the second. */
export function clockUtc(t: number, seconds = true): string {
  const s = Math.round(t);
  const d = ((s % 86400) + 86400) % 86400;
  const h = Math.floor(d / 3600);
  const m = Math.floor((d % 3600) / 60);
  return seconds ? `${pad2(h)}:${pad2(m)}:${pad2(d % 60)}` : `${pad2(h)}:${pad2(m)}`;
}

/** "2026-11-01 21:34:05 UTC". */
export function isoUtc(t: number): string {
  const d = new Date(Math.round(t) * 1000);
  return `${d.toISOString().slice(0, 10)} ${clockUtc(t)} UTC`;
}

/** Duration in the BRAND 5 style: "1h 05m", "12m 30s", "45 s". */
export function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${pad2(s % 60)}s`;
  return `${Math.floor(s / 3600)}h ${pad2(Math.floor((s % 3600) / 60))}m`;
}

/** JD / BJD with 5 decimals (0.86 s), BRAND 5. */
export function julian(v: number): string {
  return v.toFixed(5);
}

/** Degrees, 2 decimals, no space before the sign (BRAND 5: "41.27°"). */
export function degrees(v: number, digits = 2): string {
  return `${fixed(v, digits)}°`;
}

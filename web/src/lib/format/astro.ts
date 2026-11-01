/**
 * Astronomical number formats and coordinate parsing (BRAND.md section 5).
 *
 * One format per quantity, everywhere:
 *   RA      05h 35m 17.3s        zero-padded, tenths of a second
 *   Dec     +05° 23′ 28″         sign always, U+2032 / U+2033, whole arcseconds
 *   Alt/Az  41.27°               two decimals, no space before the degree sign
 * Negative values use U+2212 MINUS SIGN so "+" and "−" take the same width in
 * tabular figures. Values are rounded once to the displayed precision and then
 * carried (59.96 s shows as 00.0 s of the next minute), like format_ra_hms in
 * argos/core/imaging/platesolve.py, and RA and Dec are rounded the same way.
 */

export const MINUS = '−';
export const PRIME = '′';
export const DOUBLE_PRIME = '″';

const pad2 = (n: number) => String(n).padStart(2, '0');

/** Right ascension in hours -> "HHh MMm SS.Ss" (wrapped to [0, 24)). */
export function formatRA(hours: number): string {
  if (!Number.isFinite(hours)) return '—';
  const DAY = 24 * 36000; // tenths of a second per day
  const tenths = ((Math.round(hours * 36000) % DAY) + DAY) % DAY;
  const h = Math.floor(tenths / 36000);
  const m = Math.floor((tenths % 36000) / 600);
  const s = (tenths % 600) / 10;
  return `${pad2(h)}h ${pad2(m)}m ${s.toFixed(1).padStart(4, '0')}s`;
}

/**
 * Declination in degrees -> "±DD° MM′ SS″" (or "SS.S″" with `decimals` = 1).
 * The sign follows the rounded value, so −00° 30′ keeps its minus and a value
 * that rounds to zero shows "+00° 00′ 00″".
 */
export function formatDec(degrees: number, decimals: 0 | 1 = 0): string {
  if (!Number.isFinite(degrees)) return '—';
  const unit = decimals === 1 ? 10 : 1; // steps per arcsecond
  const steps = Math.round(Math.abs(degrees) * 3600 * unit);
  const sign = degrees < 0 && steps > 0 ? MINUS : '+';
  const d = Math.floor(steps / (3600 * unit));
  const m = Math.floor((steps % (3600 * unit)) / (60 * unit));
  const sSteps = steps % (60 * unit);
  const s = decimals === 1 ? (sSteps / 10).toFixed(1).padStart(4, '0') : pad2(sSteps);
  return `${sign}${pad2(d)}° ${pad2(m)}${PRIME} ${s}${DOUBLE_PRIME}`;
}

/** Signed decimal with U+2212 for negatives (no sign for positives). */
export function formatSigned(value: number, digits: number): string {
  if (!Number.isFinite(value)) return '—';
  const text = Math.abs(value).toFixed(digits);
  const isZero = Number(text) === 0;
  return value < 0 && !isZero ? `${MINUS}${text}` : text;
}

/** Altitude / azimuth / any angle in decimal degrees: "41.27°". */
export function formatDegrees(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${formatSigned(value, digits)}°`;
}

/** Great-circle separation in degrees between two (RA hours, Dec degrees) points. */
export function separationDeg(ra1h: number, dec1: number, ra2h: number, dec2: number): number {
  const rad = Math.PI / 180;
  const a1 = ra1h * 15 * rad;
  const a2 = ra2h * 15 * rad;
  const d1 = dec1 * rad;
  const d2 = dec2 * rad;
  const hav =
    Math.sin((d2 - d1) / 2) ** 2 + Math.cos(d1) * Math.cos(d2) * Math.sin((a2 - a1) / 2) ** 2;
  return (2 * Math.asin(Math.min(1, Math.sqrt(hav)))) / rad;
}

// ---------------------------------------------------------------------------
// Parsing (GoTo form): sexagesimal or decimal input
// ---------------------------------------------------------------------------

export type ParseResult = { ok: true; value: number } | { ok: false; error: string };

const ok = (value: number): ParseResult => ({ ok: true, value });
const fail = (error: string): ParseResult => ({ ok: false, error });

/** Normalise unicode signs and separators; keep unit letters for the caller. */
function normalise(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[−‒–—]/g, '-') // minus and dashes
    .replace(/,/g, '.')
    .replace(/\s+/g, ' ');
}

/** Leading sign, then the unsigned remainder. */
function splitSign(text: string): { negative: boolean; signed: boolean; rest: string } {
  const m = /^([+-])\s*/.exec(text);
  if (!m) return { negative: false, signed: false, rest: text };
  return { negative: m[1] === '-', signed: true, rest: text.slice(m[0].length) };
}

const NUMBER = /^\d+(?:\.\d*)?$|^\.\d+$/;

/**
 * Split "05 35 17.3", "05:35:17.3", "5h35m17.3s", "-5°23'28\"" into up to three
 * unsigned numeric fields. Unit markers act as separators; returns null when
 * something else is left over.
 */
function sexagesimalFields(rest: string, units: RegExp): number[] | null {
  const cleaned = rest
    .replace(units, ' ')
    .replace(/[:'"′″°]/g, ' ')
    .trim();
  if (!cleaned) return null;
  const parts = cleaned.split(' ').filter(Boolean);
  if (parts.length < 1 || parts.length > 3) return null;
  if (!parts.every((p) => NUMBER.test(p))) return null;
  const values = parts.map(Number);
  // Only the last field may carry decimals ("5.5 30" is ambiguous).
  for (let i = 0; i < values.length - 1; i++) {
    if (!Number.isInteger(values[i])) return null;
  }
  return values;
}

function combine(fields: number[]): number | string {
  const [a, b = 0, c = 0] = fields;
  if (b >= 60) return 'minutes must be below 60';
  if (c >= 60) return 'seconds must be below 60';
  return a + b / 60 + c / 3600;
}

/**
 * Right ascension -> hours in [0, 24).
 * Accepts "05h 35m 17.3s", "5h35m17.3s", "05:35:17.3", "05 35 17.3", "5 35",
 * decimal hours "5.5883", or decimal degrees with a unit: "83.82°", "83.82d",
 * "83.82 deg".
 */
export function parseRA(input: string): ParseResult {
  const text = normalise(input);
  if (!text) return fail('Enter a right ascension');
  const { signed, rest } = splitSign(text);
  if (signed) return fail('Right ascension has no sign');

  // Decimal degrees, explicitly marked.
  const deg = /^(\d+(?:\.\d*)?|\.\d+)\s*(?:°|d|deg|degrees?)$/.exec(rest);
  if (deg) {
    const degrees = Number(deg[1]);
    if (degrees >= 360) return fail('Right ascension in degrees must be below 360');
    return ok(degrees / 15);
  }
  if (/°|deg/.test(rest)) return fail('Use h m s, or degrees as a single value (83.82°)');

  if (NUMBER.test(rest)) {
    const hours = Number(rest);
    if (hours >= 24) return fail('Right ascension must be below 24h');
    return ok(hours);
  }

  const fields = sexagesimalFields(rest, /[hms]/g);
  if (!fields) return fail('Not a right ascension (try 05h 35m 17.3s or 5.588)');
  const hours = combine(fields);
  if (typeof hours === 'string') return fail(hours);
  if (hours >= 24) return fail('Right ascension must be below 24h');
  return ok(hours);
}

/**
 * Declination -> degrees in [−90, +90].
 * Accepts "+05° 23′ 28″", "-05 23 28", "−05:23:28.5", "5d23m28s", "-0 30",
 * and decimal degrees "5.391" / "−5.391". The leading sign applies to the
 * whole value (so "-00 30 00" is −0.5°).
 */
export function parseDec(input: string): ParseResult {
  const text = normalise(input);
  if (!text) return fail('Enter a declination');
  const { negative, rest } = splitSign(text);
  const sign = negative ? -1 : 1;
  if (/^-|^\+/.test(rest)) return fail('Only one sign is allowed');

  let degrees: number;
  if (NUMBER.test(rest.replace(/\s*(?:°|d|deg)$/, ''))) {
    degrees = Number(rest.replace(/\s*(?:°|d|deg)$/, ''));
  } else {
    const fields = sexagesimalFields(rest.replace(/deg/g, ' '), /[dms]/g);
    if (!fields) return fail('Not a declination (try +05° 23′ 28″ or −5.391)');
    const value = combine(fields);
    if (typeof value === 'string') return fail(value);
    degrees = value;
  }
  if (degrees > 90) return fail('Declination must be within ±90°');
  return ok(sign * degrees);
}

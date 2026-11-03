/**
 * Number formatting and parsing for display (BRAND.md section 5, owner decision D5).
 *
 * One implementation for the whole UI, merged from the three lab copies
 * (src/lab/controls/format.ts, src/lab/charts/core/format.ts,
 * src/lab/workspace/model/format.ts; web/lab/PROPOSAL.md section 6):
 *
 * - negatives use U+2212 MINUS SIGN, so "+" and "−" take the same width in
 *   tabular figures; a value that rounds to zero never prints "−0";
 * - integers and counts group thousands with U+202F NARROW NO-BREAK SPACE from
 *   1 000 up ("1 000", "65 535 ADU"): one cell wide in Plex Mono, never broken
 *   across lines, never a comma (a decimal mark for much of Europe) or a plain
 *   space. Decimal values are grouped only when asked (`{ group: true }`);
 *   Julian dates and identifiers never are;
 * - factors and products use U+00D7 ("2.5× baseline", "20 × 10 s"), never the
 *   letter x;
 * - no Intl formatter for display: Intl gives U+002D for negatives and its
 *   grouping depends on the locale (and toFixed is cheaper on hot paths such as
 *   tick labels and cursor readouts);
 * - a missing or non-finite value prints "—".
 *
 * parseNumber() reads what an observer types: point or comma decimal, any
 * minus sign, spaces and narrow spaces as grouping.
 */

/** U+2212 MINUS SIGN. */
export const MINUS = '−';
/** U+202F NARROW NO-BREAK SPACE: the thousands separator. */
export const GROUP = ' ';
/** U+00D7 MULTIPLICATION SIGN: factors and products. */
export const TIMES = '×';
/** U+00B1 PLUS-MINUS SIGN: uncertainties. */
export const PLUS_MINUS = '±';
/** U+2014 EM DASH: a value that is missing, unknown or not finite. */
export const DASH = '—';

export type Num = number | null | undefined;

export interface FixedOptions {
  /** Group the integer part with U+202F from 1 000 up (default false for decimals). */
  group?: boolean;
}

const finite = (v: Num): v is number => typeof v === 'number' && Number.isFinite(v);

/** "1234567" -> "1 234 567" (U+202F); strings shorter than 4 digits are unchanged. */
export function groupDigits(digits: string): string {
  if (digits.length < 4) return digits;
  let out = '';
  for (let i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 === 0) out += GROUP;
    out += digits[i];
  }
  return out;
}

/** |v| rounded to `digits`, as text, plus whether the rounded value is zero. */
function magnitude(v: number, digits: number, group: boolean): { text: string; zero: boolean } {
  const s = Math.abs(v).toFixed(digits);
  const zero = !/[1-9]/.test(s);
  // toFixed writes |v| >= 1e21 in exponent form ("1e+21"): never group into it.
  if (!group || /e/i.test(s)) return { text: s, zero };
  const dot = s.indexOf('.');
  const int = dot < 0 ? s : s.slice(0, dot);
  return { text: groupDigits(int) + (dot < 0 ? '' : s.slice(dot)), zero };
}

/** Fixed decimals with U+2212 for negatives; "−0.000" prints "0.000". */
export function fixed(v: Num, digits: number, opts: FixedOptions = {}): string {
  if (!finite(v)) return DASH;
  const { text, zero } = magnitude(v, digits, opts.group ?? false);
  return v < 0 && !zero ? MINUS + text : text;
}

/**
 * Always signed (declinations, offsets, deltas, latitudes): "+0.83", "−0.12".
 * Zero takes "+" too, so a column of signed values keeps its sign column.
 */
export function signed(v: Num, digits: number, opts: FixedOptions = {}): string {
  if (!finite(v)) return DASH;
  const { text, zero } = magnitude(v, digits, opts.group ?? false);
  return (v < 0 && !zero ? MINUS : '+') + text;
}

/** Rounded integer, thousands grouped: 65535 -> "65 535", −1250 -> "−1 250". */
export function int(v: Num): string {
  return fixed(v, 0, { group: true });
}

/** Always-signed grouped integer (step deltas): "+300", "−1 000", "+0". */
export function signedInt(v: Num): string {
  return signed(v, 0, { group: true });
}

/** A count with its noun: "1 line", "12 450 lines". `plural` defaults to noun + "s". */
export function count(n: Num, noun: string, plural = `${noun}s`): string {
  if (!finite(n)) return `${DASH} ${plural}`;
  return `${int(n)} ${Math.round(Math.abs(n)) === 1 ? noun : plural}`;
}

/** A factor: "2.5×" (U+00D7, no space). */
export function factor(v: Num, digits = 1): string {
  const s = fixed(v, digits);
  return s === DASH ? s : `${s}${TIMES}`;
}

/** A product: times(20, "10 s") -> "20 × 10 s" (U+00D7 between spaces). */
export function times(n: Num, rhs: string): string {
  return `${int(n)} ${TIMES} ${rhs}`;
}

/** A value with its uncertainty: "12.345 ± 0.012". */
export function withError(v: Num, err: Num, digits: number): string {
  if (!finite(err)) return fixed(v, digits);
  return `${fixed(v, digits)} ${PLUS_MINUS} ${fixed(err, digits)}`;
}

/** Magnitude, 3 decimals, with its uncertainty when known (BRAND 5): "12.345 ± 0.012". */
export function mag(v: Num, err?: Num): string {
  return withError(v, err, 3);
}

/**
 * Seconds with the precision the quantity uses in the UI: 3 decimals below
 * one second, one above, grouped ("0.250 s", "2.0 s", "1 200.0 s").
 */
export function seconds(s: Num): string {
  if (!finite(s)) return DASH;
  // Decimals from the value as it will print: 0.9996 rounds to 1.000, so it is "1.0 s".
  const small = Math.abs(s) < 1 && Math.abs(+s.toFixed(3)) < 1;
  return `${fixed(s, small ? 3 : 1, { group: true })} s`;
}

/** A percentage, rounded: "100 %" (SI, space before the sign). */
export function percent(fraction: Num, digits = 0): string {
  if (!finite(fraction)) return DASH;
  return `${fixed(fraction * 100, digits, { group: true })} %`;
}

/** Compact counts for log axes and tight chips: 1, 10, 100, 1k, 10k, 1.5M. */
export function compactCount(v: Num): string {
  if (!finite(v)) return DASH;
  // Round first, then choose the unit: 999 950 is "1M", never "1000k"; 999.6 is "1k".
  const a = Math.round(Math.abs(v));
  const sign = v < 0 && a !== 0 ? MINUS : '';
  const k = +(a / 1e3).toFixed(1);
  if (a >= 1e6 || k >= 1000) return `${sign}${+(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}${k}k`;
  return sign + String(a);
}

// ---------------------------------------------------------------------------
// Units and ranges
// ---------------------------------------------------------------------------

/** Angle units written against the number (BRAND 5: "41.27°", "5′", "3.67″/px"); °C keeps its space (SI). */
const TIGHT_UNIT = /^(°|′|″)/;

/** A value and its unit: "41.27°", "18.0 mag", "−10.0 °C". */
export function withUnit(text: string, unit?: string | null): string {
  if (!unit || text === DASH) return text;
  return TIGHT_UNIT.test(unit) && !/^°C/.test(unit) ? `${text}${unit}` : `${text} ${unit}`;
}

/** A limit at its natural precision (no padding zeros), grouped from 1 000 up. */
function limitText(v: number, sign: boolean, digits?: number): string {
  if (digits !== undefined) return sign ? signed(v, digits, { group: true }) : fixed(v, digits, { group: true });
  const d = Math.min(6, decimalsIn(v));
  return sign ? signed(v, d, { group: true }) : fixed(v, d, { group: true });
}

function decimalsIn(v: number): number {
  const s = String(Number(Math.abs(v).toPrecision(12)));
  if (/e/i.test(s)) return 0;
  const dot = s.indexOf('.');
  return dot < 0 ? 0 : s.length - dot - 1;
}

export interface RangeOptions {
  /** Both limits signed (latitudes, longitudes): "−90° … +90°". */
  signed?: boolean;
  /** Fixed decimals for the limits; default: their natural precision. */
  digits?: number;
  unit?: string | null;
}

/**
 * One way to write a range everywhere (field captions, refusals, the help
 * column): "−90° … +90°", "0° … 180°", "1 … 3 600 s", "−500 … 9 000 m".
 * Limits at their natural precision, U+2212 for negatives, an angle unit on
 * both limits (no space), any other unit once after the upper limit.
 */
export function formatRange(min: number, max: number, opts: RangeOptions = {}): string {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return '';
  const sign = opts.signed ?? false;
  const lo = limitText(min, sign, opts.digits);
  const hi = limitText(max, sign, opts.digits);
  const unit = opts.unit ?? null;
  if (unit && TIGHT_UNIT.test(unit) && !/^°C/.test(unit)) return `${lo}${unit} … ${hi}${unit}`;
  return withUnit(`${lo} … ${hi}`, unit);
}

/** One limit with its unit, as formatRange writes it: "+90°", "9 000 m". */
export function formatLimit(v: number, opts: RangeOptions = {}): string {
  if (!Number.isFinite(v)) return '';
  return withUnit(limitText(v, opts.signed ?? false, opts.digits), opts.unit);
}

/** "between −90° and +90°" (a refusal of the field, before anything is sent). */
export function betweenText(min: number, max: number, opts: RangeOptions = {}): string {
  return formatRange(min, max, opts).replace(' … ', ' and ');
}

// ---------------------------------------------------------------------------
// Parsing
// ---------------------------------------------------------------------------

/** Characters taken as grouping marks and ignored: space, NBSP, thin, narrow. */
const SPACES = /[\s   ]/g;
/** Minus look-alikes an observer may type or paste. */
const MINUSES = /[−‒–—﹣－]/g;

/** "1,234,567" or "1.234.567": every group after the first is exactly three digits. */
function validGroups(int: string, mark: string): boolean {
  const parts = int.split(mark);
  return /^\d{1,3}$/.test(parts[0]) && parts.slice(1).every((p) => /^\d{3}$/.test(p));
}

export interface ParseOptions {
  /**
   * A whole-number field (counts, ADU, ports): one comma before exactly three
   * digits groups thousands, so "60,000" is 60 000 there (a decimal comma
   * makes no sense in it), while "1,5" stays 1.5 and is refused as not whole.
   */
  integer?: boolean;
}

/** One comma before exactly three digits, no point: "60,000" (60 000, or 60.000 with a decimal comma). */
const AMBIGUOUS_COMMA = /^[+-]?([1-9]\d{0,2}),(\d{3})$/;

/**
 * True when `text` reads both ways ("60,000": sixty thousand with a grouping
 * comma, sixty with a decimal comma) in a field that takes decimals. The
 * field refuses it and asks for a point or a space instead of guessing (a
 * factor of 1 000 either way). "0,500" is not ambiguous (no one groups a
 * leading zero) and stays 0.5.
 */
export function ambiguousComma(text: string): { grouped: string; decimal: string } | null {
  const t = text.trim().replace(SPACES, '').replace(MINUSES, '-');
  const m = AMBIGUOUS_COMMA.exec(t);
  if (!m) return null;
  const neg = t.startsWith('-') ? MINUS : '';
  return { grouped: `${neg}${m[1]}${GROUP}${m[2]}`, decimal: `${neg}${m[1]}.${m[2]}` };
}

/**
 * Parse a number as an observer types it. Returns null when it is not one.
 *
 * - Decimal mark: point or comma. A single comma is a decimal comma, so
 *   "0,500" is 0.5 (the lab's "comma before three digits groups" rule would
 *   read it as 500, a silent factor of 1 000 on an exposure). In a
 *   whole-number field (`{ integer: true }`) "60,000" is 60 000; a decimal
 *   field should refuse it as ambiguous (ambiguousComma) before parsing.
 * - Grouping: spaces of any width are ignored; several commas ("1,234,567")
 *   or several points ("1.234.567") group thousands; with both marks, the
 *   last one is the decimal mark ("12,450.5", "12.450,5").
 * - Signs: "+", "-", U+2212 and dash look-alikes; an exponent ("1e-3") is accepted.
 */
export function parseNumber(text: string, opts: ParseOptions = {}): number | null {
  let t = text.trim().replace(SPACES, '').replace(MINUSES, '-');
  if (!t) return null;
  const m = /^([+-]?)(.*?)([eE][+-]?\d+)?$/.exec(t);
  if (!m) return null;
  const [, sign, body, exp = ''] = m;
  if (!body || /[+-]/.test(body)) return null;
  const commas = (body.match(/,/g) ?? []).length;
  const points = (body.match(/\./g) ?? []).length;
  let normal: string;
  if (commas && points) {
    const lastComma = body.lastIndexOf(',');
    const lastPoint = body.lastIndexOf('.');
    const decimal = lastComma > lastPoint ? ',' : '.';
    const groupMark = decimal === ',' ? '.' : ',';
    const cut = body.lastIndexOf(decimal);
    const int = body.slice(0, cut);
    const frac = body.slice(cut + 1);
    if (body.split(decimal).length !== 2 || !validGroups(int, groupMark)) return null;
    normal = `${int.split(groupMark).join('')}.${frac}`;
  } else if (commas > 1 || points > 1) {
    const mark = commas > 1 ? ',' : '.';
    if (!validGroups(body, mark)) return null;
    normal = body.split(mark).join('');
  } else if (opts.integer && commas === 1 && /^\d{1,3},\d{3}$/.test(body)) {
    normal = body.replace(',', ''); // a grouping comma in a whole-number field
  } else {
    normal = body.replace(',', '.');
  }
  if (!/^(\d+\.?\d*|\.\d+)$/.test(normal)) return null;
  t = `${sign}${normal}${exp}`;
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
}

/**
 * The filter's name for display (S49 in the UI, wave 6b design review). Since S49 a star has
 * one curve per (star, filter), keyed by the filter TOKEN the frame file names use (the
 * core's `fits_writer.filter_token`: "ir", "lp", "v", "clear"). Tokens stay in file names;
 * every label shows the filter as the wheel, the frame chip and the Plan name it ("IR",
 * "LP", "V"), so a magnitude never reads with a lowercase token beside it.
 */

/** The core's FILTER_ABBREV (argos/core/imaging/fits_writer.py), for the token. */
const ABBREV: Record<string, string> = { LRGB: 'LRGB', Ha: 'Ha', OIII: 'OIII', SII: 'SII', 'IR-cut': 'IRc' };

/** Tokens whose name is not their upper case. */
const NAMED: Record<string, string> = { ha: 'Ha', irc: 'IR-cut', clear: 'no filter' };

/** `filter_token` of the core: "IR" → "ir", "IR-cut" → "irc", "" → "clear". */
export function filterToken(name: string | null | undefined): string {
  const n = String(name ?? '').trim();
  const a = ABBREV[n] ?? n;
  const ascii = a.normalize('NFKD').replace(/[̀-ͯ]/g, '');
  return ascii.replace(/ /g, '_').replace(/[^A-Za-z0-9_-]/g, '').toLowerCase() || 'clear';
}

/**
 * The display name of a curve's filter token: the first of `names` (the wheel's slots, the
 * plan's filters) whose token it is, else its usual spelling ("ir" → "IR"); "" for none.
 */
export function filterLabel(token: string | null | undefined, names: readonly string[] = []): string {
  if (!token) return '';
  for (const n of names) if (filterToken(n) === token) return n;
  return NAMED[token] ?? token.toUpperCase();
}

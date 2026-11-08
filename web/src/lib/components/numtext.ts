/**
 * Splits a sentence into its words and its numbers, so the numbers can be set
 * in Plex Mono (BRAND 5: "Plex Mono for every number") inside a Sans caption,
 * menu label or status line, where they are composed (design review of wave 3:
 * U+202F grouping is only 0.118 em wide in Sans, "10 000" read "10000").
 *
 * A number run: an optional sign (−, +, ±), digits with the grouping and
 * decimal marks between them ("10 000", "0.7", "16.69500", "13:38:39").
 */

export interface Run {
  text: string;
  num: boolean;
}

const NUMBER = /[−+±-]?\d(?:[\d  .,:]*\d)?/g;

export function numberRuns(text: string): Run[] {
  const out: Run[] = [];
  let last = 0;
  for (const m of text.matchAll(NUMBER)) {
    const at = m.index ?? 0;
    if (at > last) out.push({ text: text.slice(last, at), num: false });
    out.push({ text: m[0], num: true });
    last = at + m[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last), num: false });
  return out;
}

/**
 * A plain integer of 4+ digits with the U+202F grouping of `int()` ("5000" ->
 * "5 000"), for sentences the server composed ("Returned to 5000."). Only
 * whole runs of digits; anything with a decimal mark, a clock or a date is left
 * as written.
 */
export function groupInteger(run: string): string {
  const m = /^([−+±-]?)(\d{4,})$/.exec(run);
  if (!m) return run;
  return m[1] + m[2].replace(/\B(?=(\d{3})+(?!\d))/g, '\u202f');
}

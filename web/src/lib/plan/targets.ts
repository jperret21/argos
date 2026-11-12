/**
 * The Plan's Target set card in words (06 §2.2 rows 1.13 #3; TS:98 summary, P31): role counts
 * and the TSV Qt's TargetTable copied (same columns and header, target_table.py:24, 84-93;
 * coordinates in BRAND 5).
 */

import { formatDec, formatRA } from '../format/astro';
import type { TargetStar } from '../imaging/field/types';

export function roleCounts(stars: readonly Pick<TargetStar, 'role'>[]): { target: number; comparison: number; check: number } {
  const c = { target: 0, comparison: 0, check: 0 };
  for (const s of stars) if (s.role in c) c[s.role as keyof typeof c]++;
  return c;
}

/** "Role\tName\tRA\tDec\tMags" + one line per star; mags as Qt ("V 10.20  B 11.02"). */
export function targetSetTsv(stars: readonly TargetStar[]): string {
  const lines = ['Role\tName\tRA\tDec\tMags'];
  for (const s of stars) {
    const mags = Object.entries(s.mags ?? {})
      .filter((e): e is [string, number] => typeof e[1] === 'number' && Number.isFinite(e[1]))
      .map(([b, m]) => `${b} ${m.toFixed(2)}`)
      .join('  ');
    const name = (s.display_name || s.name || s.auid || s.key).replace(/[\t\r\n]+/g, ' ');
    lines.push([s.role, name, formatRA(s.ra_hours), formatDec(s.dec_deg), mags].join('\t'));
  }
  return lines.join('\n') + '\n';
}

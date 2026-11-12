/**
 * Run progress as frames, not as a smooth percentage (promoted from
 * src/lab/charts/mini/RunProgress.svelte, web/lab/PROPOSAL.md section 6, W6): the
 * frames taken are coverage segments on a time axis (planned start to end), so a
 * pause or a slow cadence shows as the fill lagging the now marker. A gap is where
 * the next frame came later than the overdue limit of the observed cadence (the
 * AgeMeter's rule, charts/conditions.ts), not a fixed number of seconds.
 */

import { observedCadence, overdueAfter } from '../conditions';

/** Contiguous runs of frames as [first, last] times (seconds); gaps past the overdue limit split them. */
export function coverageSegments(times: ArrayLike<number>, n: number): [number, number][] {
  const out: [number, number][] = [];
  if (n < 1) return out;
  const limit = overdueAfter(observedCadence(times, n, n));
  let i0 = 0;
  for (let i = 1; i <= n; i++) {
    if (i === n || times[i] - times[i - 1] > limit) {
      out.push([times[i0], times[i - 1]]);
      i0 = i;
    }
  }
  return out;
}

/** Position of t on [start, end] as a percentage, held to the bar (0..100). */
export function percentOf(t: number, start: number, end: number): number {
  if (!(end > start) || !Number.isFinite(t)) return 0;
  return Math.max(0, Math.min(1, (t - start) / (end - start))) * 100;
}

/** "37 of 50 frames, 74 %, 2 autofocus passes": the bar in words (its accessible name). */
export function progressText(done: number, total: number, marks = 0): string {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return `${done} of ${total} frames, ${pct} %${marks ? `, ${marks} autofocus pass${marks > 1 ? 'es' : ''}` : ''}`;
}

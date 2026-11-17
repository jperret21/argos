/**
 * The job strip (web/spec/07-review-analysis.md WF-F, README 3.7): which job a one-line strip
 * shows, its count text and its ETA. Pure, tested without a browser.
 *
 * - The strip shows the newest ACTIVE job of the kinds it is given; when none runs, the
 *   newest finished one that was not dismissed (its outcome stays until the observer
 *   dismisses it or another job starts), so a failure is never only a toast.
 * - ETA from the observed rate: only once two units are done and three seconds have passed
 *   (an early estimate swings by minutes), never for an indeterminate job.
 */

import { duration } from '../format/time';
import { int } from '../format/number';
import { isActive, type JobEntry } from '../app/jobs';

/** The job the strip shows, and how many other active ones it hides. */
export function stripJob(jobs: readonly JobEntry[], kinds: readonly string[] | null = null): { job: JobEntry | null; others: number } {
  const mine = kinds ? jobs.filter((j) => kinds.includes(j.kind)) : [...jobs];
  const active = mine.filter(isActive);
  if (active.length) return { job: active[active.length - 1], others: active.length - 1 };
  return { job: mine.length ? mine[mine.length - 1] : null, others: 0 };
}

/** Seconds left at the observed rate, or null when it cannot be said yet. */
export function etaSeconds(job: Pick<JobEntry, 'done' | 'total' | 'started_utc' | 'state'>, now: number = Date.now()): number | null {
  if (!isActive(job) || job.total === null || !(job.total > 0)) return null;
  const start = job.started_utc ? Date.parse(job.started_utc) : NaN;
  if (!Number.isFinite(start)) return null;
  const elapsed = (now - start) / 1000;
  if (job.done < 2 || elapsed < 3) return null;
  const left = Math.max(0, job.total - job.done);
  return (left * elapsed) / job.done;
}

/** "ETA 2m 10s", or null. */
export function etaText(job: Pick<JobEntry, 'done' | 'total' | 'started_utc' | 'state'>, now: number = Date.now()): string | null {
  const s = etaSeconds(job, now);
  return s === null ? null : `ETA ${duration(s)}`;
}

/** "37 / 195 frames" (grouped digits), or null for an indeterminate job. */
export function countText(job: Pick<JobEntry, 'done' | 'total'>, unit = ''): string | null {
  if (job.total === null || !(job.total > 0)) return null;
  return `${int(job.done)} / ${int(job.total)}${unit ? ` ${unit}` : ''}`;
}

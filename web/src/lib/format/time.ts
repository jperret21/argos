/**
 * Time formats (BRAND.md section 5): UTC named, durations "1h 05m", "12m 30s",
 * "45 s", Julian dates with 5 decimals (0.86 s). Merged from the lab copies
 * (src/lab/charts/core/format.ts, src/lab/workspace/model/format.ts) with
 * lib/app/jobs.ts' duration rule. Pure string operations, no Intl.
 */

import { DASH } from './number';

const pad2 = (n: number) => (n < 10 ? `0${n}` : String(n));

/** "21:34:05" (or "21:34") from unix seconds, UTC, rounded to the second. */
export function clockUtc(t: number, withSeconds = true): string {
  if (!Number.isFinite(t)) return DASH;
  const s = Math.round(t);
  const d = ((s % 86400) + 86400) % 86400;
  const h = Math.floor(d / 3600);
  const m = Math.floor((d % 3600) / 60);
  return withSeconds ? `${pad2(h)}:${pad2(m)}:${pad2(d % 60)}` : `${pad2(h)}:${pad2(m)}`;
}

/** "2026-11-01" from unix seconds, UTC. */
export function utcDate(t: number): string {
  if (!Number.isFinite(t)) return DASH;
  return new Date(Math.round(t) * 1000).toISOString().slice(0, 10);
}

/** "2026-11-01 21:34:05 UTC" from unix seconds. */
export function isoUtc(t: number): string {
  if (!Number.isFinite(t)) return DASH;
  return `${utcDate(t)} ${clockUtc(t)} UTC`;
}

/** BRAND 5 durations: "45 s", "12m 30s", "1h 05m"; negative or non-finite -> "—". */
export function duration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return DASH;
  const s = Math.round(seconds);
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${pad2(s % 60)}s`;
  return `${Math.floor(s / 3600)}h ${pad2(Math.floor((s % 3600) / 60))}m`;
}

/** Julian date of a unix time (seconds). */
export function julianDate(t: number): number {
  return t / 86400 + 2440587.5;
}

/** A Julian date with 5 decimals (0.86 s), never grouped: "2461346.40123". */
export function julian(jd: number): string {
  return Number.isFinite(jd) ? jd.toFixed(5) : DASH;
}

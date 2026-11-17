/**
 * Model of the visibility timeline (spec 06 sections 1.7 and 2.3.1, Q-P6, S26): pure
 * functions over the server's A65 samples (api/sequence.ts checkVisibility). The sky
 * geometry is the server's; nothing here computes a position. What is derived: the
 * crossings of the minimum altitude (linear between samples), the windows above it during
 * the astronomical night, the twilight steps (from the Sun samples when the server sends
 * them, else the night window alone), the planning check of a run span, the hover readout.
 *
 * Every check says what it found in words: a run that starts below the limit or before
 * dusk is reported, never moved (no silent clamp).
 */

import type { Visibility } from '../api/sequence';
import { DASH, fixed } from '../format/number';
import { clockUtc, duration } from '../format/time';

/** Sun altitudes of the twilight limits (degrees; sunset with refraction and the solar radius). */
export const TWILIGHT = { sunset: -0.833, civil: -6, nautical: -12, astronomical: -18 } as const;

export interface Span {
  start: number;
  end: number;
}

export interface Crossing {
  t: number;
  rising: boolean;
}

/** Where the sampled series crosses `level`, interpolated linearly between the two samples. */
export function crossings(t: ArrayLike<number>, v: ArrayLike<number>, level: number): Crossing[] {
  const out: Crossing[] = [];
  for (let i = 1; i < t.length; i++) {
    const a = v[i - 1] - level;
    const b = v[i] - level;
    if (!Number.isFinite(a) || !Number.isFinite(b)) continue;
    if ((a < 0 && b >= 0) || (a >= 0 && b < 0)) {
      const f = a === b ? 0 : a / (a - b);
      out.push({ t: t[i - 1] + f * (t[i] - t[i - 1]), rising: b >= 0 });
    }
  }
  return out;
}

/** The spans where the series is at or above `level`, each clipped to `clip` when given. */
export function aboveSpans(t: ArrayLike<number>, v: ArrayLike<number>, level: number, clip: Span | null = null): Span[] {
  const n = t.length;
  if (n < 2) return [];
  const spans: Span[] = [];
  let start: number | null = v[0] >= level ? t[0] : null;
  for (const c of crossings(t, v, level)) {
    if (c.rising) start = c.t;
    else if (start !== null) {
      spans.push({ start, end: c.t });
      start = null;
    }
  }
  if (start !== null) spans.push({ start, end: t[n - 1] });
  if (!clip) return spans;
  return spans.map((s) => ({ start: Math.max(s.start, clip.start), end: Math.min(s.end, clip.end) })).filter((s) => s.end > s.start);
}

/** 0 night, 1 astronomical, 2 nautical, 3 civil twilight, 4 day. */
export function twilightLevel(sunAlt: number): 0 | 1 | 2 | 3 | 4 {
  return sunAlt > TWILIGHT.sunset ? 4 : sunAlt > TWILIGHT.civil ? 3 : sunAlt > TWILIGHT.nautical ? 2 : sunAlt > TWILIGHT.astronomical ? 1 : 0;
}

export const PHASE_NAMES = ['night', 'astronomical twilight', 'nautical twilight', 'civil twilight', 'day'] as const;

export interface TwilightSpan extends Span {
  level: 1 | 2 | 3 | 4;
}

/**
 * The washes behind the plot: contiguous spans of one twilight level (night left clear).
 * With the Sun samples, the four steps, bounded half-way between samples; with the night
 * window only, everything outside it as one level-2 wash ("not astronomical night").
 */
export function twilightSpans(vis: Pick<Visibility, 't' | 'sun' | 'dark'>): TwilightSpan[] {
  const { t, sun, dark } = vis;
  const n = t.length;
  if (n < 2) return [];
  const t0 = t[0];
  const t1 = t[n - 1];
  const out: TwilightSpan[] = [];
  if (sun) {
    const edge = (i: number) => (i <= 0 ? t0 : i >= n ? t1 : (t[i - 1] + t[i]) / 2);
    let i0 = 0;
    for (let i = 1; i <= n; i++) {
      if (i === n || twilightLevel(sun[i]) !== twilightLevel(sun[i0])) {
        const lv = twilightLevel(sun[i0]);
        if (lv > 0) out.push({ start: edge(i0), end: edge(i), level: lv as 1 | 2 | 3 | 4 });
        i0 = i;
      }
    }
    return out;
  }
  if (!dark) return [];
  if (dark.start > t0) out.push({ start: t0, end: Math.min(dark.start, t1), level: 2 });
  if (dark.end < t1) out.push({ start: Math.max(dark.end, t0), end: t1, level: 2 });
  return out;
}

/** The altitude split at the limit: solid above, dashed below; each part keeps the sample next to the crossing so they join. */
export function splitAtLimit(alt: ArrayLike<number>, limit: number): { above: (number | null)[]; below: (number | null)[] } {
  const n = alt.length;
  const above: (number | null)[] = new Array(n);
  const below: (number | null)[] = new Array(n);
  const up = (i: number) => i >= 0 && i < n && alt[i] >= limit;
  const down = (i: number) => i >= 0 && i < n && alt[i] < limit;
  for (let i = 0; i < n; i++) {
    const a = alt[i];
    above[i] = Number.isFinite(a) && (up(i) || up(i - 1) || up(i + 1)) ? a : null;
    below[i] = Number.isFinite(a) && (down(i) || down(i - 1) || down(i + 1)) ? a : null;
  }
  return { above, below };
}

/** Pickering (2002) airmass, as sky_geometry.compute_airmass (null at or below the horizon). */
export function airmass(altDeg: number): number | null {
  if (!(altDeg > 0)) return null;
  const d = Math.sin(((altDeg + 244 / (165 + 47 * altDeg ** 1.1)) * Math.PI) / 180);
  return d > 0 ? Math.round((1 / d) * 1e4) / 1e4 : null;
}

/** "UTC+1", "UTC−3:30", "UTC" for the browser's zone at unix time t (the computer's clock, as Qt). */
export function zoneLabel(offsetMin: number): string {
  if (!offsetMin) return 'UTC';
  const s = offsetMin > 0 ? '+' : '−';
  const a = Math.abs(offsetMin);
  return `UTC${s}${Math.floor(a / 60)}${a % 60 ? `:${String(a % 60).padStart(2, '0')}` : ''}`;
}

/** Minutes east of UTC of the browser's zone at unix time t. */
export const browserOffsetMin = (t: number): number => -new Date(t * 1000).getTimezoneOffset();

export interface RunCheck {
  /** ok: inside the night and above the limit; note: part of it is not. */
  ok: boolean;
  text: string;
}

/**
 * The planning check of a run span (spec 2.3.3 "coverage ends below 30°"): what part of it
 * is below the limit (from `above`, the spans above the limit whatever the Sun) and what
 * part is outside the astronomical night, in words; `nightWindows` (above the limit AND in
 * the night) only decides "stays below during the night". Null without a run.
 */
export function runCheck(run: Span | null, above: readonly Span[], nightWindows: readonly Span[], limit: number, dark: Span | null, label: string): RunCheck | null {
  if (!run || !(run.end > run.start)) return null;
  const range = `${clockUtc(run.start, false)} → ${clockUtc(run.end, false)} UTC`;
  if (!nightWindows.length) return { ok: false, text: `${label} stays below ${limit}° during the astronomical night` };
  const total = run.end - run.start;
  let inside = 0;
  for (const w of above) inside += Math.max(0, Math.min(run.end, w.end) - Math.max(run.start, w.start));
  const parts: string[] = [];
  if (total - inside > 30) {
    const first = above.find((w) => w.end > run.start) ?? null;
    const before = first ? Math.max(0, Math.min(first.start, run.end) - run.start) : total;
    const last = [...above].reverse().find((w) => w.start < run.end) ?? null;
    const after = last ? Math.max(0, run.end - Math.max(last.end, run.start)) : 0;
    if (before > 30 && before < total) parts.push(`first ${duration(before)}`);
    if (after > 30) parts.push(`last ${duration(after)}`);
    if (!parts.length) parts.push(duration(total - inside));
  }
  const night: string[] = [];
  if (dark && run.start < dark.start - 30) night.push(`starts ${duration(dark.start - run.start)} before astronomical dusk`);
  if (dark && run.end > dark.end + 30) night.push(`ends ${duration(run.end - dark.end)} after astronomical dawn`);
  if (!parts.length && !night.length) return { ok: true, text: `Planned run ${range} stays above ${limit}°` };
  const bits = [...(parts.length ? [`${parts.join(' and ')} below ${limit}°`] : []), ...night];
  return { ok: false, text: `Planned run ${range}: ${bits.join('; ')}` };
}

/** Index of the sample nearest to x (samples ascending). */
export function nearestIndex(t: ArrayLike<number>, x: number): number {
  let lo = 0;
  let hi = t.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (t[mid] <= x) lo = mid;
    else hi = mid;
  }
  return Math.abs(t[hi] - x) < Math.abs(x - t[lo]) ? hi : lo;
}

export interface HoverRead {
  utc: string;
  local: string;
  alt: string;
  airmass: string;
  phase: string;
}

/** The readout of sample i: times, altitude (the server's value, 1 decimal), airmass, sky phase. */
export function hoverRead(vis: Pick<Visibility, 't' | 'alt' | 'sun' | 'dark'>, i: number, offsetMin: number): HoverRead {
  const t = vis.t[i];
  const a = vis.alt[i];
  const am = airmass(a);
  const phase = vis.sun
    ? PHASE_NAMES[twilightLevel(vis.sun[i])]
    : vis.dark
      ? t >= vis.dark.start && t <= vis.dark.end
        ? 'astronomical night'
        : 'outside the astronomical night'
      : DASH;
  return {
    utc: clockUtc(t, false),
    local: clockUtc(t + offsetMin * 60, false),
    alt: `${fixed(a, 1)}°`,
    airmass: am === null ? DASH : fixed(am, 2),
    phase,
  };
}

/** The peak sits on a night edge within this (s): the source culminates outside the night. */
const EDGE_S = 600;

/**
 * The night's highest point in words. The server's peak is the highest point inside the
 * astronomical night: when it sits on dusk or dawn the source culminated outside the night
 * (the curve rises higher before dusk), so it is "highest at night" with the edge named, never
 * "peak" (design review W6a).
 */
export function peakWords(vis: Pick<Visibility, 'dark' | 'peak'>): string | null {
  const pk = vis.peak;
  if (!pk) return null;
  const edge = vis.dark ? (Math.abs(pk.t - vis.dark.start) <= EDGE_S ? 'dusk' : Math.abs(pk.t - vis.dark.end) <= EDGE_S ? 'dawn' : null) : null;
  return edge
    ? `highest at night ${fixed(pk.alt, 1)}° at ${clockUtc(pk.t, false)} (${edge})`
    : `peak ${fixed(pk.alt, 1)}° at ${clockUtc(pk.t, false)}`;
}

/** The header's facts: night, peak, time above the limit (one line, UTC named). */
export function factsLine(vis: Pick<Visibility, 'dark' | 'peak'>, windows: readonly Span[], limit: number): string {
  const bits: string[] = [];
  if (vis.dark) bits.push(`night ${clockUtc(vis.dark.start, false)} → ${clockUtc(vis.dark.end, false)} UTC`);
  const pk = peakWords(vis);
  if (pk) bits.push(pk);
  if (windows.length) {
    const total = windows.reduce((s, w) => s + w.end - w.start, 0);
    const w = windows.length === 1 ? `${clockUtc(windows[0].start, false)} → ${clockUtc(windows[0].end, false)}` : `${windows.length} spans`;
    bits.push(`above ${limit}° ${w} (${duration(total)})`);
  } else bits.push(`never above ${limit}° at night`);
  return bits.join(' · ');
}

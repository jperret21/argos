/**
 * A synthetic night, modelled on the AGGREGATE numbers of the owner's longest
 * run (RR Lyr, 2026-09-25, functional-spaces.md 1.2): 195 frames of 10 s,
 * median start-to-start 51.5 s, HFD near 6.25 px that jumps to about 17 px
 * from frame 148 to the end, star count near 2 982, sky 1 168-1 192 ADU, the
 * target fading about 0.12 mag/h, comparisons used mostly 5 of 6.
 *
 * Nothing here is a copy of the owner's data: every value is generated from a
 * seeded model, so screenshots are reproducible. Unlike the real run, this
 * one has a check star (the UI must also handle "no check star"; see the
 * Watch view's variant).
 */

import { prng } from './field';

export const RUN = {
  object: 'RR Lyr',
  /** 2026-09-25 20:04:53 UTC (session 20260925T200453Z), unix seconds. */
  start: Date.UTC(2026, 8, 25, 20, 4, 53) / 1000,
  frames: 195,
  exposure: 10,
  gain: 80,
  filter: 'IR',
  band: 'TG',
  endAction: 'Nothing',
  comparisons: 6,
} as const;

export interface FrameRecord {
  /** Frame number, 1-based. */
  n: number;
  /** Mid-exposure time, unix seconds (UTC). */
  t: number;
  /** Half-flux diameter, px. */
  hfd: number;
  stars: number;
  /** Sky median, ADU. */
  sky: number;
  target: number;
  targetErr: number;
  check: number;
  checkErr: number;
  /** Comparisons kept in the ensemble after clipping. */
  compsUsed: number;
  /** Target altitude, degrees. */
  alt: number;
}

function gauss(rand: () => number): number {
  let u = 0;
  while (u === 0) u = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rand());
}

/** Frame number where the synthetic focus loss starts (as in the real run). */
export const FOCUS_LOSS_FRAME = 148;

export function buildNight(seed = 25): FrameRecord[] {
  const rand = prng(seed);
  const out: FrameRecord[] = [];
  let t = RUN.start + RUN.exposure / 2;
  const span = 169.3 * 60;
  for (let n = 1; n <= RUN.frames; n++) {
    if (n > 1) {
      // Cadence 51.5 s with ±0.8 s jitter, and one slow frame (74.6 s) as in the real run.
      t += n === 88 ? 74.6 : 51.5 + 0.8 * gauss(rand);
    }
    const hours = (t - RUN.start) / 3600;
    const lost = n >= FOCUS_LOSS_FRAME;
    const hfd = lost
      ? 16.6 + 0.012 * (n - FOCUS_LOSS_FRAME) + 0.7 * gauss(rand)
      : 6.25 + 0.22 * Math.sin(n / 23) + 0.16 * gauss(rand);
    const stars = Math.round((lost ? 2460 : 2982) + (lost ? 120 : 105) * gauss(rand));
    const sky = 1180 + 6 * Math.sin(n / 31) + 3 * gauss(rand);
    const tErr = lost ? 0.035 : 0.012;
    const cErr = lost ? 0.03 : 0.011;
    const frac = Math.min(1, (t - RUN.start) / span);
    // Comparisons used: mostly 5 of 6, sometimes 4 or 3; a lone 2 is possible
    // but never twice in a row (the rule would fire).
    const r = rand();
    let comps = r < 0.55 ? 5 : r < 0.85 ? 4 : 3;
    if (lost && r > 0.96 && out[out.length - 1]?.compsUsed !== 2) comps = 2;
    out.push({
      n,
      t,
      hfd,
      stars,
      sky,
      target: 7.36 + 0.12 * hours + tErr * gauss(rand),
      targetErr: tErr * (0.9 + 0.2 * rand()),
      check: 8.62 + cErr * gauss(rand),
      checkErr: cErr * (0.9 + 0.2 * rand()),
      compsUsed: comps,
      alt: 75.4 - 28.3 * Math.pow(frac, 1.15),
    });
  }
  return out;
}

export function median(values: ArrayLike<number>): number {
  const a = Array.from(values).filter(Number.isFinite).sort((x, y) => x - y);
  if (!a.length) return NaN;
  const m = a.length >> 1;
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
}

/** Median start-to-start interval of the records so far (s). */
export function medianCadence(records: readonly FrameRecord[]): number {
  if (records.length < 2) return NaN;
  const d: number[] = [];
  for (let i = 1; i < records.length; i++) d.push(records[i].t - records[i - 1].t);
  return median(d);
}

/** Planned end of the run from the observed cadence. */
export function expectedEnd(records: readonly FrameRecord[], total: number): number {
  const last = records[records.length - 1];
  const c = medianCadence(records);
  if (!last || !Number.isFinite(c)) return NaN;
  return last.t + (total - last.n) * c;
}

// -- Autofocus (Focus mode) ------------------------------------------------------------

export interface FocusStep {
  position: number;
  hfd: number;
}

/** A V-curve: 14 positions, best focus near 1 305 steps, HFD minimum near 5.8 px. */
export function buildAutofocus(seed = 7): { steps: FocusStep[]; best: number; bestHfd: number } {
  const rand = prng(seed);
  const best = 1305;
  const steps: FocusStep[] = [];
  for (let i = 0; i < 14; i++) {
    const position = 975 + i * 50;
    const d = (position - best) / 52;
    steps.push({ position, hfd: Math.sqrt(5.8 * 5.8 + (2.15 * d) ** 2) + 0.18 * gauss(rand) });
  }
  return { steps, best, bestHfd: 5.8 };
}

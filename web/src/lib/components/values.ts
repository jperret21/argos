/**
 * Pure value logic shared by the value controls (NumberField, Stepper,
 * Slider, later the focuser): stepping, ladders, fine adjustment, ticks,
 * detents, auto-repeat timing. No DOM; unit-tested (values.test.ts).
 *
 * Promoted from src/lab/controls/values.ts (web/lab/PROPOSAL.md section 6,
 * W2). One modifier convention on every value control (BRAND 8, PROPOSAL 4):
 *   plain        one step
 *   Shift        ×10 (coarse; a slider drag snaps to the minor ticks)
 *   Alt/Option   ×0.1 (fine; a slider drag also slows to 1/10 of the pointer)
 * The wheel acts only on a focused control; Esc returns to the device value.
 */

export type Precision = 'normal' | 'coarse' | 'fine';

export function precisionOf(e: { shiftKey: boolean; altKey: boolean }): Precision {
  if (e.altKey) return 'fine';
  if (e.shiftKey) return 'coarse';
  return 'normal';
}

export const FACTOR: Record<Precision, number> = { normal: 1, coarse: 10, fine: 0.1 };

/** Decimals needed to show a step exactly (0.1 -> 1, 0.25 -> 2, 5 -> 0). */
export function decimalsOf(step: number): number {
  if (!Number.isFinite(step) || step <= 0) return 0;
  const s = step.toString();
  if (s.includes('e-')) return Number(s.split('e-')[1]);
  const i = s.indexOf('.');
  return i < 0 ? 0 : s.length - i - 1;
}

/** Round to a multiple of `step` from `origin`, without float dust. */
export function roundTo(v: number, step: number, origin = 0): number {
  if (step <= 0) return v;
  const n = Math.round((v - origin) / step);
  const digits = Math.min(12, Math.max(decimalsOf(step), decimalsOf(Math.abs(origin))));
  return Number((origin + n * step).toFixed(digits));
}

export function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

/**
 * The step a precision gives. Integer quantities never get a fractional
 * step: Alt on a step of 1 stays 1 (a gain is not 80.1).
 */
export function stepFor(step: number, p: Precision, integer = false): number {
  const s = step * FACTOR[p];
  return integer ? Math.max(1, Math.round(s)) : s;
}

/**
 * One step in a direction with a precision (keyboard, wheel, stepper); stops
 * at the limits. The value moves to the next multiple of the step in that
 * direction: on the grid that is exactly one step (80 -> 90 with Shift); a
 * value between grid lines goes to the neighbouring line (85 -> 90, never
 * past it), so a step never overshoots and repeated steps land on round
 * numbers.
 */
export function stepValue(
  v: number,
  dir: 1 | -1,
  step: number,
  p: Precision,
  min: number,
  max: number,
  integer = false,
): number {
  const s = stepFor(step, p, integer);
  if (!(s > 0) || !Number.isFinite(v)) return clamp(v, min, max);
  const q = v / s;
  const n = dir > 0 ? Math.floor(q + 1e-9) + 1 : Math.ceil(q - 1e-9) - 1;
  return clamp(roundTo(n * s, s), min, max);
}

// -- Ladders (exposure): preferred values the controls step through ------------------

export const EXPOSURE_LADDER: readonly number[] = [
  0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 3, 5, 8, 10, 15, 20, 30, 45, 60, 90, 120, 180, 300, 600,
];

/** Next rung strictly above (dir 1) or below (dir -1) `v`; a value between rungs goes to the neighbour. */
export function ladderStep(ladder: readonly number[], v: number, dir: 1 | -1, rungs = 1): number {
  let out = v;
  for (let k = 0; k < rungs; k++) {
    if (dir > 0) {
      const next = ladder.find((r) => r > out + 1e-12);
      if (next === undefined) break;
      out = next;
    } else {
      let prev: number | undefined;
      for (const r of ladder) if (r < out - 1e-12) prev = r;
      if (prev === undefined) break;
      out = prev;
    }
  }
  return out;
}

/** Index of the rung nearest to `v` (log distance, so 1.4 is nearer 1 than 2). */
export function nearestRung(ladder: readonly number[], v: number): number {
  let best = 0;
  let d = Infinity;
  ladder.forEach((r, i) => {
    const dist = Math.abs(Math.log(r) - Math.log(Math.max(v, 1e-9)));
    if (dist < d) {
      d = dist;
      best = i;
    }
  });
  return best;
}

// -- Scrubbing (drag on a field's label or body; first used in W3) -------------------

export interface ScrubSpec {
  start: number;
  /** Pointer travel since the press, px (right positive). */
  dx: number;
  step: number;
  min: number;
  max: number;
  precision: Precision;
  /** Pixels per step at normal precision. */
  pxPerStep?: number;
  ladder?: readonly number[];
}

/**
 * Value under a scrub. Linear fields: one step per `pxPerStep`, ×10 / ×0.1
 * with Shift / Alt. Ladder fields: one rung per 12 px (4 px with Shift); Alt
 * leaves the ladder for linear fine steps of `step`.
 */
export function scrubValue(s: ScrubSpec): number {
  const px = s.pxPerStep ?? 4;
  if (s.ladder && s.precision !== 'fine') {
    const per = s.precision === 'coarse' ? 4 : 12;
    const rungs = Math.trunc(s.dx / per);
    if (rungs === 0) return s.start;
    return clamp(ladderStep(s.ladder, s.start, rungs > 0 ? 1 : -1, Math.abs(rungs)), s.min, s.max);
  }
  const unit = s.step * FACTOR[s.precision];
  const n = Math.trunc(s.dx / px);
  return clamp(roundTo(s.start + n * unit, unit), s.min, s.max);
}

// -- Sliders -----------------------------------------------------------------------------

export function ratioOf(v: number, min: number, max: number): number {
  return max === min ? 0 : clamp((v - min) / (max - min), 0, 1);
}

export function valueAt(ratio: number, min: number, max: number): number {
  return min + clamp(ratio, 0, 1) * (max - min);
}

export interface Tick {
  value: number;
  major: boolean;
}

/** Minor ticks every `minor`, major every `major` (aligned on multiples from 0). */
export function ticks(min: number, max: number, minor: number, major: number): Tick[] {
  const out: Tick[] = [];
  if (!(minor > 0) || !(major > 0) || !(max >= min)) return out;
  const first = Math.ceil(min / minor - 1e-9) * minor;
  for (let v = first; v <= max + 1e-9; v += minor) {
    const value = roundTo(v, minor);
    const q = value / major;
    out.push({ value, major: Math.abs(q - Math.round(q)) < 1e-6 });
  }
  return out;
}

/**
 * Value during a drag. Normal: the thumb is under the pointer (absolute),
 * rounded to `step`. Coarse (Shift): snapped to `snap` (the minor ticks).
 * Fine (Alt): relative to where fine mode began, at 1/10 of the pointer's
 * travel, rounded to step / 10.
 */
export function dragValue(o: {
  x: number;
  width: number;
  min: number;
  max: number;
  step: number;
  precision: Precision;
  snap?: number;
  fineFrom?: { x: number; value: number };
}): number {
  if (o.precision === 'fine' && o.fineFrom) {
    const perPx = (o.max - o.min) / Math.max(1, o.width);
    const v = o.fineFrom.value + (o.x - o.fineFrom.x) * perPx * FACTOR.fine;
    return clamp(roundTo(v, o.step * FACTOR.fine), o.min, o.max);
  }
  const raw = valueAt(o.x / Math.max(1, o.width), o.min, o.max);
  const q = o.precision === 'coarse' ? (o.snap ?? o.step * 10) : o.step;
  return clamp(roundTo(raw, q, o.min), o.min, o.max);
}

/** Magnetic detent: within `radius` (value units) of a detent, the value IS the detent. */
export function applyDetent(v: number, detents: readonly number[], radius: number): number {
  for (const d of detents) if (Math.abs(v - d) <= radius) return d;
  return v;
}

// -- Auto-repeat (steppers, focuser taps held down) ----------------------------------
// The same numbers as --repeat-delay / --repeat-interval (tokens.css); timers
// cannot read CSS before the first paint, so they are restated here.

export interface RepeatTiming {
  delay: number;
  interval: number;
  /** After this long repeating, each repeat is ×10 (coarse). */
  accelAfter: number;
}

export const REPEAT: RepeatTiming = { delay: 400, interval: 80, accelAfter: 1600 };

/** How many repeats have fired `elapsed` ms after the press (the press itself is not counted). */
export function repeatsBy(elapsed: number, t: RepeatTiming = REPEAT): number {
  if (elapsed < t.delay) return 0;
  return 1 + Math.floor((elapsed - t.delay) / t.interval);
}

/** Step multiplier for the repeat that fires at `elapsed`. */
export function repeatFactor(elapsed: number, t: RepeatTiming = REPEAT): 1 | 10 {
  return elapsed - t.delay >= t.accelAfter ? 10 : 1;
}

// -- Time ring -----------------------------------------------------------------------

/**
 * The fraction a time ring draws: clamped to 0..1, floored to quarters under
 * reduced motion (the state stays visible, nothing glides); null = no arc.
 */
export function ringFraction(value: number | null | undefined, stepped = false): number | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  const v = clamp(value, 0, 1);
  return stepped ? Math.floor(v * 4 + 1e-9) / 4 : v;
}

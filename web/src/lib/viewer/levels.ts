/**
 * Display levels as handles on the histogram's x axis (ADU).
 *
 * Black and white are ADU values and sit where they are. The midtones
 * balance m is not an ADU value: after the transfer T (linear, log or asinh),
 * the midtones transfer function maps T(x) = m to 0.5. Its handle therefore
 * sits at the raw level whose stretched value is one half:
 *
 *   x = black + T⁻¹(m) (white − black)
 *
 * and dragging it inverts that relation. Dragged values snap to whole ADU,
 * the balance to 0.001 (the precision of its numeric field). Display only:
 * the data and every measurement keep the raw values.
 */

import { ASINH_K, effectiveMidtones, LOG_K, type StretchMode, type StretchParams } from './stretch';

export type LevelHandle = 'black' | 'mid' | 'white';

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Linear fraction of [black, white] at which the transfer reaches the balance m. */
export function midtonesFraction(midtones: number, mode: StretchMode): number {
  const m = effectiveMidtones(midtones);
  if (mode === 'log') return Math.expm1(m * Math.log1p(LOG_K)) / LOG_K;
  if (mode === 'asinh') return Math.sinh(m * Math.asinh(ASINH_K)) / ASINH_K;
  return m;
}

/** Inverse of midtonesFraction: the balance whose handle sits at fraction f. */
export function midtonesFromFraction(f: number, mode: StretchMode): number {
  const x = clamp(f, 0, 1);
  let m = x;
  if (mode === 'log') m = Math.log1p(LOG_K * x) / Math.log1p(LOG_K);
  else if (mode === 'asinh') m = Math.asinh(ASINH_K * x) / Math.asinh(ASINH_K);
  return clamp(Math.round(m * 1000) / 1000, 0.001, 0.999);
}

/** ADU of each handle (white kept above black, as the shader does). */
export function handleLevels(p: StretchParams): Record<LevelHandle, number> {
  const white = p.white <= p.black ? p.black + 1 : p.white;
  return {
    black: p.black,
    mid: p.black + midtonesFraction(p.midtones, p.mode) * (white - p.black),
    white,
  };
}

/** The level change for handle `which` dragged to `adu`. Black stays below white. */
export function dragLevel(
  which: LevelHandle,
  adu: number,
  p: StretchParams,
): Partial<Omit<StretchParams, 'mode'>> {
  const v = Math.round(clamp(adu, 0, 65535));
  if (which === 'black') return { black: Math.min(v, p.white - 1) };
  if (which === 'white') return { white: Math.max(v, p.black + 1) };
  const white = p.white <= p.black ? p.black + 1 : p.white;
  return { midtones: midtonesFromFraction((adu - p.black) / (white - p.black), p.mode) };
}

/** The handle within `tolerance` px of `x` (nearest first), given their positions in px. */
export function pickHandle(
  x: number,
  positions: Record<LevelHandle, number>,
  tolerance = 8,
): LevelHandle | null {
  let best: LevelHandle | null = null;
  let bestD = tolerance;
  // Black and white before mid: at equal distance the ends win (they are the ones that move most).
  for (const h of ['black', 'white', 'mid'] as const) {
    const d = Math.abs(positions[h] - x);
    if (d < bestD || (best === null && d <= bestD)) {
      best = h;
      bestD = d;
    }
  }
  return best;
}

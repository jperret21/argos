/**
 * What the Statistics card says (web/spec/04-viewer-and-image-tools.md 2.2 rows
 * 1.7, 2.3 "Rail cards"; Qt statistics_dock.py:22, rows R1-R11), as pure
 * functions:
 * - Frame block: mean, median, std, MAD, min, max of ALL raw samples (ADU),
 *   exact from the viewer's 65 536-bin histogram (no subsampling);
 * - ADC depth from the quantization step (Q-O21, fixes P16): a 12-bit sensor
 *   scaled into 16 bits reads "12-bit (16 ADU steps)", never "16-bit";
 * - Stars block from the server's frame_metrics (A26), with the frame it was
 *   measured on when that is not the frame on screen.
 */

import { quantizationStep } from '../histogram';
import { median, medianAbsDeviation, stdDev, type Histogram16 } from '../stretch';

export interface FrameStatistics {
  n: number;
  mean: number;
  median: number;
  std: number;
  mad: number;
  min: number;
  max: number;
  /** ADU between adjacent levels the sensor delivers (1: every value). */
  step: number;
  /** Effective ADC bits: 16 − log2(step). */
  bits: number;
}

export function frameStatistics(h: Histogram16 | null): FrameStatistics | null {
  if (!h || h.n === 0) return null;
  let sum = 0;
  for (let v = h.min; v <= h.max; v++) sum += h.counts[v] * v;
  const med = median(h);
  const step = quantizationStep(h);
  return {
    n: h.n,
    mean: sum / h.n,
    median: med,
    std: stdDev(h),
    mad: medianAbsDeviation(h, med),
    min: h.min,
    max: h.max,
    step,
    bits: 16 - Math.round(Math.log2(step)),
  };
}

/** "12-bit (16 ADU steps)", or "16-bit" for data on every level. */
export function adcText(s: Pick<FrameStatistics, 'bits' | 'step'>): string {
  return s.step > 1 ? `${s.bits}-bit (${s.step} ADU steps)` : `${s.bits}-bit`;
}

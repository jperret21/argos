/**
 * The exposure check of the Framing band ("check the peak, not the
 * picture"), as data: true-length bars from 0 to full scale (65 535 ADU) for
 * the brightest stars of the frame on screen, with the profile's linearity
 * limit and full well marked, the pixels the ADC clipped, the sky and the
 * server's frame metrics. Never an "OK" badge: the numbers and a word per
 * star (clipped, above the linearity limit) say what the observer needs.
 *
 * Promoted from src/lab/workspace/observe/bands/FramingBand.svelte (web/lab/
 * PROPOSAL.md section 6, W3). In wave 3 there are no roles yet (field
 * identification is wave 4), so the bars are the brightest stars by peak,
 * measured by the frame worker (viewer/framestats.ts); once roles exist the
 * target and the comparisons take the first rows.
 */

import type { Clipping, StarPeaks } from '../../viewer/framestats';

export const FULL_SCALE = 65535;

/** The server's metrics of one frame (A26 `frame_metrics`). */
export interface FrameMetricsRecord {
  seq: number;
  hfd_px?: number | null;
  fwhm_px?: number | null;
  eccentricity?: number | null;
  star_count?: number | null;
  n_detected?: number | null;
  sky_adu?: number | null;
  peak_adu?: number | null;
  star_radius_px?: number | null;
  plane?: string | null;
  t?: string | null;
}

export type PeakState = 'ok' | 'nonlinear' | 'clipped';

export interface PeakRow {
  /** "1", "2" … rank by peak. */
  rank: number;
  peak: number;
  /** 0..1 of full scale (65 535); an unknown peak draws an empty bar, never a full one. */
  frac: number;
  state: PeakState;
  x: number;
  y: number;
}

export interface ExposureCheck {
  /** The unclipped stars when several clipped (they are one group line), else the brightest. */
  rows: PeakRow[];
  /** Two or more stars at the top code: one line says how many (0: none, or one shown as a row). */
  clippedGroup: number;
  /** Where the stars of the clipped line are (frame px), to mark them on the image on hover. */
  clippedPoints: { x: number; y: number }[];
  /** Lines the band has room for: the list keeps this height whatever the frame (no jump). */
  capacity: number;
  /** Frames between the one measured and the one on screen (0: this frame; null: none). */
  lag: number | null;
  /** Marks on the bars, fractions of full scale. */
  linearity: number | null;
  fullWell: number | null;
  /** The ADC's top code in this data (65 520 for 12-bit data in 16 bits). */
  topCode: number | null;
  clipped: number | null;
  clippedFraction: number | null;
  /** Detected stars at or above the linearity limit / at the top code. */
  starsNonLinear: number;
  starsClipped: number;
  sky: number | null;
  /**
   * Server metrics of the frame on screen, or of a frame just before it while
   * this one is measured (`metricsCurrent` false; the view says which frame).
   */
  metrics: FrameMetricsRecord | null;
  metricsCurrent: boolean;
  /** The frame the star peaks were measured on (null: none). */
  peaksSeq: number | null;
  /** Peaks belong to the frame on screen (false while the worker measures it). */
  current: boolean;
}

/**
 * How many frames back a measurement may still be shown, marked with its frame
 * number, while the frame on screen is being measured. Without it the numbers
 * would blink to "—" on every live frame (the measurements arrive 50-300 ms
 * after the pixels).
 */
export const RECENT_FRAMES = 3;

/**
 * The star peaks stay on screen, labelled with their frame and lag, up to this
 * many frames behind the frame on screen (the frame worker can lag on a slow
 * GPU): the list never blanks between two measurements (design review W3).
 */
export const KEEP_PEAKS_FRAMES = 10;

/** A measurement of frame `of` may stand for frame `seq` (the same, or just before it, never after). */
export function recent(of: number | null | undefined, seq: number | null): boolean {
  return typeof of === 'number' && seq !== null && of <= seq && seq - of <= RECENT_FRAMES;
}

export const frac = (v: number | null | undefined) =>
  typeof v === 'number' && Number.isFinite(v) ? Math.min(1, Math.max(0, v / FULL_SCALE)) : 0;

export function peakState(peak: number, topCode: number | null, linearity: number | null): PeakState {
  if (topCode !== null && peak >= topCode) return 'clipped';
  if (linearity !== null && peak >= linearity) return 'nonlinear';
  return 'ok';
}

export interface ExposureInput {
  seq: number | null;
  peaks: { seq: number; result: StarPeaks } | null;
  clip: Clipping | null;
  metrics: FrameMetricsRecord | null;
  linearity?: number | null;
  fullWell?: number | null;
  /** Bars shown (the band's height decides). */
  rows?: number;
}

export function exposureCheck(i: ExposureInput): ExposureCheck {
  const current = i.peaks !== null && i.seq !== null && i.peaks.seq === i.seq;
  const usable =
    i.peaks !== null && i.seq !== null && i.peaks.seq <= i.seq && i.seq - i.peaks.seq <= KEEP_PEAKS_FRAMES;
  const stars = usable ? i.peaks!.result.stars : [];
  const lin = i.linearity ?? null;
  const top = i.clip?.topCode ?? null;
  const capacity = i.rows ?? 5;
  const all = stars.map((s, k) => ({
    rank: k + 1,
    peak: s.peak,
    frac: frac(s.peak),
    state: peakState(s.peak, top, lin),
    x: s.x,
    y: s.y,
  }));
  // Identical clipped rows carry one bit: say how many, then the brightest unclipped peaks.
  const clippedAll = all.filter((r) => r.state === 'clipped').length;
  const clippedGroup = clippedAll >= 2 ? clippedAll : 0;
  const rows = clippedGroup ? all.filter((r) => r.state !== 'clipped').slice(0, capacity - 1) : all.slice(0, capacity);
  const metrics = i.metrics && recent(i.metrics.seq, i.seq) ? i.metrics : null;
  const sky = metrics?.sky_adu ?? (usable ? i.peaks!.result.sky : null);
  return {
    rows,
    clippedGroup,
    clippedPoints: clippedGroup ? all.filter((r) => r.state === 'clipped').map((r) => ({ x: r.x, y: r.y })) : [],
    capacity,
    lag: usable ? i.seq! - i.peaks!.seq : null,
    linearity: lin !== null ? frac(lin) : null,
    fullWell: i.fullWell != null ? frac(i.fullWell) : null,
    topCode: top,
    clipped: i.clip?.clipped ?? null,
    clippedFraction: i.clip?.fraction ?? null,
    starsNonLinear: stars.filter((s) => peakState(s.peak, top, lin) !== 'ok').length,
    starsClipped: stars.filter((s) => peakState(s.peak, top, lin) === 'clipped').length,
    sky: typeof sky === 'number' && Number.isFinite(sky) ? sky : null,
    metrics,
    metricsCurrent: metrics !== null && metrics.seq === i.seq,
    peaksSeq: usable ? i.peaks!.seq : null,
    current,
  };
}

/** The effective saturation limits of the active profile (its values, or the observer's overrides). */
export function profileLimits(
  profile: { full_well_adu?: number; linearity_max_adu?: number; overrides?: Record<string, unknown> } | null | undefined,
): { linearity: number | null; fullWell: number | null } {
  if (!profile) return { linearity: null, fullWell: null };
  const o = profile.overrides ?? {};
  const pick = (k: string, v: number | undefined) => {
    const ov = o[k];
    if (typeof ov === 'number' && Number.isFinite(ov)) return ov;
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
  };
  return { linearity: pick('linearity_max_adu', profile.linearity_max_adu), fullWell: pick('full_well_adu', profile.full_well_adu) };
}

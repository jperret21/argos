/**
 * CFA preview of a colour sensor's raw mosaic, computed by the GPU (owner
 * answer Q-O22, README 8.3; web/spec/04-viewer-and-image-tools.md 2.5
 * "client-only"): the CPU part is here, the per-pixel part in viewer/shaders.ts.
 *
 * Port of the Qt preview (argos/workers/preview_processor.py:68-70 and
 * argos/core/imaging/debayer.py):
 * - Colour: the super-pixel RGB of each 2 x 2 cell (debayer.superpixel_rgb,
 *   :120-131: R, (G1 + G2) >> 1, B, real samples, no interpolation), shown on
 *   the full sensor geometry (expand_cfa_cells, :134-157), after the display
 *   balance of neutralise_rgb_for_display (:186-206): each channel's median
 *   (its sky) is brought to the median of the channel medians, gains clipped
 *   to 0.25-4, values floored into uint16 like numpy's astype.
 * - Raw: the mosaic as delivered (grey).
 * - R, G, B: one real-sample plane (debayer.extract_plane, :79-112; G is
 *   (G1 + G2) >> 1), expanded onto its cells.
 * Every view keeps the frame's geometry, so overlays and readouts never move.
 * The automatic levels follow the view, as in Qt (auto_stf of the rendered
 * array, fits_viewer.py:305-306); measurements always use the raw samples.
 *
 * Display only: the FITS data and every measurement keep the raw values.
 */

import { median, type Histogram16 } from '../stretch';

export const PREVIEWS = ['colour', 'raw', 'r', 'g', 'b'] as const;
export type Preview = (typeof PREVIEWS)[number];

export const PREVIEW_LABELS: Record<Preview, string> = { colour: 'Colour', raw: 'Raw', r: 'R', g: 'G', b: 'B' };

export function isPreview(v: unknown): v is Preview {
  return typeof v === 'string' && (PREVIEWS as readonly string[]).includes(v);
}

/** Where each colour sits in the 2 x 2 cell, [x, y] (x = column). */
export interface CfaSites {
  pattern: string;
  r: [number, number];
  g1: [number, number];
  g2: [number, number];
  b: [number, number];
}

/** "GRBG" -> sites; null for anything that is not a 2 x 2 Bayer pattern (mono data). */
export function cfaSites(pattern: string | null | undefined): CfaSites | null {
  if (typeof pattern !== 'string') return null;
  const p = pattern.trim().toUpperCase();
  if (!/^[RGB]{4}$/.test(p)) return null;
  const at = (i: number): [number, number] => [i % 2, i >> 1];
  const r = p.indexOf('R');
  const b = p.indexOf('B');
  const g1 = p.indexOf('G');
  const g2 = p.indexOf('G', g1 + 1);
  if (r < 0 || b < 0 || g1 < 0 || g2 < 0 || p.lastIndexOf('R') !== r || p.lastIndexOf('B') !== b) return null;
  return { pattern: p, r: at(r), g1: at(g1), g2: at(g2), b: at(b) };
}

/** What kind of picture a frame holds. */
export type FrameKind = 'mono' | 'cfa' | 'rgb';

export function frameKind(channels: number, bayer: string | null | undefined): FrameKind {
  if (channels === 3) return 'rgb';
  return cfaSites(bayer) ? 'cfa' : 'mono';
}

/** The previews offered for a frame (none for mono: the row is hidden, 04 2.4 "States"). */
export function previewsFor(kind: FrameKind): readonly Preview[] {
  if (kind === 'cfa') return PREVIEWS;
  if (kind === 'rgb') return ['colour', 'r', 'g', 'b'];
  return [];
}

/** The preview drawn: the observer's choice when the frame offers it. */
export function effectivePreview(chosen: Preview, kind: FrameKind): Preview {
  if (kind === 'mono') return 'raw';
  if (kind === 'rgb' && chosen === 'raw') return 'colour';
  return chosen;
}

/**
 * Shader code of a preview: 0 = the samples as delivered (mono, raw mosaic,
 * or an RGB frame); 1 = CFA colour (super-pixel, balanced); 2 / 3 / 4 = the
 * R / G / B plane (a CFA plane, or one channel of an RGB frame).
 */
export function previewCode(preview: Preview, kind: FrameKind): number {
  const p = effectivePreview(preview, kind);
  if (p === 'raw') return 0;
  if (p === 'colour') return kind === 'cfa' ? 1 : 0;
  return p === 'r' ? 2 : p === 'g' ? 3 : 4;
}

/** Real-sample histograms of the three CFA planes (complete cells only, as split_cfa). */
export interface CfaPlanes {
  sites: CfaSites;
  r: Histogram16;
  /** (G1 + G2) >> 1 per cell. */
  g: Histogram16;
  b: Histogram16;
  cells: number;
}

function hist(counts: Uint32Array, n: number): Histogram16 {
  let min = 0;
  let max = 0;
  if (n > 0) {
    while (counts[min] === 0) min++;
    max = 65535;
    while (counts[max] === 0) max--;
  }
  return { counts, n, min, max };
}

/** One pass over the cells of a raw mosaic (width x height, row 0 at the top). */
export function cfaPlanes(pixels: Uint16Array, width: number, height: number, sites: CfaSites): CfaPlanes {
  const hr = new Uint32Array(65536);
  const hg = new Uint32Array(65536);
  const hb = new Uint32Array(65536);
  const cw = width >> 1;
  const ch = height >> 1;
  const offR = sites.r[1] * width + sites.r[0];
  const offB = sites.b[1] * width + sites.b[0];
  const offG1 = sites.g1[1] * width + sites.g1[0];
  const offG2 = sites.g2[1] * width + sites.g2[0];
  for (let j = 0; j < ch; j++) {
    let i0 = 2 * j * width;
    for (let i = 0; i < cw; i++, i0 += 2) {
      hr[pixels[i0 + offR]]++;
      hb[pixels[i0 + offB]]++;
      hg[(pixels[i0 + offG1] + pixels[i0 + offG2]) >> 1]++;
    }
  }
  const n = cw * ch;
  return { sites, r: hist(hr, n), g: hist(hg, n), b: hist(hb, n), cells: n };
}

/** Per-channel medians of an RGB frame (interleaved), as histograms. */
export function rgbPlanes(pixels: Uint16Array): { r: Histogram16; g: Histogram16; b: Histogram16 } {
  const n = pixels.length / 3;
  const hr = new Uint32Array(65536);
  const hg = new Uint32Array(65536);
  const hb = new Uint32Array(65536);
  for (let i = 0, k = 0; i < n; i++, k += 3) {
    hr[pixels[k]]++;
    hg[pixels[k + 1]]++;
    hb[pixels[k + 2]]++;
  }
  return { r: hist(hr, n), g: hist(hg, n), b: hist(hb, n) };
}

/**
 * neutralise_rgb_for_display gains from the channel backgrounds (medians):
 * reference = median of the positive backgrounds, gain = clip(ref / bg, 0.25, 4),
 * 1 for a channel whose background is 0.
 */
export function neutralGains(backgrounds: readonly [number, number, number]): [number, number, number] {
  const valid = backgrounds.filter((b) => b > 0).sort((a, b) => a - b);
  if (!valid.length) return [1, 1, 1];
  const mid = valid.length >> 1;
  const ref = valid.length % 2 ? valid[mid] : (valid[mid - 1] + valid[mid]) / 2;
  return backgrounds.map((b) => (b > 0 ? Math.min(4, Math.max(0.25, ref / b)) : 1)) as [number, number, number];
}

/** float32 product, as numpy computes `values.astype(float32) * gains` (and the shader). */
const f32 = Math.fround;

/** The balanced value of one sample: floor(clip(v x gain, 0, 65535)) in float32. */
export function balanced(v: number, gain: number): number {
  return Math.floor(Math.min(65535, Math.max(0, f32(f32(v) * f32(gain)))));
}

/** Histogram of the balanced colour view: every channel value of every cell. */
export function colourHistogram(planes: { r: Histogram16; g: Histogram16; b: Histogram16 }, gains: readonly [number, number, number]): Histogram16 {
  const out = new Uint32Array(65536);
  const chans = [planes.r, planes.g, planes.b];
  for (let c = 0; c < 3; c++) {
    const h = chans[c];
    const g = gains[c];
    for (let v = h.min; v <= h.max; v++) {
      const k = h.counts[v];
      if (k) out[balanced(v, g)] += k;
    }
  }
  return hist(out, planes.r.n + planes.g.n + planes.b.n);
}

/** What the viewer needs to draw a preview: the balance gains and the samples the auto levels use. */
export interface PreviewStats {
  preview: Preview;
  code: number;
  gains: [number, number, number];
  /** Histogram of the displayed values (null: the raw histogram is the view's). */
  view: Histogram16 | null;
}

/**
 * Gains and view histogram of a preview. `planes` is computed once per frame
 * (cfaPlanes / rgbPlanes) and reused when the observer changes the preview.
 */
export function previewStats(
  chosen: Preview,
  kind: FrameKind,
  planes: { r: Histogram16; g: Histogram16; b: Histogram16 } | null,
): PreviewStats {
  const preview = effectivePreview(chosen, kind);
  const code = previewCode(preview, kind);
  if (!planes || code === 0) return { preview, code, gains: [1, 1, 1], view: null };
  if (code === 1) {
    const gains = neutralGains([median(planes.r), median(planes.g), median(planes.b)]);
    return { preview, code, gains, view: colourHistogram(planes, gains) };
  }
  const plane = code === 2 ? planes.r : code === 3 ? planes.g : planes.b;
  return { preview, code, gains: [1, 1, 1], view: plane };
}

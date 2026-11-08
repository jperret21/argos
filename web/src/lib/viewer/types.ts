import type { DecodedFrame } from '../api/frames';
import type { Preview } from './palettes/cfa';
import type { Histogram16, StretchParams } from './stretch';

/** What is under the cursor, for the status bar. */
export interface PointerInfo {
  /** Column / row of the pixel under the cursor (0-based, row 0 = top). */
  x: number;
  y: number;
  /** Raw ADU: one value for mono frames, [r, g, b] for colour frames. */
  value: number | [number, number, number];
}

/**
 * Passed to the `overlay` snippet. The snippet renders inside an SVG <g>
 * already transformed to image coordinates in the numpy/photutils convention:
 * (x, y) = (column, row) with the CENTRE of pixel (i, j) at (i, j), so a
 * centroid from the scientific core can be drawn as-is. Draw strokes with
 * vector-effect="non-scaling-stroke", and divide by `scale` for sizes that
 * must stay constant on screen (e.g. r={8 / scale} is 8 CSS px).
 */
export interface OverlayContext {
  /** CSS px per image px. */
  scale: number;
  width: number;
  height: number;
}

export interface RenderTiming {
  seq: number;
  /** decodeFrame() time, when the frame came from a FrameStream. */
  decodeMs: number | null;
  /** texSubImage2D (plus the GPU work when syncTiming is on). */
  uploadMs: number;
  /** histogram + auto-stretch statistics on the CPU. */
  statsMs: number;
  /** draw call (plus the GPU work when syncTiming is on). */
  drawMs: number;
}

/** Emitted once per frame actually displayed (frames can be coalesced). */
export interface DisplayInfo {
  frame: DecodedFrame;
  /** Exact 65536-bin histogram of the displayed samples (reuse it for plots). */
  histogram: Histogram16;
  /**
   * auto_stf() of what is displayed, whether or not auto-stretch is active: the raw
   * samples, or the CFA preview's view (palettes/cfa.ts), as Qt's auto levels did.
   */
  auto: StretchParams;
  /** The CFA preview drawn (palettes/cfa.ts; "raw" for a mono frame). */
  preview?: Preview;
  /** The same frame sent again with new levels (the preview changed): not a new frame. */
  redisplay?: boolean;
  timing: RenderTiming;
}

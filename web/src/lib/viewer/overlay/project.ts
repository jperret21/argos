/**
 * Frame pixels <-> screen pixels for the field overlay (web/spec/04-viewer-and-image-tools.md
 * 2.4 "Overlay drawing", README 4.1 "positions in frame px, numpy convention, un-rotated").
 *
 * The overlay is drawn in SCREEN space, not inside the viewer's image transform: labels and
 * the check-star triangle stay upright whatever the display rotation, marker sizes stay
 * constant in CSS px at any zoom, and label de-overlap is computed in screen px after each
 * zoom (04 P27). Pure functions, tested without a browser.
 *
 * Two transforms are composed:
 * 1. the tracking transform (A48 `field_transform`): the reference solve's frame px to the
 *    frame on screen, a rotation about a pivot followed by a translation, exactly
 *    `RigidTransform.apply` of argos/core/photometry/tracking.py:129-158 (the server sends
 *    it in frame px; markers of A47 are positions on the reference solve);
 * 2. the display: rotation by quarter turns (viewer/rotation.ts frameToDisplay, the Qt
 *    `_rot_pt`), then the viewer's pan and zoom given by the image rectangle it reports
 *    (FitsViewer `onrect`). A frame pixel centre (i, j) sits at the centre of its
 *    displayed pixel: screen = rect.left + (u + 0.5) * scale.
 */

import { displaySize, frameToDisplay, type Turns } from '../rotation';

/** A rigid tracking correction (A48), in frame px; identity when null. */
export interface RigidTransform {
  /** Translation applied after the rotation, frame px. */
  dx: number;
  dy: number;
  /** Rotation about (cx, cy), degrees, in the frame's pixel axes (y down). */
  rot_deg: number;
  /** Pivot of the rotation, frame px (the frame centre when absent). */
  cx?: number | null;
  cy?: number | null;
}

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface Size {
  width: number;
  height: number;
}

/** Everything needed to place a frame pixel on the stage. */
export interface ScreenMap {
  /** The displayed image in stage CSS px (FitsViewer onrect). */
  rect: Rect;
  /** The frame as delivered (un-rotated). */
  frame: Size;
  /** Display quarter turns (viewer/rotation.ts effectiveTurns). */
  turns: Turns;
}

export interface Point {
  x: number;
  y: number;
}

function pivot(t: RigidTransform, frame: Size | null): Point {
  const cx = t.cx ?? (frame ? frame.width / 2 : 0);
  const cy = t.cy ?? (frame ? frame.height / 2 : 0);
  return { x: cx, y: cy };
}

/** Reference-solve frame px -> current frame px (tracking.py RigidTransform.apply). */
export function applyTransform(t: RigidTransform | null, x: number, y: number, frame: Size | null = null): Point {
  if (!t) return { x, y };
  const th = (t.rot_deg * Math.PI) / 180;
  const c = Math.cos(th);
  const s = Math.sin(th);
  const p = pivot(t, frame);
  const dx = x - p.x;
  const dy = y - p.y;
  return { x: p.x + c * dx - s * dy + t.dx, y: p.y + s * dx + c * dy + t.dy };
}

/** Current frame px -> reference-solve frame px (tracking.py RigidTransform.invert). */
export function invertTransform(t: RigidTransform | null, x: number, y: number, frame: Size | null = null): Point {
  if (!t) return { x, y };
  const th = (t.rot_deg * Math.PI) / 180;
  const c = Math.cos(th);
  const s = Math.sin(th);
  const p = pivot(t, frame);
  const dx = x - p.x - t.dx;
  const dy = y - p.y - t.dy;
  return { x: p.x + c * dx + s * dy, y: p.y - s * dx + c * dy };
}

/** CSS px per frame px (0 when the image has no size yet). */
export function screenScale(map: ScreenMap): number {
  const d = displaySize(map.frame.width, map.frame.height, map.turns);
  return d.width > 0 ? map.rect.width / d.width : 0;
}

/** Frame px (centre convention) -> stage CSS px. */
export function frameToScreen(map: ScreenMap, x: number, y: number): Point {
  const s = screenScale(map);
  const d = frameToDisplay(x, y, map.frame.width, map.frame.height, map.turns);
  return { x: map.rect.left + (d.u + 0.5) * s, y: map.rect.top + (d.v + 0.5) * s };
}

/**
 * Stage CSS px -> frame px (continuous inverse of frameToScreen, so a click between pixel
 * centres keeps its sub-pixel position).
 */
export function screenToFrame(map: ScreenMap, sx: number, sy: number): Point {
  const s = screenScale(map);
  if (s <= 0) return { x: NaN, y: NaN };
  const u = (sx - map.rect.left) / s - 0.5;
  const v = (sy - map.rect.top) / s - 0.5;
  const { width: w, height: h } = map.frame;
  switch (map.turns) {
    case 1:
      return { x: v, y: h - 1 - u };
    case 2:
      return { x: w - 1 - u, y: h - 1 - v };
    case 3:
      return { x: w - 1 - v, y: u };
    default:
      return { x: u, y: v };
  }
}

/** A frame-px vector (dx, dy) as it points on screen (display turns only; no pan / zoom). */
export function turnVector(dx: number, dy: number, turns: Turns): Point {
  switch (turns) {
    case 1:
      return { x: -dy, y: dx };
    case 2:
      return { x: -dx, y: -dy };
    case 3:
      return { x: dy, y: -dx };
    default:
      return { x: dx, y: dy };
  }
}

/** Inverse of turnVector: a screen vector back to frame px axes. */
export function unturnVector(sx: number, sy: number, turns: Turns): Point {
  switch (turns) {
    case 1:
      return { x: sy, y: -sx };
    case 2:
      return { x: -sx, y: -sy };
    case 3:
      return { x: -sy, y: sx };
    default:
      return { x: sx, y: sy };
  }
}

/**
 * The hit tolerance sent to the server (A49 `tol_px`, frame px) so a click selects within
 * `screenPx` CSS px at any zoom (04 2.4, fixes P9). Never below half a pixel.
 */
export function tolFramePx(map: ScreenMap, screenPx = 10): number {
  const s = screenScale(map);
  return s > 0 ? Math.max(0.5, screenPx / s) : screenPx;
}

/** Reference frame px -> stage px through the tracking transform and the display. */
export function project(map: ScreenMap, t: RigidTransform | null, x: number, y: number): Point {
  const p = applyTransform(t, x, y, map.frame);
  return frameToScreen(map, p.x, p.y);
}

/** Inside the stage, with a margin in CSS px (markers partly visible still draw). */
export function onStage(p: Point, stage: Size, margin = 24): boolean {
  return p.x >= -margin && p.y >= -margin && p.x <= stage.width + margin && p.y <= stage.height + margin;
}

/**
 * A selection ring on the stage (A49 `ring`): a catalogue hit is a reference-solve position
 * (`space: "reference"`, moved by the tracking), a measured star a current-frame one
 * (`space: "frame"`, the default). The radius is the aperture on screen, at least `minR`.
 */
export function placeRing(
  map: ScreenMap,
  t: RigidTransform | null,
  ring: { x: number; y: number; r_px: number; space?: string | null },
  minR = 10,
): Point & { r: number } {
  const p = project(map, ring.space === 'reference' ? t : null, ring.x, ring.y);
  return { x: p.x, y: p.y, r: Math.max(minR, ring.r_px * screenScale(map)) };
}

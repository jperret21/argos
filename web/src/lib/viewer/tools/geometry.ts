/**
 * Where the image sits on screen, for the screen-space tools over the viewer
 * (region box, hover marks, loupe, context menu): pure functions over the
 * viewer's geometry, which FitsViewer reports through `ongeometry`.
 *
 * Conventions (viewer/types.ts, viewer/view.ts, viewer/rotation.ts):
 * - frame px: un-rotated, numpy / photutils convention, the CENTRE of pixel
 *   (i, j) at (i, j); what the server and the overlays use;
 * - display px: the rotated picture, pixel (u, v) covering [u, u + 1);
 * - screen: CSS px inside the viewer element.
 * Rotation is a multiple of 90°, so a frame-aligned box stays a box on screen.
 */

import { displaySize, type Turns } from '../rotation';
import type { Size, ViewState } from '../view';

export interface ViewerGeometry {
  view: ViewState;
  /** Frame size as delivered (un-rotated). */
  frame: Size;
  turns: Turns;
  /** The viewer element, CSS px. */
  viewport: Size;
  /** Device px per CSS px of the canvas. */
  dpr: number;
}

export interface Point {
  x: number;
  y: number;
}

/** Frame point (numpy convention, continuous) -> display point (numpy convention). */
export function frameToDisplayPoint(x: number, y: number, frame: Size, k: Turns): Point {
  switch (k) {
    case 1:
      return { x: frame.height - 1 - y, y: x };
    case 2:
      return { x: frame.width - 1 - x, y: frame.height - 1 - y };
    case 3:
      return { x: y, y: frame.width - 1 - x };
    default:
      return { x, y };
  }
}

/** Display point (numpy convention) -> frame point (numpy convention). */
export function displayToFramePoint(u: number, v: number, frame: Size, k: Turns): Point {
  switch (k) {
    case 1:
      return { x: v, y: frame.height - 1 - u };
    case 2:
      return { x: frame.width - 1 - u, y: frame.height - 1 - v };
    case 3:
      return { x: frame.width - 1 - v, y: u };
    default:
      return { x: u, y: v };
  }
}

/** Frame point (numpy convention) -> screen CSS px. */
export function frameToScreen(g: ViewerGeometry, x: number, y: number): Point {
  const d = frameToDisplayPoint(x, y, g.frame, g.turns);
  return { x: g.view.tx + (d.x + 0.5) * g.view.scale, y: g.view.ty + (d.y + 0.5) * g.view.scale };
}

/** Screen CSS px -> frame point (numpy convention, continuous). */
export function screenToFrame(g: ViewerGeometry, sx: number, sy: number): Point {
  const u = (sx - g.view.tx) / g.view.scale - 0.5;
  const v = (sy - g.view.ty) / g.view.scale - 0.5;
  return displayToFramePoint(u, v, g.frame, g.turns);
}

/** The frame pixel under a screen point, or null outside the frame. */
export function pixelAt(g: ViewerGeometry, sx: number, sy: number): Point | null {
  const p = screenToFrame(g, sx, sy);
  const x = Math.round(p.x) + 0; // + 0: never -0
  const y = Math.round(p.y) + 0;
  if (x < 0 || y < 0 || x >= g.frame.width || y >= g.frame.height) return null;
  return { x, y };
}

/** Rotate a frame-px direction into screen space (y down), as the display rotation does. */
export function frameVectorToScreen(dx: number, dy: number, k: Turns): Point {
  switch (k) {
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

/** Pixel rectangle in frame px: columns [x0, x1), rows [y0, y1), integers. */
export interface FrameRect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface ScreenRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** The screen box covering the pixels of a frame rectangle (their outer edges). */
export function frameRectToScreen(g: ViewerGeometry, r: FrameRect): ScreenRect {
  const a = frameToScreen(g, r.x0 - 0.5, r.y0 - 0.5);
  const b = frameToScreen(g, r.x1 - 0.5, r.y1 - 0.5);
  const left = Math.min(a.x, b.x);
  const top = Math.min(a.y, b.y);
  return { left, top, width: Math.abs(b.x - a.x), height: Math.abs(b.y - a.y) };
}

/** Pixels covered by a screen box (rounded to whole pixels, clamped to the frame; may be empty). */
export function screenRectToFrame(g: ViewerGeometry, r: ScreenRect): FrameRect {
  const a = screenToFrame(g, r.left, r.top);
  const b = screenToFrame(g, r.left + r.width, r.top + r.height);
  return clampRect(
    {
      x0: Math.round(Math.min(a.x, b.x) + 0.5),
      y0: Math.round(Math.min(a.y, b.y) + 0.5),
      x1: Math.round(Math.max(a.x, b.x) + 0.5),
      y1: Math.round(Math.max(a.y, b.y) + 0.5),
    },
    g.frame,
  );
}

/** Keep a rectangle inside the frame (x1 >= x0, y1 >= y0). */
export function clampRect(r: FrameRect, frame: Size): FrameRect {
  const x0 = Math.max(0, Math.min(frame.width, Math.round(r.x0)));
  const y0 = Math.max(0, Math.min(frame.height, Math.round(r.y0)));
  const x1 = Math.max(x0, Math.min(frame.width, Math.round(r.x1)));
  const y1 = Math.max(y0, Math.min(frame.height, Math.round(r.y1)));
  return { x0, y0, x1, y1 };
}

/** Move a rectangle by whole pixels, keeping its size and keeping it inside the frame. */
export function moveRect(r: FrameRect, dx: number, dy: number, frame: Size): FrameRect {
  const w = r.x1 - r.x0;
  const h = r.y1 - r.y0;
  const x0 = Math.max(0, Math.min(frame.width - w, Math.round(r.x0 + dx)));
  const y0 = Math.max(0, Math.min(frame.height - h, Math.round(r.y0 + dy)));
  return { x0, y0, x1: x0 + w, y1: y0 + h };
}

/** A centred square of `side` pixels (the region's first place, 04 2.2: 80 x 80). */
export function centredRect(frame: Size, side = 80, at?: Point): FrameRect {
  const s = Math.max(1, Math.min(side, frame.width, frame.height));
  const cx = at ? at.x : (frame.width - 1) / 2;
  const cy = at ? at.y : (frame.height - 1) / 2;
  return moveRect({ x0: 0, y0: 0, x1: s, y1: s }, Math.round(cx - (s - 1) / 2), Math.round(cy - (s - 1) / 2), frame);
}

export function isFrameRect(v: unknown): v is FrameRect {
  if (typeof v !== 'object' || v === null) return false;
  const r = v as Record<string, unknown>;
  return ['x0', 'y0', 'x1', 'y1'].every((k) => typeof r[k] === 'number' && Number.isFinite(r[k] as number)) && (r.x1 as number) > (r.x0 as number) && (r.y1 as number) > (r.y0 as number);
}

/** The displayed image's size (for callers that only hold the geometry). */
export function displayedSize(g: ViewerGeometry): Size {
  return displaySize(g.frame.width, g.frame.height, g.turns);
}

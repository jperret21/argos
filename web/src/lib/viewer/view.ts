/**
 * Pan/zoom transform of the image viewer (pure, unit-tested).
 *
 * Units: everything here is in CSS pixels of the viewer element. An image
 * pixel (i, j) covers [tx + i*scale, tx + (i+1)*scale) horizontally, likewise
 * vertically, with row 0 at the top. The renderer converts to device pixels
 * with the canvas' devicePixelRatio.
 *
 * "1:1" means one image pixel per *device* pixel (scale = 1/dpr): every sensor
 * pixel is shown exactly once, with no resampling, on HiDPI screens too.
 */

export interface ViewState {
  /** CSS px per image px. */
  scale: number;
  /** CSS position of the image's top-left corner inside the viewer. */
  tx: number;
  ty: number;
}

export interface Size {
  width: number;
  height: number;
}

/** Zoom limits, in device px per image px. */
export const MAX_DEVICE_ZOOM = 64;
/** Never zoom out further than this fraction of the fit scale. */
export const MIN_FIT_FRACTION = 0.125;
/** While panning, keep at least this many CSS px of the image on screen. */
export const PAN_MARGIN = 48;

export function fitScale(image: Size, viewport: Size): number {
  if (image.width <= 0 || image.height <= 0 || viewport.width <= 0 || viewport.height <= 0) {
    return 1;
  }
  return Math.min(viewport.width / image.width, viewport.height / image.height);
}

/** Whole image visible and centred. */
export function fitView(image: Size, viewport: Size): ViewState {
  const scale = fitScale(image, viewport);
  return centredAt(viewport, scale, image.width / 2, image.height / 2);
}

/**
 * How "fit" frames the image: "fit" shows the whole frame (bands on the short
 * sides when the aspects differ), "fill" fills the viewer and crops the
 * frame's long sides equally (BRAND 11.1: no dead bands).
 */
export type FitMode = 'fit' | 'fill';

export const isFitMode = (v: unknown): v is FitMode => v === 'fit' || v === 'fill';

/** Smallest scale at which the image covers the whole viewport. */
export function fillScale(image: Size, viewport: Size): number {
  if (image.width <= 0 || image.height <= 0 || viewport.width <= 0 || viewport.height <= 0) {
    return 1;
  }
  return Math.max(viewport.width / image.width, viewport.height / image.height);
}

/** The viewport covered, image centred (its overflow cropped equally on both sides). */
export function fillView(image: Size, viewport: Size): ViewState {
  const scale = fillScale(image, viewport);
  return centredAt(viewport, scale, image.width / 2, image.height / 2);
}

export function framedView(mode: FitMode, image: Size, viewport: Size): ViewState {
  return mode === 'fill' ? fillView(image, viewport) : fitView(image, viewport);
}

/** Fraction of the image hidden by a view, per axis (0 = all of it visible). */
export function croppedFraction(view: ViewState, image: Size, viewport: Size): { x: number; y: number } {
  const w = image.width * view.scale;
  const h = image.height * view.scale;
  const visW = Math.max(0, Math.min(view.tx + w, viewport.width) - Math.max(view.tx, 0));
  const visH = Math.max(0, Math.min(view.ty + h, viewport.height) - Math.max(view.ty, 0));
  return { x: w > 0 ? 1 - visW / w : 0, y: h > 0 ? 1 - visH / h : 0 };
}

/** View at `scale` with image point (cx, cy) at the viewport centre. */
export function centredAt(viewport: Size, scale: number, cx: number, cy: number): ViewState {
  return { scale, tx: viewport.width / 2 - cx * scale, ty: viewport.height / 2 - cy * scale };
}

/** Device-pixel 1:1, keeping the image point at the viewport centre fixed. */
export function oneToOneView(image: Size, viewport: Size, view: ViewState, dpr: number): ViewState {
  const centre = screenToImage(view, viewport.width / 2, viewport.height / 2);
  return clampPan(centredAt(viewport, 1 / dpr, centre.x, centre.y), image, viewport);
}

export function scaleLimits(image: Size, viewport: Size, dpr: number): { min: number; max: number } {
  const fit = fitScale(image, viewport);
  const max = MAX_DEVICE_ZOOM / dpr;
  // Allow at least 1:1 even for an image smaller than the viewport.
  const min = Math.min(fit * MIN_FIT_FRACTION, 1 / dpr);
  return { min, max: Math.max(max, min) };
}

/** CSS point -> continuous image coordinates (pixel (i,j) spans [i,i+1)). */
export function screenToImage(view: ViewState, x: number, y: number): { x: number; y: number } {
  return { x: (x - view.tx) / view.scale, y: (y - view.ty) / view.scale };
}

export function imageToScreen(view: ViewState, x: number, y: number): { x: number; y: number } {
  return { x: view.tx + x * view.scale, y: view.ty + y * view.scale };
}

/**
 * Zoom by `factor` keeping the image point under (px, py) fixed on screen
 * (wheel zoom around the cursor). The factor is clamped to the zoom limits.
 */
export function zoomAt(
  view: ViewState,
  factor: number,
  px: number,
  py: number,
  limits: { min: number; max: number },
): ViewState {
  const scale = Math.min(Math.max(view.scale * factor, limits.min), limits.max);
  const anchor = screenToImage(view, px, py);
  return { scale, tx: px - anchor.x * scale, ty: py - anchor.y * scale };
}

/** Keep at least PAN_MARGIN px of the image inside the viewport. */
export function clampPan(view: ViewState, image: Size, viewport: Size): ViewState {
  const w = image.width * view.scale;
  const h = image.height * view.scale;
  const mx = Math.min(PAN_MARGIN, w);
  const my = Math.min(PAN_MARGIN, h);
  const tx = Math.min(Math.max(view.tx, mx - w), viewport.width - mx);
  const ty = Math.min(Math.max(view.ty, my - h), viewport.height - my);
  return { scale: view.scale, tx, ty };
}

/**
 * Wheel delta -> multiplicative zoom factor. Pixel-mode deltas (trackpads,
 * precise wheels) are small and continuous; line/page modes are notched mice.
 * A trackpad pinch arrives as a ctrl+wheel and gets a stronger gain.
 */
export function wheelZoomFactor(deltaY: number, deltaMode: number, ctrlKey: boolean): number {
  const LINE = 1;
  const PAGE = 2;
  let px = deltaY;
  if (deltaMode === LINE) px *= 16;
  else if (deltaMode === PAGE) px *= 400;
  const gain = ctrlKey ? 0.01 : 0.0015;
  // Bound one event to x2 / /2 so a fast flick cannot jump across the range.
  return Math.exp(Math.min(Math.max(-px * gain, -Math.LN2), Math.LN2));
}

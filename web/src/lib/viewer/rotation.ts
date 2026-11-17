/**
 * Display rotation (BRAND.md 11.1), mirroring the Qt viewer
 * (argos/ui/widgets/fits_viewer.py: ROTATION_MODES, _effective_k, _rot_pt,
 * _unrot_pt). "auto" turns portrait frames 90° clockwise so a Seestar frame
 * (1080 x 1920) reads landscape; the fixed modes are clockwise angles.
 *
 * Rotation is display-only. The shown image is numpy.rot90(frame, -k) (row 0
 * at the top); cursor readouts, overlays and anything sent to the server stay
 * in un-rotated frame pixels. The fragment shader applies displayToFrame() to
 * every fetched texel (same integer formulas).
 */

export const ROTATION_MODES = ['auto', '0', '90', '180', '270'] as const;
export type RotationMode = (typeof ROTATION_MODES)[number];

/** Clockwise quarter turns. */
export type Turns = 0 | 1 | 2 | 3;

export function isRotationMode(v: unknown): v is RotationMode {
  return typeof v === 'string' && (ROTATION_MODES as readonly string[]).includes(v);
}

/** fits_viewer._effective_k: auto = 1 for a portrait frame, else 0. */
export function effectiveTurns(mode: RotationMode, width: number, height: number): Turns {
  if (mode === 'auto') return height > width ? 1 : 0;
  return ((Number(mode) / 90) % 4) as Turns;
}

/** Size of the image as displayed. */
export function displaySize(width: number, height: number, k: Turns): { width: number; height: number } {
  return k % 2 === 1 ? { width: height, height: width } : { width, height };
}

/** Displayed pixel (u, v) -> frame pixel (x, y): fits_viewer._unrot_pt. */
export function displayToFrame(
  u: number,
  v: number,
  width: number,
  height: number,
  k: Turns,
): { x: number; y: number } {
  switch (k) {
    case 1:
      return { x: v, y: height - 1 - u };
    case 2:
      return { x: width - 1 - u, y: height - 1 - v };
    case 3:
      return { x: width - 1 - v, y: u };
    default:
      return { x: u, y: v };
  }
}

/** Frame pixel (x, y) -> displayed pixel (u, v): fits_viewer._rot_pt. */
export function frameToDisplay(
  x: number,
  y: number,
  width: number,
  height: number,
  k: Turns,
): { u: number; v: number } {
  switch (k) {
    case 1:
      return { u: height - 1 - y, v: x };
    case 2:
      return { u: width - 1 - x, v: height - 1 - y };
    case 3:
      return { u: y, v: width - 1 - x };
    default:
      return { u: x, v: y };
  }
}

/**
 * SVG matrix(a b c d e f) taking frame coordinates (pixel centres at integers,
 * numpy/photutils convention) to display coordinates (same convention), so
 * overlays keep drawing in frame pixels whatever the rotation.
 */
export function overlayMatrix(width: number, height: number, k: Turns): string {
  switch (k) {
    case 1:
      return `matrix(0 1 -1 0 ${height - 1} 0)`;
    case 2:
      return `matrix(-1 0 0 -1 ${width - 1} ${height - 1})`;
    case 3:
      return `matrix(0 -1 1 0 0 ${width - 1})`;
    default:
      return 'matrix(1 0 0 1 0 0)';
  }
}

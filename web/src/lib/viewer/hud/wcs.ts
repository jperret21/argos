/**
 * The field's WCS on the client: gnomonic (TAN) pixel <-> sky, the N / E
 * compass and the arcminute scale bar of the image HUD (web/lab/PROPOSAL.md
 * 3.1 and 6, W4: "HUD compass and arcminute scale bar"), and the cursor
 * RA / Dec (04 2.5: "cursor RA/Dec (TAN)", no round trip).
 *
 * The maths is the FITS TAN projection that astropy applies in
 * argos/core/imaging/platesolve.py FrameWCS (:329-378): pixel -> (p, q) =
 * pixel + 1 - CRPIX (FITS is 1-based), (xi, eta) = CD (p, q) in degrees, then
 * the gnomonic deprojection about CRVAL. No distortion terms (ASTAP's solution
 * has none). Coordinates here are FRAME px, numpy convention (the wire
 * convention, README 4.1); a WCS on another grid (the green plane, half the
 * frame) goes through `wcsToFrame` first.
 *
 * Display rotation: the compass is drawn in SCREEN space, so its arms turn
 * with the display (viewer/rotation.ts) and its letters stay upright. East is
 * wherever the solution puts it: on a north-up sky image it is on the left.
 */

import { frameVectorToScreen } from '../tools/geometry';
import type { Turns } from '../rotation';

/** A TAN WCS: reference sky point (deg), reference pixel (FITS 1-based), CD matrix (deg / px). */
export interface TanWcs {
  crval: readonly [number, number];
  crpix: readonly [number, number];
  /** [CD1_1, CD1_2, CD2_1, CD2_2]. */
  cd: readonly [number, number, number, number];
}

const RAD = Math.PI / 180;

/** A WCS fitted on a sub-sampled grid (frame = factor x grid + offset) -> the same WCS in frame px. */
export function wcsToFrame(w: TanWcs, factor: number, offset: readonly [number, number] = [0, 0]): TanWcs {
  // grid g (0-based) = (frame - offset) / factor; FITS p = g + 1 - crpix.
  const [c11, c12, c21, c22] = w.cd;
  return {
    crval: w.crval,
    crpix: [(w.crpix[0] - 1) * factor + offset[0] + 1, (w.crpix[1] - 1) * factor + offset[1] + 1],
    cd: [c11 / factor, c12 / factor, c21 / factor, c22 / factor],
  };
}

/**
 * The wire's FrameWcs (protocol.md "Field (A43-A45)": crval [ra, dec] deg,
 * crpix FITS 1-based frame px, cd [[cd1_1, cd1_2], [cd2_1, cd2_2]]) -> TanWcs;
 * null for anything else.
 */
export function fromFrameWcs(v: unknown): TanWcs | null {
  if (typeof v !== 'object' || v === null) return null;
  const r = v as { crval?: unknown; crpix?: unknown; cd?: unknown };
  const cd = Array.isArray(r.cd) && r.cd.length === 2 && r.cd.every((row) => Array.isArray(row)) ? (r.cd as unknown[][]).flat() : r.cd;
  const w = { crval: r.crval, crpix: r.crpix, cd } as unknown;
  return isTanWcs(w) ? { crval: [...w.crval] as [number, number], crpix: [...w.crpix] as [number, number], cd: [...w.cd] as [number, number, number, number] } : null;
}

/** The per-frame tracking transform of the field (protocol.md FieldTransform, A48). */
export interface FieldMotion {
  rot_deg: number;
  dx: number;
  dy: number;
  cx: number;
  cy: number;
}

/**
 * The WCS of a later frame of the tracked field: the reference point (x, y)
 * is now at cx + R(θ)(x − cx, y − cy) + (dx, dy) (protocol.md "Tracking"),
 * so CRPIX moves the same way and the CD matrix turns by −θ. Exact for a rigid
 * transform; the identity leaves the WCS unchanged.
 */
export function trackedWcs(w: TanWcs, t: FieldMotion | null | undefined): TanWcs {
  if (!t || (t.rot_deg === 0 && t.dx === 0 && t.dy === 0)) return w;
  const th = t.rot_deg * RAD;
  const c = Math.cos(th);
  const s = Math.sin(th);
  const x = w.crpix[0] - 1 - t.cx;
  const y = w.crpix[1] - 1 - t.cy;
  const crpix: [number, number] = [t.cx + c * x - s * y + t.dx + 1, t.cy + s * x + c * y + t.dy + 1];
  // CD' = CD · R(−θ): (p, q) of the reference grid = R(−θ) (p', q').
  const [a, b, d, e] = w.cd;
  const cd: [number, number, number, number] = [a * c - b * s, a * s + b * c, d * c - e * s, d * s + e * c];
  return { crval: w.crval, crpix, cd };
}

export function isTanWcs(v: unknown): v is TanWcs {
  if (typeof v !== 'object' || v === null) return false;
  const w = v as Record<string, unknown>;
  const nums = (a: unknown, n: number) => Array.isArray(a) && a.length === n && a.every((x) => typeof x === 'number' && Number.isFinite(x));
  return nums(w.crval, 2) && nums(w.crpix, 2) && nums(w.cd, 4) && Math.abs(det(w.cd as TanWcs['cd'])) > 0;
}

const det = (cd: TanWcs['cd']) => cd[0] * cd[3] - cd[1] * cd[2];

/** Frame px (numpy convention) -> (RA hours in [0, 24), Dec degrees). */
export function pixelToSky(w: TanWcs, x: number, y: number): { raHours: number; decDeg: number } {
  const p = x + 1 - w.crpix[0];
  const q = y + 1 - w.crpix[1];
  const xi = (w.cd[0] * p + w.cd[1] * q) * RAD;
  const eta = (w.cd[2] * p + w.cd[3] * q) * RAD;
  const a0 = w.crval[0] * RAD;
  const d0 = w.crval[1] * RAD;
  const den = Math.cos(d0) - eta * Math.sin(d0);
  const ra = a0 + Math.atan2(xi, den);
  const dec = Math.atan2(Math.sin(d0) + eta * Math.cos(d0), Math.hypot(xi, den));
  const raDeg = (((ra / RAD) % 360) + 360) % 360;
  return { raHours: raDeg / 15, decDeg: dec / RAD };
}

/** (RA hours, Dec degrees) -> frame px; null on the far hemisphere (no gnomonic image). */
export function skyToPixel(w: TanWcs, raHours: number, decDeg: number): { x: number; y: number } | null {
  const a = raHours * 15 * RAD;
  const d = decDeg * RAD;
  const a0 = w.crval[0] * RAD;
  const d0 = w.crval[1] * RAD;
  const cosc = Math.sin(d0) * Math.sin(d) + Math.cos(d0) * Math.cos(d) * Math.cos(a - a0);
  if (cosc <= 1e-9) return null;
  const xi = (Math.cos(d) * Math.sin(a - a0)) / cosc / RAD;
  const eta = (Math.cos(d0) * Math.sin(d) - Math.sin(d0) * Math.cos(d) * Math.cos(a - a0)) / cosc / RAD;
  const [c11, c12, c21, c22] = w.cd;
  const D = det(w.cd);
  const p = (c22 * xi - c12 * eta) / D;
  const q = (-c21 * xi + c11 * eta) / D;
  return { x: p + w.crpix[0] - 1, y: q + w.crpix[1] - 1 };
}

/** Plate scale at the reference pixel, arcsec per frame px (platesolve.parse_astap_ini: sqrt|det CD|). */
export function plateScaleArcsec(w: TanWcs): number {
  return Math.sqrt(Math.abs(det(w.cd))) * 3600;
}

/** Unit vectors, in frame px, toward north and east at a frame point (null when undefined, e.g. at a pole). */
export function skyAxesAt(w: TanWcs, x: number, y: number): { north: [number, number]; east: [number, number] } | null {
  const c = pixelToSky(w, x, y);
  const eps = 1 / 3600; // 1 arcsec
  const unit = (to: { x: number; y: number } | null, sign = 1): [number, number] | null => {
    if (!to) return null;
    const dx = (to.x - x) * sign;
    const dy = (to.y - y) * sign;
    const n = Math.hypot(dx, dy);
    return n > 0 ? [dx / n, dy / n] : null;
  };
  // Near the north pole step south and flip, so the step never crosses it.
  const north = c.decDeg < 89.9 ? unit(skyToPixel(w, c.raHours, c.decDeg + eps)) : unit(skyToPixel(w, c.raHours, c.decDeg - eps), -1);
  const cosd = Math.cos(c.decDeg * RAD);
  const east = cosd > 1e-6 ? unit(skyToPixel(w, c.raHours + eps / 15 / cosd, c.decDeg)) : null;
  return north && east ? { north, east } : null;
}

export interface Compass {
  /** Screen unit vectors (y down). */
  north: { x: number; y: number };
  east: { x: number; y: number };
  /** East is 90° counter-clockwise of north on screen (the sky as seen from inside: a mirror image otherwise). */
  mirrored: boolean;
}

/** The compass at a frame point, in screen space for this display rotation. */
export function compassAt(w: TanWcs, x: number, y: number, turns: Turns): Compass | null {
  const a = skyAxesAt(w, x, y);
  if (!a) return null;
  const n = frameVectorToScreen(a.north[0], a.north[1], turns);
  const e = frameVectorToScreen(a.east[0], a.east[1], turns);
  // Screen y is down: for the usual sky view (E left of N, counter-clockwise) the cross product is negative.
  const cross = n.x * e.y - n.y * e.x;
  return { north: n, east: e, mirrored: cross > 0 };
}

/** Side of the HUD compass, CSS px. */
export const COMPASS_SIZE = 56;

export interface ScaleBar {
  /** Bar length, CSS px. */
  px: number;
  /** "5′", "30″", "1°". */
  label: string;
  arcmin: number;
}

/** Lengths offered, arcminutes. */
export const SCALE_STEPS = [0.25, 0.5, 1, 2, 5, 10, 15, 20, 30, 60, 120] as const;

/**
 * The shortest round length at least `minPx` long on screen (the lab's 56 px),
 * from the plate scale (arcsec / frame px) and the zoom (CSS px / frame px).
 */
export function scaleBar(arcsecPerPx: number, cssPerPx: number, minPx = 56, maxPx = 180): ScaleBar | null {
  if (!(arcsecPerPx > 0) || !(cssPerPx > 0)) return null;
  const pxPerArcmin = (60 / arcsecPerPx) * cssPerPx;
  const m = SCALE_STEPS.find((c) => c * pxPerArcmin >= minPx);
  if (m === undefined || m * pxPerArcmin > maxPx * 2) return null;
  const label = m < 1 ? `${Math.round(m * 60)}″` : m >= 60 ? `${m / 60}°` : `${m}′`;
  return { px: m * pxPerArcmin, label, arcmin: m };
}

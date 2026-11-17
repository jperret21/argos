/**
 * The synthetic field of the prototype: a Seestar S50-like portrait frame
 * (1080 x 1920 px, 2.39″/px) centred near RR Lyr, a linear plate solution,
 * the photometric roles and the VSP-like comparison candidates.
 *
 * Everything here is invented and deterministic (seeded) except the target's
 * name and catalogue position. Comparison identifiers use the AUID shape with
 * a "LAB" block (000-LAB-665) so they can never be mistaken for real AAVSO
 * identifiers. Pixel coordinates are frame pixels, un-rotated, numpy
 * convention (pixel centres at integers), row 0 at the top.
 */

export const FRAME_W = 1080;
export const FRAME_H = 1920;
/** ″ per pixel (S50: 250 mm focal length, 2.9 µm pixels). */
export const PLATE_SCALE = 2.39;
/** Position angle of the frame's "up" (−y) from north, east of north, degrees. */
export const ROTATION_DEG = 91.2;
/** Magnitude giving 1 ADU of total flux in one exposure (synthetic zero point). */
export const ZERO_POINT = 23.19;

export const TARGET_NAME = 'RR Lyr';
/** RR Lyr, catalogue position (J2000). */
export const TARGET_RA_H = 19 + 25 / 60 + 27.9 / 3600;
export const TARGET_DEC = 42 + 47 / 60 + 4 / 3600;

export type Role = 'target' | 'comparison' | 'check';

export interface Star {
  id: number;
  x: number;
  y: number;
  /** V magnitude (the target's varies: this is its mean). */
  v: number;
  name?: string;
  role?: Role;
  /** Colour index from the (synthetic) VSP sequence. */
  bv?: number;
}

/** mulberry32: small, fast, seedable (same as the research lab). */
export function prng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// -- Plate solution -----------------------------------------------------------

const CX = (FRAME_W - 1) / 2;
const CY = (FRAME_H - 1) / 2;
const TH = (ROTATION_DEG * Math.PI) / 180;
/** Unit CD matrix (″ per px divided by the scale): [xi, eta] = s * M [dx, dy]. */
const M = [
  [-Math.cos(TH), Math.sin(TH)],
  [-Math.sin(TH), -Math.cos(TH)],
];

/** Target pixel, chosen 1.5′ from the frame centre (a recent centring). */
export const TARGET_PX = { x: 512, y: 935 };

function offsetsArcsec(x: number, y: number): [number, number] {
  const dx = x - CX;
  const dy = y - CY;
  return [PLATE_SCALE * (M[0][0] * dx + M[0][1] * dy), PLATE_SCALE * (M[1][0] * dx + M[1][1] * dy)];
}

/** Sky centre of the frame, derived so that RR Lyr lands on TARGET_PX. */
const [txi, teta] = offsetsArcsec(TARGET_PX.x, TARGET_PX.y);
export const CENTER_DEC = TARGET_DEC - teta / 3600;
export const CENTER_RA_H = TARGET_RA_H - txi / (15 * 3600 * Math.cos((CENTER_DEC * Math.PI) / 180));

/** Frame pixel -> (RA hours, Dec degrees). Linear (tangent-plane) approximation. */
export function pixelToSky(x: number, y: number): { ra: number; dec: number } {
  const [xi, eta] = offsetsArcsec(x, y);
  const dec = CENTER_DEC + eta / 3600;
  const ra = CENTER_RA_H + xi / (15 * 3600 * Math.cos((CENTER_DEC * Math.PI) / 180));
  return { ra: ((ra % 24) + 24) % 24, dec };
}

/** (RA hours, Dec degrees) -> frame pixel; inverse of pixelToSky (M orthonormal). */
export function skyToPixel(ra: number, dec: number): { x: number; y: number } {
  let dra = ra - CENTER_RA_H;
  if (dra > 12) dra -= 24;
  if (dra < -12) dra += 24;
  const xi = (dra * 15 * 3600 * Math.cos((CENTER_DEC * Math.PI) / 180)) / PLATE_SCALE;
  const eta = ((dec - CENTER_DEC) * 3600) / PLATE_SCALE;
  return { x: CX + M[0][0] * xi + M[1][0] * eta, y: CY + M[0][1] * xi + M[1][1] * eta };
}

/**
 * Unit vectors of north and east in frame pixels (y down), for the compass.
 * M is orthonormal, so its inverse is its transpose.
 */
export function skyAxes(): { north: [number, number]; east: [number, number] } {
  return {
    north: [M[1][0], M[1][1]],
    east: [M[0][0], M[0][1]],
  };
}

/** Separation in arcminutes between two frame pixels (flat field). */
export function sepArcmin(a: { x: number; y: number }, b: { x: number; y: number }): number {
  return (Math.hypot(a.x - b.x, a.y - b.y) * PLATE_SCALE) / 60;
}

// -- Stars ------------------------------------------------------------------------

export const TARGET_ID = 1;

/** Named stars: target, comparisons, check, and the extra VSP candidates. */
const NAMED: Star[] = [
  { id: TARGET_ID, x: TARGET_PX.x, y: TARGET_PX.y, v: 7.6, name: TARGET_NAME, role: 'target', bv: 0.52 },
  { id: 2, x: 690, y: 820, v: 7.95, name: '000-LAB-665', role: 'comparison', bv: 0.62 },
  { id: 3, x: 330, y: 1180, v: 8.41, name: '000-LAB-953', role: 'comparison', bv: 0.48 },
  { id: 4, x: 820, y: 1260, v: 8.86, name: '000-LAB-666', role: 'comparison', bv: 0.71 },
  { id: 5, x: 250, y: 640, v: 8.12, name: '000-LAB-418', role: 'comparison', bv: 0.39 },
  { id: 6, x: 600, y: 1420, v: 9.27, name: '000-LAB-207', role: 'comparison', bv: 0.58 },
  { id: 7, x: 905, y: 560, v: 9.05, name: '000-LAB-731', role: 'comparison', bv: 0.81 },
  { id: 8, x: 420, y: 470, v: 8.62, name: '000-LAB-523', role: 'check', bv: 0.55 },
  // Candidates not in the ensemble: clipped, red, blended, far.
  { id: 9, x: 160, y: 1500, v: 6.1, name: '000-LAB-512', bv: 1.31 },
  { id: 10, x: 760, y: 1010, v: 9.44, name: '000-LAB-874', bv: 0.47 },
  { id: 11, x: 980, y: 1720, v: 8.95, name: '000-LAB-390', bv: 1.02 },
  { id: 12, x: 120, y: 240, v: 9.71, name: '000-LAB-146', bv: 0.66 },
];

/** A close faint neighbour inside a candidate's aperture (blend risk). */
const NEIGHBOURS: Star[] = [
  { id: 101, x: 760 + 7, y: 1010 - 5, v: 11.9 },
  { id: 102, x: 820 - 6, y: 1260 + 6, v: 11.6 },
];

function fieldStars(): Star[] {
  const rand = prng(20260925);
  const out: Star[] = [];
  let id = 1000;
  // About 1 400 stars from V 9.0 to 14.8 with N(<V) growing as 10^(0.33 V)
  // (inverse of that cumulative law): most stars are faint, a few dozen bright.
  const a = 0.33;
  const lo = Math.pow(10, a * 9.0);
  const hi = Math.pow(10, a * 14.8);
  for (let i = 0; i < 1400; i++) {
    const v = Math.log10(lo + rand() * (hi - lo)) / a;
    out.push({ id: id++, x: 6 + rand() * (FRAME_W - 12), y: 6 + rand() * (FRAME_H - 12), v });
  }
  return out;
}

export const STARS: readonly Star[] = [...NAMED, ...NEIGHBOURS, ...fieldStars()];
export const NAMED_STARS: readonly Star[] = NAMED;

export function starById(id: number): Star | undefined {
  return STARS.find((s) => s.id === id);
}

/** Nearest catalogue star to a frame pixel within `radius` px (bright first on ties). */
export function pickStar(x: number, y: number, radius: number): Star | null {
  let best: Star | null = null;
  let bestScore = Infinity;
  for (const s of STARS) {
    const d = Math.hypot(s.x - x, s.y - y);
    if (d > radius) continue;
    // A bright star wins over a faint one at a similar distance.
    const score = d + (s.v - 6) * 1.5;
    if (score < bestScore) {
      best = s;
      bestScore = score;
    }
  }
  return best;
}

/** Catalogue stars inside `radiusPx` of `s`, brighter than its V + 3 (blend risk). */
export function neighboursInAperture(s: Star, radiusPx: number): Star[] {
  return STARS.filter((o) => o.id !== s.id && Math.hypot(o.x - s.x, o.y - s.y) <= radiusPx && o.v < s.v + 3);
}

/** Aperture radius used by the photometry, px (2.5 x FWHM, method 3.1). */
export const APERTURE_PX = 13; // 31″ at 2.39″/px

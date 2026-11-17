/**
 * Display palettes of the image viewer: the 256-entry lookup tables the
 * fragment shader reads after the stretch (viewer/shaders.ts, `u_lut`).
 * Promoted from src/lab/research/frame/gl.ts (web/lab/PROPOSAL.md 3.4 and 6,
 * W4: "Perceptual (OKLCH) Fire and Ice LUTs").
 *
 * - Neutral: grey, v -> (v, v, v) (the stretch alone).
 * - Negative: 1 - v (dark stars on a light sky).
 * - Fire (red, orange, yellow, white) and Ice (indigo, blue, cyan, white): the
 *   OKLab LIGHTNESS of entry v is exactly v, and only hue and chroma vary, so
 *   a brighter pixel is always a lighter colour and the palette adds hue
 *   without lying about intensity (the Qt stops, fits_viewer.py:337-345, had
 *   lightness steps varying 21-fold; a rainbow lies more). Chroma is reduced
 *   until the colour fits the sRGB gamut, never the lightness.
 * - Night Red (owner decision D30, README 1.3): Neutral only. Negative, Fire
 *   and Ice are refused with the reason "false colour is off in Night Red":
 *   Fire and Ice would emit green and blue light, and Negative turns the whole
 *   sky bright red (more light, against dark adaptation). `effectivePalette`
 *   applies the rule wherever a palette reaches the GPU.
 *
 * Display only: the FITS data and every measurement keep the raw values.
 */

export const PALETTES = ['neutral', 'negative', 'fire', 'ice'] as const;
export type Palette = (typeof PALETTES)[number];

export const PALETTE_LABELS: Record<Palette, string> = {
  neutral: 'Neutral',
  negative: 'Negative',
  fire: 'Fire',
  ice: 'Ice',
};

export function isPalette(v: unknown): v is Palette {
  return typeof v === 'string' && (PALETTES as readonly string[]).includes(v);
}

/** D30: why a palette cannot be used in this theme (null: it can). */
export function paletteReason(palette: Palette, nightRed: boolean): string | null {
  return nightRed && palette !== 'neutral' ? 'false colour is off in Night Red' : null;
}

/** The palette actually drawn: the observer's choice, Neutral in Night Red (D30). */
export function effectivePalette(chosen: Palette, nightRed: boolean): Palette {
  return paletteReason(chosen, nightRed) ? 'neutral' : chosen;
}

/** Shader code of a palette (0 = no lookup, the grey stretch is drawn as is). */
export function paletteCode(p: Palette): number {
  return p === 'neutral' ? 0 : p === 'negative' ? 1 : 2;
}

// -- OKLab / OKLCH (Björn Ottosson, 2020), no library ------------------------------

/** OKLab -> gamma-encoded sRGB, 0..1 per channel, unclipped. */
export function oklabToSrgb(L: number, a: number, b: number): [number, number, number] {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const lin = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
  const enc = (c: number) => (c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);
  return [enc(lin[0]), enc(lin[1]), enc(lin[2])];
}

/** sRGB bytes -> OKLab lightness L (0..1): the inverse of oklabToSrgb's L. */
export function oklabLightness(r: number, g: number, b: number): number {
  const lin = (c: number) => {
    const x = c / 255;
    return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
  };
  const [R, G, B] = [lin(r), lin(g), lin(b)];
  const l = Math.cbrt(0.4122214708 * R + 0.5363015239 * G + 0.0514459929 * B);
  const m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B);
  const s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B);
  return 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
}

/** OKLCH -> sRGB; chroma is reduced (bisection) until the colour is in gamut, lightness never. */
export function oklchToSrgbInGamut(L: number, C: number, hDeg: number): [number, number, number] {
  const h = (hDeg * Math.PI) / 180;
  const inside = (c: number) => oklabToSrgb(L, c * Math.cos(h), c * Math.sin(h)).every((v) => v >= -1e-4 && v <= 1 + 1e-4);
  let lo = 0;
  let hi = C;
  if (!inside(hi)) {
    for (let k = 0; k < 24; k++) {
      const mid = (lo + hi) / 2;
      if (inside(mid)) lo = mid;
      else hi = mid;
    }
    hi = lo;
  }
  const rgb = oklabToSrgb(L, hi * Math.cos(h), hi * Math.sin(h));
  return [clamp01(rgb[0]), clamp01(rgb[1]), clamp01(rgb[2])];
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

/**
 * The OKLab lightness of the darkest 8-bit grey (sRGB 1/255). 8-bit sRGB cannot encode a
 * lighter-than-black colour below it, so a ramp starting at L = 0 crushes its first entries to
 * the same black (the faintest 3.5 % of the stretch for Fire): the ramps start here instead.
 */
export const RAMP_L0 = Math.cbrt(1 / 255 / 12.92);

/** The OKLab lightness a false-colour ramp gives the stretched value v: 0 at 0, then L0 → 1. */
export function rampLightness(v: number): number {
  return v <= 0 ? 0 : RAMP_L0 + (1 - RAMP_L0) * Math.min(1, v);
}

/**
 * A false-colour ramp whose OKLab lightness rises linearly with the stretched value v
 * (`rampLightness`); the hue turns from h0 to h1 and the chroma peaks mid-range (0 at black
 * and white).
 */
function perceptualRamp(v: number, h0: number, h1: number, cMax: number): [number, number, number] {
  const C = cMax * Math.pow(Math.sin(Math.PI * v), 0.75);
  return oklchToSrgbInGamut(rampLightness(v), C, h0 + (h1 - h0) * v);
}

/** Ramp parameters (hue from, hue to, peak chroma), as validated in the lab. */
const RAMPS: Record<'fire' | 'ice', [number, number, number]> = {
  fire: [20, 100, 0.2], // red -> orange -> yellow -> white
  ice: [275, 200, 0.16], // indigo -> blue -> cyan -> white
};

/** One palette entry for the stretched value v (0..1), sRGB 0..1. */
export function paletteColour(palette: Palette, v: number): [number, number, number] {
  const x = clamp01(v);
  switch (palette) {
    case 'negative':
      return [1 - x, 1 - x, 1 - x];
    case 'fire':
    case 'ice': {
      const [h0, h1, c] = RAMPS[palette];
      return perceptualRamp(x, h0, h1, c);
    }
    default:
      return [x, x, x];
  }
}

/** Entries of a LUT; the shader samples entry centres, so v = i / 255 is exact. */
export const LUT_SIZE = 256;

const cache = new Map<Palette, Uint8Array>();

/** 256 x RGBA8 lookup table of a palette (cached: the tables never change). */
export function buildLut(palette: Palette): Uint8Array {
  const hit = cache.get(palette);
  if (hit) return hit;
  const out = new Uint8Array(LUT_SIZE * 4);
  const ramp = palette === 'fire' || palette === 'ice';
  let prevL = -1;
  for (let i = 0; i < LUT_SIZE; i++) {
    const c = paletteColour(palette, i / (LUT_SIZE - 1));
    let rgb: [number, number, number] = [Math.round(c[0] * 255), Math.round(c[1] * 255), Math.round(c[2] * 255)];
    if (ramp && i > 0) rgb = monotoneByte(rgb, rampLightness(i / (LUT_SIZE - 1)), prevL);
    out[i * 4] = rgb[0];
    out[i * 4 + 1] = rgb[1];
    out[i * 4 + 2] = rgb[2];
    out[i * 4 + 3] = 255;
    if (ramp) prevL = oklabLightness(rgb[0], rgb[1], rgb[2]);
  }
  cache.set(palette, out);
  return out;
}

/**
 * Rounding each channel to 8 bits can make a dark entry a little darker than the one before
 * (a channel of 1 rounding to 0). Among the bytes within ±1 of the rounded colour, keep the
 * one closest to the target lightness that is not darker than the previous entry.
 */
function monotoneByte(rgb: [number, number, number], target: number, prevL: number): [number, number, number] {
  const L = oklabLightness(rgb[0], rgb[1], rgb[2]);
  if (L > prevL) return rgb;
  let best = rgb;
  let bestErr = Infinity;
  for (const dr of [-1, 0, 1])
    for (const dg of [-1, 0, 1])
      for (const db of [-1, 0, 1]) {
        const q: [number, number, number] = [rgb[0] + dr, rgb[1] + dg, rgb[2] + db];
        if (q.some((v) => v < 0 || v > 255)) continue;
        const l = oklabLightness(q[0], q[1], q[2]);
        if (l <= prevL) continue;
        const err = Math.abs(l - target) + 1e-3 * (Math.abs(dr) + Math.abs(dg) + Math.abs(db));
        if (err < bestErr) {
          best = q;
          bestErr = err;
        }
      }
  return best;
}

/** CSS gradient of a palette, for the swatch beside its name (D11: a data ramp may show colour). */
export function paletteGradient(palette: Palette, stops = 9): string {
  const parts: string[] = [];
  for (let i = 0; i < stops; i++) {
    const v = i / (stops - 1);
    const [r, g, b] = paletteColour(palette, v).map((c) => Math.round(c * 255));
    parts.push(`rgb(${r} ${g} ${b}) ${Math.round(v * 100)}%`);
  }
  return `linear-gradient(90deg, ${parts.join(', ')})`;
}

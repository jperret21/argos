/**
 * The Inspector's aperture thumbnail as data (promoted from the canvas of
 * src/lab/workspace/observe/cards/InspectorCard.svelte, PROPOSAL 3.1, W4): the frame's own
 * pixels around a star, turned like the display so the thumbnail matches the image, stretched
 * with the display levels and multiplied by the viewer tint (red only in Night Red). Pure:
 * the component puts the bytes on a canvas.
 */

import type { Turns } from '../../viewer/rotation';
import { stretchValue, type StretchParams } from '../../viewer/stretch';
import { unturnVector } from '../../viewer/overlay/project';

export interface ThumbSource {
  pixels: Uint16Array;
  width: number;
  height: number;
  channels: 1 | 3;
}

/**
 * RGBA bytes of an n × n window (n odd) centred on frame px (cx, cy), as displayed with
 * `turns`. Outside the frame: black. Colour frames use the mean of the three channels, mono
 * the sample. `tint` is the --viewer-tint colour in sRGB bytes (0-255).
 */
export function thumbPixels(
  src: ThumbSource,
  cx: number,
  cy: number,
  n: number,
  levels: StretchParams,
  tint: readonly [number, number, number],
  turns: Turns,
): Uint8ClampedArray<ArrayBuffer> {
  const out = new Uint8ClampedArray(new ArrayBuffer(n * n * 4));
  const h = (n - 1) / 2;
  const x0 = Math.round(cx);
  const y0 = Math.round(cy);
  for (let v = 0; v < n; v++) {
    for (let u = 0; u < n; u++) {
      const d = unturnVector(u - h, v - h, turns);
      const x = x0 + d.x;
      const y = y0 + d.y;
      let s = 0;
      if (x >= 0 && y >= 0 && x < src.width && y < src.height) {
        const i = (y * src.width + x) * src.channels;
        const raw = src.channels === 1 ? src.pixels[i] : (src.pixels[i] + src.pixels[i + 1] + src.pixels[i + 2]) / 3;
        s = stretchValue(raw, levels);
      }
      const o = (v * n + u) * 4;
      out[o] = s * tint[0];
      out[o + 1] = s * tint[1];
      out[o + 2] = s * tint[2];
      out[o + 3] = 255;
    }
  }
  return out;
}

/** Window size for an aperture: the sky annulus fits with a margin; odd, 31 to 121 px. */
export function thumbSize(apertureR: number | null, annulusOut: number | null): number {
  const r = Math.max(annulusOut ?? 0, (apertureR ?? 0) * 2, 12);
  const n = Math.ceil(r * 2.3);
  const odd = n % 2 === 0 ? n + 1 : n;
  return Math.max(31, Math.min(121, odd));
}

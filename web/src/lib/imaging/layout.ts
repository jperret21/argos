/**
 * Height of the levels strip docked under the image (BRAND 11.1).
 *
 * A 16:9 frame fitted to the viewer's width leaves a band of black under and
 * over it whenever the viewer is taller than the frame's aspect. The strip
 * takes exactly that band (its top border included), so the image keeps its
 * fitted size and the bands disappear:
 *
 *   band = centre height − reserved (log drawer) − centre width × image h / w
 *
 * - band ≥ STRIP.min: the full strip (histogram, levels, transfer, rotation),
 *   at most STRIP.max tall;
 * - smaller band (rail closed): one compact row of the three levels, as
 *   tall as the band (at least STRIP.compact), so the band is still taken;
 * - a band under STRIP.compact (a square frame): the compact row, and the
 *   Fill fit mode removes what remains.
 */

export const STRIP = { min: 150, max: 300, compact: 34 } as const;

export interface Size {
  width: number;
  height: number;
}

export interface StripLayout {
  /** CSS px, 0 when the strip is closed. */
  height: number;
  compact: boolean;
}

export function stripLayout(center: Size, image: Size, reserved: number, open: boolean): StripLayout {
  if (!open || center.width <= 0 || center.height <= 0 || image.width <= 0 || image.height <= 0) {
    return { height: 0, compact: false };
  }
  const band = center.height - reserved - (center.width * image.height) / image.width;
  if (band >= STRIP.min) return { height: Math.min(STRIP.max, Math.floor(band)), compact: false };
  return { height: Math.max(STRIP.compact, Math.floor(band)), compact: true };
}

/** Black margin left on each short side of a fitted image, CSS px. */
export function fitBands(stage: Size, image: Size): { x: number; y: number } {
  if (stage.width <= 0 || stage.height <= 0 || image.width <= 0 || image.height <= 0) {
    return { x: 0, y: 0 };
  }
  const scale = Math.min(stage.width / image.width, stage.height / image.height);
  return {
    x: (stage.width - image.width * scale) / 2,
    y: (stage.height - image.height * scale) / 2,
  };
}

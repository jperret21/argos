import { describe, expect, it } from 'vitest';
import {
  clampPan,
  croppedFraction,
  fillView,
  fitView,
  framedView,
  isFitMode,
  imageToScreen,
  oneToOneView,
  PAN_MARGIN,
  scaleLimits,
  screenToImage,
  wheelZoomFactor,
  zoomAt,
} from './view';

const image = { width: 1080, height: 1920 }; // Seestar portrait frame
const viewport = { width: 800, height: 600 };

describe('view transform', () => {
  it('fit shows the whole image, centred', () => {
    const v = fitView(image, viewport);
    expect(v.scale).toBeCloseTo(600 / 1920, 12);
    const tl = imageToScreen(v, 0, 0);
    const br = imageToScreen(v, image.width, image.height);
    expect(tl.y).toBeCloseTo(0, 9);
    expect(br.y).toBeCloseTo(600, 9);
    expect((tl.x + br.x) / 2).toBeCloseTo(400, 9);
  });

  it('screenToImage inverts imageToScreen', () => {
    const v = { scale: 2.5, tx: -123.4, ty: 56.7 };
    const p = screenToImage(v, 321, 89);
    const q = imageToScreen(v, p.x, p.y);
    expect(q.x).toBeCloseTo(321, 9);
    expect(q.y).toBeCloseTo(89, 9);
  });

  it('zoomAt keeps the image point under the cursor fixed', () => {
    const v = fitView(image, viewport);
    const limits = scaleLimits(image, viewport, 2);
    const before = screenToImage(v, 250, 410);
    const z = zoomAt(v, 3, 250, 410, limits);
    expect(z.scale).toBeCloseTo(v.scale * 3, 12);
    const after = screenToImage(z, 250, 410);
    expect(after.x).toBeCloseTo(before.x, 9);
    expect(after.y).toBeCloseTo(before.y, 9);
  });

  it('zoom is clamped to the limits (max 64 device px per image px)', () => {
    const limits = scaleLimits(image, viewport, 2);
    expect(limits.max).toBe(32); // CSS px at DPR 2
    const v = zoomAt({ scale: 30, tx: 0, ty: 0 }, 10, 0, 0, limits);
    expect(v.scale).toBe(32);
    const w = zoomAt(fitView(image, viewport), 1e-6, 0, 0, limits);
    expect(w.scale).toBe(limits.min);
  });

  it('1:1 is one image pixel per device pixel and keeps the centre', () => {
    const v = fitView(image, viewport);
    const centre = screenToImage(v, 400, 300);
    const o = oneToOneView(image, viewport, v, 2);
    expect(o.scale).toBe(0.5);
    const c2 = screenToImage(o, 400, 300);
    expect(c2.x).toBeCloseTo(centre.x, 9);
    expect(c2.y).toBeCloseTo(centre.y, 9);
  });

  it('pan keeps part of the image on screen', () => {
    const v = clampPan({ scale: 1, tx: 5000, ty: -5000 }, image, viewport);
    expect(v.tx).toBe(viewport.width - PAN_MARGIN);
    expect(v.ty).toBe(PAN_MARGIN - image.height);
  });

  it('wheel: scrolling down zooms out, up zooms in, one event at most x2', () => {
    expect(wheelZoomFactor(100, 0, false)).toBeLessThan(1);
    expect(wheelZoomFactor(-100, 0, false)).toBeGreaterThan(1);
    expect(wheelZoomFactor(-1e6, 0, false)).toBeCloseTo(2, 12);
    expect(wheelZoomFactor(3, 1, false)).toBeCloseTo(wheelZoomFactor(48, 0, false), 12);
  });
});

describe('fill mode', () => {
  // The owner's case: a rotated 1920x1080 Seestar frame in a 928x821 viewer.
  const frame = { width: 1920, height: 1080 };
  const stage = { width: 928, height: 821 };

  it('fit leaves bands on the short sides, fill covers the viewer', () => {
    const fit = fitView(frame, stage);
    expect(fit.ty).toBeCloseTo((821 - 1080 * (928 / 1920)) / 2, 9); // ~150 px bands
    const fill = fillView(frame, stage);
    expect(fill.scale).toBeCloseTo(821 / 1080, 12);
    const tl = imageToScreen(fill, 0, 0);
    const br = imageToScreen(fill, frame.width, frame.height);
    expect(tl.y).toBeCloseTo(0, 9);
    expect(br.y).toBeCloseTo(821, 9);
    expect(tl.x).toBeLessThan(0);
    expect((tl.x + br.x) / 2).toBeCloseTo(464, 9); // crop shared equally
  });

  it('reports what each view hides', () => {
    expect(croppedFraction(fitView(frame, stage), frame, stage)).toEqual({ x: 0, y: 0 });
    const c = croppedFraction(fillView(frame, stage), frame, stage);
    expect(c.y).toBeCloseTo(0, 9);
    expect(c.x).toBeCloseTo(1 - 928 / (1920 * (821 / 1080)), 9);
    // Rail closed at 1440x900: a 1348x821 viewer, about 3.8 % cropped per side.
    const wide = { width: 1348, height: 821 };
    expect(croppedFraction(fillView(frame, wide), frame, wide).x / 2).toBeCloseTo(0.038, 3);
  });

  it('dispatches on the mode and validates stored values', () => {
    expect(framedView('fill', frame, stage)).toEqual(fillView(frame, stage));
    expect(framedView('fit', frame, stage)).toEqual(fitView(frame, stage));
    expect(isFitMode('fill')).toBe(true);
    expect(isFitMode('stretch')).toBe(false);
  });
});

import { describe, expect, it } from 'vitest';
import { compassAt, fromFrameWcs, isTanWcs, pixelToSky, plateScaleArcsec, scaleBar, skyAxesAt, skyToPixel, trackedWcs, wcsToFrame, type TanWcs } from './wcs';

/** Reference values from astropy.wcs (wcs_pix2world, origin 0), as FrameWCS computes them. */
const ORION: TanWcs = { crval: [83.8221, -5.3911], crpix: [540.5, 960.5], cd: [-1.0281e-3, 1.21e-5, 1.13e-5, 1.0279e-3] };
const ASTROPY: [number, number, number, number][] = [
  [0, 0, 84.36843928298188, -6.383079382446516],
  [1079, 1919, 83.27754369275877, -4.398634917796202],
  [539.5, 959.5, 83.8221, -5.3910999999999945],
  [100.25, 1500.75, 84.2818501993482, -4.839574603682804],
];
const POLE: TanWcs = { crval: [10, 88.5], crpix: [100, 100], cd: [-2e-3, 0, 0, 2e-3] };
const POLE_REF: [number, number, number, number][] = [
  [0, 0, 16.652024675609216, 88.29049917656633],
  [199, 199, 1.253156716732045, 88.68470747149279],
];

describe('TAN projection (FrameWCS)', () => {
  for (const [w, refs] of [
    [ORION, ASTROPY],
    [POLE, POLE_REF],
  ] as const) {
    it(`pixel -> sky matches astropy to 1 mas (crval ${w.crval})`, () => {
      for (const [x, y, ra, dec] of refs) {
        const s = pixelToSky(w, x, y);
        expect(Math.abs(s.raHours * 15 - ra) * 3600 * Math.cos((dec * Math.PI) / 180)).toBeLessThan(1e-3);
        expect(Math.abs(s.decDeg - dec) * 3600).toBeLessThan(1e-3);
      }
    });

    it(`sky -> pixel inverts it to 1e-6 px (crval ${w.crval})`, () => {
      for (const [x, y, ra, dec] of refs) {
        const p = skyToPixel(w, ra / 15, dec)!;
        expect(p.x).toBeCloseTo(x, 6);
        expect(p.y).toBeCloseTo(y, 6);
      }
    });
  }

  it('no gnomonic image of the far hemisphere', () => {
    expect(skyToPixel(ORION, (83.8221 + 180) / 15, 5.3911)).toBeNull();
  });

  it('plate scale is sqrt|det CD|', () => {
    expect(plateScaleArcsec(ORION)).toBeCloseTo(3.7, 1);
  });

  it('a green-plane WCS becomes the same sky in frame px', () => {
    const green: TanWcs = { crval: [83.8221, -5.3911], crpix: [270.5, 480.5], cd: [-2.0562e-3, 0, 0, 2.0558e-3] };
    const frame = wcsToFrame(green, 2, [0.5, 0.5]);
    // Green px (g) is centred on frame px 2 g + 0.5.
    for (const [gx, gy] of [
      [0, 0],
      [100, 300],
    ]) {
      const a = pixelToSky(green, gx, gy);
      const b = pixelToSky(frame, 2 * gx + 0.5, 2 * gy + 0.5);
      expect(b.raHours).toBeCloseTo(a.raHours, 10);
      expect(b.decDeg).toBeCloseTo(a.decDeg, 10);
    }
    expect(plateScaleArcsec(frame)).toBeCloseTo(plateScaleArcsec(green) / 2, 9);
  });

  it('reads the wire FrameWcs (nested CD)', () => {
    const w = fromFrameWcs({ ctype: ['RA---TAN', 'DEC--TAN'], crval: [83.8221, -5.3911], crpix: [540.5, 960.5], cd: [[-1.0281e-3, 1.21e-5], [1.13e-5, 1.0279e-3]], frame_shape: [1920, 1080] });
    expect(w).toEqual(ORION);
    expect(fromFrameWcs({ crval: [1, 2], crpix: [1, 2], cd: [[0, 0], [0, 0]] })).toBeNull();
    expect(fromFrameWcs(null)).toBeNull();
  });

  it('follows the tracked field: a marker moved by the transform keeps its sky position', () => {
    const t = { rot_deg: 0.8, dx: 12.5, dy: -7.25, cx: 540, cy: 960 };
    const th = (t.rot_deg * Math.PI) / 180;
    const moved = trackedWcs(ORION, t);
    for (const [x, y] of [
      [100, 200],
      [900, 1700],
    ]) {
      const xp = t.cx + Math.cos(th) * (x - t.cx) - Math.sin(th) * (y - t.cy) + t.dx;
      const yp = t.cy + Math.sin(th) * (x - t.cx) + Math.cos(th) * (y - t.cy) + t.dy;
      const a = pixelToSky(ORION, x, y);
      const b = pixelToSky(moved, xp, yp);
      expect(b.raHours).toBeCloseTo(a.raHours, 10);
      expect(b.decDeg).toBeCloseTo(a.decDeg, 10);
    }
    expect(trackedWcs(ORION, { rot_deg: 0, dx: 0, dy: 0, cx: 1, cy: 1 })).toBe(ORION);
    expect(plateScaleArcsec(moved)).toBeCloseTo(plateScaleArcsec(ORION), 9);
  });

  it('validates the wire shape', () => {
    expect(isTanWcs(ORION)).toBe(true);
    expect(isTanWcs({ crval: [1, 2], crpix: [1, 2], cd: [0, 0, 0, 0] })).toBe(false);
    expect(isTanWcs({ crval: [1], crpix: [1, 2], cd: [1, 0, 0, 1] })).toBe(false);
    expect(isTanWcs(null)).toBe(false);
  });
});

describe('compass', () => {
  // RA grows to -x, Dec grows to +y (row 0 at the top: north is DOWN on an un-rotated frame).
  const W: TanWcs = { crval: [150, 20], crpix: [500, 400], cd: [-1e-3, 0, 0, 1e-3] };

  it('north and east in frame px follow the CD matrix', () => {
    const a = skyAxesAt(W, 499, 399)!;
    expect(a.north[0]).toBeCloseTo(0, 5);
    expect(a.north[1]).toBeCloseTo(1, 5);
    expect(a.east[0]).toBeCloseTo(-1, 5);
    expect(a.east[1]).toBeCloseTo(0, 5);
  });

  it('turns with the display rotation; letters stay upright (screen vectors)', () => {
    const c0 = compassAt(W, 499, 399, 0)!;
    expect([c0.north.x, c0.north.y].map((v) => Math.round(v) + 0)).toEqual([0, 1]);
    expect([c0.east.x, c0.east.y].map((v) => Math.round(v) + 0)).toEqual([-1, 0]);
    // A quarter turn clockwise: +y of the frame points left on screen.
    const c1 = compassAt(W, 499, 399, 1)!;
    expect([c1.north.x, c1.north.y].map((v) => Math.round(v) + 0)).toEqual([-1, 0]);
    expect([c1.east.x, c1.east.y].map((v) => Math.round(v) + 0)).toEqual([0, -1]);
    const c2 = compassAt(W, 499, 399, 2)!;
    expect([c2.north.x, c2.north.y].map((v) => Math.round(v) + 0)).toEqual([0, -1]);
    expect([c2.east.x, c2.east.y].map((v) => Math.round(v) + 0)).toEqual([1, 0]);
  });

  it('says when the picture is a mirror image of the sky', () => {
    // North down, east left: a mirror image (with north up, east would be on the right).
    expect(compassAt(W, 499, 399, 0)!.mirrored).toBe(true);
    // Flip y: north up, east left = the sky as seen.
    const sky: TanWcs = { ...W, cd: [-1e-3, 0, 0, -1e-3] };
    expect(compassAt(sky, 499, 399, 0)!.mirrored).toBe(false);
    expect(compassAt(sky, 499, 399, 3)!.mirrored).toBe(false);
  });

  it('still points north next to the pole', () => {
    const p: TanWcs = { crval: [0, 89.95], crpix: [100, 100], cd: [-1e-3, 0, 0, 1e-3] };
    expect(skyAxesAt(p, 99, 99)).not.toBeNull();
  });
});

describe('scale bar', () => {
  it('picks the shortest round length at least 56 px long', () => {
    // 3.7″/px at 0.45 CSS px per px: 1′ = 7.3 px -> 10′ = 73 px.
    expect(scaleBar(3.7, 0.45)).toMatchObject({ label: '10′', arcmin: 10 });
    expect(scaleBar(3.7, 0.45)!.px).toBeCloseTo((600 / 3.7) * 0.45, 9);
    expect(scaleBar(3.7, 8)!.label).toBe('30″');
    expect(scaleBar(3.7, 40)!.label).toBe('15″');
    expect(scaleBar(3.7, 0.05)!.label).toBe('2°');
    // Too far out for the longest step: no bar rather than a misleading one.
    expect(scaleBar(3.7, 0.02)).toBeNull();
  });

  it('nothing without a scale', () => {
    expect(scaleBar(0, 1)).toBeNull();
    expect(scaleBar(3.7, 0)).toBeNull();
  });
});

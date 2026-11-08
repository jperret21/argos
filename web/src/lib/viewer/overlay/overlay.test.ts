import { describe, expect, it } from 'vitest';
import { frameToDisplay, type Turns } from '../rotation';
import {
  defaultVisibility,
  hitTest,
  LAYER_IDS,
  LAYERS,
  passesDepth,
  countWithin,
  placeLabels,
  roleRadius,
  rolePath,
  type Placed,
} from './layers';
import {
  applyTransform,
  frameToScreen,
  invertTransform,
  project,
  screenScale,
  screenToFrame,
  tolFramePx,
  turnVector,
  type ScreenMap,
} from './project';

const frame = { width: 1080, height: 1920 };

function map(turns: Turns, scale = 0.5, left = 10, top = 20): ScreenMap {
  const w = turns % 2 ? frame.height : frame.width;
  const h = turns % 2 ? frame.width : frame.height;
  return { rect: { left, top, width: w * scale, height: h * scale }, frame, turns };
}

describe('tracking transform (core RigidTransform)', () => {
  it('matches tracking.py apply: rotation about the pivot, then the translation', () => {
    // A quarter turn about (100, 50) then (+3, -2): (110, 50) -> (100, 60) -> (103, 58).
    const p = applyTransform({ dx: 3, dy: -2, rot_deg: 90, cx: 100, cy: 50 }, 110, 50);
    expect(p.x).toBeCloseTo(103, 9);
    expect(p.y).toBeCloseTo(58, 9);
  });

  it('pivots on the frame centre when the server omits it', () => {
    const p = applyTransform({ dx: 0, dy: 0, rot_deg: 180 }, 0, 0, frame);
    expect(p.x).toBeCloseTo(1080, 9);
    expect(p.y).toBeCloseTo(1920, 9);
  });

  it('inverts exactly', () => {
    const t = { dx: 4.25, dy: -7.5, rot_deg: 1.3, cx: 540, cy: 960 };
    for (const [x, y] of [[0, 0], [1079, 1919], [321.4, 777.7]]) {
      const a = applyTransform(t, x, y);
      const b = invertTransform(t, a.x, a.y);
      expect(b.x).toBeCloseTo(x, 9);
      expect(b.y).toBeCloseTo(y, 9);
    }
  });

  it('is the identity when there is no transform', () => {
    expect(applyTransform(null, 5, 6)).toEqual({ x: 5, y: 6 });
    expect(invertTransform(null, 5, 6)).toEqual({ x: 5, y: 6 });
  });
});

describe('frame <-> screen', () => {
  it('puts a pixel centre at the centre of its displayed pixel', () => {
    const m = map(0, 2, 0, 0);
    expect(frameToScreen(m, 0, 0)).toEqual({ x: 1, y: 1 });
    expect(frameToScreen(m, 3, 1)).toEqual({ x: 7, y: 3 });
  });

  it('follows the display rotation of rotation.ts for every quarter turn', () => {
    for (const k of [0, 1, 2, 3] as Turns[]) {
      const m = map(k);
      const s = screenScale(m);
      expect(s).toBeCloseTo(0.5, 12);
      const p = frameToScreen(m, 100, 400);
      const d = frameToDisplay(100, 400, frame.width, frame.height, k);
      expect(p.x).toBeCloseTo(10 + (d.u + 0.5) * 0.5, 9);
      expect(p.y).toBeCloseTo(20 + (d.v + 0.5) * 0.5, 9);
    }
  });

  it('round-trips through screenToFrame with sub-pixel positions', () => {
    for (const k of [0, 1, 2, 3] as Turns[]) {
      const m = map(k, 0.37, -50, 33);
      for (const [x, y] of [[0, 0], [1079, 1919], [12.25, 1500.75]]) {
        const p = frameToScreen(m, x, y);
        const q = screenToFrame(m, p.x, p.y);
        expect(q.x).toBeCloseTo(x, 9);
        expect(q.y).toBeCloseTo(y, 9);
      }
    }
  });

  it('turns vectors like the display (auto: 90° clockwise)', () => {
    // North up in the frame (0, -1) points right on a frame turned 90° clockwise.
    const n = turnVector(0, -1, 1);
    expect([n.x, n.y + 0]).toEqual([1, 0]);
    const e = turnVector(1, 0, 2);
    expect([e.x, e.y + 0]).toEqual([-1, 0]);
  });

  it('sends a tolerance of 10 screen px in frame px at any zoom', () => {
    expect(tolFramePx(map(1, 0.5))).toBeCloseTo(20, 9);
    expect(tolFramePx(map(0, 4))).toBeCloseTo(2.5, 9);
    expect(tolFramePx(map(0, 100))).toBe(0.5);
  });

  it('projects reference positions through the tracking transform', () => {
    const m = map(0, 1, 0, 0);
    const p = project(m, { dx: 10, dy: 5, rot_deg: 0 }, 100, 100);
    expect(p).toEqual({ x: 110.5, y: 105.5 });
  });
});

describe('layers', () => {
  it('shows on a first solve what Qt shows; labels and VSP stay off (03 2.4)', () => {
    const v = defaultVisibility();
    expect(v.labels).toBe(false);
    expect(v.vsp).toBe(false);
    expect(v.grid).toBe(true);
    for (const id of LAYER_IDS) if (id !== 'vsp') expect(v[id]).toBe(true);
  });

  it('filters the Gaia depth on stars only, keeping stars without a G', () => {
    expect(passesDepth('stars', { x: 0, y: 0, g_mag: 17 }, 16.5)).toBe(false);
    expect(passesDepth('stars', { x: 0, y: 0, g_mag: 16.5 }, 16.5)).toBe(true);
    expect(passesDepth('stars', { x: 0, y: 0 }, 10)).toBe(true);
    expect(passesDepth('galaxies', { x: 0, y: 0, g_mag: 20 }, 10)).toBe(true);
    expect(countWithin([{ x: 0, y: 0, g_mag: 12 }, { x: 0, y: 0, g_mag: 18 }], 16)).toBe(1);
  });

  it('hit-tests within 10 px, the set and variables before Gaia, then the nearest', () => {
    const P = (layer: Placed['layer'], sx: number, sy: number, index = 0): Placed => ({ layer, index, marker: { x: 0, y: 0 }, sx, sy });
    const placed = [P('stars', 100, 100), P('variables', 106, 100), P('stars', 101, 100, 1), P('selected', 200, 200)];
    expect(hitTest(placed, { x: 100, y: 100 })?.layer).toBe('variables');
    expect(hitTest(placed, { x: 195, y: 200 })?.layer).toBe('selected');
    expect(hitTest(placed, { x: 140, y: 140 })).toBeNull();
    expect(hitTest([P('stars', 0, 0), P('stars', 3, 0, 1)], { x: 2.6, y: 0 })?.index).toBe(1);
    expect(LAYERS.selected.priority).toBeLessThan(LAYERS.variables.priority);
  });

  it('places labels without overlap, inside the stage, dropping what cannot fit', () => {
    const stage = { width: 300, height: 200 };
    const reqs = [
      { id: 'a', text: 'RR Lyr', x: 100, y: 100, r: 10 },
      { id: 'b', text: 'V0123', x: 104, y: 100, r: 10 },
      { id: 'c', text: 'edge', x: 296, y: 100, r: 10 },
      { id: 'd', text: '', x: 50, y: 50, r: 10 },
    ];
    const out = placeLabels(reqs, stage);
    expect(out.map((l) => l.id)).toEqual(['a', 'b', 'c']);
    expect(out[0].anchor).toBe('start');
    expect(out[1].anchor).not.toBe('start');
    expect(out[2].anchor).toBe('end');
    // The same name twice at one place (target and VSX variable): one label.
    expect(placeLabels([{ id: 's', text: 'RR Lyr', x: 50, y: 50, r: 13 }, { id: 'v', text: 'RR Lyr', x: 51, y: 50, r: 14 }], stage).length).toBe(1);
    const crowd = Array.from({ length: 50 }, (_, i) => ({ id: `s${i}`, text: 'TYC 1234-5678-1', x: 150, y: 100, r: 9 }));
    expect(placeLabels(crowd, stage).length).toBeLessThanOrEqual(4);
  });

  it('draws role markers at the aperture size, never below the role floor (the set stands out)', () => {
    expect(roleRadius(5, 0.5)).toBe(17);
    expect(roleRadius(5, 0.5, 'comparison')).toBe(15);
    expect(roleRadius(5, 0.5, 'check')).toBe(15);
    // Larger than a variable's circle (14), whatever the role.
    expect(Math.min(roleRadius(0, 1, 'target'), roleRadius(0, 1, 'check'))).toBeGreaterThan(14);
    expect(roleRadius(8, 3)).toBe(24);
    expect(roleRadius(8, 100)).toBe(64);
    expect(rolePath('target', 0, 0, 10)).toMatch(/a10 10/);
    expect(rolePath('comparison', 0, 0, 10)).toMatch(/z$/);
    // The check triangle points up on screen.
    expect(rolePath('check', 0, 0, 10)).toMatch(/^M0 -13\.5/);
  });
});

describe('selection ring', () => {
  it('moves a reference-space ring with the tracking, never a frame-space one', async () => {
    const { placeRing } = await import('./project');
    const m = { rect: { left: 0, top: 0, width: 100, height: 100 }, frame: { width: 100, height: 100 }, turns: 0 as const };
    const t = { dx: 10, dy: 0, rot_deg: 0, cx: 50, cy: 50 };
    expect(placeRing(m, t, { x: 20, y: 20, r_px: 3, space: 'reference' })).toEqual({ x: 30.5, y: 20.5, r: 10 });
    expect(placeRing(m, t, { x: 20, y: 20, r_px: 30, space: 'frame' })).toEqual({ x: 20.5, y: 20.5, r: 30 });
    expect(placeRing(m, t, { x: 20, y: 20, r_px: 3 }).x).toBe(20.5);
  });
});

describe('overlay text and marks (design review)', () => {
  it("shortens long names with Qt's 18-character rule", async () => {
    const { shortLabel, markerLabel } = await import('./layers');
    expect(shortLabel('RR Lyr')).toBe('RR Lyr');
    expect(shortLabel('Gaia DR3 2053638685606798976')).toBe('Gaia DR3 20…798976');
    expect(shortLabel('ROTSE1 J192351.77+425833.4')).toBe('ROTSE1 J192…5833.4');
    expect(markerLabel({ x: 0, y: 0, label: 'ABCDEFGHIJKLMNOPQR' })).toBe('ABCDEFGHIJKLMNOPQR');
  });

  it('writes grid labels in the UI coordinate format at the grid precision', async () => {
    const { gridLabelText } = await import('./layers');
    expect(gridLabelText('19h28m00.0s', 'ra')).toBe('19h 28m');
    expect(gridLabelText('19h28m30.0s', 'ra')).toBe('19h 28m 30s');
    expect(gridLabelText('+42°30\'00.0"', 'dec')).toBe('+42° 30′');
    expect(gridLabelText('-05°10\'00.0"', 'dec')).toBe('−05° 10′');
  });

  it('keeps labels off the HUD boxes', async () => {
    const { placeLabels } = await import('./layers');
    const hud = [{ x0: 0, y0: 0, x1: 300, y1: 30 }];
    const out = placeLabels([{ id: 'a', text: 'NGC 6792', x: 100, y: 20, r: 9 }], { width: 300, height: 200 }, 250, hud);
    expect(out).toHaveLength(1);
    expect(out[0].y).toBeGreaterThan(30);
  });

  it('draws the selection and list hovers as corner brackets, nebulae with ticks', async () => {
    const { bracketPath, nebulaPath } = await import('./layers');
    expect(bracketPath(0, 0, 10).match(/M/g)).toHaveLength(4);
    expect(nebulaPath(0, 0, 10).match(/M/g)?.length).toBe(5);
  });

  it('gives a marker popover a title, facts and RA / Dec in the UI format', async () => {
    const { tipContent } = await import('./layers');
    const t = tipContent('variables', {
      x: 0,
      y: 0,
      name: 'NSV 11944',
      tooltip: 'Variable star\nNSV 11944\ntype S  (suspected)\nmax 6.9 V  min 7.2 V\nAUID 000-BCG-372\nRA 19h21m02.8s  Dec +42°41\'15.0"',
      ra_hours: 19.350778,
      dec_deg: 42.6875,
    });
    expect(t.title).toBe('NSV 11944');
    expect(t.kind).toBe('Variable star');
    expect(t.rows).toContainEqual({ k: 'AUID', v: '000-BCG-372' });
    expect(t.rows).toContainEqual({ k: 'RA', v: '19h 21m 02.8s' });
    expect(t.rows).toContainEqual({ k: 'Dec', v: '+42° 41′ 15″' });
    expect(t.rows.some((r) => r.v.includes("'"))).toBe(false);
  });
});

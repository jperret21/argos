import { describe, expect, it, vi } from 'vitest';
import { LiveCurveStore } from './store';
import { CurveDisplay, CurveView, curveToolsLayout, nextAxis, TOOL_W, zoomText, ZOOM_STEP } from './view.svelte';

describe('the curve view lifted out of the plot (wave 6b)', () => {
  it('names the zoom state as BRAND 10 does', () => {
    expect(zoomText('fit', 0)).toBe('Whole run');
    expect(zoomText('follow', 900)).toBe('Following · 15m 00s');
    expect(zoomText('manual', 120)).toBe('Zoom kept');
  });

  it('sends the tools to the attached plot only, and detaches cleanly', () => {
    const v = new CurveView();
    const ctrl = { fit: vi.fn(), follow: vi.fn(), zoomBy: vi.fn(), copy: vi.fn() };
    v.fit(); // nothing attached: no throw, nothing done
    const off = v.attach(ctrl);
    expect(v.attached).toBe(true);
    v.fit();
    v.follow();
    v.zoomIn();
    v.zoomOut();
    v.copy();
    expect(ctrl.fit).toHaveBeenCalledOnce();
    expect(ctrl.follow).toHaveBeenCalledOnce();
    expect(ctrl.zoomBy.mock.calls).toEqual([[1 / ZOOM_STEP], [ZOOM_STEP]]);
    expect(ctrl.copy).toHaveBeenCalledOnce();
    // A newer plot attached: the old one's detach must not drop it.
    const ctrl2 = { fit: vi.fn(), follow: vi.fn(), zoomBy: vi.fn(), copy: vi.fn() };
    const off2 = v.attach(ctrl2);
    off();
    expect(v.attached).toBe(true);
    v.fit();
    expect(ctrl2.fit).toHaveBeenCalledOnce();
    off2();
    expect(v.attached).toBe(false);
  });

  it('keeps the zoom state the plot publishes, without churn on equal values', () => {
    const v = new CurveView();
    v.setZoom('follow', [100, 1000]);
    expect(v.mode).toBe('follow');
    expect(v.span).toBe(900);
    const r = v.range;
    v.setZoom('follow', [100, 1000]);
    expect(v.range).toBe(r);
    v.setZoom('fit', null);
    expect(v.range).toBeNull();
    expect(v.span).toBe(0);
  });

  it('shares one display between views (the band and the drawer show the same axis)', () => {
    const d = new CurveDisplay({ axis: 'jd', errors: false });
    const band = new CurveView(d);
    const drawer = new CurveView(d);
    band.cycleAxis();
    expect(drawer.display.axis).toBe('bjd');
    band.bjdOk = false;
    drawer.display.axis = 'jd';
    band.cycleAxis(); // no site: BJD is skipped
    expect(drawer.display.axis).toBe('utc');
  });

  it('cycles UTC, JD, BJD, and skips BJD without a site', () => {
    expect(nextAxis('utc', true)).toBe('jd');
    expect(nextAxis('jd', true)).toBe('bjd');
    expect(nextAxis('bjd', true)).toBe('utc');
    expect(nextAxis('jd', false)).toBe('utc');
  });

  it('drops the least needed tools first as the row narrows; Fit, Follow and the state stay', () => {
    const wide = curveToolsLayout(2000, { copy: true });
    expect(wide).toEqual({ axis: 'segmented', steps: true, toggles: true, copy: true, hint: true });
    const widths = [600, 400, 360, 330, 300, 260, 230, 200, 120];
    const seq = widths.map((w) => curveToolsLayout(w, { copy: true }));
    // Monotone: a narrower row never shows a tool a wider one dropped.
    const score = (l: ReturnType<typeof curveToolsLayout>) => (l.axis === 'segmented' ? 2 : l.axis === 'cycle' ? 1 : 0) + +l.steps + +l.toggles + +l.copy + +l.hint;
    for (let i = 1; i < seq.length; i++) expect(score(seq[i])).toBeLessThanOrEqual(score(seq[i - 1]));
    // − / + go first, then the axis becomes one cycling button, then U and M, then Copy.
    const order: string[] = [];
    let prev = wide;
    for (let w = 2000; w > 0; w -= 2) {
      const l = curveToolsLayout(w, { copy: true });
      if (prev.steps && !l.steps) order.push('steps');
      if (prev.axis === 'segmented' && l.axis === 'cycle') order.push('cycle');
      if (prev.toggles && !l.toggles) order.push('toggles');
      if (prev.copy && !l.copy) order.push('copy');
      if (prev.axis !== 'none' && l.axis === 'none') order.push('axis');
      prev = l;
    }
    expect(order).toEqual(['steps', 'cycle', 'toggles', 'copy', 'axis']);
    // The band variant has no Copy: the same width keeps more.
    expect(curveToolsLayout(TOOL_W.core + TOOL_W.cycle + TOOL_W.toggles, { copy: false }).toggles).toBe(true);
  });
});

describe('S49: one curve per star and filter', () => {
  const pt = (jd: number, mag: number) => ({ jd_utc: jd, utc: '', mag, mag_err: 0.01, flux: 1000, flux_err: 10 }) as never;

  it('lists the filters, picks the newest frame’s, and draws only that filter’s curves', () => {
    const s = new LiveCurveStore();
    s.load({
      revision: 1,
      seq: 0,
      curves: [
        { key: 'T|V', star_key: 'T', role: 'target', filter: 'V', points: [pt(2461000.1, 12.1), pt(2461000.2, 12.2)] },
        { key: 'T|B', star_key: 'T', role: 'target', filter: 'B', points: [pt(2461000.15, 12.9), pt(2461000.25, 13.0)] },
        { key: 'C|V', star_key: 'C', role: 'check', filter: 'V', points: [pt(2461000.1, 11.0)] },
        { key: 'C|B', star_key: 'C', role: 'check', filter: 'B', points: [pt(2461000.15, 11.6)] },
        { key: 'K', star_key: 'K', role: 'comparison', points: [pt(2461000.1, 10.0)] },
      ],
    });
    expect(s.filters()).toEqual(['V', 'B']);
    expect(s.newestFilter()).toBe('B');
    expect(s.primary('target', 'T', 'V')?.key).toBe('T|V');
    expect(s.primary('target', 'T', 'B')?.key).toBe('T|B');
    expect(s.primary('check', null, 'B')?.key).toBe('C|B');
    // The key of one filter's curve (the server's "AUID@ir") names the star in every filter.
    expect(s.primary('target', 'T|V', 'B')?.key).toBe('T|B');
    expect(s.primary('check', 'C|B', 'V')?.key).toBe('C|V');
    // A curve that names no filter (before S49) belongs to every filter.
    expect(s.comparisons('B').map((c) => c.key)).toEqual(['K']);
    // Without a filter: as before S49, the first of the role.
    expect(s.primary('target')?.key).toBe('T|V');
  });

  it('a stream without filters behaves as before', () => {
    const s = new LiveCurveStore();
    s.load({ revision: 1, seq: 0, curves: [{ key: 'T', role: 'target', points: [pt(2461000.1, 12.1)] }] });
    expect(s.filters()).toEqual([]);
    expect(s.newestFilter()).toBeNull();
    expect(s.primary('target', null, null)?.key).toBe('T');
  });
});

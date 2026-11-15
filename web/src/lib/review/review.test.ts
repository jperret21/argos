import { describe, expect, it } from 'vitest';
import { LiveCurveStore } from '../charts/lightcurve/store';
import { facetData, magBaselineOf, robustExtent } from '../charts/lightcurve/facets';
import { readoutAt } from '../charts/lightcurve/readout';
import { unixFromJd } from '../charts/lightcurve/columns';
import { FLAG_RECORDER, FLAG_SATURATED, FLAG_SUSPECT } from '../charts/uplot/markers';
import { fileStem, toTsv } from '../charts/export';
import { CurveLink } from '../charts/lightcurve/link.svelte';
import { frameRows } from './frames/frames';
import { curveFilters, extraRow, flagWord, parseCurves, parseQuality, parseQualityBlock, parseQualityList, qualityFor, seriesLabel, starKeyOf, statusWord, storeFromCurves } from './source';
import { arrange, cellMenu, cellStats, cellTsv, CONDITIONS_ID, metricMenu, defaultCells, estimateScatter, healthOf, isWallLayout, loadWallLayout, metricSeries, moveCell, robustSigma, rowHeight, saveWallLayout, wallColumns, wallExtent } from './wall';
import { aavsoChecks, ensembleRows, pointInfo } from './rail';
import { WallLayoutState } from './layout.svelte';
import { ReviewSource, parseSession, summaryRows, wallFramesOf } from './session.svelte';
import { fixtureLoader, makeSession } from './gallery/fixtures';

const memory = () => {
  const m = new Map<string, string>();
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) };
};

function loaded(opts: Parameters<typeof makeSession>[0] = {}) {
  const f = makeSession(opts);
  const curves = parseCurves(f.curves);
  const info = parseSession(f.session, f.path);
  const { store, skipped, extras } = storeFromCurves({ curves: curves.curves, targets: info.targets, band: info.band, object: info.object });
  const frames = frameRows(f.session.frames as unknown[]);
  return { f, curves, info, store, skipped, extras, frames, wall: wallFramesOf(frames) };
}

describe('A69 curves (columns) into the shared store', () => {
  it('reads the columns of every curve and keeps the roles (S9: the check stays a check)', () => {
    const { store, skipped, curves } = loaded({ n: 60, comps: 3 });
    expect(skipped).toEqual([]);
    expect(curves.curves).toHaveLength(5);
    const roles = [...store.stars.values()].map((s) => s.role);
    expect(roles).toEqual(['target', 'check', 'comparison', 'comparison', 'comparison']);
    const t = store.primary('target')!;
    expect(t.n).toBe(60);
    expect(t.filter).toBe('ir');
    expect(t.starKey).toBe('000-AAA-001');
    // Flags from the boolean columns.
    expect(t.cols.flags.subarray(0, t.n).filter((f) => f & FLAG_SATURATED).length).toBe(1);
    // The check takes its catalogue V from the targets (D10): check − V is drawn.
    expect(store.primary('check')!.catalogue).toBe(10.74);
  });

  it('refuses a column of the wrong length, and an answer without curves (atomic, 07 P13)', () => {
    expect(() => parseCurves({ curves: [{ key: 'a', role: 'target', points: { jd_utc: [1, 2], mag: [1] } }] })).toThrow(/a\.mag has 1 values for 2 times/);
    expect(() => parseCurves({ nothing: true })).toThrow(/no curves list/);
    expect(parseCurves([{ key: 'a', role: 'target', points: { jd_utc: [] } }]).curves).toHaveLength(1);
  });

  it('leaves out a curve whose role is unknown, and says so (never drawn as a target)', () => {
    const { store, skipped } = storeFromCurves({ curves: [{ key: 'x', role: 'mystery', csv: 'x.csv', points: { jd_utc: [2461346.5], mag: [10] } }] });
    expect(store.stars.size).toBe(0);
    expect(skipped[0]).toMatch(/x\.csv: role "mystery" unknown/);
  });

  it('S49: star keys across filters, the filters loaded, "Name [IR]" only with two filters', () => {
    expect(starKeyOf({ key: '000-BCG-719@ir', auid: '000-BCG-719', name: 'RR Lyr' })).toBe('000-BCG-719');
    expect(starKeyOf({ key: 'RR Lyr', auid: null, name: 'RR Lyr' })).toBe('RR Lyr');
    expect(curveFilters([{ filter: 'ir' }, { filter: null }, { filter: 'lp' }, { filter: 'ir' }])).toEqual(['ir', 'lp']);
    expect(seriesLabel('RR Lyr', 'ir', 1)).toBe('RR Lyr');
    expect(seriesLabel('RR Lyr', 'ir', 2)).toBe('RR Lyr [IR]');
    expect(seriesLabel('RR Lyr', 'irc', 2)).toBe('RR Lyr [IR-cut]');
    expect(seriesLabel('RR Lyr', null, 2)).toBe('RR Lyr');
  });

  it('reads a pre-0.5.0 session (no filter on the curves): every curve under any filter', () => {
    const { store } = loaded({ n: 30, legacy: true });
    expect(store.filters()).toEqual([]);
    expect(store.primary('target')!.key).toBe('000-AAA-001@'); // curve_key with no token (S49)
    expect(store.primary('target')!.starKey).toBe('000-AAA-001');
    expect(defaultCells(store, null).filter((c) => c.kind !== 'conditions')).toHaveLength(7);
  });
});

describe('vetting reports (S57)', () => {
  it('one per filter, a report without "filter" vets a one-filter run', () => {
    const two = parseQualityList([{ comparison_stars: [{ name: 'a', status: 'stable' }], filter: 'ir' }, { comparison_stars: [], filter: 'lp' }]);
    expect(qualityFor(two, 'lp')!.filter).toBe('lp');
    expect(qualityFor(two, 'v')).toBeNull();
    const legacy = parseQualityList({ comparison_stars: [{ name: 'a', status: 'noisy' }] });
    expect(qualityFor(legacy, 'ir')!.stars[0].status).toBe('noisy');
    expect(parseQuality(null)).toBeNull();
    expect(statusWord('insufficient_data')).toBe('Insufficient data');
  });

  it('A68 `quality`: the default report (its filter, else none: pre-0.5.0) and one per filter', () => {
    const rep = (filter?: string) => ({ selection_status: 'not_ready', comparison_stars: [{ name: 'a', auid: '000-A', status: 'stable', scatter_mag: 0.01 }], ...(filter ? { filter } : {}) });
    const legacy = parseQualityBlock({ default: rep(), default_filter: null, by_filter: {} });
    expect(legacy).toHaveLength(1);
    expect(legacy[0].filter).toBeNull();
    expect(qualityFor(legacy, 'ir')!.stars[0].scatter_mag).toBe(0.01); // one-filter run: it vets that filter
    const two = parseQualityBlock({ default: rep('ir'), default_filter: 'ir', by_filter: { lp: rep('lp') } });
    expect(two.map((r) => r.filter)).toEqual(['ir', 'lp']);
    expect(qualityFor(two, 'lp')!.filter).toBe('lp');
    // A per-filter file without the key takes its token from the file name (the server's key).
    expect(parseQualityBlock({ default: null, by_filter: { lp: rep() } })[0].filter).toBe('lp');
    expect(parseQualityBlock({ default: null, default_filter: null, by_filter: {} })).toEqual([]);
  });
});

describe('the wall model', () => {
  it('orders targets, Conditions beside them (WF-B, in the first screen), checks, comparisons; the layout reorders and hides', () => {
    const { store } = loaded({ n: 40, comps: 3 });
    const cells = defaultCells(store, 'ir');
    expect(cells.map((c) => c.kind)).toEqual(['target', 'conditions', 'check', 'comparison', 'comparison', 'comparison']);
    expect(cells[0].id).toBe('target:000-AAA-001');
    expect(cells[1].id).toBe(CONDITIONS_ID);
    const { shown, hidden } = arrange(cells, { order: ['comparison:000-AAA-101', 'target:000-AAA-001'], hidden: ['check:000-AAA-090'] });
    expect(shown.map((c) => c.id).slice(0, 2)).toEqual(['comparison:000-AAA-101', 'target:000-AAA-001']);
    expect(hidden.map((c) => c.id)).toEqual(['check:000-AAA-090']);
    expect(moveCell(shown, shown[1].id, -1).slice(0, 2)).toEqual(['target:000-AAA-001', 'comparison:000-AAA-101']);
    expect(moveCell(shown, shown[0].id, -1)).toEqual(shown.map((c) => c.id));
  });

  it('two filters: one set of cells per filter shown, labelled "Name [IR]"', () => {
    const { store } = loaded({ n: 40, comps: 2, filters: ['ir', 'lp'] });
    const ir = defaultCells(store, 'ir', { filtersLoaded: 2 });
    const lp = defaultCells(store, 'lp', { filtersLoaded: 2 });
    expect(ir[0].label).toBe('SW And [IR]');
    expect(lp[0].label).toBe('SW And [LP]');
    expect(ir[0].id).toBe(lp[0].id); // the layout follows the star across filters
    expect(ir[0].key).toBe('000-AAA-001@ir');
  });

  it('columns: 2, 3 with the rail collapsed from 1200 px; rows fill the height whole', () => {
    expect(wallColumns(928, true)).toBe(2);
    expect(wallColumns(1348, false)).toBe(3);
    expect(wallColumns(1100, false)).toBe(2);
    expect(wallColumns(400, true)).toBe(1);
    expect(rowHeight(716)).toBe(238); // 1440 × 900, rail open: three rows, six cells
    expect(rowHeight(512)).toBe(256);
    expect(rowHeight(150)).toBe(200);
  });

  it('ports the core scatter estimator (uncertainty.py) to the last digit', () => {
    const jd = Array.from({ length: 15 }, (_, i) => 2461346.0 + i * 0.001);
    const mag = Array.from({ length: 15 }, (_, i) => 10 + 0.01 * Math.sin(i * 1.7) + 0.003 * ((i * 7) % 5));
    // Python: estimate_lightcurve_scatter(zip(jd, mag)) = 0.011718824291862759
    expect(estimateScatter(jd, mag, 15)).toBeCloseTo(0.011718824291862759, 15);
    expect(robustSigma([1, 2, 3, 4, 100])).toBeCloseTo(1.4826, 12);
    expect(estimateScatter(jd, mag, 9)).toBeNull();
  });

  it('header numbers: the report for a vetted comparison, the check against its catalogue', () => {
    const { store, info, f } = loaded({ n: 120, comps: 3 });
    const report = qualityFor(parseQualityBlock(f.session.quality), 'ir');
    const comp = store.primary('comparison', '000-AAA-100@ir', 'ir')!;
    const st = cellStats(comp, report);
    expect(st.scatterFrom).toBe('report');
    expect(st.vetting!.status).toBe('stable');
    const chk = cellStats(store.primary('check')!, report);
    expect(chk.meanOffset).toBeGreaterThan(0.005);
    expect(chk.meanOffset).toBeLessThan(0.02);
    expect(chk.scatter).toBeGreaterThan(0.005);
    expect(info.chartId).toBe('X99999AA');
    // Without a report the estimate is computed here.
    expect(cellStats(comp, null).scatterFrom).toBe('estimate');
  });

  it('health lanes: gap, HFD episode, fewer comparisons, flags', () => {
    const { store, wall, extras } = loaded({ n: 100, comps: 4, gapAt: 50, gapS: 1800, hfdEpisodeAt: 20, missing: [3], zpOutlier: [60, 61] });
    const tgt = store.primary('target')!;
    const h = healthOf(wall, tgt, store.comparisons('ir').length, 1.5, extras.get(tgt.key) ?? null);
    expect(h.coverage).toHaveLength(2);
    expect(h.gaps).toHaveLength(1);
    expect(h.missing).toHaveLength(1);
    expect(h.hfd).toHaveLength(1);
    expect(h.fewComps.length).toBeGreaterThan(0);
    expect(h.suspect).toHaveLength(2);
    expect(h.saturated).toHaveLength(1);
    expect(h.lights).toBe(100);
    expect(h.flagged).toHaveLength(2);
    expect(h.flaggedBy).toEqual({ zp_outlier: 2 });
    // Fewer comparisons than the run's best frame (4), the tick as tall as the shortfall (2 of 4).
    expect(h.compsBest).toBe(4);
    expect(h.fewCompsDeficit.every((d) => d === 0.5)).toBe(true);
    const ex = wallExtent(store, 'ir', wall)!;
    expect(ex[1] - ex[0]).toBeGreaterThan(99 * 30);
  });

  it('Conditions airmass: the FITS header when given, else the photometry CSV, named', () => {
    const a = loaded({ n: 30, headerAirmass: true });
    expect(a.info.airmassSource).toBe('header');
    expect(a.info.siteNote).toMatch(/not where the telescope was/);
    const hdr = metricSeries(a.wall, 'airmass', a.store.primary('target'));
    expect(hdr.source).toBe('FITS header AIRMASS');
    const b = loaded({ n: 30 });
    expect(b.info.airmassSource).toBe('csv');
    const csv = metricSeries(b.wall, 'airmass', b.store.primary('target'));
    expect(csv.source).toMatch(/photometry CSV/);
    // The fixture's CSV airmass is 2x the header's (a wrong Settings site): the header wins.
    expect(csv.y[0]).toBeCloseTo(hdr.y[0], 3);
    expect(a.store.primary('target')!.cols.airmass[0]).toBeCloseTo(2 * hdr.y[0], 3);
    const hfd = metricSeries(b.wall, 'hfd', null);
    expect(hfd.n).toBe(30);
    // Mid-exposure: the header's (DATE-OBS + EXPTIME / 2), the curves' time.
    expect(hfd.x[0]).toBeCloseTo(b.store.primary('target')!.cols.t[0], 3); // JD → unix: 10 µs
    // A frame whose header was not read (missing FITS): its logged start + exposure / 2.
    const rows = frameRows([{ filename: 'a.fit', image_type: 'Light', exposure_s: 10, timestamp: '2026-11-01T20:00:00', header: null }]);
    expect(wallFramesOf(rows)[0].mid).toBe(Date.UTC(2026, 10, 1, 20, 0, 5) / 1000);
    const hdrMid = frameRows([{ filename: 'b.fit', image_type: 'Light', exposure_s: 10, timestamp: '2026-11-01T20:00:00', header: { mid_utc: '2026-11-01T20:00:06.500+00:00', airmass: 1.234 } }]);
    expect(wallFramesOf(hdrMid)[0]).toMatchObject({ mid: Date.UTC(2026, 10, 1, 20, 0, 6, 500) / 1000, airmass: 1.234 });
    expect(metricSeries(wallFramesOf(rows), 'temp', null).source).toMatch(/CCD-TEMP/);
  });

  it('copy data: full precision, the plotted value of a comparison is Δ from its own median', () => {
    const { store } = loaded({ n: 40, comps: 2 });
    const comp = store.primary('comparison')!;
    const { header, rows } = cellTsv(comp, 'mag');
    expect(header[3]).toBe('plotted');
    const med = magBaselineOf(comp);
    expect(Number(rows[0][3])).toBeCloseTo(comp.cols.mag[0] - med, 12);
    expect(rows[0][4]).toBe(String(comp.cols.mag[0]));
    expect(rows).toHaveLength(40);
    const text = toTsv(header, rows);
    expect(text.split('\n')).toHaveLength(42);
  });

  it('the cell menu says why a move is not possible; the metric menu checks the current one', () => {
    const first = cellMenu({ kind: 'target' }, 0, 7, false);
    expect(first.find((e) => 'id' in e && e.id === 'earlier')).toMatchObject({ disabledReason: 'Already the first plot' });
    expect(first.find((e) => 'id' in e && e.id === 'later')).toMatchObject({ disabledReason: null });
    const last = cellMenu({ kind: 'conditions' }, 6, 7, true);
    expect(last.find((e) => 'id' in e && e.id === 'expand')).toMatchObject({ label: 'Restore the wall' });
    expect(last.find((e) => 'id' in e && e.id === 'later')).toMatchObject({ disabledReason: 'Restore the wall first' });
    const m = metricMenu('airmass');
    expect(m.filter((e) => 'checked' in e && e.checked)).toHaveLength(1);
    expect(m.find((e) => 'id' in e && e.id === 'airmass')).toMatchObject({ checked: true });
  });

  it('the layout is remembered and validated', () => {
    const st = memory();
    expect(loadWallLayout(st)).toEqual({ order: [], hidden: [], metric: 'hfd' });
    saveWallLayout({ order: ['a'], hidden: ['b'], metric: 'sky' }, st);
    expect(loadWallLayout(st)).toEqual({ order: ['a'], hidden: ['b'], metric: 'sky' });
    expect(isWallLayout({ order: [], hidden: [], metric: 'nope' })).toBe(false);
    const l = new WallLayoutState(st);
    expect(l.metric).toBe('sky');
    l.setHidden('c', true);
    l.toggleExpand('c');
    expect(l.expanded).toBe('c');
    l.reset();
    expect(l.hidden).toEqual([]);
    expect(l.expanded).toBeNull();
    expect(loadWallLayout(st).metric).toBe('hfd');
  });
});

describe('the comparison facet (LightCurvePlot, Qt Review diagnostic)', () => {
  it('mag: leave-one-out mag minus its median of the unsaturated points; flux: f / baseline − 1', () => {
    const s = new LiveCurveStore();
    s.load({
      curves: [
        {
          key: 'c',
          role: 'comparison',
          points: [
            { jd_utc: 2461346.5, mag: 10, mag_err: 0.01, relative_flux: 1.0, relative_flux_err: 0.01 },
            { jd_utc: 2461346.51, mag: 10.02, mag_err: 0.01, relative_flux: 1.1, relative_flux_err: 0.01 },
            { jd_utc: 2461346.52, mag: 12, mag_err: 0.01, relative_flux: 9, saturated: true },
            { jd_utc: 2461346.53, mag: 10.04, mag_err: 0.01, relative_flux: 1.2, relative_flux_err: 0.01 },
          ],
        },
      ],
    });
    const d = facetData(s, 'comparison', 'mag', { comparison: 'c' })!;
    expect(Array.from(d.y)).toEqual([10 - 10.02, 0, 12 - 10.02, 10.04 - 10.02].map((v) => expect.closeTo(v, 12)));
    const fl = facetData(s, 'comparison', 'flux', { comparison: 'c' })!;
    expect(fl.y[1]).toBeCloseTo(0, 12);
    expect(fl.y[0]).toBeCloseTo(1 / 1.1 - 1, 12);
    expect(facetData(s, 'comparison', 'mag', { comparison: 'nope' })).not.toBeNull(); // the first comparison
    const r = readoutAt(s, unixFromJd(2461346.53), 'mag', { comparison: 'c' })!;
    expect(r.comparison!.value).toBe('+0.020 ± 0.010');
    expect(readoutAt(s, unixFromJd(2461346.53), 'mag', {})).toBeNull(); // a comparison is read only when asked
  });
});

describe('the rail cards', () => {
  it('Selected point: every star at that time, the frame it was measured on, Δt from its start', () => {
    const { store, frames } = loaded({ n: 40, comps: 2, missing: [5] });
    const t = store.primary('target')!.cols.t[10];
    const p = pointInfo(store, t, { filter: 'ir', frames, tol: 15 })!;
    expect(p.stars.map((s) => s.role)).toEqual(['target', 'check', 'comparison', 'comparison']);
    expect(p.frame!.filename).toMatch(/_00011\.fit$/);
    expect(p.dt).toBeCloseTo(5, 3);
    expect(p.frameReason).toBeNull();
    expect(p.bjd).toMatch(/^2461\d{3}\.\d{5}$/);
    const miss = pointInfo(store, store.primary('target')!.cols.t[5], { filter: 'ir', frames, tol: 15 })!;
    expect(miss.frameReason).toMatch(/File not found: .*_00006\.fit/);
    expect(pointInfo(store, 0, { filter: 'ir', frames })).toBeNull();
    expect(pointInfo(store, t, { filter: 'ir', frames: [], imported: true, tol: 15 })!.frameReason).toMatch(/imported/);
  });

  it('Selected point: the header airmass when the Settings site was wrong (A68), the recorder flags in words', () => {
    const { store, frames, extras, info } = loaded({ n: 40, comps: 2, headerAirmass: true, zpOutlier: [12] });
    const tgt = store.primary('target')!;
    const p = pointInfo(store, tgt.cols.t[12], { filter: 'ir', frames, tol: 15, extras, airmassSource: info.airmassSource })!;
    expect(p.airmassFrom).toBe('header');
    const hdr = extras.get(tgt.key)!.headerAirmass[extraRow(extras.get(tgt.key), tgt.cols.t[12])];
    expect(p.airmass).toBe(hdr.toFixed(3));
    expect(Number(p.airmassOther)).toBeCloseTo(2 * hdr, 2); // the CSV's (wrong site), said beside it
    expect(p.flags).toBe('ZP outlier');
    expect(p.stars.every((s) => s.flags.includes('ZP outlier'))).toBe(true);
    // A run whose site was right: the CSV's airmass (the AAVSO AMASS).
    const ok = loaded({ n: 40, comps: 2 });
    const q = pointInfo(ok.store, ok.store.primary('target')!.cols.t[3], { filter: 'ir', frames: ok.frames, tol: 15, extras: ok.extras, airmassSource: 'csv' })!;
    expect(q.airmassFrom).toBe('csv');
    expect(q.airmassOther).toBeNull();
    expect(flagWord('low_snr')).toBe('low SNR');
    expect(flagWord('new_code')).toBe('new code');
  });

  it('Ensemble rows: the report of the filter, a status word, the catalogue magnitude', () => {
    const { store, f, info } = loaded({ n: 60, comps: 3 });
    const report = qualityFor(parseQualityBlock(f.session.quality), 'ir');
    const rows = ensembleRows(store, 'ir', report, info.targets, 'TG');
    expect(rows).toHaveLength(3);
    expect(rows[0].status).toBe('Stable');
    expect(rows[0].catMag).toBeCloseTo(9.93, 6);
    expect(ensembleRows(store, 'ir', null)[0].status).toBe('—');
  });

  it('AAVSO pre-checks: observer code required, target curves only, flagged points left out', () => {
    const { store, info } = loaded({ n: 60, comps: 2 });
    const ok = aavsoChecks({ store, filter: 'ir', filters: ['ir'], obscode: 'XYZ', band: 'TG', frameFilters: info.filters, chartId: info.chartId });
    expect(ok.blocked).toBeNull();
    expect(ok.rows).toBe(57); // 60 − 2 suspect − 1 saturated
    expect(ok.checks.find((c) => c.id === 'excluded')!.value).toBe('1 saturated · 2 suspect');
    expect(ok.checks.find((c) => c.id === 'amass')).toBeUndefined();
    // The card says what the dialog warns about: a wrong-site AMASS (design review).
    const wrongSite = aavsoChecks({ store, filter: 'ir', filters: ['ir'], obscode: 'XYZ', band: 'TG', frameFilters: info.filters, chartId: info.chartId, airmassWrong: true });
    expect(wrongSite.checks.find((c) => c.id === 'amass')).toMatchObject({ level: 'warn', value: 'wrong site' });
    const noCode = aavsoChecks({ store, filter: 'ir', filters: ['ir'], obscode: '  ', band: 'TG', frameFilters: {}, chartId: null });
    expect(noCode.blocked).toMatch(/observer code/);
    // Q-R2: Qt's placeholder "XXX" is no observer code either.
    expect(aavsoChecks({ store, filter: 'ir', filters: ['ir'], obscode: 'xxx', band: 'TG', frameFilters: {}, chartId: null }).blocked).toMatch(/observer code/);
    // S60: a point dated JD 0 (a pre-0.5.0 batch re-run) is left out, counted apart; no magnitude error: left out.
    const odd = new LiveCurveStore();
    odd.load({
      curves: [
        {
          key: 't',
          role: 'target',
          points: [
            { jd_utc: 0, mag: 10, mag_err: 0.01 },
            { jd_utc: 2461346.5, mag: 10, mag_err: null },
            { jd_utc: 2461346.51, mag: 10, mag_err: 0.01 },
          ],
        },
      ],
    });
    const oc = aavsoChecks({ store: odd, filter: null, filters: [], obscode: 'XYZ', band: 'TG', frameFilters: {}, chartId: null });
    expect(oc.rows).toBe(1);
    expect(oc.checks.find((c) => c.id === 'excluded')!.value).toBe('1 without a magnitude · 1 undated');
    const noTarget = new LiveCurveStore();
    noTarget.load({ curves: [{ key: 'c', role: 'comparison', points: [{ jd_utc: 2461346.5, mag: 10, mag_err: 0.01 }] }] });
    expect(aavsoChecks({ store: noTarget, filter: null, filters: [], obscode: 'XYZ', band: 'TG', frameFilters: {}, chartId: null }).blocked).toMatch(/No target-role curve/);
    const two = loaded({ n: 40, filters: ['ir', 'lp'] });
    const lp = aavsoChecks({ store: two.store, filter: 'lp', filters: ['ir', 'lp'], obscode: 'XYZ', band: 'TG', frameFilters: two.info.filters, chartId: null });
    expect(lp.checks.find((c) => c.id === 'filter')!.value).toMatch(/^LP · one filter per file/);
    expect(lp.rows).toBe(20); // the LP half of the frames; the fixture's flagged rows are all IR
    expect(lp.checks.some((c) => c.id === 'excluded')).toBe(false);
    expect(aavsoChecks({ store: two.store, filter: 'ir', filters: ['ir', 'lp'], obscode: 'XYZ', band: 'TG', frameFilters: two.info.filters, chartId: null }).rows).toBe(17);
  });
});

describe('ReviewSource (A68 + A69, atomic) and the link', () => {
  it('opens a session, then keeps it when the next one fails', async () => {
    const src = new ReviewSource();
    const f = makeSession({ n: 50, comps: 2 });
    await src.open(fixtureLoader(f), f.path);
    expect(src.status).toBe('ready');
    expect(src.kind).toBe('session');
    expect(src.frames).toHaveLength(50);
    expect(src.filters).toEqual(['ir']);
    expect(src.report()!.stars).toHaveLength(2);
    expect(src.info!.issues[0]).toMatch(/^Missing FITS frame: SW_And_ir_light_.*_00004\.fit$/);
    expect(src.info!.readiness).toBe('warnings');
    expect(src.info!.filters).toEqual({ IR: 50 });
    expect(src.info!.chartId).toBe('X99999AA');
    expect(src.ref()).toEqual({ kind: 'session', path: f.path });
    expect(src.curveRefs()[0]).toEqual({ key: '000-AAA-001@ir', role: 'target', name: 'SW And', filter: 'ir', n: 50, exportable: true, problem: null });
    expect(src.wallFrames()[0].mid).toBeCloseTo(src.store.primary('target')!.cols.t[0], 3);
    const before = src.store;
    await expect(src.open({ session: async () => f.session, curves: async () => ({ curves: [{ key: 'x' }] }) }, '/bad')).rejects.toThrow();
    expect(src.store).toBe(before);
    expect(src.status).toBe('ready');
    expect(src.error).toMatch(/x has no jd_utc/);
    src.link.select(123);
    src.close();
    expect(src.link.selection.t).toBeNull();
    expect(src.store.stars.size).toBe(0);
  });

  it('imports a CSV as a pseudo-session without frames; reviews the live store read-only', () => {
    const src = new ReviewSource();
    const f = makeSession({ n: 20, comps: 1 });
    src.openImport({ ...f.curves, object_name: 'SW And' }, '/tmp/target_SW_And.csv');
    expect(src.kind).toBe('import');
    expect(src.frames).toEqual([]);
    expect(src.info!.folder).toBe('target_SW_And.csv');
    expect(src.ref()).toEqual({ kind: 'import', path: '/tmp/target_SW_And.csv' });
    const live = new LiveCurveStore();
    src.openLive(live, { object: 'SW And' });
    expect(src.store).toBe(live);
    live.load({ curves: [{ key: 't', role: 'target', points: [{ jd_utc: 2461346.5, mag: 10, mag_err: 0.01 }] }] });
    expect(src.version).toBe(live.version);
    expect(src.ref()).toEqual({ kind: 'live' });
    expect(src.curveRefs()).toEqual([{ key: 't', role: 'target', name: 't', filter: '', n: 1 }]);
  });

  it('CurveLink: one zoom and one selected time, every listener told', () => {
    let ext: [number, number] | null = [0, 1000];
    const heard: string[] = [];
    const link = new CurveLink({ extent: () => ext, minSpan: 10, reducedMotion: () => true, onChange: (m) => heard.push(m) });
    link.onZoom((m) => heard.push(`plot:${m}`));
    link.zoom.update();
    link.zoom.setUser(100, 200);
    expect(link.mode).toBe('manual');
    expect(link.view).toEqual([100, 200]);
    expect(heard).toEqual(['manual', 'plot:manual']);
    link.select(150);
    expect(link.selection.t).toBe(150);
    link.reset();
    expect(link.selection.t).toBeNull();
    ext = null;
    expect(link.zoom.update()).toBeNull();
  });
});

describe('export hooks (charts/export.ts)', () => {
  it('TSV keeps its columns: tabs and line breaks inside a value become one space', () => {
    expect(toTsv(['a', 'b'], [['x\ty', 1], ['p\r\nq', 2.5]])).toBe('a\tb\nx y\t1\np q\t2.5\n');
  });
  it('file stems: letters, digits, dot, dash, underscore; never empty', () => {
    expect(fileStem('XX Cyg', 'target', '2026-09-07')).toBe('XX_Cyg_target_2026-09-07');
    expect(fileStem('Étoile [IR]', null, '')).toBe('Etoile_IR');
    expect(fileStem('', '  ')).toBe('plot');
  });
});

describe('W7 review fixes', () => {
  it('names the session.json summary keys with units, the frame counts left to the Lights row', () => {
    const rows = summaryRows({ frame_count: 195, light_count: 195, mean_hfd: 10.403, mean_fwhm: 2.168, mean_sky_adu: 1178.349, mean_star_count: 2896.441, other: 1 });
    expect(rows.filter((r) => r.known).map((r) => [r.label, r.value])).toEqual([
      ['Mean HFD', `10.40 px`],
      ['Mean FWHM', `2.17 px`],
      ['Mean sky', `1 178 ADU`],
      ['Mean stars', `2 896`],
    ]);
    expect(rows.filter((r) => !r.known)).toEqual([{ label: 'other', value: '1', known: false }]);
  });

  it('ranges a wall cell on its good points: flagged and suspect frames become edge chevrons', () => {
    const n = 100;
    const x = new Float64Array(n).map((_, i) => i);
    const y = new Float64Array(n).map((_, i) => 7.3 + 0.004 * (i % 10));
    const flags = new Uint8Array(n);
    y[52] = 6.26;
    flags[52] = FLAG_RECORDER;
    y[80] = 8.9;
    flags[80] = FLAG_SUSPECT;
    const [lo, hi] = robustExtent({ n, x, y, err: null, flags, band: null }, 0, n)!;
    expect(lo).toBeGreaterThanOrEqual(7.3);
    expect(hi).toBeLessThanOrEqual(7.34);
  });
});

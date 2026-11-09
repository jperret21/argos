import { describe, expect, it } from 'vitest';
import type { TargetStar } from '../field/types';
import { PhotometryStore, type CurveSink } from './photometry.svelte';
import { LiveCurveStore } from '../../charts/lightcurve/store';
import {
  brightestOf,
  catalogV,
  comparisonSplit,
  countLine,
  curveFor,
  ensembleRows,
  ensembleTsv,
  ENSEMBLE_TSV_HEADERS,
  filterVariables,
  latestMag,
  statusLabel,
  statusLine,
  trailingStats,
  variablesCount,
  verdict,
} from './present';
import type { Curve, FieldVariable, LcPoint, QualityReport } from './types';

const pt = (jd: number, mag: number | null, extra: Partial<LcPoint> = {}): LcPoint => ({
  jd_utc: jd,
  bjd_tdb: null,
  mag,
  mag_err: 0.01,
  formal_mag_err: 0.01,
  sigma_syst: null,
  airmass: null,
  fwhm: 3,
  sky_adu: 100,
  comps_used: 4,
  relative_flux: 1,
  relative_flux_err: 0.01,
  relative_comps_used: 4,
  saturated: false,
  suspect: false,
  ...extra,
});

const star = (over: Partial<TargetStar>): TargetStar =>
  ({ key: 'k', role: 'comparison', name: 'S', display_name: 'S', ra_deg: 300, dec_deg: 58, ra_hours: 20, auid: null, source: 'vsp', mags: { V: 11, B: 11.5 }, chart_id: 'X1', note: '', x: 10, y: 20, ...over }) as TargetStar;

const snapshot = (over: Record<string, unknown> = {}) => ({
  object_name: 'XX Cyg',
  run_root: null,
  sequence_running: false,
  band: 'TG',
  obscode: 'ABC',
  chart_id: 'X1',
  site_set: true,
  geometry: { aperture_px: 6, annulus_in_px: 8, annulus_out_px: 12, fwhm_px: 3, fwhm_source: 'frame', series_fwhm_px: 3.1 },
  curves: [{ key: 'XX Cyg', star_key: 'auid:T', role: 'target', name: 'XX Cyg', auid: 'T', mags: {}, catalogue_v: null, sigma_syst: null, points: [pt(1, 11.5), pt(2, 11.6)] }],
  quality: null,
  status: { state: 'measured', reason: null, message: null, frames: 2, points: 2, last: null },
  revision: 1,
  seq: 2,
  ...over,
});

function client(routes: Record<string, unknown>) {
  const calls: [string, string, unknown][] = [];
  return {
    calls,
    async request<T>(method: string, path: string, body?: unknown): Promise<T> {
      calls.push([method, path, body]);
      const r = routes[`${method} ${path}`];
      if (r instanceof Error) throw r;
      return r as T;
    },
  };
}

const ev = (seq: number, index: number, mag: number, over: Record<string, unknown> = {}) => ({
  type: 'photometry_point',
  seq,
  revision: 1,
  frame_seq: 10 + seq,
  key: 'XX Cyg',
  star_key: 'auid:T',
  role: 'target',
  name: 'XX Cyg',
  auid: 'T',
  index,
  point: pt(seq, mag),
  sigma_syst: null,
  ...over,
});

describe('PhotometryStore (A54-A57 stream)', () => {
  it('appends points in order and drops what the snapshot already holds', () => {
    const s = new PhotometryStore();
    expect(s.ingest('snapshot', snapshot())).toBe(true);
    expect(s.curves[0].points.length).toBe(2);
    expect(s.ingest('photometry_point', ev(2, 1, 11.6))).toBe(false); // seq 2 is in the snapshot
    expect(s.ingest('photometry_point', ev(3, 2, 11.7))).toBe(true);
    expect(s.curves[0].points.map((p) => p.mag)).toEqual([11.5, 11.6, 11.7]);
    expect(s.seq).toBe(3);
  });

  it('reads the snapshot again on a gap, a foreign revision or an index that does not follow', async () => {
    const cases = [ev(5, 2, 11.7), ev(3, 5, 11.7), ev(3, 2, 11.7, { revision: 2 })]; // seq 3-4 missed; index 5 of 2; a reset missed
    for (const e of cases) {
      const c = client({ 'GET /api/photometry/live': snapshot({ seq: 9, curves: [] }) });
      const s = new PhotometryStore();
      s.attach({ on: () => () => undefined }, c);
      s.ingest('snapshot', snapshot());
      expect(s.ingest('photometry_point', e)).toBe(false);
      expect(s.refetches).toBe(1);
      await new Promise((r) => setTimeout(r, 0));
      expect(c.calls.filter((x) => x[1] === '/api/photometry/live').length).toBe(1);
      expect(s.seq).toBe(9);
    }
  });

  it('gives every earlier point hypot(formal, floor) when a point moves the floor (S19), with the Python bits', () => {
    const s = new PhotometryStore();
    s.ingest('snapshot', snapshot());
    // The server's values: math.hypot(0.01, 0.02) in Python is 0.022360679774997897.
    const point = pt(3, 11.7, { mag_err: 0.022360679774997897, sigma_syst: 0.02 });
    s.ingest('photometry_point', ev(3, 2, 11.7, { point, sigma_syst: 0.02 }));
    const pts = s.curves[0].points;
    expect(pts.map((p) => p.mag_err)).toEqual([0.022360679774997897, 0.022360679774997897, 0.022360679774997897]);
    expect(pts.every((p) => p.sigma_syst === 0.02)).toBe(true);
    expect(s.curves[0].sigma_syst).toBe(0.02);
  });

  it('keeps a ratio-only point (mag null, S18) without a floor on it', () => {
    const s = new PhotometryStore();
    s.ingest('snapshot', snapshot());
    s.ingest('photometry_point', ev(3, 2, 0, { point: { ...pt(3, null), mag: null, mag_err: null }, sigma_syst: 0.02 }));
    const p = s.curves[0].points[2];
    expect(p.mag).toBeNull();
    expect(p.sigma_syst).toBeNull();
    expect(latestMag(s.curves[0])?.mag).toBe(11.6);
  });

  it('clears on a reset and re-reads the snapshot; the quality follows its event', async () => {
    const c = client({ 'GET /api/photometry/live': snapshot({ revision: 2, seq: 4, curves: [] }) });
    const s = new PhotometryStore();
    s.attach({ on: () => () => undefined }, c);
    s.ingest('snapshot', snapshot());
    const q: QualityReport = { selection_status: 'not_ready', scientific_note: 'n', criteria: { min_points: 10, max_scatter_mag: 0.1, max_formal_error_mag: 0.1 }, comparison_stars: [] };
    expect(s.ingest('comparison_quality', { type: 'comparison_quality', revision: 1, frame_seq: 3, report: q })).toBe(true);
    expect(s.quality?.selection_status).toBe('not_ready');
    s.ingest('photometry_reset', { type: 'photometry_reset', seq: 3, revision: 2, reason: 'object_changed' });
    expect(s.curves).toEqual([]);
    expect(s.quality).toBeNull();
    await new Promise((r) => setTimeout(r, 0));
    expect(s.revision).toBe(2);
    expect(s.seq).toBe(4);
    expect(s.ingest('comparison_quality', { type: 'comparison_quality', revision: 2, frame_seq: null, report: null })).toBe(true);
    expect(s.quality).toBeNull();
  });

  it('ignores a snapshot older than the points it already applied', () => {
    const s = new PhotometryStore();
    s.ingest('snapshot', snapshot());
    s.ingest('photometry_point', ev(3, 2, 11.7));
    expect(s.ingest('snapshot', snapshot())).toBe(false);
    expect(s.curves[0].points.length).toBe(3);
  });

  it('feeds the plot store: the held state first, then each applied point without its revision', () => {
    const s = new PhotometryStore();
    s.ingest('snapshot', snapshot());
    const got: string[] = [];
    const sink: CurveSink = {
      load: (snap) => got.push(`load ${snap.curves[0]?.points.length ?? 0}`),
      apply: (e) => got.push(`apply ${e.index} rev ${String(e.revision)}`),
      reset: () => got.push('reset'),
    };
    const off = s.feed(sink);
    s.ingest('photometry_point', ev(3, 2, 11.7));
    s.ingest('photometry_point', ev(3, 2, 11.7)); // duplicate: not forwarded
    off();
    s.ingest('photometry_point', ev(4, 3, 11.8));
    expect(got).toEqual(['load 2', 'apply 2 rev undefined']);
  });

  it('keeps the plot store in step: a late feed and a reset carry the stream position held', () => {
    const s = new PhotometryStore();
    s.ingest('snapshot', snapshot());
    s.ingest('photometry_point', ev(3, 2, 11.7));
    // The plot mounts after a point: its store starts at seq 3, so seq 4 is not a gap.
    const plot = new LiveCurveStore();
    s.feed({ load: (snap) => plot.load(snap), apply: (e) => plot.apply(e), reset: (e) => plot.reset(e) });
    expect(plot.seq).toBe(3);
    s.ingest('photometry_point', ev(4, 3, 11.8));
    expect(plot.primary('target')!.n).toBe(4);
    // A reset (object changed), then the new curve's first point.
    s.ingest('photometry_reset', { type: 'photometry_reset', seq: 5, revision: 2, reason: 'object_changed' });
    expect(plot.stars.size).toBe(0);
    s.ingest('photometry_point', ev(6, 0, 12.1, { revision: 2 }));
    expect(plot.primary('target')!.n).toBe(1);
    expect(plot.seq).toBe(6);
  });

  it('reloads a plot store that answers gap rather than leave it frozen', async () => {
    const c = client({ 'GET /api/photometry/live': snapshot({ seq: 3, curves: [] }) });
    const s = new PhotometryStore();
    s.attach({ on: () => () => undefined }, c);
    s.ingest('snapshot', snapshot());
    const loads: number[] = [];
    s.feed({ load: (snap) => loads.push(snap.seq ?? -1), apply: () => 'gap', reset: () => undefined });
    expect(s.ingest('photometry_point', ev(3, 2, 11.7))).toBe(true);
    expect(s.refetches).toBe(1);
    await new Promise((r) => setTimeout(r, 0));
    expect(loads).toEqual([2, 3]); // the held state, then the snapshot read again
  });

  it('reads the field variables (A50) and posts a recommendation (A58)', async () => {
    const rows = [{ index: 0, name: 'XX Cyg', var_type: 'HADS', mag_text: '11.2 – 12.1 V', brightest_mag: 11.2, period_d: 0.134865, sep_arcmin: 1.2, in_set_role: 'target', suspected: false, auid: 'T', key: 'auid:T', x: 5, y: 6 }];
    const c = client({
      'GET /api/field/variables': { available: true, generation: 3, rows },
      'POST /api/photometry/comparisons/recommend': { added: 2, removed: [], comparisons: [], targets: null },
    });
    const s = new PhotometryStore();
    s.attach({ on: () => () => undefined }, c);
    await s.reloadVariables();
    expect(s.variables?.rows[0].in_set_role).toBe('target');
    const r = await s.recommend('complete', 6.2);
    expect(r.added).toBe(2);
    expect(c.calls.at(-1)).toEqual(['POST', '/api/photometry/comparisons/recommend', { mode: 'complete', count: 6 }]);
  });
});

describe('present (Qt texts, D10)', () => {
  it('words the verdict as Qt does, with the counts', () => {
    const q = (status: string): QualityReport => ({
      selection_status: status,
      scientific_note: 'Leave-one-out live-preview assessment only.',
      criteria: { min_points: 10, max_scatter_mag: 0.1, max_formal_error_mag: 0.1 },
      comparison_stars: [
        { name: 'A', auid: 'A', n_valid: 12, scatter_mag: 0.01, median_formal_error_mag: 0.01, status: 'stable' },
        { name: 'B', auid: 'B', n_valid: 12, scatter_mag: 0.2, median_formal_error_mag: 0.01, status: 'unstable' },
      ],
    });
    expect(verdict(q('live_preview_consistent'))?.words).toBe('consistent in live preview');
    expect(verdict(q('not_ready'))?.line).toBe('Ensemble: not ready: fewer than 3 stable comparisons. Leave-one-out live-preview assessment only.');
    expect(verdict(q('insufficient_data'))?.counts).toBe('1 of 2 stable');
    expect(verdict(null)).toBeNull();
    expect(statusLabel('insufficient_data', 10)).toBe('Waiting for 10 points');
    expect(statusLabel('noisy')).toBe('Noisy');
  });

  it('keeps Qt\'s count line word for word', () => {
    expect(countLine([])).toBe('No comparison stars — refresh the catalogue after a successful solve.');
    expect(countLine([star({ key: 'a' }), star({ key: 'b', mags: {}, source: 'manual' })])).toBe('1 calibrated comparison(s) · 1 uncalibrated manual star(s)');
    expect(countLine([star({ key: 'a' })])).toBe('1 calibrated comparison star(s)');
    expect(comparisonSplit([star({ key: 'a' }), star({ key: 'b', source: 'manual', mags: {}, chart_id: null })]).text).toBe('2 (VSP 1, manual 1)');
  });

  it('computes the check star\'s trailing statistics on check − catalogue V, unsaturated points only', () => {
    const c: Curve = { key: 'C', star_key: 'auid:C', role: 'check', name: 'C', auid: 'C', catalogue_v: 10, sigma_syst: null, points: [] };
    for (let i = 0; i < 20; i++) c.points.push(pt(i, 10 + (i % 2 ? 0.01 : -0.01)));
    c.points.push(pt(21, 13, { saturated: true }));
    const st = trailingStats(c, catalogV(null, c) ?? 0);
    expect(st.n).toBe(15);
    // The last 15 unsaturated points (i = 5..19): 8 at +0.01, 7 at −0.01; the saturated one is left out.
    expect(st.mean).toBeCloseTo(0.01 / 15, 12);
    const m = 0.01 / 15;
    expect(st.sd).toBeCloseTo(Math.sqrt((8 * (0.01 - m) ** 2 + 7 * (0.01 + m) ** 2) / 14), 12);
    // Two points: no σ, as the plot's band claims none under 3 (one rule for card and plot).
    const two: Curve = { ...c, points: c.points.slice(0, 2) };
    expect(trailingStats(two, 10).sd).toBeNull();
    expect(trailingStats({ ...c, points: c.points.slice(0, 3) }, 10).sd).not.toBeNull();
  });

  it('finds a star\'s curve by its set key, else by Qt\'s key (AUID, else the name)', () => {
    const curves: Curve[] = [
      { key: '000-AAA', star_key: null, role: 'comparison', name: '000-AAA', auid: '000-AAA', catalogue_v: 11, sigma_syst: null, points: [] },
      { key: 'XX Cyg', star_key: 'pos:1,2', role: 'target', name: 'XX Cyg', auid: null, catalogue_v: null, sigma_syst: null, points: [] },
    ];
    expect(curveFor(curves, star({ key: 'auid:000-AAA', auid: '000-AAA' }))?.key).toBe('000-AAA');
    expect(curveFor(curves, star({ key: 'pos:1,2', auid: null, display_name: 'other' }))?.key).toBe('XX Cyg');
  });

  it('builds the ensemble rows: report entry, leave-one-out residual, field flags, check last', () => {
    const stars = [star({ key: 'auid:C', auid: 'C', display_name: 'C', role: 'check' }), star({ key: 'auid:A', auid: 'A', display_name: 'A', mags: { V: 11, B: 11.6 } }), star({ key: 't', role: 'target' })];
    const q: QualityReport = {
      selection_status: 'insufficient_data',
      scientific_note: '',
      criteria: { min_points: 10, max_scatter_mag: 0.1, max_formal_error_mag: 0.1 },
      comparison_stars: [{ name: 'A', auid: 'A', n_valid: 4, scatter_mag: null, median_formal_error_mag: 0.012, status: 'insufficient_data', star_key: 'auid:A', last: { mag: 11.023, mag_err: 0.012, comps_used: 3, jd_utc: 5 } }],
    };
    const rows = ensembleRows(stars, q, { flagsOf: (s) => (s.key === 'auid:A' ? ['variable?'] : []), lastJd: 5 });
    expect(rows.map((r) => r.key)).toEqual(['auid:A', 'auid:C']);
    expect(rows[0]).toMatchObject({ label: 'Waiting for 10 points', n: 4, flags: ['variable?'], onLastFrame: true });
    expect(rows[0].bv).toBeCloseTo(0.6, 10);
    expect(rows[0].residual).toBeCloseTo(0.023, 10);
    expect(rows[1].label).toBe('Check star');
    const tsv = ensembleTsv(rows, { ra: () => 'RA', dec: () => 'DEC' }).split('\n');
    expect(tsv[0].split('\t').slice(0, 10)).toEqual(['Name', 'AUID', 'RA (J2000)', 'Dec (J2000)', 'Catalogue mags', 'Source', 'Samples', 'Scatter (mag)', 'Formal error (mag)', 'Live status']);
    expect(tsv[0].split('\t').length).toBe(ENSEMBLE_TSV_HEADERS.length);
    expect(tsv[1].split('\t')[8]).toBe('0.0120');
  });

  it('filters the variables as Qt does (normalised designation or type, brightest magnitude)', () => {
    const v = (name: string, mag_text: string | null, var_type = 'EW'): FieldVariable =>
      ({ index: 0, name, var_type, mag_text, brightest_mag: brightestOf(mag_text), period_d: null, sep_arcmin: null, in_set_role: null, suspected: false, auid: null, key: name, x: null, y: null }) as FieldVariable;
    const rows = [v('XX Cyg', '11.2 – 12.1 V', 'HADS'), v('V1234 Cyg', '14.0 – 14.5 V'), v('NSV 1', null)];
    expect(filterVariables(rows, 'xxcyg', null).map((r) => r.name)).toEqual(['XX Cyg']);
    expect(filterVariables(rows, 'hads', null).map((r) => r.name)).toEqual(['XX Cyg']);
    expect(filterVariables(rows, '', 12).map((r) => r.name)).toEqual(['XX Cyg']);
    expect(filterVariables(rows, '', 0).length).toBe(3);
    expect(variablesCount(1, 3)).toBe('1 of 3 stars');
    expect(variablesCount(0, 1)).toBe('0 of 1 star');
  });

  it('says the live state in the spec\'s words', () => {
    const base = { status: null, connected: true, solved: true, hasTarget: true, comparisons: 4, points: 0 };
    expect(statusLine({ ...base, hasTarget: false }).text).toBe('No target');
    // A target set after the last solution: the stale `off` status does not hide it.
    const off = { state: 'off', reason: 'no_target', message: 'No target star', frames: 0, points: 0, last: null };
    expect(statusLine({ ...base, status: off }).text).toBe('Measuring: no point yet; the next solution measures the set.');
    expect(statusLine({ ...base, solved: false }).text).toBe('Waiting for a solved full-resolution frame.');
    expect(statusLine({ ...base, comparisons: 0 }).text).toBe('No comparison stars — refresh the catalogue after a successful solve.');
    expect(statusLine({ ...base, points: 3 }).text).toBe('Measuring: 3 points, uncertainty floor after 10.');
    expect(statusLine({ ...base, points: 12 }).text).toBe('Measuring: 12 points.');
    const skipped = { state: 'skipped', reason: 'no_epoch', message: 'Photometry skipped: the frame has no exposure time (DATE-OBS/EXPTIME).', frames: 1, points: 0, last: null };
    expect(statusLine({ ...base, status: skipped }).text).toBe('Photometry skipped: the frame has no exposure time (DATE-OBS/EXPTIME).');
  });
});

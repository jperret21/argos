import { describe, expect, it } from 'vitest';
import {
  aavsoBody,
  bandReason,
  csvBlock,
  csvBody,
  csvCountText,
  csvCurves,
  csvDefaultName,
  curvesIn,
  excludedText,
  exportBlock,
  exportTarget,
  filterName,
  filtersOf,
  initialFilter,
  isAbsolute,
  joinPath,
  otherNotes,
  rowsText,
  UNCALIBRATED_NOTE,
  type CurveRef,
} from './aavso';
import { parseAavsoPreview, parseExportResult, parseRerunPlan, parseRerunResult, parseSource, ReviewExportApi, type AavsoPreview, type ReviewRequest } from './api';
import { apertureLine, checkRmsLines, framesLine, paramsLine, rerunBlock, rerunBody, rerunResultText, starsLine, trackingText } from './rerun';

const NNBSP = '\u202f';
const SRC = { kind: 'session', path: '/data/sessions/20260925T200453Z_SW_And' } as const;

const C = (key: string, role: string, filter: string, n = 100, extra: Partial<CurveRef> = {}): CurveRef => ({ key, role, name: key.split('@')[0], filter, n, ...extra });

/** Two filters (S49 keys), a check in each, comparisons. */
const TWO: CurveRef[] = [
  C('000-AAA-001@b', 'target', 'b'),
  C('000-AAA-001@v', 'target', 'v'),
  C('000-AAA-002@b', 'check', 'b'),
  C('000-AAA-002@v', 'check', 'v'),
  C('000-AAA-003@b', 'comparison', 'b'),
  C('000-AAA-003@v', 'comparison', 'v'),
];
/** A pre-0.5.0 session: no filter token on any curve. */
const LEGACY: CurveRef[] = [C('SW And@', 'target', ''), C('000-AAA-002@', 'check', ''), C('000-AAA-003@', 'comparison', '', 0)];

const PREVIEW_RAW = {
  source: SRC,
  object: 'SW And',
  obscode: 'XYZ',
  obscode_set: true,
  band: 'TG',
  band_source: 'settings',
  filter: 'ir',
  filters: ['ir'],
  band_note: null,
  chart: 'X12345AB',
  chart_source: 'targets',
  check: { key: '000-AAA-002@ir', name: 'Check', kname: '000-AAA-002', points: 183, kmag_rows: 181 },
  targets: [{ key: '000-AAA-001@ir', name: 'SW And', points: 183, rows: 178, saturated: 1, suspect: 2, nonfinite: 1, undated: 1 }],
  rows: 178,
  excluded: { saturated: 1, suspect: 2, nonfinite: 1, undated: 1 },
  airmass: { source: 'csv', state: 'mismatch', message: 'The site in Settings was wrong.' },
  notes: ['2 suspect points left out'],
  refusal: null,
  head: '#TYPE=EXTENDED\n#OBSCODE=XYZ\n',
  default_path: '/data/sessions/x/SW_And_ir_aavso.txt',
};

describe('AAVSO and CSV dialogs: filters (S53, S61)', () => {
  it('lists the target and check filters in curve order, "" left out', () => {
    expect(filtersOf(TWO)).toEqual(['b', 'v']);
    expect(filtersOf(LEGACY)).toEqual([]);
    expect(filtersOf([C('a@ir', 'comparison', 'ir')])).toEqual([]);
    expect(filtersOf([C('a@ir', 'comparison', 'ir')], ['comparison'])).toEqual(['ir']);
  });

  it('starts on the only filter, else lets the observer choose', () => {
    expect(initialFilter(['ir'])).toBe('ir');
    expect(initialFilter(['b', 'v'])).toBeNull();
    expect(initialFilter([])).toBeNull();
  });

  it('keeps one filter’s curves of a role; a legacy curve counts when there is one filter at most', () => {
    expect(curvesIn(TWO, 'target', 'v').map((c) => c.key)).toEqual(['000-AAA-001@v']);
    expect(curvesIn(TWO, 'check', 'b').map((c) => c.key)).toEqual(['000-AAA-002@b']);
    expect(curvesIn(LEGACY, 'target', null).map((c) => c.key)).toEqual(['SW And@']);
    // Several filters and none chosen yet: nothing listed (the observer chooses first, S53).
    expect(curvesIn(TWO, 'target', null)).toEqual([]);
    const mixed = [C('t@', 'target', ''), C('t@b', 'target', 'b'), C('t@v', 'target', 'v')];
    expect(curvesIn(mixed, 'target', 'b').map((c) => c.key)).toEqual(['t@b']);
  });

  it('names a filter for the labels', () => {
    expect(filterName(null)).toBe('choose');
    expect(filterName('')).toBe('no filter named');
    expect(filterName('ir', ['IR'])).toBe('IR');
  });
});

describe('AAVSO dialog: the request and what blocks Export', () => {
  const choice = { filter: 'v', keys: ['000-AAA-001@v'], allTargets: true, checkKey: '000-AAA-002@v', useCheck: true, filt: ' ', chart: '' };

  it('builds the A77/A78 body: null for "every target", the Settings band and the targets’ chart', () => {
    expect(aavsoBody(SRC, choice)).toEqual({ source: SRC, filter: 'v', keys: null, check_key: '000-AAA-002@v', use_check: true, obscode: null, filt: null, chart: null });
    const b = aavsoBody(SRC, { ...choice, allTargets: false, useCheck: false, filt: ' TG ', chart: ' X1 ' });
    expect(b.keys).toEqual(['000-AAA-001@v']);
    expect(b.check_key).toBeNull();
    expect(b.use_check).toBe(false);
    expect(b.filt).toBe('TG');
    expect(b.chart).toBe('X1');
    // obscode is never typed here: Settings (Q-R2)
    expect(b.obscode).toBeNull();
  });

  it('checks FILT as the server does (1-5 letters or digits; empty = Settings)', () => {
    expect(bandReason('')).toBeNull();
    expect(bandReason('TG')).toBeNull();
    expect(bandReason('CV')).toBeNull();
    expect(bandReason('TOOLONG')).toMatch(/1 to 5/);
    expect(bandReason('T-G')).toMatch(/1 to 5/);
  });

  it('says why Export is blocked, the dialog’s own reasons first, then the server’s refusal', () => {
    const pv = parseAavsoPreview(PREVIEW_RAW);
    const ok = { filter: 'ir', keys: ['k'], allTargets: true, filt: '' };
    expect(exportBlock(pv, { ...ok, filter: null }, ['b', 'v'], 'file', '/x.txt')).toMatch(/2 filters: choose/);
    expect(exportBlock(pv, { ...ok, allTargets: false, keys: [] }, ['ir'], 'file', '/x.txt')).toBe('Tick at least one target.');
    expect(exportBlock(pv, { ...ok, filt: 'x y' }, ['ir'], 'file', '/x.txt')).toMatch(/FILT/);
    expect(exportBlock(pv, ok, ['ir'], 'file', '')).toBe('Choose the file to write.');
    expect(exportBlock(pv, ok, ['ir'], 'file', 'rel/x.txt')).toBe('The file must be an absolute path.');
    expect(exportBlock(pv, ok, ['ir'], 'download', '')).toBeNull();
    const refused = { ...pv, refusal: { code: 'obscode_unset', message: 'Set your AAVSO observer code in Settings first: it is stamped on every AAVSO report.' } };
    expect(exportBlock(refused, ok, ['ir'], 'file', '/x.txt')).toMatch(/^Set your AAVSO observer code/);
    // A refusal the destination cannot fix is said before the missing file.
    expect(exportBlock(refused, ok, ['ir'], 'file', '')).toMatch(/^Set your AAVSO observer code/);
    expect(exportBlock(null, ok, ['ir'], 'file', '/x.txt', true)).toBe('Preparing the preview…');
    expect(exportBlock(null, ok, ['ir'], 'file', '/x.txt')).toBe('No preview yet.');
    expect(exportBlock(pv, ok, ['ir'], 'file', '/x.txt')).toBeNull();
  });

  it('shows each server note once (the band note and the airmass message sit beside their field)', () => {
    const pv = parseAavsoPreview({ ...PREVIEW_RAW, band_note: 'B', notes: ['A', 'B', 'The site in Settings was wrong.'], recorder_flagged: 2 });
    expect(otherNotes(pv)).toEqual(['A']);
    expect(pv.recorder_flagged).toBe(2);
  });

  it('accepts absolute paths only (POSIX, Windows drive, home)', () => {
    expect(isAbsolute('/a/b.txt')).toBe(true);
    expect(isAbsolute('~/a.txt')).toBe(true);
    expect(isAbsolute('C:\\a\\b.txt')).toBe(true);
    expect(isAbsolute('a/b.txt')).toBe(false);
    expect(isAbsolute('  ')).toBe(false);
  });

  it('says the points left out, non-zero counts only, grouped digits', () => {
    expect(excludedText({ saturated: 0, no_detection: 0, suspect: 0, nonfinite: 0, undated: 0 })).toBeNull();
    expect(excludedText(null)).toBeNull();
    expect(excludedText({ saturated: 3, no_detection: 0, suspect: 1200, nonfinite: 0, undated: 1 })).toBe(`Left out: 3 saturated · 1${NNBSP}200 suspect · 1 undated`);
    // S67: the no-detection points (the run's flight recorder) are named apart.
    expect(excludedText({ saturated: 0, no_detection: 2, suspect: 1, nonfinite: 0, undated: 0 })).toBe('Left out: 2 suspect (no detection) · 1 suspect');
    expect(parseAavsoPreview({ ...PREVIEW_RAW, excluded: { no_detection: 2 } }).excluded.no_detection).toBe(2);
    expect(rowsText(1)).toBe('1 row');
    expect(rowsText(1365)).toBe(`1${NNBSP}365 rows`);
  });

  it('says the frames are uncalibrated (owner decision 0.5.0: warn, the file unchanged)', () => {
    expect(UNCALIBRATED_NOTE).toMatch(/no bias, dark or flat/);
    expect(UNCALIBRATED_NOTE).toMatch(/flat-field/);
  });

  it('sends a null path for a download, the trimmed path for a file', () => {
    expect(exportTarget('download', '/x', true)).toEqual({ path: null, overwrite: true });
    expect(exportTarget('file', ' /x.txt ', false)).toEqual({ path: '/x.txt', overwrite: false });
    expect(joinPath('/data/s/', 'a.csv')).toBe('/data/s/a.csv');
  });
});

describe('CSV dialog (A79)', () => {
  it('lists the curves with points of the filter, every role; a legacy set as one filter', () => {
    expect(csvCurves(TWO, 'b').map((c) => c.key)).toEqual(['000-AAA-001@b', '000-AAA-002@b', '000-AAA-003@b']);
    expect(csvCurves(TWO, null)).toEqual([]);
    expect(csvCurves(LEGACY, null).map((c) => c.key)).toEqual(['SW And@', '000-AAA-002@']);
  });

  it('blocks with two filters and no choice, nothing to export, nothing ticked, no file', () => {
    expect(csvBlock(TWO, { filter: null, keys: [], allCurves: false }, 'file', '/x.csv')).toMatch(/2 filters: choose one/);
    expect(csvBlock([C('a@', 'target', '', 0)], { filter: null, keys: [], allCurves: false }, 'file', '/x.csv')).toBe('No measurements to export.');
    expect(csvBlock(TWO, { filter: 'b', keys: [], allCurves: false }, 'file', '/x.csv')).toBe('Tick at least one curve.');
    expect(csvBlock(TWO, { filter: 'b', keys: [], allCurves: true }, 'file', '')).toBe('Choose the file to write.');
    expect(csvBlock(TWO, { filter: 'b', keys: [], allCurves: true }, 'download', '')).toBeNull();
  });

  it('builds the body and the server’s default name', () => {
    expect(csvBody(SRC, { filter: 'b', keys: ['k'], allCurves: true })).toEqual({ source: SRC, filter: 'b', keys: null });
    expect(csvBody(SRC, { filter: 'b', keys: ['k'], allCurves: false }).keys).toEqual(['k']);
    expect(csvDefaultName('RR Lyr', 'ir')).toBe('RR_Lyr_ir_photometry.csv');
    expect(csvDefaultName(null, null)).toBe('curves_photometry.csv');
    expect(csvDefaultName('  ', 'v')).toBe('curves_v_photometry.csv');
    expect(csvCountText([C('a', 'target', 'v', 1)])).toBe('1 curve · 1 point');
    expect(csvCountText(TWO)).toBe('6 curves · 600 points');
  });
});

describe('export and re-run records (A76-A79 edge checks)', () => {
  it('parses a preview and refuses a malformed one', () => {
    const pv: AavsoPreview = parseAavsoPreview(PREVIEW_RAW);
    expect(pv.targets[0].rows).toBe(178);
    expect(pv.airmass.state).toBe('mismatch');
    expect(pv.check?.kmag_rows).toBe(181);
    expect(pv.chart_source).toBe('targets');
    expect(parseAavsoPreview({ ...PREVIEW_RAW, refusal: { code: 'no_target', message: 'No target points to export.' } }).refusal?.code).toBe('no_target');
    expect(parseAavsoPreview({ ...PREVIEW_RAW, chart_source: 'other', band_source: 'x' }).chart_source).toBe('none');
    expect(() => parseAavsoPreview({ targets: [] })).toThrow(/aavso\/preview/);
  });

  it('parses sources, results, plans', () => {
    expect(parseSource({ kind: 'live' })).toEqual({ kind: 'live' });
    expect(parseSource({ kind: 'import', path: '/a.csv' })).toEqual({ kind: 'import', path: '/a.csv' });
    expect(parseSource({ kind: 'session' })).toBeNull();
    expect(parseExportResult({ name: 'a.txt', bytes: 12, rows: 3, curves: 1, excluded: { suspect: 2 } })?.excluded?.suspect).toBe(2);
    expect(parseExportResult({})).toBeNull();
    const plan = parseRerunPlan({
      session: '/s',
      frames_dir: '/s/lights',
      frames: 195,
      frame_names: { first: 'a.fit', last: 'b.fit' },
      left_out: { calibration: 2, other_object: 1, outside_lights: 0, duplicates: 0 },
      stars: { object: 'SW And', target: 1, comparison: 6, check: 1 },
      targets: 'session',
      reference: { mode: 'solve', frame: null, live_available: false, astap: true },
      params: { aperture_fwhm_mult: 2.5, aperture_min_px: 4, annulus_in_px: 8, annulus_out_px: 12, egain: 2.31, read_noise_e: 3.5, sat_adu: 60000, band: 'TG', min_comps: 3, track_apertures: true },
      site_set: true,
      out_dir: '/s/photometry_rerun_20261115T183000Z',
      refusal: null,
    });
    expect(plan.params.egain).toBe(2.31);
    expect(() => parseRerunPlan({ out_dir: '/x' })).toThrow(/rerun\/plan/);
    const res = parseRerunResult({ out_dir: '/s/photometry_rerun_x', folder: 'photometry_rerun_x', curves: [{ key: 'a@ir', role: 'target', name: 'SW And', filter: 'ir', points: 195, file: 'target_SW_And_ir_SW_And.csv' }], check_rms: [{ key: 'c@ir', filter: 'ir', rms_mag: 0.012, n: 183 }] });
    expect(res?.source).toEqual({ kind: 'import', path: '/s/photometry_rerun_x' });
    expect(res?.curves[0].points).toBe(195);
  });

  it('calls the routes of the contract', async () => {
    const calls: [string, string, unknown][] = [];
    const client: ReviewRequest = {
      async request<T>(method: string, path: string, body?: unknown): Promise<T> {
        calls.push([method, path, body]);
        if (path === '/api/export/aavso/preview') return PREVIEW_RAW as T;
        return { job_id: 'j1', job: { id: 'j1' } } as T;
      },
    };
    const api = new ReviewExportApi(client);
    const body = aavsoBody(SRC, { filter: 'ir', keys: [], allTargets: true, checkKey: null, useCheck: true, filt: '', chart: '' });
    await api.aavsoPreview(body);
    expect((await api.exportAavso(body, { path: '/x.txt', overwrite: false })).job_id).toBe('j1');
    await api.exportCsv(csvBody(SRC, { filter: null, keys: [], allCurves: true }), { path: null, overwrite: false });
    await api.rerun(rerunBody('/s', { frames: '', targets: 'session', reference: 'solve', diagnostics: null }));
    expect(calls.map((c) => `${c[0]} ${c[1]}`)).toEqual(['POST /api/export/aavso/preview', 'POST /api/export/aavso', 'POST /api/export/csv', 'POST /api/review/rerun']);
    expect(calls[1][2]).toMatchObject({ path: '/x.txt', overwrite: false, filter: 'ir', keys: null });
    expect(calls[2][2]).toMatchObject({ path: null, keys: null });
  });
});

describe('Re-run dialog (A76, M50)', () => {
  const plan = parseRerunPlan({
    session: '/s',
    frames_dir: '/s/lights',
    frames: 195,
    frame_names: { first: null, last: null },
    left_out: { calibration: 0, other_object: 3, outside_lights: 0, duplicates: 0 },
    stars: { object: 'SW And', target: 1, comparison: 6, check: 0 },
    reference: { mode: 'solve', live_available: false, astap: true },
    params: { aperture_fwhm_mult: 2.5, aperture_min_px: 4, annulus_in_px: 8, annulus_out_px: 12, egain: null, read_noise_e: 3.5, sat_adu: 60000, band: 'TG', min_comps: 3, track_apertures: true },
    site_set: false,
    out_dir: '/s/photometry_rerun_x',
    refusal: null,
  });

  it('sends the session’s frames by default and a typed folder when given', () => {
    expect(rerunBody('/s', { frames: ' ', targets: 'session', reference: 'solve', diagnostics: null })).toEqual({ session: '/s', frames: null, targets: 'session', reference: 'solve', reference_frame: null, diagnostics: null });
    expect(rerunBody('/s', { frames: '/other ', targets: 'live', reference: 'live', diagnostics: true }).frames).toBe('/other');
  });

  it('says the frames, stars, aperture and parameters in words (true minus, grouped digits)', () => {
    expect(framesLine(plan)).toBe('195 light frames (.fit .fits .fts) · left out: 3 of another object');
    // S63: Siril's process/ copies beside lights/ and links to a frame listed (RR Lyr: 390).
    expect(framesLine({ ...plan, left_out: { calibration: 0, other_object: 0, outside_lights: 390, duplicates: 1 } })).toBe(
      '195 light frames (.fit .fits .fts) · left out: 390 outside lights/, 1 link to a frame listed',
    );
    expect(starsLine(plan.stars)).toBe('1 target · 6 comparisons · 0 checks');
    expect(apertureLine(plan.params)).toBe('2.50 × FWHM, floor 4.0 px · annulus 8.0–12.0 px');
    expect(paramsLine(plan.params, false)).toBe(`tracking on · read noise 3.5 e− · saturation 60${NNBSP}000 ADU · band TG · min 3 comparisons · no site: no airmass, no BJD_TDB`);
    expect(trackingText({ rotation_deg: -0.42, shift_px: 3.1 })).toBe('field rot −0.42° · drift 3.1 px');
    expect(trackingText({ rotation_deg: 0.01, shift_px: 0.5 })).toBeNull();
  });

  it('blocks Start with the failure, the wait, the server’s refusal, no frames', () => {
    expect(rerunBlock(null, 'Cannot reach the server', false)).toBe('Cannot reach the server');
    expect(rerunBlock(null, null, true)).toBe('Checking the frames…');
    expect(rerunBlock({ ...plan, refusal: { code: 'no_comparisons', message: 'No comparison stars in targets.json.' } }, null, false)).toBe('No comparison stars in targets.json.');
    expect(rerunBlock({ ...plan, frames: 0 }, null, false)).toBe('No FITS files (.fit, .fits, .fts) in /s/lights');
    expect(rerunBlock(plan, null, false)).toBeNull();
  });

  it('says the outcome: frames, curves, skipped, unverified (suspect), the new folder', () => {
    const r = parseRerunResult({
      out_dir: '/s/photometry_rerun_x',
      folder: 'photometry_rerun_x',
      frames_total: 195,
      frames_done: 193,
      frames_skipped: 2,
      frames_unverified: 4,
      curves: [{ key: 'a' }, { key: 'b' }],
      check_rms: [{ key: 'c@ir', filter: 'ir', rms_mag: 0.0123, n: 183 }],
    })!;
    expect(rerunResultText(r)).toBe('193 of 195 frames · 2 curves · 2 skipped · 4 unverified (suspect) → photometry_rerun_x/');
    expect(checkRmsLines(r, (k) => k.replace('@ir', ' [IR]'))).toEqual(['Check c [IR]: RMS 0.012 mag over 183 frames']);
  });

  it('says the S69 counts: re-solves for rotation and off-centre measurements', () => {
    const r = parseRerunResult({
      out_dir: '/s/photometry_rerun_y',
      folder: 'photometry_rerun_y',
      frames_total: 24,
      frames_done: 24,
      frames_rotation_solved: 7,
      stars_off_centre: 15,
      curves: [{ key: 'a' }],
    })!;
    expect(r.frames_rotation_solved).toBe(7);
    expect(rerunResultText(r)).toBe('24 of 24 frames · 1 curve · 7 re-solved for rotation · 15 off-centre (suspect) → photometry_rerun_y/');
    const old = parseRerunResult({ out_dir: '/s/r', folder: 'r', frames_total: 1, frames_done: 1, curves: [] })!;
    expect(old.frames_rotation_solved).toBe(0); // a server before S69
    expect(old.stars_off_centre).toBe(0);
  });

  it('says the failed rotation re-solves, frames without a target point, no detection and a wrong site', () => {
    const r = parseRerunResult({
      out_dir: '/s/photometry_rerun_z',
      folder: 'photometry_rerun_z',
      frames_total: 24,
      frames_done: 24,
      frames_rotation_unsolved: 7,
      frames_no_target_point: 1,
      frames_no_detection: 1,
      frames_header_airmass: 24,
      frames_site_wrong: 24,
      curves: [{ key: 'a' }],
    })!;
    expect(r.frames_header_airmass).toBe(24);
    expect(rerunResultText(r)).toBe(
      '24 of 24 frames · 1 curve · 7 not re-solved for rotation · 1 without a target point · 1 no detection (suspect) · site in Settings wrong on 24 → photometry_rerun_z/',
    );
    const old = parseRerunResult({ out_dir: '/s/r', folder: 'r', frames_total: 1, frames_done: 1, curves: [] })!;
    expect([old.frames_rotation_unsolved, old.frames_no_target_point, old.frames_no_detection, old.frames_site_wrong]).toEqual([0, 0, 0, 0]);
  });
});

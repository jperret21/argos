/**
 * Synthetic records for the Review R0, R2, Frames, dialogs and job strip gallery
 * (FilesGallery.svelte), in the A67-A79 wire shapes. No real data and no personal metadata:
 * invented sessions under "/Users/observer", the fake observer code "XYZ", no site.
 */

import type { SessionPage, SessionSummary } from '../../api/types';
import type { JobEntry } from '../../app/jobs';
import { SOLVED as FIELD_SOLVED, W, H } from '../../imaging/field/gallery/fixtures';
import type { CurveRef } from '../dialogs/aavso';
import { parseAavsoPreview, parseRerunPlan, type AavsoPreview, type RerunPlan } from '../dialogs/api';
import type { FileSolution, FitsCard, StarMeasure } from '../inspector/api';
import type { LiveSource, RecentItem } from '../landing/landing';

export const ROOT = '/Users/observer/Argos/sessions';
export const NOW = Date.parse('2026-11-15T21:30:00Z');

const S = (folder: string, extra: Partial<SessionSummary> = {}): SessionSummary => {
  const stamp = folder.slice(0, 16);
  const iso = `${stamp.slice(0, 4)}-${stamp.slice(4, 6)}-${stamp.slice(6, 8)}T${stamp.slice(9, 11)}:${stamp.slice(11, 13)}:${stamp.slice(13, 15)}+00:00`;
  return {
    path: `${ROOT}/${folder}`,
    folder,
    object: folder.slice(17).replace(/_/g, ' '),
    started_utc: iso,
    frames: 195,
    lights: 195,
    filters: { IR: 195 },
    image_types: { 'Light Frame': 195 },
    missing_frames: 0,
    curves: { target: 1, comparison: 6, check: 1 },
    has_quality: true,
    has_targets: true,
    issues: [],
    ...extra,
  };
};

export const SESSIONS: SessionSummary[] = [
  S('20261114T201210Z_SW_And', { lights: 412, frames: 412, filters: { IR: 206, LP: 206 }, curves: { target: 2, comparison: 12, check: 2 } }),
  S('20261102T190455Z_DY_Peg', { lights: 731, frames: 731, curves: { target: 1, comparison: 5, check: 0 } }),
  S('20261020T183320Z_AH_Cep', { lights: 88, frames: 90, missing_frames: 2, image_types: { 'Light Frame': 88, Dark: 2 }, issues: ['Missing FITS frame: AH_Cep_ir_light_e010000ms_g080_00041.fit', 'Missing FITS frame: AH_Cep_ir_light_e010000ms_g080_00042.fit'] }),
  S('20261003T201500Z_V1143_Cyg', { lights: 0, frames: 12, filters: { '—': 12 }, image_types: { Dark: 12 }, curves: { target: 0, comparison: 0, check: 0 }, has_quality: false, has_targets: false, issues: ['No light frames in this session'] }),
  S('20260925T200453Z_TU_UMa', { lights: 195, curves: { target: 1, comparison: 2, check: 0 }, issues: ['The site in Settings was not where the telescope was during this run: the curves’ airmass is wrong; the FITS header AIRMASS (from the mount) is right.'] }),
  S('20260907T030115Z_AB_Cas', { lights: 1203, frames: 1203 }),
  S('20260829T204400Z_BE_Lyn', { lights: 640, frames: 640, has_quality: false }),
  S('20260801T212000Z_Focus_test', { object: '', lights: 40, frames: 40, filters: { '—': 40 }, curves: { target: 0, comparison: 0, check: 0 }, has_quality: false, has_targets: false }),
];

export const PAGE: SessionPage = { root: ROOT, exists: true, total: SESSIONS.length, offset: 0, limit: 500, sessions: SESSIONS, scanned_utc: '2026-11-15T21:29:00Z' };
export const PAGE_EMPTY: SessionPage = { ...PAGE, total: 0, sessions: [] };
export const PAGE_MISSING: SessionPage = { ...PAGE_EMPTY, root: '/Volumes/Astro/sessions', exists: false };
export const PAGE_PAGED: SessionPage = { ...PAGE, total: 812 };

export const RECENT: RecentItem[] = [
  { kind: 'session', path: `${ROOT}/20261114T201210Z_SW_And`, label: 'SW And · 2026-11-14 20:12', t: NOW - 3600e3 },
  { kind: 'import', path: `${ROOT}/20261102T190455Z_DY_Peg/photometry/target_DY_Peg_ir_DY_Peg.csv`, label: 'target_DY_Peg_ir_DY_Peg.csv', t: NOW - 7200e3 },
  { kind: 'fits', path: `${ROOT}/20261020T183320Z_AH_Cep/lights/AH_Cep_ir_light_e010000ms_g080_00007.fit`, label: 'AH_Cep_ir_light_e010000ms_g080_00007.fit', t: NOW - 9000e3 },
];

export const LIVE: LiveSource = { object: 'SW And', started_utc: '2026-11-15T20:12:10+00:00', frames: 137, state: 'running' };

// -- Frames (A68 frames[]) -----------------------------------------------------------------------

function prng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** `n` light frames every 30 s from `start`, two missing FITS, two darks at the end. */
export function framesRaw(n = 195, folder = '20261114T201210Z_SW_And', start = '2026-11-14T20:12:10Z'): Record<string, unknown>[] {
  const r = prng(11);
  const t0 = Date.parse(start);
  const obj = folder.slice(17);
  const out: Record<string, unknown>[] = [];
  for (let i = 0; i < n; i++) {
    const hfd = 2.3 + (i > 60 && i < 70 ? 1.6 : 0) + 0.15 * (r() - 0.5);
    const alt = 62 - (30 * i) / n;
    out.push({
      index: i,
      filename: `${obj}_ir_light_e010000ms_g080_${String(i + 1).padStart(5, '0')}.fit`,
      image_type: 'Light Frame',
      filter_name: 'IR',
      filter: 'ir',
      light: true,
      exposure_s: 10,
      gain: 80,
      timestamp: new Date(t0 + i * 30e3).toISOString().replace('Z', ''),
      hfd: Math.round(hfd * 100) / 100,
      fwhm: Math.round(hfd * 0.92 * 100) / 100,
      star_count: Math.round(3100 - (i > 60 && i < 70 ? 1200 : 0) + 80 * (r() - 0.5)),
      sky_adu: Math.round(1170 + i * 0.4 + 6 * (r() - 0.5)),
      peak_adu: 65520,
      eccentricity: Math.round((0.45 + 0.08 * (r() - 0.5)) * 1000) / 1000,
      ccd_temp: Math.round((-1.5 - (3 * i) / n) * 10) / 10,
      path: i === 41 || i === 42 ? null : `${ROOT}/${folder}/lights/${obj}_ir_light_e010000ms_g080_${String(i + 1).padStart(5, '0')}.fit`,
      header: { date_obs: null, mid_utc: null, jd_mid: null, airmass: Math.round((1 / Math.sin((alt * Math.PI) / 180)) * 1e4) / 1e4, altitude: alt, azimuth: null, width: W, height: H, bayer: 'GRBG' },
    });
  }
  for (let k = 0; k < 2; k++) {
    out.push({ index: n + k, filename: `${obj}_dark_e010000ms_g080_${String(k + 1).padStart(5, '0')}.fit`, image_type: 'Dark', filter_name: '', filter: '', light: false, exposure_s: 10, gain: 80, timestamp: new Date(t0 + (n + 4 + k) * 30e3).toISOString().replace('Z', ''), ccd_temp: -4.5, path: `${ROOT}/${folder}/darks/d${k}.fit`, header: null });
  }
  return out;
}

// -- R2 ------------------------------------------------------------------------------------------

/** R2 shows the W4 synthetic field (imaging/field/gallery): its own session of that object. */
export const R2_FOLDER = '20261108T223700Z_RR_Lyr';
export const R2_LABEL = 'RR Lyr · 2026-11-08 22:37';
export const R2_FRAMES = framesRaw(195, R2_FOLDER, '2026-11-08T22:37:00Z');
export const FILE = `${ROOT}/${R2_FOLDER}/lights/RR_Lyr_ir_light_e010000ms_g080_00007.fit`;

export const CARDS: FitsCard[] = [
  ['SIMPLE', 'True', 'conforms to FITS standard'],
  ['BITPIX', '16', 'array data type'],
  ['NAXIS', '2', 'number of array dimensions'],
  ['NAXIS1', String(W), ''],
  ['NAXIS2', String(H), ''],
  ['BZERO', '32768', ''],
  ['DATE-OBS', '2026-11-08T22:40:00.000', 'exposure start (UTC)'],
  ['EXPTIME', '10.0', 'exposure time (s)'],
  ['GAIN', '80', 'sensor gain'],
  ['CCD-TEMP', '-1.6', 'sensor temperature (C)'],
  ['FILTER', 'IR', 'filter wheel position'],
  ['IMAGETYP', 'Light Frame', ''],
  ['OBJECT', 'RR Lyr', ''],
  ['OBJCTRA', '19 26 30.0', 'hinted RA'],
  ['OBJCTDEC', '+42 47 00', 'hinted Dec'],
  ['AIRMASS', '1.1412', 'from the mount'],
  ['BAYERPAT', 'GRBG', 'CFA pattern'],
  ['INSTRUME', 'Smart telescope', ''],
  ['SWCREATE', 'ARGOS 0.5.0', ''],
].map(([key, value, comment]) => ({ key, value, comment }));

export const KEYWORDS: Record<string, string> = Object.fromEntries(CARDS.map((c) => [c.key, c.value]));

export const MEASURE: StarMeasure = {
  found: true,
  message: null,
  x: 292.4,
  y: 452.1,
  fwhm_px: 4.06,
  hfd_px: 4.52,
  fwhm_arcsec: 4.83,
  hfd_arcsec: 5.38,
  scale_arcsec_px: 1.19,
  scale_source: 'solution',
  eccentricity: 0.18,
  snr: 412.6,
  peak_adu: 41210,
  sky_adu: 1801.4,
  flux: 2.1e6,
  radius_green_px: 5,
  ra_hours: 19.4428,
  dec_deg: 42.784,
};

/** A TAN WCS on the synthetic frame: 1.19″/px, rotated 12.3°, centred on the frame. */
const SCALE = 1.19 / 3600;
const ROT = (12.3 * Math.PI) / 180;
export const SOLUTION: FileSolution = {
  path: FILE,
  file_name: FILE.slice(FILE.lastIndexOf('/') + 1),
  solution: { ra_hours: 19.4417, dec_deg: 42.7833, scale_arcsec_px: 1.19, rotation_deg: 12.3, mirrored: false, frame_shape: [H, W], hint: { ra_hours: 19.4417, dec_deg: 42.7833, source: 'header' }, solved_utc: '2026-11-15T21:20:04Z', summary: 'Solved' },
  wcs: {
    crval: [19.4417 * 15, 42.7833],
    crpix: [W / 2 + 1, H / 2 + 1],
    cd: [
      [-SCALE * Math.cos(ROT), SCALE * Math.sin(ROT)],
      [SCALE * Math.sin(ROT), SCALE * Math.cos(ROT)],
    ],
  },
  grid: FIELD_SOLVED.grid ? clippedGrid(FIELD_SOLVED.grid) : null,
};

/** The W4 graticule clipped to the frame, as the server sends it (polylines broken off-frame). */
function clippedGrid(g: NonNullable<typeof FIELD_SOLVED.grid>): FileSolution['grid'] {
  const clip = ([x0, y0]: readonly [number, number], [x1, y1]: readonly [number, number]): [number, number][] | null => {
    // Liang–Barsky on [0, W] × [0, H].
    const dx = x1 - x0;
    const dy = y1 - y0;
    let t0 = 0;
    let t1 = 1;
    for (const [p, q] of [[-dx, x0], [dx, W - x0], [-dy, y0], [dy, H - y0]] as const) {
      if (p === 0) {
        if (q < 0) return null;
        continue;
      }
      const t = q / p;
      if (p < 0) t0 = Math.max(t0, t);
      else t1 = Math.min(t1, t);
      if (t0 > t1) return null;
    }
    return [
      [x0 + t0 * dx, y0 + t0 * dy],
      [x0 + t1 * dx, y0 + t1 * dy],
    ];
  };
  const lines: [number, number][][] = [];
  for (const line of g.lines) for (let i = 1; i < line.length; i++) {
    const seg = clip(line[i - 1], line[i]);
    if (seg) lines.push(seg);
  }
  const labels = g.labels.filter((l) => l.x >= 0 && l.y >= 0 && l.x <= W && l.y <= H).map((l) => ({ ...l }));
  return { lines, labels };
}

// -- Dialogs -------------------------------------------------------------------------------------

export const SOURCE = { kind: 'session', path: `${ROOT}/20261114T201210Z_SW_And` } as const;

const C = (key: string, role: string, name: string, filter: string, n: number, extra: Partial<CurveRef> = {}): CurveRef => ({ key, role, name, filter, n, ...extra });

/** One filter: a target, a check, five comparisons. */
export const CURVES_ONE: CurveRef[] = [
  C('000-ZZZ-001@ir', 'target', 'SW And', 'ir', 195),
  C('000-ZZZ-102@ir', 'check', '000-ZZZ-102', 'ir', 195),
  ...[103, 104, 105, 106, 107].map((k) => C(`000-ZZZ-${k}@ir`, 'comparison', `000-ZZZ-${k}`, 'ir', 195)),
];

/** Two filters (S49 keys): the observer chooses one (S53). */
export const CURVES_TWO: CurveRef[] = ['ir', 'lp'].flatMap((f) => [
  C(`000-ZZZ-001@${f}`, 'target', 'SW And', f, 206),
  C(`000-ZZZ-102@${f}`, 'check', '000-ZZZ-102', f, 206),
  C(`000-ZZZ-103@${f}`, 'comparison', '000-ZZZ-103', f, 206),
  C(`000-ZZZ-104@${f}`, 'comparison', '000-ZZZ-104', f, 206),
]);

/** A curve CSV whose star and role are unknown (S10). */
export const CURVES_UNIDENTIFIED: CurveRef[] = [C('mystery@ir', 'target', 'mystery', 'ir', 88, { exportable: false, problem: 'The star or role of this light curve is unknown — no AAVSO export.' })];

const HEAD = [
  '#TYPE=EXTENDED',
  '#OBSCODE=XYZ',
  '#SOFTWARE=ARGOS 0.5.0',
  '#DELIM=,',
  '#DATE=JD',
  '#OBSTYPE=CCD',
  '#NAME,DATE,MAG,MERR,FILT,TRANS,MTYPE,CNAME,CMAG,KNAME,KMAG,AMASS,GROUP,CHART,NOTES',
  'SW And,2461359.34536,9.412,0.011,TG,NO,STD,ENSEMBLE,na,000-ZZZ-102,10.231,1.1412,na,X99999AA,na',
  'SW And,2461359.34571,9.418,0.011,TG,NO,STD,ENSEMBLE,na,000-ZZZ-102,10.226,1.1409,na,X99999AA,na',
  'SW And,2461359.34606,9.409,0.012,TG,NO,STD,ENSEMBLE,na,000-ZZZ-102,10.229,1.1406,na,X99999AA,na',
].join('\n');

const PREVIEW_BASE = {
  source: SOURCE,
  object: 'SW And',
  obscode: 'XYZ',
  obscode_set: true,
  band: 'TG',
  band_source: 'settings',
  filter: 'ir',
  filters: ['ir'],
  band_note: null,
  chart: 'X99999AA',
  chart_source: 'targets',
  check: { key: '000-ZZZ-102@ir', name: '000-ZZZ-102', kname: '000-ZZZ-102', points: 195, kmag_rows: 190 },
  targets: [{ key: '000-ZZZ-001@ir', name: 'SW And', points: 195, rows: 190, saturated: 1, suspect: 3, nonfinite: 1, undated: 0 }],
  rows: 190,
  excluded: { saturated: 1, suspect: 3, nonfinite: 1, undated: 0 },
  airmass: { source: 'csv', state: 'ok', message: null },
  notes: ['3 suspect points (measured without a verified lock) are left out.'],
  refusal: null,
  head: HEAD,
  default_path: `${ROOT}/20261114T201210Z_SW_And/SW_And_ir_aavso.txt`,
};

export const PREVIEW: AavsoPreview = parseAavsoPreview(PREVIEW_BASE);
/** The server's texts (argos/server/exports.py): an LP run, and a run whose Settings site was wrong. */
const LP_NOTE = 'The frames were taken through the LP filter, a duo-band nebula filter: no AAVSO band matches it. FILT=TG would misreport the band.';
const AIRMASS_NOTE = 'AMASS comes from the curves’ airmass, computed for the site in Settings, which was not where the telescope was during this run: these values are wrong (the FITS header AIRMASS, from the mount, is right).';
export const CURVES_LP: CurveRef[] = CURVES_ONE.map((c) => ({ ...c, key: c.key.replace('@ir', '@lp'), filter: 'lp' }));
export const PREVIEW_MISMATCH: AavsoPreview = parseAavsoPreview({
  ...PREVIEW_BASE,
  filter: 'lp',
  filters: ['lp'],
  check: { ...PREVIEW_BASE.check, key: '000-ZZZ-102@lp' },
  targets: PREVIEW_BASE.targets.map((t) => ({ ...t, key: t.key.replace('@ir', '@lp') })),
  band_note: LP_NOTE,
  airmass: { source: 'csv', state: 'mismatch', message: AIRMASS_NOTE },
  recorder_flagged: 2,
  notes: [...PREVIEW_BASE.notes, '2 point(s) would be written although the run’s flight recorder marks them as no detection (target SNR below 3) or a zero point more than 1 mag off: check them before you submit.', LP_NOTE, AIRMASS_NOTE],
  default_path: `${ROOT}/20261114T201210Z_SW_And/SW_And_lp_aavso.txt`,
});
export const PREVIEW_NO_OBSCODE: AavsoPreview = parseAavsoPreview({
  ...PREVIEW_BASE,
  obscode: '',
  obscode_set: false,
  refusal: { code: 'obscode_unset', message: 'Set your AAVSO observer code in Settings first: it is stamped on every AAVSO report.' },
  head: HEAD.replace('#OBSCODE=XYZ', '#OBSCODE='),
});
export const PREVIEW_UNIDENTIFIED: AavsoPreview = parseAavsoPreview({
  ...PREVIEW_BASE,
  object: null,
  check: null,
  targets: [{ key: 'mystery@ir', name: 'mystery', points: 88, rows: 0, saturated: 0, suspect: 0, nonfinite: 0, undated: 0 }],
  rows: 0,
  excluded: { saturated: 0, suspect: 0, nonfinite: 0, undated: 0 },
  notes: [],
  refusal: { code: 'curve_unidentified', message: 'The star or role of this light curve is unknown — no AAVSO export.' },
  head: '',
  default_path: null,
});

const PLAN_BASE = {
  session: SOURCE.path,
  frames_dir: `${SOURCE.path}/lights`,
  frames: 195,
  frame_names: { first: 'SW_And_ir_light_e010000ms_g080_00001.fit', last: 'SW_And_ir_light_e010000ms_g080_00195.fit' },
  left_out: { calibration: 2, other_object: 0 },
  stars: { object: 'SW And', target: 1, comparison: 5, check: 1 },
  targets: 'session',
  reference: { mode: 'solve', frame: null, live_available: false, astap: true },
  params: { aperture_fwhm_mult: 2.5, aperture_min_px: 4, annulus_in_px: 8, annulus_out_px: 12, egain: 2.31, read_noise_e: 3.5, sat_adu: 60000, band: 'TG', min_comps: 3, track_apertures: true },
  site_set: true,
  out_dir: `${SOURCE.path}/photometry_rerun_20261115T213000Z`,
  refusal: null,
};
export const PLAN: RerunPlan = parseRerunPlan(PLAN_BASE);
export const PLAN_LIVE: RerunPlan = parseRerunPlan({ ...PLAN_BASE, reference: { mode: 'live', frame: null, live_available: true, astap: true }, site_set: false });
export const PLAN_NO_FRAMES: RerunPlan = parseRerunPlan({ ...PLAN_BASE, frames_dir: '/Users/observer/Desktop/empty', frames: 0, frame_names: { first: null, last: null }, left_out: { calibration: 0, other_object: 0 }, refusal: { code: 'no_frames', message: 'No FITS files (.fit, .fits, .fts) in /Users/observer/Desktop/empty' } });
export const PLAN_NO_COMPS: RerunPlan = parseRerunPlan({ ...PLAN_BASE, stars: { object: 'SW And', target: 1, comparison: 0, check: 0 }, refusal: { code: 'no_comparisons', message: 'No comparison stars in targets.json: assign comparisons in Observe first.' } });

// -- Jobs ----------------------------------------------------------------------------------------

const J = (id: string, kind: string, state: JobEntry['state'], extra: Partial<JobEntry> = {}): JobEntry => ({
  id,
  kind,
  state,
  done: 0,
  total: null,
  stage: null,
  message: null,
  started_utc: new Date(NOW - 74e3).toISOString(),
  ended_utc: null,
  result: null,
  error: null,
  cancellable: true,
  cancel_requested: false,
  seq: 1,
  cancelling: false,
  cancelError: null,
  ...extra,
});

export const JOBS = {
  rerun: J('r1', 'rerun', 'running', { done: 37, total: 195, stage: 'measuring', message: 'SW_And_ir_light_e010000ms_g080_00037.fit' }),
  resolving: J('r2', 'rerun', 'running', { done: 112, total: 195, stage: 're-solving', message: 'ASTAP on SW_And_ir_light_e010000ms_g080_00112.fit' }),
  cancelling: J('r3', 'rerun', 'running', { done: 64, total: 195, cancelling: true }),
  queued: J('e0', 'export', 'queued', { cancellable: false }),
  open: J('o1', 'session_open', 'running', { done: 0, total: null, stage: 'headers', started_utc: new Date(NOW - 1e3).toISOString() }),
  done: J('r4', 'rerun', 'done', { done: 195, total: 195, ended_utc: new Date(NOW).toISOString() }),
  failed: J('r5', 'rerun', 'failed', { done: 3, total: 195, error: { code: 'not_solved', message: 'ASTAP could not identify the reference frame SW_And_ir_light_e010000ms_g080_00001.fit (no solution in 120 s).' } }),
  cancelled: J('r6', 'rerun', 'cancelled', { done: 64, total: 195, message: 'Batch photometry cancelled after 64/195 frame(s) — nothing saved.' }),
  exported: J('e1', 'export', 'done', { message: 'AAVSO export: 190 observation(s) written to SW_And_ir_aavso.txt; left out: 1 saturated, 3 suspect, 1 without a magnitude.' }),
};

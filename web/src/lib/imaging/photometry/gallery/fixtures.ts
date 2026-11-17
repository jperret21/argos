/**
 * Deterministic fixtures of live photometry for the gallery (development only): an XX Cyg-like
 * set (target, five VSP comparisons, one of them listed in VSX, a check star), 40 points per
 * curve on a HADS-like light curve, the leave-one-out report in its three verdicts, the field's
 * variables and the live status in each state. Synthetic: not a measurement.
 */

import type { TargetStar } from '../../field/types';
import type { Curve, FieldVariable, LcPoint, LiveStatus, QualityEntry, QualityReport } from '../types';

export const JD0 = 2461282.395; // 2026-08-29 21:28:48 UTC
const CADENCE_D = 30 / 86400;

function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}
const gauss = (r: () => number) => Math.sqrt(-2 * Math.log(Math.max(1e-12, r()))) * Math.cos(2 * Math.PI * r());

const star = (over: Partial<TargetStar> & Pick<TargetStar, 'key' | 'role'>): TargetStar =>
  ({ name: '', display_name: '', ra_deg: 300.81, dec_deg: 58.95, ra_hours: 20.054, auid: null, source: 'vsp_auto', mags: {}, chart_id: 'X39253ABC', note: '', x: null, y: null, ...over }) as TargetStar;

export const STARS: TargetStar[] = [
  star({ key: 'auid:000-BBC-123', role: 'target', name: 'XX Cyg', display_name: 'XX Cyg', auid: '000-BBC-123', source: 'vsx', mags: {}, chart_id: null, x: 540, y: 960 }),
  star({ key: 'auid:000-BCG-653', role: 'comparison', name: '114', display_name: '000-BCG-653', auid: '000-BCG-653', mags: { V: 11.42, B: 11.98 }, x: 380, y: 820 }),
  star({ key: 'auid:000-BCG-661', role: 'comparison', name: '119', display_name: '000-BCG-661', auid: '000-BCG-661', mags: { V: 11.93, B: 12.61 }, x: 702, y: 1104 }),
  star({ key: 'auid:000-BCG-670', role: 'comparison', name: '122', display_name: '000-BCG-670', auid: '000-BCG-670', mags: { V: 12.18, B: 12.66 }, x: 610, y: 690 }),
  star({ key: 'auid:000-BCG-702', role: 'comparison', name: '125', display_name: '000-BCG-702', auid: '000-BCG-702', mags: { V: 12.51, B: 13.32 }, x: 300, y: 1210 }),
  star({ key: 'pos:300.79210,+58.91003', role: 'comparison', name: 'manual', display_name: 'Gaia 2194…', auid: null, source: 'manual', mags: {}, chart_id: null, x: 812, y: 870 }),
  star({ key: 'auid:000-BCG-688', role: 'check', name: '121', display_name: '000-BCG-688', auid: '000-BCG-688', mags: { V: 12.07, B: 12.71 }, x: 460, y: 1290 }),
];

/** A HADS-like target (period 0.1349 d) and flat stars, with the server's fields. */
function curve(s: TargetStar, n: number, seed: number): Curve {
  const r = rng(seed);
  const v = typeof s.mags?.V === 'number' ? (s.mags.V as number) : null;
  const pts: LcPoint[] = [];
  for (let i = 0; i < n; i++) {
    const jd = JD0 + i * CADENCE_D;
    const phase = ((jd - JD0) / 0.134865) % 1;
    const base = s.role === 'target' ? 11.65 - 0.45 * Math.exp(-((phase - 0.1) ** 2) / 0.004) + 0.25 * phase : (v ?? 12.0);
    const formal = s.role === 'target' ? 0.008 : 0.011;
    const sigma = i >= 9 ? 0.006 : null;
    const err = sigma !== null ? Math.hypot(formal, sigma) : formal;
    const drift = s.key === 'auid:000-BCG-702' ? 0.002 * i : 0; // a drifting comparison (VSX-listed)
    pts.push({
      jd_utc: jd,
      bjd_tdb: jd + 0.0037,
      mag: base + drift + gauss(r) * err,
      mag_err: err,
      formal_mag_err: formal,
      sigma_syst: sigma,
      airmass: 1.12 + i * 0.004,
      fwhm: 3.1,
      sky_adu: 410 + gauss(r) * 4,
      comps_used: 4,
      relative_flux: 1 + gauss(r) * 0.01,
      relative_flux_err: 0.01,
      relative_comps_used: 4,
      saturated: s.role === 'target' && i === 17,
      suspect: s.role === 'check' && i === 23,
      t: new Date((jd - 2440587.5) * 86400000).toISOString(),
      frame_seq: 100 + i,
    });
  }
  return {
    key: s.auid || s.display_name || s.key,
    star_key: s.key,
    role: s.role,
    name: s.display_name ?? s.key,
    auid: s.auid,
    mags: s.mags as Record<string, number>,
    catalogue_v: v,
    sigma_syst: n >= 10 ? 0.006 : null,
    points: pts,
  };
}

export function curves(n: number): Curve[] {
  return STARS.filter((s) => s.mags && (s.role !== 'comparison' || Object.keys(s.mags).length)).map((s, i) => curve(s, n, 7 + i));
}

const entry = (s: TargetStar, status: QualityEntry['status'], n: number, scatter: number | null, formal: number | null, last: number | null): QualityEntry => ({
  name: s.display_name ?? s.key,
  auid: s.auid,
  n_valid: n,
  scatter_mag: scatter,
  median_formal_error_mag: formal,
  status,
  key: s.auid || s.display_name || s.key,
  star_key: s.key,
  last: last === null ? null : { mag: last, mag_err: 0.0128, comps_used: 3, jd_utc: JD0 + 39 * CADENCE_D },
});

const NOTE = 'Leave-one-out live-preview assessment only. Confirm the ensemble on registered, calibrated frames in Siril / star_var_script.';
const CRIT = { min_points: 10, max_scatter_mag: 0.1, max_formal_error_mag: 0.1 };
const [, c1, c2, c3, c4] = STARS;

export const REPORT_WAITING: QualityReport = {
  selection_status: 'insufficient_data',
  scientific_note: NOTE,
  criteria: CRIT,
  comparison_stars: [entry(c1, 'insufficient_data', 6, 0.0102, 0.0111, 11.431), entry(c2, 'insufficient_data', 6, 0.0131, 0.0123, 11.918), entry(c3, 'insufficient_data', 6, null, 0.0129, 12.192), entry(c4, 'insufficient_data', 6, null, 0.0141, 12.533)],
};
export const REPORT_OK: QualityReport = {
  selection_status: 'live_preview_consistent',
  scientific_note: NOTE,
  criteria: CRIT,
  comparison_stars: [entry(c1, 'stable', 40, 0.0098, 0.0111, 11.426), entry(c2, 'stable', 40, 0.0124, 0.0123, 11.941), entry(c3, 'stable', 40, 0.0131, 0.0129, 12.171), entry(c4, 'unstable', 40, 0.1183, 0.0141, 12.588)],
};
export const REPORT_NOT_READY: QualityReport = {
  selection_status: 'not_ready',
  scientific_note: NOTE,
  criteria: CRIT,
  comparison_stars: [entry(c1, 'stable', 40, 0.0098, 0.0111, 11.426), entry(c2, 'noisy', 40, 0.0124, 0.1123, 11.941), entry(c3, 'unstable', 40, 0.131, 0.0129, 12.171), entry(c4, 'unstable', 40, 0.1183, 0.0141, 12.588)],
};

export const GEOMETRY = { aperture_px: 6.2, annulus_in_px: 9, annulus_out_px: 14, aperture_r_px: 12.4, annulus_in_r_px: 18, annulus_out_r_px: 28, fwhm_px: 3.1, fwhm_source: 'frame', series_fwhm_px: 3.1 };

export const STATUS_MEASURED: LiveStatus = {
  state: 'measured',
  reason: null,
  message: null,
  frames: 40,
  points: 240,
  last: { frame_seq: 139, t: '2026-08-29T21:48:18Z', jd_utc: JD0 + 39 * CADENCE_D, bjd_tdb: null, points: 6, target: { key: 'XX Cyg', mag: 11.48, mag_err: 0.01 }, aperture_px: 6.2, fwhm_px: 3.1, anchors: 5, tracking: null },
};
export const STATUS_SKIPPED: LiveStatus = { state: 'skipped', reason: 'no_epoch', message: 'Photometry skipped: the frame has no exposure time (DATE-OBS/EXPTIME).', frames: 3, points: 0, last: null };

const v = (index: number, name: string, var_type: string, mag_text: string, brightest: number, period: number | null, sep: number, role: FieldVariable['in_set_role'] = null, suspected = false): FieldVariable => ({
  index,
  name,
  var_type,
  mag_text,
  brightest_mag: brightest,
  period_d: period,
  sep_arcmin: sep,
  in_set_role: role,
  suspected,
  auid: null,
  key: `vsx:${index}`,
  x: 100 + index * 37,
  y: 200 + index * 53,
});

export const VARIABLES: FieldVariable[] = [
  v(0, 'XX Cyg', 'HADS', '11.27 – 12.1 V', 11.27, 0.134865, 0.4, 'target'),
  v(1, 'V0532 Cyg', 'EA', '12.4 – 12.9 V', 12.4, 3.2251, 6.8),
  v(2, 'NSV 12945', 'VAR', '13.1 – 13.5 p', 13.1, null, 9.3, null, true),
  v(3, 'ASASSN-V J200312.10+585432.4', 'EW', '13.62 – 13.95 V', 13.62, 0.31244, 11.2),
  v(4, 'V0687 Cyg', 'SR', '12.2 – 12.8 V', 12.2, 74.0, 14.0, 'comparison'),
  v(5, 'Gaia DR3 2194123456', 'RRAB', '14.8 – 15.6 G', 14.8, 0.5512, 15.7),
];

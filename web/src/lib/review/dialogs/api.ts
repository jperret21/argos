/**
 * Exports and re-run, client side of API 2 wave 7 (README rows A76-A79; contract in
 * argos/server/protocol.md "Review (wave 7): exports and re-run"). The server drives the
 * fixed core writers (`write_aavso`, `write_curves_csv`) and the fixed batch worker; the
 * client never builds a file itself: the preview IS the file's head as the export writes it.
 *
 * - Previews and plans never write (A77, `POST /api/review/rerun/plan`): the dialogs ask them
 *   again whenever a choice changes, and show the server's refusal before any job starts.
 * - Starts return `202 {job_id, job}`: the job strip shows the progress; the result comes as
 *   the job's `result` (ExportResult, RerunResult).
 * - Records are checked at the edge; a malformed answer is refused with the route's name.
 */

import type { RequestOptions } from '../../api/client';
import type { Source } from '../landing/landing';

/** The request function of the shared client (ArgosClient.request). */
export interface ReviewRequest {
  request<T>(method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE', path: string, body?: unknown, options?: RequestOptions): Promise<T>;
}

export interface Refusal {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

// -- AAVSO (A77, A78) ----------------------------------------------------------------------------

export interface AavsoBody {
  source: Source;
  /** Filter token to report (S53); null: the source's only one. */
  filter: string | null;
  /** Target curve keys; null: every target curve of that filter. */
  keys: string[] | null;
  check_key: string | null;
  use_check: boolean;
  /** null: Settings observer.obscode. */
  obscode: string | null;
  /** FITS band code FILT; null: Settings photometry.default_band. */
  filt: string | null;
  /** CHART; null: the target set's comparison chart. */
  chart: string | null;
}

export interface ExportTarget {
  /** Absolute file; null: kept by the server for a download. */
  path: string | null;
  overwrite: boolean;
}

export interface AavsoTargetLine {
  key: string;
  name: string;
  points: number;
  rows: number;
  saturated: number;
  suspect: number;
  nonfinite: number;
  undated: number;
}

export interface Excluded {
  saturated: number;
  suspect: number;
  nonfinite: number;
  undated: number;
}

export interface AavsoPreview {
  source: Source;
  object: string | null;
  obscode: string;
  obscode_set: boolean;
  band: string;
  band_source: 'request' | 'settings';
  filter: string | null;
  filters: string[];
  band_note: string | null;
  chart: string;
  chart_source: 'request' | 'targets' | 'none';
  check: { key: string; name: string; kname: string; points: number; kmag_rows: number } | null;
  targets: AavsoTargetLine[];
  rows: number;
  excluded: Excluded;
  /** Rows written although the flight recorder flags them (zp_outlier, low_snr): a `warnings` line. */
  recorder_flagged: number;
  /** Rows on a frame where fewer than 3 anchors reached SNR 10 (S56 rule, conservative). */
  unverified_lock: number;
  /** Those rows, each named (the dialog lists their times). */
  flagged_points: { key: string; index: number; jd_utc: number; mag: number; mag_err: number; flags: string[] }[];
  /** Science warnings the export would carry (AMASS at a wrong site, flagged rows): shown with the warning glyph. */
  warnings: { code: string; count: number; message: string }[];
  airmass: { source: string; state: 'ok' | 'mismatch'; message: string | null };
  /** Every line the dialog shows (the band note and the airmass message among them). */
  notes: string[];
  refusal: Refusal | null;
  head: string;
  default_path: string | null;
}

export interface ExportResult {
  path: string | null;
  name: string;
  bytes: number;
  download: boolean;
  rows: number;
  curves: number;
  filter: string | null;
  excluded: Excluded | null;
  notes: string[];
}

// -- CSV (A79) -----------------------------------------------------------------------------------

export interface CsvBody {
  source: Source;
  keys: string[] | null;
  filter: string | null;
}

// -- Re-run (A76) --------------------------------------------------------------------------------

export interface RerunBody {
  session: string;
  frames: string | null;
  targets: 'session' | 'live';
  reference: 'solve' | 'live';
  reference_frame: string | null;
  diagnostics: boolean | null;
}

export interface RerunParams {
  aperture_fwhm_mult: number | null;
  aperture_min_px: number | null;
  annulus_in_px: number | null;
  annulus_out_px: number | null;
  egain: number | null;
  read_noise_e: number | null;
  sat_adu: number | null;
  band: string | null;
  min_comps: number | null;
  track_apertures: boolean | null;
}

export interface RerunPlan {
  session: string;
  frames_dir: string;
  frames: number;
  frame_names: { first: string | null; last: string | null };
  /** S62: another object; S63: FITS outside lights/ (Siril's process/ copies), links to a frame listed. */
  left_out: { calibration: number; other_object: number; outside_lights: number; duplicates: number };
  stars: { object: string; target: number; comparison: number; check: number };
  targets: 'session' | 'live';
  reference: { mode: 'solve' | 'live'; frame: string | null; live_available: boolean; astap: boolean };
  params: RerunParams;
  site_set: boolean;
  out_dir: string;
  refusal: Refusal | null;
}

export interface RerunResult {
  out_dir: string;
  folder: string;
  source: Source;
  frames_total: number;
  frames_done: number;
  frames_skipped: number;
  frames_resolved: number;
  frames_unanchored: number;
  frames_unverified: number;
  /** S62: another object; S63: FITS outside lights/ (Siril's process/ copies), links to a frame listed. */
  left_out: { calibration: number; other_object: number; outside_lights: number; duplicates: number };
  rotation_deg: number;
  shift_px: number;
  series_fwhm_px: number | null;
  aperture_px: number;
  curves: { key: string; role: string; name: string; auid: string | null; filter: string; points: number; file: string }[];
  check_rms: { key: string; filter: string; rms_mag: number; n: number }[];
  notes: string[];
}

export interface JobStart {
  job_id: string;
  job: unknown;
}

// -- Edge checks -------------------------------------------------------------------------------

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const num = (v: unknown, d = 0): number => (typeof v === 'number' && Number.isFinite(v) ? v : d);
const numOrNull = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v: unknown, d = ''): string => (typeof v === 'string' ? v : d);
const strOrNull = (v: unknown): string | null => (typeof v === 'string' ? v : null);
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []);

class BadRecord extends Error {
  constructor(route: string) {
    super(`Unexpected answer from ${route}`);
    this.name = 'BadRecord';
  }
}

export function parseSource(v: unknown): Source | null {
  if (!isObj(v)) return null;
  if (v.kind === 'live') return { kind: 'live' };
  if ((v.kind === 'session' || v.kind === 'import') && typeof v.path === 'string') return { kind: v.kind, path: v.path };
  return null;
}

function parseRefusal(v: unknown): Refusal | null {
  if (!isObj(v) || typeof v.message !== 'string') return null;
  return { code: str(v.code, 'refused'), message: v.message, details: isObj(v.details) ? v.details : undefined };
}

function parseExcluded(v: unknown): Excluded {
  const o = isObj(v) ? v : {};
  return { saturated: num(o.saturated), suspect: num(o.suspect), nonfinite: num(o.nonfinite), undated: num(o.undated) };
}

export function parseAavsoPreview(v: unknown): AavsoPreview {
  if (!isObj(v) || typeof v.head !== 'string' || !Array.isArray(v.targets)) throw new BadRecord('POST /api/export/aavso/preview');
  const check = isObj(v.check)
    ? { key: str(v.check.key), name: str(v.check.name), kname: str(v.check.kname), points: num(v.check.points), kmag_rows: num(v.check.kmag_rows) }
    : null;
  const air = isObj(v.airmass) ? v.airmass : {};
  return {
    source: parseSource(v.source) ?? { kind: 'live' },
    object: strOrNull(v.object),
    obscode: str(v.obscode),
    obscode_set: v.obscode_set === true,
    band: str(v.band),
    band_source: v.band_source === 'request' ? 'request' : 'settings',
    filter: strOrNull(v.filter),
    filters: strs(v.filters),
    band_note: strOrNull(v.band_note),
    chart: str(v.chart, 'na'),
    chart_source: v.chart_source === 'request' || v.chart_source === 'targets' ? v.chart_source : 'none',
    check,
    targets: v.targets.filter(isObj).map((t) => ({
      key: str(t.key),
      name: str(t.name),
      points: num(t.points),
      rows: num(t.rows),
      saturated: num(t.saturated),
      suspect: num(t.suspect),
      nonfinite: num(t.nonfinite),
      undated: num(t.undated),
    })),
    rows: num(v.rows),
    excluded: parseExcluded(v.excluded),
    recorder_flagged: num(v.recorder_flagged),
    unverified_lock: num(v.unverified_lock),
    flagged_points: (Array.isArray(v.flagged_points) ? v.flagged_points : []).filter(isObj).map((p) => ({ key: str(p.key), index: num(p.index), jd_utc: num(p.jd_utc), mag: num(p.mag), mag_err: num(p.mag_err), flags: strs(p.flags) })),
    warnings: (Array.isArray(v.warnings) ? v.warnings : []).filter(isObj).map((w) => ({ code: str(w.code), count: num(w.count), message: str(w.message) })),
    airmass: { source: str(air.source, 'csv'), state: air.state === 'mismatch' ? 'mismatch' : 'ok', message: strOrNull(air.message) },
    notes: strs(v.notes),
    refusal: parseRefusal(v.refusal),
    head: v.head,
    default_path: strOrNull(v.default_path),
  };
}

export function parseExportResult(v: unknown): ExportResult | null {
  if (!isObj(v) || typeof v.name !== 'string') return null;
  return {
    path: strOrNull(v.path),
    name: v.name,
    bytes: num(v.bytes),
    download: v.download === true,
    rows: num(v.rows),
    curves: num(v.curves),
    filter: strOrNull(v.filter),
    excluded: isObj(v.excluded) ? parseExcluded(v.excluded) : null,
    notes: strs(v.notes),
  };
}

export function parseRerunPlan(v: unknown): RerunPlan {
  if (!isObj(v) || typeof v.out_dir !== 'string' || !isObj(v.stars) || !isObj(v.reference)) throw new BadRecord('POST /api/review/rerun/plan');
  const p = isObj(v.params) ? v.params : {};
  const names = isObj(v.frame_names) ? v.frame_names : {};
  const left = isObj(v.left_out) ? v.left_out : {};
  return {
    session: str(v.session),
    frames_dir: str(v.frames_dir),
    frames: num(v.frames),
    frame_names: { first: strOrNull(names.first), last: strOrNull(names.last) },
    left_out: { calibration: num(left.calibration), other_object: num(left.other_object), outside_lights: num(left.outside_lights), duplicates: num(left.duplicates) },
    stars: { object: str(v.stars.object), target: num(v.stars.target), comparison: num(v.stars.comparison), check: num(v.stars.check) },
    targets: v.targets === 'live' ? 'live' : 'session',
    reference: {
      mode: v.reference.mode === 'live' ? 'live' : 'solve',
      frame: strOrNull(v.reference.frame),
      live_available: v.reference.live_available === true,
      astap: v.reference.astap !== false,
    },
    params: {
      aperture_fwhm_mult: numOrNull(p.aperture_fwhm_mult),
      aperture_min_px: numOrNull(p.aperture_min_px),
      annulus_in_px: numOrNull(p.annulus_in_px),
      annulus_out_px: numOrNull(p.annulus_out_px),
      egain: numOrNull(p.egain),
      read_noise_e: numOrNull(p.read_noise_e),
      sat_adu: numOrNull(p.sat_adu),
      band: strOrNull(p.band),
      min_comps: numOrNull(p.min_comps),
      track_apertures: typeof p.track_apertures === 'boolean' ? p.track_apertures : null,
    },
    site_set: v.site_set === true,
    out_dir: v.out_dir,
    refusal: parseRefusal(v.refusal),
  };
}

export function parseRerunResult(v: unknown): RerunResult | null {
  if (!isObj(v) || typeof v.out_dir !== 'string') return null;
  const left = isObj(v.left_out) ? v.left_out : {};
  return {
    out_dir: v.out_dir,
    folder: str(v.folder),
    source: parseSource(v.source) ?? { kind: 'import', path: v.out_dir },
    frames_total: num(v.frames_total),
    frames_done: num(v.frames_done),
    frames_skipped: num(v.frames_skipped),
    frames_resolved: num(v.frames_resolved),
    frames_unanchored: num(v.frames_unanchored),
    frames_unverified: num(v.frames_unverified),
    left_out: { calibration: num(left.calibration), other_object: num(left.other_object), outside_lights: num(left.outside_lights), duplicates: num(left.duplicates) },
    rotation_deg: num(v.rotation_deg),
    shift_px: num(v.shift_px),
    series_fwhm_px: numOrNull(v.series_fwhm_px),
    aperture_px: num(v.aperture_px),
    curves: (Array.isArray(v.curves) ? v.curves : []).filter(isObj).map((c) => ({
      key: str(c.key),
      role: str(c.role),
      name: str(c.name),
      auid: strOrNull(c.auid),
      filter: str(c.filter),
      points: num(c.points),
      file: str(c.file),
    })),
    check_rms: (Array.isArray(v.check_rms) ? v.check_rms : []).filter(isObj).map((c) => ({ key: str(c.key), filter: str(c.filter), rms_mag: num(c.rms_mag, NaN), n: num(c.n) })),
    notes: strs(v.notes),
  };
}

function jobStart(v: unknown, route: string): JobStart {
  if (!isObj(v) || typeof v.job_id !== 'string') throw new BadRecord(route);
  return { job_id: v.job_id, job: v.job };
}

/** A preview, plan or start that may scan a large session (one header per frame) or reopen it. */
const LONG_MS = 60_000;

export class ReviewExportApi {
  constructor(private readonly client: ReviewRequest) {}

  /** A77: what the export would write now (never writes). */
  async aavsoPreview(body: AavsoBody, signal?: AbortSignal): Promise<AavsoPreview> {
    return parseAavsoPreview(await this.client.request<unknown>('POST', '/api/export/aavso/preview', body, { signal, timeoutMs: LONG_MS }));
  }

  /** A78: start the `export` job; 409 with the preview's refusal codes, `file_exists`. */
  async exportAavso(body: AavsoBody, target: ExportTarget): Promise<JobStart> {
    return jobStart(await this.client.request<unknown>('POST', '/api/export/aavso', { ...body, ...target }), 'POST /api/export/aavso');
  }

  /** A79: start the `export` job; 409 `no_points`, `unknown_curve`, `multiple_filters`, `file_exists`. */
  async exportCsv(body: CsvBody, target: ExportTarget): Promise<JobStart> {
    return jobStart(await this.client.request<unknown>('POST', '/api/export/csv', { ...body, ...target }), 'POST /api/export/csv');
  }

  /** A76: what a start now would do (never writes). */
  async rerunPlan(body: RerunBody, signal?: AbortSignal): Promise<RerunPlan> {
    return parseRerunPlan(await this.client.request<unknown>('POST', '/api/review/rerun/plan', body, { signal, timeoutMs: LONG_MS }));
  }

  /** A76: start the `rerun` job; 409 `no_frames`, `no_targets`, `no_comparisons`, `not_solved`, `astap_missing`, `busy`. */
  async rerun(body: RerunBody): Promise<JobStart> {
    return jobStart(await this.client.request<unknown>('POST', '/api/review/rerun', body, { timeoutMs: LONG_MS }), 'POST /api/review/rerun');
  }
}

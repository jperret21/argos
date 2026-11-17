/**
 * What Review reads of a session (README A68, A69; spec 07 §2.5) and how its curves reach
 * the shared light-curve store. Pure, tested without a browser; the wire adapter is this
 * file alone (a renamed field is one edit here).
 *
 * A69 `GET /api/review/session/curves?path=` sends every curve as COLUMNS (one array per
 * `LcPoint` field of argos/core/photometry/lightcurve.py, the CSV's columns, unrounded;
 * null for a value the CSV leaves empty): thousands of points without one object each on
 * the wire. They are read into LiveCurveStore (charts/lightcurve/store.ts), the store the
 * Observe drawer draws, so a Review cell and the live plot draw a point the same way.
 *
 * Inherited rules (web/spec/progress.md, wave 6b §8):
 * - S9: a `check_` CSV is a check star (the server fixes the role; a role the client does
 *   not know is never turned into "target" silently here: it is reported).
 * - S49: curves are keyed `<AUID or name>@<token>` with `filter` the token ("ir"); a curve
 *   from a CSV written before 0.5.0 has no filter (null). A series is labelled
 *   "Name [IR]" only when more than one filter is loaded (format/filter.ts).
 * - Vetting files (S57): `photometry_quality.json` for the run's first filter and
 *   `photometry_quality_<filter>.json` for the others, each naming its filter in a last
 *   key "filter"; a file without it was written before 0.5.0 (one-filter runs only).
 * - Suspect points (S56, S58) are kept and drawn hollow; saturated ones as ×.
 */

import { filterLabel } from '../format/filter';
import { LiveCurveStore, type Role, type TargetStarLike } from '../charts/lightcurve/store';
import type { LcPoint } from '../charts/lightcurve/columns';

// -- A69: curves ---------------------------------------------------------------------------------

/** The `LcPoint` columns of one curve (A69); every array as long as `jd_utc`. */
export interface CurveColumnsWire {
  jd_utc: (number | null)[];
  bjd_tdb?: (number | null)[];
  mag?: (number | null)[];
  mag_err?: (number | null)[];
  formal_mag_err?: (number | null)[];
  sigma_syst?: (number | null)[];
  airmass?: (number | null)[];
  fwhm?: (number | null)[];
  sky_adu?: (number | null)[];
  comps_used?: (number | null)[];
  relative_flux?: (number | null)[];
  relative_flux_err?: (number | null)[];
  relative_comps_used?: (number | null)[];
  saturated?: (boolean | number | null)[];
  suspect?: (boolean | number | null)[];
  /** The flight recorder's ensemble zero point and its rms on that frame (A69, 4 dp). */
  zero_point?: (number | null)[];
  zp_rms?: (number | null)[];
  /** That frame's FITS header AIRMASS (the mount's; A69), beside the CSV's `airmass`. */
  header_airmass?: (number | null)[];
  /** ReviewSession.frames index of the point's frame (Qt's nearest_light_frame). */
  frame?: (number | null)[];
  /** Display flags beyond the CSV's: "zp_outlier", "low_snr", "few_anchors", "no_frame" (A69); [] clean. */
  flags?: string[][];
}

/** One curve of A69 (or of an imported CSV, A70). */
export interface ReviewCurveWire {
  key: string;
  role: string;
  name?: string | null;
  auid?: string | null;
  /** S49 filter token ("ir"); null or "" for a CSV written before 0.5.0. */
  filter?: string | null;
  /** The CSV it was read from (file name or path). */
  csv?: string | null;
  /** The star's catalogue magnitudes in targets.json, and its V (A69). */
  mags?: Record<string, number | null> | null;
  catalogue_v?: number | null;
  sigma_syst?: number | null;
  /** False when the star or role is unknown (no export), with the core's text (S10). */
  exportable?: boolean;
  problem?: string | null;
  points: CurveColumnsWire;
}

export interface CurvesWire {
  curves: ReviewCurveWire[];
  /** Problems the server met reading the CSVs ("{file}: role unknown …"). */
  problems?: string[];
  /** "header" when the header site check found the Settings site wrong (A68): the CSV airmass is wrong. */
  airmass_source?: 'csv' | 'header';
  /** What the `airmass` column holds: "header" once the server applied S66 (each frame's header AIRMASS). */
  airmass_column?: 'csv' | 'header';
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);
const numOrNull = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

const COLUMN_KEYS = [
  'jd_utc',
  'bjd_tdb',
  'mag',
  'mag_err',
  'formal_mag_err',
  'sigma_syst',
  'airmass',
  'fwhm',
  'sky_adu',
  'comps_used',
  'relative_flux',
  'relative_flux_err',
  'relative_comps_used',
  'saturated',
  'suspect',
  'zero_point',
  'zp_rms',
  'header_airmass',
  'frame',
] as const;

/**
 * A69's answer, checked at the edge: the curves list (a bare array or `{curves}`), each
 * with its columns as arrays of the same length. A malformed curve is refused with its key
 * (the whole answer, never half of it: 07 P13).
 */
export function parseCurves(raw: unknown): CurvesWire {
  const list = Array.isArray(raw) ? raw : isObj(raw) && Array.isArray(raw.curves) ? raw.curves : null;
  if (!list) throw new Error('Session curves: the answer has no curves list');
  const curves: ReviewCurveWire[] = [];
  for (const c of list) {
    if (!isObj(c)) throw new Error('Session curves: a curve is not an object');
    const key = str(c.key);
    if (!key) throw new Error('Session curves: a curve has no key');
    const cols = isObj(c.points) ? c.points : isObj(c.columns) ? c.columns : null;
    if (!cols || !Array.isArray(cols.jd_utc)) throw new Error(`Session curves: ${key} has no jd_utc column`);
    const n = cols.jd_utc.length;
    const points: Record<string, unknown[]> = {};
    for (const k of COLUMN_KEYS) {
      const a = cols[k];
      if (a === undefined || a === null) continue;
      if (!Array.isArray(a) || a.length !== n) throw new Error(`Session curves: ${key}.${k} has ${Array.isArray(a) ? a.length : 'no'} values for ${n} times`);
      points[k] = a;
    }
    // The display flags: one list of words per point (a malformed entry is read as clean).
    if (Array.isArray(cols.flags)) {
      if (cols.flags.length !== n) throw new Error(`Session curves: ${key}.flags has ${cols.flags.length} values for ${n} times`);
      points.flags = cols.flags.map((f) => (Array.isArray(f) ? f.filter((w): w is string => typeof w === 'string') : []));
    }
    const mags: Record<string, number | null> = {};
    if (isObj(c.mags)) for (const [b, v] of Object.entries(c.mags)) mags[b] = numOrNull(v);
    curves.push({
      key,
      role: str(c.role) ?? '',
      name: str(c.name),
      auid: str(c.auid),
      filter: str(c.filter) || null,
      csv: str(c.csv) ?? str(c.file_name),
      mags: isObj(c.mags) ? mags : null,
      catalogue_v: numOrNull(c.catalogue_v),
      sigma_syst: numOrNull(c.sigma_syst),
      exportable: c.exportable !== false,
      problem: str(c.problem),
      points: points as unknown as CurveColumnsWire,
    });
  }
  const problems = isObj(raw) && Array.isArray(raw.problems) ? raw.problems.filter((p): p is string => typeof p === 'string') : [];
  const airmass = isObj(raw) && raw.airmass_source === 'header' ? 'header' : 'csv';
  const column = isObj(raw) && raw.airmass_column === 'header' ? 'header' : 'csv';
  return { curves, problems, airmass_source: airmass, airmass_column: column };
}

const ROLES: readonly Role[] = ['target', 'check', 'comparison'];
export const isRole = (r: unknown): r is Role => typeof r === 'string' && (ROLES as readonly string[]).includes(r);

/** Row i of a curve's columns as an `LcPoint` (what LiveCurveStore keeps). */
export function pointAt(p: CurveColumnsWire, i: number): LcPoint {
  const n = (a: (number | null)[] | undefined) => (a ? numOrNull(a[i]) : null);
  const b = (a: (boolean | number | null)[] | undefined) => !!(a && a[i]);
  return {
    jd_utc: numOrNull(p.jd_utc[i]) ?? NaN,
    bjd_tdb: n(p.bjd_tdb),
    mag: n(p.mag),
    mag_err: n(p.mag_err),
    formal_mag_err: n(p.formal_mag_err),
    sigma_syst: n(p.sigma_syst),
    airmass: n(p.airmass),
    fwhm: n(p.fwhm),
    sky_adu: n(p.sky_adu),
    comps_used: n(p.comps_used),
    relative_flux: n(p.relative_flux),
    relative_flux_err: n(p.relative_flux_err),
    relative_comps_used: n(p.relative_comps_used),
    saturated: b(p.saturated),
    suspect: b(p.suspect),
    recorder_flag: !!p.flags?.[i]?.some((w) => RECORDER_WORDS.has(w)),
    zero_point: n(p.zero_point),
    zp_rms: n(p.zp_rms),
  };
}

// -- What the store does not keep: the header airmass and the display flags (A69) -------------------

/** A curve's A69 columns the light-curve store has no place for, by point time (unix s, sorted). */
export interface CurveExtras {
  t: Float64Array;
  headerAirmass: Float64Array;
  /** Display flags per point ("zp_outlier", "low_snr", "few_anchors", "no_frame"); empty: clean. */
  words: readonly (readonly string[])[];
  frame: Int32Array;
  /** Any point has a word (the health strip's lane). */
  flagged: number;
}

export const FLAG_WORDS: Record<string, string> = {
  zp_outlier: 'ZP outlier',
  low_snr: 'low SNR',
  few_anchors: 'unverified lock',
  no_detection: 'no detection',
  no_frame: 'no frame',
};
/** The recorder's words that mean "not a measurement of the star": drawn hollow, off the range. */
export const RECORDER_WORDS: ReadonlySet<string> = new Set(['low_snr', 'zp_outlier', 'no_detection']);
/** A display flag in words (an unknown code is shown as written). */
export const flagWord = (code: string) => FLAG_WORDS[code] ?? code.replace(/_/g, ' ');

const JD_UNIX = 2440587.5;

export function extrasOf(c: ReviewCurveWire): CurveExtras | null {
  const p = c.points;
  if (!p.header_airmass && !p.flags && !p.frame) return null;
  const n = p.jd_utc.length;
  const idx: number[] = [];
  for (let i = 0; i < n; i++) if (typeof p.jd_utc[i] === 'number' && Number.isFinite(p.jd_utc[i])) idx.push(i);
  idx.sort((a, b) => (p.jd_utc[a] as number) - (p.jd_utc[b] as number));
  const m = idx.length;
  const t = new Float64Array(m);
  const headerAirmass = new Float64Array(m).fill(NaN);
  const frame = new Int32Array(m).fill(-1);
  const words: string[][] = new Array(m);
  let flagged = 0;
  idx.forEach((i, k) => {
    t[k] = ((p.jd_utc[i] as number) - JD_UNIX) * 86400;
    const a = p.header_airmass ? numOrNull(p.header_airmass[i]) : null;
    if (a !== null) headerAirmass[k] = a;
    const f = p.frame ? numOrNull(p.frame[i]) : null;
    if (f !== null) frame[k] = f;
    words[k] = p.flags?.[i] ?? [];
    if (words[k].length) flagged++;
  });
  return { t, headerAirmass, words, frame, flagged };
}

/** The row of `x` at time t (within `tol` s), else -1. */
export function extraRow(x: CurveExtras | null | undefined, t: number, tol = 1): number {
  if (!x || !x.t.length) return -1;
  let lo = 0;
  let hi = x.t.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (x.t[mid] < t) lo = mid + 1;
    else hi = mid;
  }
  let best = -1;
  for (const k of [lo - 1, lo]) if (k >= 0 && k < x.t.length && (best < 0 || Math.abs(x.t[k] - t) < Math.abs(x.t[best] - t))) best = k;
  return best >= 0 && Math.abs(x.t[best] - t) <= tol ? best : -1;
}

export interface StoreInput {
  curves: readonly ReviewCurveWire[];
  /** The session's target set (A68 `targets`): catalogue magnitudes (check − V, D10). */
  targets?: readonly TargetStarLike[];
  /** The photometric band ("TG"): the comparisons' calibration magnitude. */
  band?: string | null;
  object?: string | null;
}

/**
 * The curves in a LiveCurveStore, in the server's order. A curve whose role the client does
 * not know is left out and named in `skipped` (never drawn as a target: S9, S10).
 */
export function storeFromCurves(input: StoreInput, store = new LiveCurveStore()): { store: LiveCurveStore; skipped: string[]; extras: Map<string, CurveExtras> } {
  const skipped: string[] = [];
  const extras = new Map<string, CurveExtras>();
  const curves = [];
  for (const c of input.curves) {
    if (!isRole(c.role)) {
      skipped.push(`${c.csv ?? c.key}: role "${c.role || 'none'}" unknown`);
      continue;
    }
    const n = c.points.jd_utc.length;
    const points: LcPoint[] = new Array(n);
    for (let i = 0; i < n; i++) points[i] = pointAt(c.points, i);
    const x = extrasOf(c);
    if (x) extras.set(c.key, x);
    // The curve's own catalogue magnitudes (A69 `mags`, `catalogue_v`) when the server gives them.
    const hasCat = !!c.mags || (c.catalogue_v !== null && c.catalogue_v !== undefined);
    const cat = hasCat ? { mags: c.mags ?? undefined, catalogue_v: c.catalogue_v ?? undefined } : {};
    curves.push({ key: c.key, role: c.role, name: c.name ?? c.key, auid: c.auid ?? null, filter: c.filter ?? null, star_key: starKeyOf(c), sigma_syst: c.sigma_syst ?? null, ...cat, points });
  }
  if (input.band) store.band = input.band;
  // Catalogue magnitudes first, so every curve takes its own as it is created.
  store.applyTargets(input.targets ?? [], input.band ?? null);
  store.load({ object_name: input.object ?? null, band: input.band ?? null, curves });
  store.applyTargets(input.targets ?? [], input.band ?? null);
  return { store, skipped, extras };
}

/** The star a curve belongs to across filters (S49: "000-BCG-719@ir" → "000-BCG-719"). */
export function starKeyOf(c: Pick<ReviewCurveWire, 'key' | 'auid' | 'name'>): string {
  const at = c.key.lastIndexOf('@');
  return at > 0 ? c.key.slice(0, at) : c.auid || c.name || c.key;
}

/** The filters the curves name, in their first order (empty before S49). */
export function curveFilters(curves: readonly Pick<ReviewCurveWire, 'filter'>[]): string[] {
  const out: string[] = [];
  for (const c of curves) if (c.filter && !out.includes(c.filter)) out.push(c.filter);
  return out;
}

/**
 * A series' label: "Name [IR]" only when more than one filter is loaded (wave 6b §8), with
 * the wheel's name for the token when known.
 */
export function seriesLabel(name: string, filter: string | null | undefined, filtersLoaded: number, wheel: readonly string[] = []): string {
  return filtersLoaded > 1 && filter ? `${name} [${filterLabel(filter, wheel)}]` : name;
}

// -- A68: the session ----------------------------------------------------------------------------

/** One comparison of a vetting report (photometry_quality.json `comparison_stars[]`). */
export interface QualityStar {
  name: string;
  auid: string | null;
  n_valid: number | null;
  scatter_mag: number | null;
  median_formal_error_mag: number | null;
  /** "stable" | "noisy" | "unstable" | "insufficient_data" (core quality.py). */
  status: string;
}

/** A vetting report (core quality.py `ComparisonQualityReport.to_dict`). */
export interface QualityReport {
  selection_status: string;
  scientific_note: string;
  criteria: Record<string, number>;
  stars: QualityStar[];
  /** S57: the filter it vets (null: written before 0.5.0, a one-filter run). */
  filter: string | null;
  generated_utc: string | null;
}

export function parseQuality(raw: unknown): QualityReport | null {
  if (!isObj(raw)) return null;
  const list = Array.isArray(raw.comparison_stars) ? raw.comparison_stars : Array.isArray(raw.stars) ? raw.stars : [];
  const stars: QualityStar[] = [];
  for (const s of list) {
    if (!isObj(s)) continue;
    const name = str(s.name) ?? str(s.auid);
    if (!name) continue;
    stars.push({
      name,
      auid: str(s.auid),
      n_valid: numOrNull(s.n_valid),
      scatter_mag: numOrNull(s.scatter_mag),
      median_formal_error_mag: numOrNull(s.median_formal_error_mag),
      status: str(s.status) ?? '',
    });
  }
  const criteria: Record<string, number> = {};
  if (isObj(raw.criteria)) for (const [k, v] of Object.entries(raw.criteria)) if (typeof v === 'number') criteria[k] = v;
  return {
    selection_status: str(raw.selection_status) ?? '',
    scientific_note: str(raw.scientific_note) ?? '',
    criteria,
    stars,
    filter: str(raw.filter) || null,
    generated_utc: str(raw.generated_utc),
  };
}

/** The reports of a session: one, or one per filter (S57); null entries dropped. */
export function parseQualityList(raw: unknown): QualityReport[] {
  const list = Array.isArray(raw) ? raw : raw ? [raw] : [];
  return list.map(parseQuality).filter((q): q is QualityReport => q !== null);
}

/**
 * A68 `quality`: `{default, default_filter, by_filter}` (photometry_quality.json, its "filter"
 * key or null before 0.5.0, and photometry_quality_<token>.json by token, S57), as one list.
 * A list or a bare report is read too.
 */
export function parseQualityBlock(raw: unknown): QualityReport[] {
  if (!isObj(raw) || !('default' in raw || 'by_filter' in raw)) return parseQualityList(raw);
  const out: QualityReport[] = [];
  const def = parseQuality(raw.default);
  if (def) out.push({ ...def, filter: def.filter ?? (str(raw.default_filter) || null) });
  if (isObj(raw.by_filter))
    for (const [token, rep] of Object.entries(raw.by_filter)) {
      const q = parseQuality(rep);
      if (q && !out.some((r) => r.filter === (q.filter ?? token))) out.push({ ...q, filter: q.filter ?? token });
    }
  return out;
}

/** The report that vets `filter` (a report without a filter vets a one-filter run). */
export function qualityFor(reports: readonly QualityReport[], filter: string | null): QualityReport | null {
  if (!reports.length) return null;
  if (filter) {
    const exact = reports.find((r) => r.filter === filter);
    if (exact) return exact;
    const legacy = reports.filter((r) => r.filter === null);
    return legacy.length === reports.length && reports.length === 1 ? reports[0] : null;
  }
  return reports[0];
}

/** A comparison's line of a report, by AUID, then name (the CSV star tag). */
export function qualityOf(report: QualityReport | null, star: { auid?: string | null; name?: string | null }): QualityStar | null {
  if (!report) return null;
  return report.stars.find((s) => (!!star.auid && s.auid === star.auid) || (!!star.name && (s.name === star.name || s.auid === star.name))) ?? null;
}

/** The status in words, as the Qt table says it (comparison_table.py), capitalised. */
export function statusWord(status: string): string {
  const s = status.replace(/_/g, ' ').trim();
  return s ? s[0].toUpperCase() + s.slice(1) : '—';
}

/** "stable" is fine; anything else asks for a look (a word, never a colour alone). */
export const statusOk = (status: string) => status === 'stable';

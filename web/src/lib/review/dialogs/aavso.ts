/**
 * Export AAVSO and Export CSV dialogs, the pure part (web/spec/07-review-analysis.md WF-E,
 * 2.4 "Confirmations"; README M92, A77-A79, S11, Q-R2, Q-R3; protocol.md "AAVSO preview (A77)
 * and export (A78)", "CSV export (A79)"; S53 one filter at a time, S61 CSV one filter at a
 * time, S10 a curve whose star or role is unknown is never exported).
 *
 * The server writes the file with the fixed core writer and returns its head as the preview,
 * so nothing here formats a report line: this module only builds the request from the
 * dialog's choices and says, in words, what blocks the Export button.
 */

import { fixed, int } from '../../format/number';
import { clockUtc } from '../../format/time';
import { filterLabel } from '../../format/filter';
import type { AavsoBody, AavsoPreview, CsvBody, Excluded, ExportTarget } from './api';
import type { Source } from '../landing/landing';

/** A curve as the dialogs list it (ReviewSession.curves / CurveSet.curves, A68-A70). */
export interface CurveRef {
  key: string;
  role: string;
  name: string;
  /** Filter token ("" when nothing says, a pre-0.5.0 name). */
  filter: string;
  /** Points in the file. */
  n: number;
  exportable?: boolean;
  problem?: string | null;
}

/** Filter tokens of the curves of these roles, in curve order, "" left out. */
export function filtersOf(curves: readonly CurveRef[], roles: readonly string[] = ['target', 'check']): string[] {
  const out: string[] = [];
  for (const c of curves) if (roles.includes(c.role) && c.filter && !out.includes(c.filter)) out.push(c.filter);
  return out;
}

/** The filter a dialog starts on: the only one, else none (the observer chooses, S53). */
export function initialFilter(filters: readonly string[]): string | null {
  return filters.length === 1 ? filters[0] : null;
}

/**
 * Curves of a role in a filter. `filter` null: every curve when there is at most one filter,
 * none while the observer has still to choose among several (S53).
 */
export function curvesIn(curves: readonly CurveRef[], role: string, filter: string | null): CurveRef[] {
  const single = filtersOf(curves).length <= 1;
  return curves.filter((c) => c.role === role && (filter === null ? single : c.filter === filter || (!c.filter && single)));
}

/** The observer's choices in the AAVSO dialog. */
export interface AavsoChoice {
  filter: string | null;
  /** Target keys ticked (in the filter). */
  keys: readonly string[];
  /** Every target of the filter is ticked: send null (the server's "every target curve"). */
  allTargets: boolean;
  checkKey: string | null;
  useCheck: boolean;
  /** FILT as typed ("" = the Settings band). */
  filt: string;
  /** CHART as typed ("" = the target set's chart). */
  chart: string;
}

export function aavsoBody(source: Source, c: AavsoChoice): AavsoBody {
  const filt = c.filt.trim();
  const chart = c.chart.trim();
  return {
    source,
    filter: c.filter,
    keys: c.allTargets ? null : [...c.keys],
    check_key: c.useCheck ? c.checkKey : null,
    use_check: c.useCheck,
    obscode: null,
    filt: filt ? filt : null,
    chart: chart ? chart : null,
  };
}

/** FILT as the server accepts it (1-5 letters or digits), or the reason. */
export function bandReason(filt: string): string | null {
  const f = filt.trim();
  if (!f) return null; // the Settings band
  return /^[A-Za-z0-9]{1,5}$/.test(f) ? null : 'FILT is 1 to 5 letters or digits (AAVSO band code, e.g. TG, V, CV)';
}

export type Destination = 'file' | 'download';

/**
 * Why Export cannot start now, or null. Order: what the dialog itself can see first (a filter
 * to choose, no target ticked, FILT), then the server's refusal in its words (nothing the
 * destination can fix), then the file path.
 */
export function exportBlock(
  preview: AavsoPreview | null,
  c: Pick<AavsoChoice, 'filter' | 'keys' | 'allTargets' | 'filt'>,
  filters: readonly string[],
  dest: Destination,
  path: string,
  pending = false,
): string | null {
  if (filters.length > 1 && !c.filter) return `These curves are in ${filters.length} filters: choose the one to report (one band per AAVSO report).`;
  if (!c.allTargets && !c.keys.length) return 'Tick at least one target.';
  const band = bandReason(c.filt);
  if (band) return band;
  if (preview?.refusal) return preview.refusal.message;
  if (dest === 'file' && !isAbsolute(path)) return path.trim() ? 'The file must be an absolute path.' : 'Choose the file to write.';
  if (!preview) return pending ? 'Preparing the preview…' : 'No preview yet.';
  return null;
}

export function isAbsolute(path: string): boolean {
  const p = path.trim();
  return p.startsWith('/') || /^[A-Za-z]:[\\/]/.test(p) || p.startsWith('~/');
}

/** "Left out: 3 saturated · 2 suspect" (only the non-zero counts), or null when nothing is. */
export function excludedText(e: Excluded | null | undefined): string | null {
  if (!e) return null;
  const bits: string[] = [];
  if (e.saturated) bits.push(`${int(e.saturated)} saturated`);
  if (e.no_detection) bits.push(`${int(e.no_detection)} suspect (no detection)`);
  if (e.suspect) bits.push(`${int(e.suspect)} suspect`);
  if (e.nonfinite) bits.push(`${int(e.nonfinite)} without a magnitude`);
  if (e.undated) bits.push(`${int(e.undated)} undated`);
  return bits.length ? `Left out: ${bits.join(' · ')}` : null;
}

/** The preview's notes not already shown beside their field (the band note, the airmass message). */
export function otherNotes(pv: Pick<AavsoPreview, 'notes' | 'band_note' | 'airmass'>): string[] {
  return pv.notes.filter((n) => n !== pv.band_note && n !== pv.airmass.message);
}

/** The preview's science warnings other than the airmass one (shown on its own line). */
export function flagWarnings(pv: Pick<AavsoPreview, 'warnings'>): AavsoPreview['warnings'] {
  return pv.warnings.filter((w) => w.code !== 'airmass_wrong_site');
}

/** A flagged row as the dialog lists it: "22:35:41 UTC 6.257 ± 1.043". */
export function flaggedPointText(p: AavsoPreview['flagged_points'][number]): string {
  const t = (p.jd_utc - 2440587.5) * 86400;
  return `${clockUtc(t)} UTC ${fixed(p.mag, 3)} ± ${fixed(p.mag_err, 3)}`;
}

/** "183 rows" / "1 row" for a target line or the whole file. */
export function rowsText(n: number): string {
  return `${int(n)} ${n === 1 ? 'row' : 'rows'}`;
}

/** The filter's display name ("ir" → "IR"), "no filter named" for "". */
export function filterName(token: string | null, names: readonly string[] = []): string {
  if (token === null) return 'choose';
  return token ? filterLabel(token, names) : 'no filter named';
}

/** A default file in a folder: `<dir>/<object>_<filter>_aavso.txt` (the server's default name). */
export function joinPath(dir: string, name: string): string {
  return `${dir.replace(/[\\/]+$/, '')}/${name}`;
}

export function exportTarget(dest: Destination, path: string, overwrite: boolean): ExportTarget {
  return { path: dest === 'download' ? null : path.trim(), overwrite };
}

// -- CSV (A79) -----------------------------------------------------------------------------------

export interface CsvChoice {
  filter: string | null;
  keys: readonly string[];
  allCurves: boolean;
}

export function csvBody(source: Source, c: CsvChoice): CsvBody {
  return { source, filter: c.filter, keys: c.allCurves ? null : [...c.keys] };
}

/** Curves a CSV export can hold in a filter (any role; S61: one filter per file). */
export function csvCurves(curves: readonly CurveRef[], filter: string | null): CurveRef[] {
  const all = filtersOf(curves, ['target', 'comparison', 'check']);
  return curves.filter((c) => c.n > 0 && (filter === null ? all.length <= 1 : c.filter === filter || (!c.filter && all.length <= 1)));
}

export function csvBlock(curves: readonly CurveRef[], c: CsvChoice, dest: Destination, path: string): string | null {
  const filters = filtersOf(curves, ['target', 'comparison', 'check']);
  if (filters.length > 1 && !c.filter) return `These curves are in ${filters.length} filters: choose one (the CSV has no filter column).`;
  const shown = csvCurves(curves, c.filter);
  if (!shown.length) return 'No measurements to export.';
  if (!c.allCurves && !c.keys.length) return 'Tick at least one curve.';
  if (dest === 'file' && !isAbsolute(path)) return path.trim() ? 'The file must be an absolute path.' : 'Choose the file to write.';
  return null;
}

/** `<object>_<filter>_photometry.csv` (the server's default name for A79). */
export function csvDefaultName(object: string | null, filter: string | null): string {
  const obj = (object ?? 'curves').trim().replace(/\s+/g, '_').replace(/[^A-Za-z0-9_+-]/g, '') || 'curves';
  return `${obj}${filter ? `_${filter}` : ''}_photometry.csv`;
}

/** The count line of the CSV dialog: "7 curves · 1 365 points". */
export function csvCountText(curves: readonly CurveRef[]): string {
  const pts = curves.reduce((a, c) => a + c.n, 0);
  return `${int(curves.length)} ${curves.length === 1 ? 'curve' : 'curves'} · ${int(pts)} ${pts === 1 ? 'point' : 'points'}`;
}

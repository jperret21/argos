/**
 * Live photometry in words and rows (wave 5), pure and tested without a browser: the
 * Photometry card's lines, the Ensemble table's rows and TSV, the Variables tab's filter
 * and the Field band's live status.
 *
 * Texts that Qt shows are kept word for word where the spec says "exact" (08 1.6 #4, 1.13):
 * the ensemble verdicts and per-star labels of comparison_table.py:30-80, the count line
 * of comparison_table.py:179-190, the Variables filter of variable_table.py:39-50 and
 * 126-160. Every number comes from the server (argos/core, the Qt code): the client only
 * selects and formats; the check star's trailing statistics are a display of the points
 * the server sent (D10).
 */

import { DASH, fixed, MINUS, signed } from '../../format/number';
import type { Curve, EntryStatus, FieldVariable, LcPoint, LiveStatus, QualityEntry, QualityReport, Role, TargetStar } from './types';

// -- Curves -----------------------------------------------------------------------------------

const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/** The curve of a set star: by its key, else Qt's key (AUID, else the display name). */
export function curveFor(curves: readonly Curve[], star: Pick<TargetStar, 'key' | 'auid' | 'display_name' | 'name'>): Curve | null {
  const byKey = curves.find((c) => c.star_key && c.star_key === star.key);
  if (byKey) return byKey;
  const qtKey = star.auid || star.display_name || star.name;
  return curves.find((c) => c.key === qtKey || c.key === star.key) ?? null;
}

/** The newest point with a magnitude (a ratio-only point has none). */
export function latestMag(curve: Curve | null): LcPoint | null {
  if (!curve) return null;
  for (let i = curve.points.length - 1; i >= 0; i--) if (finite(curve.points[i].mag)) return curve.points[i];
  return null;
}

/** Catalogue V of a set star (VSP `mags.V`), for check − catalogue V (D10). */
export function catalogV(star: Pick<TargetStar, 'mags'> | null | undefined, curve?: Curve | null): number | null {
  if (curve && finite(curve.catalogue_v)) return curve.catalogue_v;
  const m = (star?.mags ?? null) as Record<string, unknown> | null;
  const v = m?.V ?? m?.v;
  return finite(v) ? v : null;
}

export interface TrailingStats {
  /** Points in the window (at most `n`). */
  n: number;
  /** Mean of mag − offset over the window. */
  mean: number | null;
  /** Sample standard deviation (n − 1) over the window: the check star's scatter. */
  sd: number | null;
}

/**
 * Trailing statistics of the newest `n` usable points (finite magnitude, not saturated),
 * of `mag − offset` (offset = catalogue V for the check star: check − catalogue V, D10).
 * The band of the light curve uses the same 15-point window.
 */
export function trailingStats(curve: Curve | null, offset = 0, n = 15): TrailingStats {
  const ys: number[] = [];
  const pts = curve?.points ?? [];
  for (let i = pts.length - 1; i >= 0 && ys.length < n; i--) {
    const p = pts[i];
    if (finite(p.mag) && !p.saturated) ys.push(p.mag - offset);
  }
  if (!ys.length) return { n: 0, mean: null, sd: null };
  const mean = ys.reduce((s, y) => s + y, 0) / ys.length;
  // No spread under 3 values: the plot's trailing band's rule (trailing.ts), so the card and the
  // plot never disagree on whether the check has a σ.
  const sd = ys.length > 2 ? Math.sqrt(ys.reduce((s, y) => s + (y - mean) ** 2, 0) / (ys.length - 1)) : null;
  return { n: ys.length, mean, sd };
}

/** Points with a magnitude (the curve's length in the observer's sense). */
export function measuredCount(curve: Curve | null): number {
  return curve ? curve.points.reduce((n, p) => n + (finite(p.mag) ? 1 : 0), 0) : 0;
}

// -- Ensemble verdict (comparison_table.py:30-56, quality.py:76-98) ----------------------------

/** Qt's verdict words (comparison_table.py `_SELECTION_VERDICTS`). */
export const SELECTION_VERDICTS: Record<string, string> = {
  insufficient_data: 'insufficient data',
  not_ready: 'not ready: fewer than 3 stable comparisons',
  live_preview_consistent: 'consistent in live preview',
};

export type VerdictTone = 'idle' | 'ok' | 'warn';

export interface Verdict {
  /** "consistent in live preview" (never "calibrated", 08 P15). */
  words: string;
  /** "4 of 5 stable". */
  counts: string | null;
  tone: VerdictTone;
  /** The report's caveat, verbatim. */
  note: string;
  /** "Ensemble: consistent in live preview." + the note (Qt's hint line). */
  line: string;
}

export function minPoints(report: QualityReport | null): number {
  const v = report?.criteria?.min_points;
  return finite(v) ? Math.round(v) : 10;
}

/** The ensemble verdict of a report; null without one (Qt shows nothing then). */
export function verdict(report: QualityReport | null): Verdict | null {
  const status = report?.selection_status;
  if (!status) return null;
  const words = SELECTION_VERDICTS[String(status)] ?? String(status).replaceAll('_', ' ');
  const note = String(report?.scientific_note ?? '').trim();
  const entries = report?.comparison_stars ?? [];
  const stable = entries.filter((e) => e.status === 'stable').length;
  const counts = entries.length ? `${stable} of ${entries.length} stable` : null;
  const tone: VerdictTone = status === 'live_preview_consistent' ? 'ok' : status === 'not_ready' ? 'warn' : 'idle';
  return { words, counts, tone, note, line: `Ensemble: ${words}.${note ? ` ${note}` : ''}` };
}

/** Qt's per-star labels (comparison_table.py `_quality_values`). */
export function statusLabel(status: EntryStatus | string | null | undefined, min = 10): string {
  const s = String(status || 'insufficient_data');
  const labels: Record<string, string> = {
    stable: 'Stable',
    unstable: 'Unstable',
    noisy: 'Noisy',
    insufficient_data: `Waiting for ${min} points`,
  };
  if (labels[s]) return labels[s];
  const t = s.replaceAll('_', ' ');
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** The table's tone for a per-star status (the label always carries the meaning). */
export function statusTone(status: string | null | undefined): 'ok' | 'warn' | 'idle' {
  return status === 'stable' ? 'ok' : status === 'unstable' || status === 'noisy' ? 'warn' : 'idle';
}

/** The report's entry for a set star: Qt keys it by AUID, else the display name. */
export function entryFor(report: QualityReport | null, star: Pick<TargetStar, 'key' | 'auid' | 'display_name' | 'name'>): QualityEntry | null {
  const entries = report?.comparison_stars ?? [];
  const byKey = entries.find((e) => e.star_key && e.star_key === star.key);
  if (byKey) return byKey;
  const k = star.auid || star.display_name || star.name;
  return entries.find((e) => e.key === k || (e.auid || e.name) === k) ?? null;
}

// -- Count line (comparison_table.py:179-190) ----------------------------------------------------

const hasMags = (s: Pick<TargetStar, 'mags'>) => !!s.mags && Object.keys(s.mags as object).length > 0;

/** The Qt count line under the ensemble, word for word. */
export function countLine(stars: readonly TargetStar[]): string {
  const comps = stars.filter((s) => s.role === 'comparison');
  const calibrated = comps.filter(hasMags).length;
  const manual = comps.length - calibrated;
  if (!comps.length) return 'No comparison stars — refresh the catalogue after a successful solve.';
  if (manual) return `${calibrated} calibrated comparison(s) · ${manual} uncalibrated manual star(s)`;
  return `${calibrated} calibrated comparison star(s)`;
}

/** The card's short split: "5 (VSP 4, manual 1)". */
export function comparisonSplit(stars: readonly TargetStar[]): { n: number; text: string } {
  const comps = stars.filter((s) => s.role === 'comparison');
  const vsp = comps.filter((s) => (s.source ?? '').toLowerCase().startsWith('vsp') || (hasMags(s) && !!s.chart_id)).length;
  const other = comps.length - vsp;
  const parts = [vsp ? `VSP ${vsp}` : null, other ? `manual ${other}` : null].filter(Boolean);
  return { n: comps.length, text: comps.length ? `${comps.length}${parts.length ? ` (${parts.join(', ')})` : ''}` : 'none' };
}

// -- Ensemble rows ----------------------------------------------------------------------------------

export interface EnsembleRow {
  key: string;
  role: Role;
  name: string;
  auid: string | null;
  /** Catalogue V and B−V (VSP). */
  v: number | null;
  bv: number | null;
  source: string;
  mags: string;
  ra_hours: number | null;
  dec_deg: number | null;
  /** Leave-one-out samples, scatter and median formal error (the report's). */
  n: number | null;
  scatter: number | null;
  formal: number | null;
  status: string;
  label: string;
  tone: 'ok' | 'warn' | 'idle';
  /** Its newest leave-one-out magnitude (against the other comparisons) and error. */
  lastMag: number | null;
  lastErr: number | null;
  /**
   * Leave-one-out residual: that magnitude minus its catalogue V (mag). Near 0 for a good
   * comparison; a drift says it disagrees with the rest of the ensemble.
   */
  residual: number | null;
  /** Its newest leave-one-out point is from the newest measured frame (false: not measured then). */
  onLastFrame: boolean | null;
  /** The field's words for this star (Δ(B−V), far, clipped, blended, "variable?"). */
  flags: string[];
  /** Reference frame px when in the frame (for the image link). */
  x: number | null;
  y: number | null;
}

/**
 * One row per comparison of the set, then the check star (its own row, no verdict). With
 * `curves`, the check row is filled from its curve: N = measured points, Scatter = σ of all its
 * unsaturated points, its newest calibrated magnitude, O − C = mean check − V of the last 15.
 */
export function ensembleRows(
  stars: readonly TargetStar[],
  report: QualityReport | null,
  opts: { flagsOf?: (s: TargetStar) => string[]; lastJd?: number | null; curves?: readonly Curve[] } = {},
): EnsembleRow[] {
  const min = minPoints(report);
  const rows: EnsembleRow[] = [];
  // The comparisons in the set's order, then the check star(s).
  const ordered = [...stars.filter((s) => s.role === 'comparison'), ...stars.filter((s) => s.role === 'check')];
  for (const s of ordered) {
    const e = s.role === 'comparison' ? entryFor(report, s) : null;
    const m = (s.mags ?? {}) as Record<string, unknown>;
    const v = finite(m.V) ? m.V : finite(m.v) ? m.v : null;
    const b = finite(m.B) ? m.B : finite(m.b) ? m.b : null;
    const flags = (opts.flagsOf?.(s) ?? []).filter((f, i, a) => a.indexOf(f) === i);
    let last: { mag: number | null; mag_err: number | null; jd_utc: number } | null = e?.last ?? null;
    let check: { n: number; scatter: number | null; mean: number | null } | null = null;
    if (s.role === 'check' && opts.curves) {
      const c = curveFor(opts.curves, s);
      const pts = (c?.points ?? []).filter((p) => finite(p.mag) && !p.saturated);
      const mags = pts.map((p) => p.mag as number);
      const mean = mags.length ? mags.reduce((a, b) => a + b, 0) / mags.length : 0;
      const sd = mags.length > 2 ? Math.sqrt(mags.reduce((a, b) => a + (b - mean) ** 2, 0) / (mags.length - 1)) : null;
      const newest = c ? latestMag(c) : null;
      if (newest) last = { mag: newest.mag, mag_err: newest.mag_err, jd_utc: newest.jd_utc };
      check = { n: measuredCount(c), scatter: sd, mean: v !== null ? trailingStats(c, v).mean : null };
    }
    const lastMag = last && finite(last.mag) ? last.mag : null;
    rows.push({
      key: s.key,
      role: s.role,
      name: s.display_name || s.name || s.auid || s.key,
      auid: s.auid || null,
      v,
      bv: v !== null && b !== null ? b - v : null,
      source: s.source || 'manual',
      mags: Object.entries(m)
        .filter(([, x]) => finite(x))
        .map(([band, x]) => `${band} ${(x as number).toFixed(2)}`)
        .join('  ') || DASH,
      ra_hours: finite(s.ra_hours) ? s.ra_hours : finite(s.ra_deg) ? s.ra_deg / 15 : null,
      dec_deg: finite(s.dec_deg) ? s.dec_deg : null,
      n: s.role === 'comparison' ? (e && finite(e.n_valid) ? e.n_valid : null) : (check?.n ?? null),
      scatter: e && finite(e.scatter_mag) ? e.scatter_mag : (check?.scatter ?? null),
      formal: e && finite(e.median_formal_error_mag) ? e.median_formal_error_mag : null,
      status: s.role === 'check' ? 'check' : (e?.status ?? 'none'),
      label: s.role === 'check' ? 'Check star' : e ? statusLabel(e.status, min) : 'Waiting for data',
      tone: s.role === 'check' ? 'idle' : statusTone(e?.status),
      lastMag,
      lastErr: last && finite(last.mag_err) ? last.mag_err : null,
      residual: check ? check.mean : lastMag !== null && v !== null ? lastMag - v : null,
      onLastFrame: last && finite(opts.lastJd) ? Math.abs(last.jd_utc - opts.lastJd) < 1e-9 : null,
      flags,
      x: finite(s.x) ? s.x : null,
      y: finite(s.y) ? s.y : null,
    });
  }
  return rows;
}

/** Qt's Copy TSV columns (comparison_table.py:27-28), then the web's live columns. */
export const ENSEMBLE_TSV_HEADERS = [
  'Name',
  'AUID',
  'RA (J2000)',
  'Dec (J2000)',
  'Catalogue mags',
  'Source',
  'Samples',
  'Scatter (mag)',
  'Formal error (mag)',
  'Live status',
  'Role',
  'Leave-one-out mag',
  'Leave-one-out error (mag)',
  'Residual vs catalogue V (mag)',
  'Flags',
] as const;

/** The table as TSV (Qt's columns first, so a Qt user's paste lands in the same columns). */
export function ensembleTsv(rows: readonly EnsembleRow[], fmt: { ra: (h: number) => string; dec: (d: number) => string }): string {
  const lines = [ENSEMBLE_TSV_HEADERS.join('\t')];
  for (const r of rows) {
    lines.push(
      [
        r.name,
        r.auid ?? DASH,
        r.ra_hours === null ? DASH : fmt.ra(r.ra_hours),
        r.dec_deg === null ? DASH : fmt.dec(r.dec_deg),
        r.mags,
        r.source,
        r.n === null ? DASH : String(r.n),
        r.scatter === null ? DASH : r.scatter.toFixed(4),
        r.formal === null ? DASH : r.formal.toFixed(4),
        r.label,
        r.role,
        r.lastMag === null ? '' : r.lastMag.toFixed(4),
        r.lastErr === null ? '' : r.lastErr.toFixed(4),
        r.residual === null ? '' : r.residual.toFixed(4),
        r.flags.join(', '),
      ].join('\t'),
    );
  }
  return lines.join('\n');
}

/** A residual in magnitudes, signed, 3 decimals ("+0.012", U+2212); a dash when unknown. */
export function residualText(d: number | null): string {
  return d === null ? DASH : signed(d, 3);
}

// -- Variables (variable_table.py:39-50, 126-160) ------------------------------------------------

/** Forgiving designation matching: "XX Cyg" matches "xxcyg". */
export function normalised(text: string): string {
  return String(text).toLowerCase().replace(/[^a-z0-9]/g, '');
}

/** The bright end of a VSX range text ("11.2 - 12.1 V" -> 11.2), as Qt reads it. */
export function brightestOf(text: string | null | undefined): number | null {
  const m = /[-+]?\d+(?:\.\d+)?/.exec(String(text ?? ''));
  return m ? parseFloat(m[0]) : null;
}

/**
 * Qt's filter: designation or type contains the query (normalised), brightest magnitude at
 * or brighter than the limit (0 or null: any; a star without a range is then left out).
 */
export function filterVariables(rows: readonly FieldVariable[], query: string, magLimit: number | null): FieldVariable[] {
  const needle = normalised(query);
  return rows.filter((r) => {
    if (needle && !normalised(`${r.name} ${r.var_type ?? ''}`).includes(needle)) return false;
    if (magLimit !== null && magLimit > 0) {
      const b = r.brightest_mag ?? brightestOf(r.mag_text);
      if (b === null || b > magLimit) return false;
    }
    return true;
  });
}

/** "3 of 12 stars" (Qt's count label; the noun follows the total). */
export function variablesCount(kept: number, total: number): string {
  return `${kept} of ${total} star${total !== 1 ? 's' : ''}`;
}

// -- The live status line (08 2.3 C sub-states) ---------------------------------------------------

/** The systematic floor needs 10 valid points (uncertainty.py:76, estimate_systematic_floor). */
export const FLOOR_POINTS = 10;

export interface StatusInput {
  /** WS `photometry`. */
  status: LiveStatus | null;
  connected: boolean;
  solved: boolean;
  hasTarget: boolean;
  comparisons: number;
  /** The target's points with a magnitude. */
  points: number;
}

export interface StatusLine {
  text: string;
  tone: 'idle' | 'busy' | 'ok' | 'warn';
  icon: string | null;
}

/**
 * One line for the Field band and the card (08 2.3 C, the server's `photometry` state and
 * reason, acquisition_engine.py:1604-1617): the server's own sentence for a skipped frame,
 * else the state in the spec's words.
 */
/** The one instruction for an empty set (card, Light curve tab). */
export const PICK_TARGET = 'Pick a target: click its circle on the image, or Set as target in Variables.';

export function statusLine(i: StatusInput): StatusLine {
  const st = i.status;
  if (!i.connected) return { text: 'Server not connected', tone: 'idle', icon: null };
  // The set (its own event) is fresher than the last attempt's status: a target chosen after
  // the last solution leaves the status at `off` until the next one.
  if (!i.hasTarget) return { text: 'No target', tone: 'idle', icon: 'target-star' };
  if (!i.solved || (st?.state === 'waiting' && !i.points)) return { text: 'Waiting for a solved full-resolution frame.', tone: 'idle', icon: 'plate-solve' };
  if (!i.comparisons || st?.reason === 'no_comparison') {
    return { text: 'No comparison stars — refresh the catalogue after a successful solve.', tone: 'warn', icon: 'comparison-star' };
  }
  if (st?.state === 'skipped') {
    const why = st.message?.trim() || (st.reason === 'no_epoch' ? 'Photometry skipped: the frame has no exposure time (DATE-OBS/EXPTIME).' : 'No point on the last frame: neither a magnitude nor a flux ratio could be measured.');
    return { text: why, tone: 'warn', icon: 'attention' };
  }
  if (!i.points) return { text: 'Measuring: no point yet; the next solution measures the set.', tone: 'busy', icon: 'photometry' };
  const floor = i.points < FLOOR_POINTS ? `, uncertainty floor after ${FLOOR_POINTS}` : '';
  return { text: `Measuring: ${i.points} point${i.points === 1 ? '' : 's'}${floor}.`, tone: 'ok', icon: 'photometry' };
}

/** A magnitude difference "check − V" in the card ("+0.012", U+2212 for negatives). */
export function offsetText(v: number | null): string {
  return v === null ? DASH : signed(v, 3);
}

/** A scatter "0.0123" (4 decimals as in Qt) or a dash. */
export function scatterText(v: number | null): string {
  return v === null ? DASH : fixed(v, 4);
}

export { MINUS };

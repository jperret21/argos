/**
 * What the R1 rail cards say (pure, tested): the Selected point card (07 §2.4 "Selection
 * model"), the Ensemble card and drawer tab (D5; 08 1.6 #3, 1.13), the AAVSO export card's
 * pre-checks (07 E13, WF-E; README Q-R2, Q-R3; S11, S53).
 *
 * Formats (BRAND 5, Q-R9): UTC to the second, JD and BJD_TDB to 5 decimals, magnitudes
 * 3 decimals ± error, scatter and formal errors 4 decimals.
 */

import { DASH, fixed, int, mag, signed } from '../format/number';
import { julian } from '../format/time';
import { FLAG_RECORDER, FLAG_SATURATED, FLAG_SUSPECT } from '../charts/uplot/markers';
import { magBaselineOf } from '../charts/lightcurve/facets';
import { catalogueMag, type LiveCurveStore, type Role, type StarCurve, type TargetStarLike } from '../charts/lightcurve/store';
import { frameAt, type FrameRow } from './frames/frames';
import { extraRow, flagWord, qualityOf, seriesLabel, statusOk, statusWord, type CurveExtras, type QualityReport } from './source';
import { cellStats, starOf } from './wall';

const inFilter = (s: StarCurve, filter: string | null) => !filter || s.filter === null || s.filter === filter;

// -- Selected point --------------------------------------------------------------------------------

export interface StarAt {
  /** The wall cell's id (`${role}:${star}`): a row click scrolls to it. */
  cellId: string;
  role: Role;
  name: string;
  /** As its cell draws it: "7.512 ± 0.012", "+0.008 ± 0.009", "Δ −0.004 ± 0.011". */
  value: string;
  flags: string[];
}

export interface PointInfo {
  t: number;
  utc: string;
  jd: string;
  /** The target's BJD_TDB (per star: the check's differs by seconds); null without a site. */
  bjd: string | null;
  stars: StarAt[];
  /** The target's point: formal error, σ_sys, comparisons used, airmass, flags. */
  formal: string | null;
  syst: string | null;
  comps: string | null;
  airmass: string | null;
  /** Where the airmass shown comes from: the FITS header (the mount's) or the photometry CSV. */
  airmassFrom: 'header' | 'csv' | null;
  /** The other source's value when it differs by 0.01 or more (a wrong Settings site), else null. */
  airmassOther: string | null;
  flags: string;
  frame: FrameRow | null;
  /** Point time − frame start, s (the point is dated at mid-exposure). */
  dt: number | null;
  /** Why the frame cannot open (missing, none, imported file), else null. */
  frameReason: string | null;
}

function rowAt(s: StarCurve, t: number, tol: number): number {
  const i = s.cols.nearest(t);
  return i >= 0 && Math.abs(s.cols.t[i] - t) <= tol ? i : -1;
}

function flagWords(f: number): string[] {
  const out: string[] = [];
  if (f & FLAG_SATURATED) out.push('saturated');
  if (f & FLAG_SUSPECT) out.push('suspect');
  return out;
}

/** A69's display flags of a curve's point at time t, in words ("ZP outlier", "low SNR"). */
function extraWords(x: CurveExtras | undefined, t: number, tol = 1): string[] {
  const r = extraRow(x, t, tol);
  return r >= 0 ? x!.words[r].map(flagWord) : [];
}

/**
 * Every star of the filter at time t (within `tol` s), the target's details and the frame it
 * was measured on. Null when no star has a point there.
 */
export function pointInfo(
  store: LiveCurveStore,
  t: number,
  opts: {
    filter: string | null;
    frames: readonly FrameRow[];
    tol?: number;
    imported?: boolean;
    filtersLoaded?: number;
    /** A69's header airmass and display flags, by curve key. */
    extras?: ReadonlyMap<string, CurveExtras>;
    /** A68 `airmass_source`: "header" when the Settings site was wrong (the CSV airmass is wrong). */
    airmassSource?: 'csv' | 'header';
  },
): PointInfo | null {
  const tol = opts.tol ?? 1;
  const stars: StarAt[] = [];
  let anchor: { s: StarCurve; i: number } | null = null;
  const order: Record<Role, number> = { target: 0, check: 1, comparison: 2 };
  const curves = [...store.stars.values()].filter((s) => inFilter(s, opts.filter) && s.n).sort((a, b) => order[a.role] - order[b.role]);
  let target: { s: StarCurve; i: number } | null = null;
  for (const s of curves) {
    const i = rowAt(s, t, tol);
    if (i < 0) continue;
    const c = s.cols;
    if (!anchor) anchor = { s, i };
    if (s.role === 'target' && !target) target = { s, i };
    let value: string;
    if (s.role === 'comparison') {
      const d = c.mag[i] - magBaselineOf(s);
      value = Number.isFinite(d) ? `Δ ${signed(d, 3)} ± ${fixed(c.err[i], 3)}` : DASH;
    } else if (s.role === 'check' && s.catalogue !== null) {
      const d = c.mag[i] - s.catalogue;
      value = Number.isFinite(d) ? `${signed(d, 3)} ± ${fixed(c.err[i], 3)}` : DASH;
    } else value = Number.isFinite(c.mag[i]) ? mag(c.mag[i], c.err[i]) : DASH;
    stars.push({ cellId: `${s.role}:${starOf(s)}`, role: s.role, name: seriesLabel(s.name, s.filter, opts.filtersLoaded ?? 0), value, flags: [...flagWords(c.flags[i]), ...extraWords(opts.extras?.get(s.key), c.t[i])] });
  }
  if (!anchor) return null;
  const a = target ?? anchor;
  const c = a.s.cols;
  const i = a.i;
  const tt = c.t[i];
  const frame = opts.frames.length ? frameAt(opts.frames, tt) : null;
  // Airmass: the FITS header's (the mount's) when the server says the CSV's is wrong, or when
  // the CSV has none; the CSV's otherwise (the AAVSO AMASS column, A77).
  const x = opts.extras?.get(a.s.key);
  const xr = extraRow(x, tt, opts.tol ?? 1);
  const hdr = xr >= 0 ? x!.headerAirmass[xr] : typeof frame?.header?.airmass === 'number' ? frame.header.airmass : NaN;
  const csv = c.airmass[i];
  const useHeader = Number.isFinite(hdr) && (opts.airmassSource === 'header' || !Number.isFinite(csv));
  const am = useHeader ? hdr : csv;
  const other = useHeader ? csv : hdr;
  const frameReason = opts.imported
    ? 'An imported file has no frames'
    : !frame
      ? 'No frame of the session at this time'
      : frame.missing
        ? `File not found: ${frame.filename}`
        : null;
  return {
    t: tt,
    utc: new Date(Math.round(tt * 1000)).toISOString().slice(0, 19).replace('T', ' '),
    jd: julian(c.jd[i]),
    bjd: Number.isFinite(c.bjd[i]) ? julian(c.bjd[i]) : null,
    stars,
    formal: Number.isFinite(c.formal[i]) ? fixed(c.formal[i], 4) : null,
    syst: Number.isFinite(c.syst[i]) ? fixed(c.syst[i], 4) : null,
    comps: Number.isFinite(c.comps[i]) ? int(c.comps[i]) : null,
    airmass: Number.isFinite(am) ? fixed(am, 3) : null,
    airmassFrom: Number.isFinite(am) ? (useHeader ? 'header' : 'csv') : null,
    airmassOther: Number.isFinite(am) && Number.isFinite(other) && Math.abs(other - am) >= 0.01 ? fixed(other, 3) : null,
    flags: [...flagWords(c.flags[i]), ...extraWords(x, tt, opts.tol)].join(', ') || '–',
    frame,
    dt: frame && frame.t !== null ? tt - frame.t : null,
    frameReason,
  };
}

// -- Ensemble -----------------------------------------------------------------------------------------

export interface EnsembleRow {
  cellId: string;
  key: string;
  name: string;
  auid: string | null;
  /** Points in its curve (the filter shown). */
  n: number;
  /** The vetting's valid points, scatter, median formal error and status (report), else estimated. */
  nValid: number | null;
  scatter: number | null;
  medianErr: number | null;
  status: string;
  ok: boolean;
  /** "report" (photometry_quality.json) or "estimate" (computed here, no report). */
  from: 'report' | 'estimate' | null;
  /** Catalogue magnitude in the band it calibrates with. */
  catMag: number | null;
}

export function ensembleRows(store: LiveCurveStore, filter: string | null, report: QualityReport | null, targets: readonly TargetStarLike[] = [], band: string | null = null): EnsembleRow[] {
  const rows: EnsembleRow[] = [];
  for (const s of store.stars.values()) {
    if (s.role !== 'comparison' || !inFilter(s, filter)) continue;
    const st = cellStats(s, report);
    const v = qualityOf(report, s);
    const t = targets.find((x) => (!!x.auid && x.auid === s.auid) || x.name === s.name || x.display_name === s.name);
    rows.push({
      cellId: `comparison:${starOf(s)}`,
      key: s.key,
      name: s.name,
      auid: s.auid || null,
      n: s.n,
      nValid: v ? v.n_valid : null,
      scatter: st.scatter,
      medianErr: st.medianErr,
      status: v ? statusWord(v.status) : report ? 'Not vetted' : '—',
      ok: v ? statusOk(v.status) : true,
      from: st.scatterFrom,
      catMag: t ? catalogueMag(t.mags, band) : null,
    });
  }
  return rows;
}

/** The report's verdict in words ("live_preview_consistent" → "Live preview consistent"). */
export function verdictText(report: QualityReport | null): string {
  if (!report) return 'No vetting report';
  const ok = report.stars.filter((s) => statusOk(s.status)).length;
  return `${statusWord(report.selection_status)} · ${ok}/${report.stars.length} stable`;
}

// -- AAVSO pre-checks ---------------------------------------------------------------------------------

export interface AavsoCheck {
  id: 'obscode' | 'target' | 'filter' | 'band' | 'chart' | 'amass' | 'flagged' | 'check' | 'excluded' | 'rows';
  /** ok: nothing to do; warn: allowed with a word; block: the export cannot run. */
  level: 'ok' | 'warn' | 'block';
  label: string;
  value: string;
  detail?: string;
}

export interface AavsoInput {
  store: LiveCurveStore;
  filter: string | null;
  filters: readonly string[];
  obscode: string | null;
  /** photometry.default_band ("TG"): FILT unless the dialog changes it. */
  band: string | null;
  /** The frames' filter names ("IR": 195). */
  frameFilters: Record<string, number>;
  chartId: string | null;
  wheel?: readonly string[];
  /** The session's site check found the Settings site wrong (A68 `airmass_source` "header"): AMASS is wrong. */
  airmassWrong?: boolean;
}

/** S60: a point dated before this is undated (JD 0 from a pre-0.5.0 batch re-run; exports.py). */
export const MIN_AAVSO_JD = 2_400_000;

/**
 * S66: the AAVSO pre-check's "AMASS wrong site". The curves' airmass is wrong only while the
 * session's site check says the Settings site was wrong (A68 `airmass_source` "header") and the
 * curves still carry the CSV's airmass: once the server put each frame's header AIRMASS in the
 * column (A69 `airmass_column` "header", `airmassFixed`) there is nothing to warn about.
 */
export function airmassWrongSite(airmassSource: 'csv' | 'header', airmassFixed: boolean): boolean {
  return airmassSource === 'header' && !airmassFixed;
}

/**
 * What the card shows before the dialog (the dialog's preview, A77, is the final word):
 * target-role curves only, one filter at a time (S53), saturated and suspect points left
 * out (Q-R3), the observer code required (Q-R2), FILT against the session's filter.
 */
export function aavsoChecks(o: AavsoInput): { checks: AavsoCheck[]; rows: number; blocked: string | null } {
  const checks: AavsoCheck[] = [];
  const targets = [...o.store.stars.values()].filter((s) => s.role === 'target' && inFilter(s, o.filter));
  const check = [...o.store.stars.values()].find((s) => s.role === 'check' && inFilter(s, o.filter)) ?? null;
  let rows = 0;
  let sat = 0;
  let noDet = 0;
  let sus = 0;
  let nonfinite = 0;
  let undated = 0;
  let flagged = 0;
  // The export's order (exports.py `_counts`, write_aavso): undated (S60), no magnitude or
  // error, saturated, suspect; the rest are rows.
  for (const s of targets) {
    const c = s.cols;
    for (let i = 0; i < c.n; i++) {
      if (!(Number.isFinite(c.jd[i]) && c.jd[i] >= MIN_AAVSO_JD)) undated++;
      else if (!(Number.isFinite(c.mag[i]) && Number.isFinite(c.err[i]))) nonfinite++;
      else if (c.flags[i] & FLAG_SATURATED) sat++;
      // S67: a suspect point of a recorder-flagged frame (no detection), counted apart.
      else if (c.flags[i] & FLAG_SUSPECT && c.flags[i] & FLAG_RECORDER) noDet++;
      else if (c.flags[i] & FLAG_SUSPECT) sus++;
      else {
        rows++;
        // Written as the fixed Qt writes them, until the owner decides (no-detection frames).
        if (c.flags[i] & FLAG_RECORDER) flagged++;
      }
    }
  }
  const code = (o.obscode ?? '').trim();
  // Q-R2 / S11: empty or Qt's "XXX" placeholder is no observer code (exports.py obscode_is_set).
  checks.push(code && code.toUpperCase() !== 'XXX' ? { id: 'obscode', level: 'ok', label: 'OBSCODE', value: code } : { id: 'obscode', level: 'block', label: 'OBSCODE', value: code ? `${code} · placeholder` : 'unset', detail: 'Set your AAVSO observer code in Settings › Observer & site' });
  checks.push(
    targets.length
      ? { id: 'target', level: 'ok', label: 'Target', value: `${targets.map((s) => s.name).join(', ')} · ${int(rows)} rows` }
      : { id: 'target', level: 'block', label: 'Target', value: 'none', detail: 'No target-role curve in this filter: comparisons and the check are never exported' },
  );
  if (o.filters.length > 1) checks.push({ id: 'filter', level: 'ok', label: 'Filter', value: `${o.filter ? o.filter.toUpperCase() : DASH} · one filter per file (${o.filters.length} loaded)` });
  const frameFilters = Object.keys(o.frameFilters).filter((f) => f && f !== '—');
  const band = o.band ?? '';
  const sessionF = frameFilters.join(', ');
  // FILT is the configured band; the dialog's preview (A77) compares it with the frames'
  // filter (Q-R2): the card only shows both, side by side.
  checks.push(
    band
      ? { id: 'band', level: 'ok', label: 'FILT', value: sessionF ? `${band} · frames ${sessionF}` : band, detail: 'The export dialog checks the band against the frames’ filter' }
      : { id: 'band', level: 'warn', label: 'FILT', value: sessionF ? `unset · frames ${sessionF}` : 'unset', detail: 'Choose the band in the export dialog' },
  );
  checks.push(o.chartId ? { id: 'chart', level: 'ok', label: 'CHART', value: o.chartId } : { id: 'chart', level: 'warn', label: 'CHART', value: 'na', detail: 'No single VSP chart for the comparisons' });
  if (o.airmassWrong) checks.push({ id: 'amass', level: 'warn', label: 'AMASS', value: 'wrong site', detail: 'The Settings site was not where the telescope was during this run: the curves’ airmass, written as AMASS, is wrong (the FITS header AIRMASS is right)' });
  if (flagged) checks.push({ id: 'flagged', level: 'warn', label: 'Flagged', value: `${int(flagged)} point${flagged === 1 ? '' : 's'} · written`, detail: 'The run’s flight recorder marks these frames as no detection or a zero point more than 1 mag off: they are written unless you leave them out; the dialog names them' });
  checks.push(check ? { id: 'check', level: 'ok', label: 'Check', value: check.name } : { id: 'check', level: 'warn', label: 'Check', value: 'none · KNAME / KMAG na', detail: 'No check star in this source' });
  if (sat || noDet || sus || nonfinite || undated)
    checks.push({
      id: 'excluded',
      level: 'warn',
      label: 'Left out',
      value: [sat ? `${int(sat)} saturated` : '', noDet ? `${int(noDet)} suspect (no detection)` : '', sus ? `${int(sus)} suspect` : '', nonfinite ? `${int(nonfinite)} without a magnitude` : '', undated ? `${int(undated)} undated` : ''].filter(Boolean).join(' · '),
      detail: 'Saturated, suspect, undated points and points without a magnitude are never exported (the file’s note says how many)',
    });
  if (targets.length && !rows) checks.push({ id: 'rows', level: 'block', label: 'Rows', value: '0', detail: 'Every point is left out (flagged, undated or without a magnitude)' });
  const blocked = checks.find((c) => c.level === 'block');
  return { checks, rows, blocked: blocked ? (blocked.detail ?? blocked.label) : null };
}

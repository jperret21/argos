/**
 * The words of LightCurvePlot (pure, tested): the single readout of every
 * series at one time (hover, selection or the newest frame) and the "Copy
 * data (TSV)" table (PROPOSAL 3.2: UTC, JD, BJD, values, errors, flags).
 *
 * Times: UTC to the second, JD and BJD_TDB to 5 decimals (0.86 s, BRAND 5);
 * BJD is the server's per point (none without a site: X2). The TSV keeps the
 * full precision of every number as the server sent it (the shortest
 * round-trip form, the one Python's repr writes in the Qt CSV), so a pasted
 * table compares exactly with photometry/*.csv.
 */

import { DASH, fixed, mag, signed } from '../../format/number';
import { clockUtc, julian } from '../../format/time';
import { FLAG_SATURATED, FLAG_SUSPECT } from '../uplot/markers';
import { baselineOf, type YMode } from './facets';
import type { LiveCurveStore, StarCurve } from './store';

export interface SeriesReadout {
  /** The value as plotted: "11.234 ± 0.012", "+0.012 ± 0.009", "1.0123 ± 0.0040". */
  value: string;
  /** What the value is (unit or definition), short. */
  what: string;
  flags: string[];
}

export interface PointReadout {
  t: number;
  utc: string;
  jd: string;
  /** Null when the point has no BJD (no observing site). The target's, else the check's. */
  bjd: string | null;
  /**
   * The check star's own BJD_TDB when a target row gives `bjd` and the check's differs at the
   * shown precision: BJD depends on the star's direction (6.4 s between XX Cyg and its check
   * 000-BCK-396 on 2026-09-07).
   */
  checkBjd: string | null;
  /** 1-based number of the point in the target curve, null when the target has no row there. */
  point: number | null;
  /** The frame it was measured on (/ws/frames seq), when known. */
  frameSeq: number | null;
  target: SeriesReadout | null;
  check: SeriesReadout | null;
  ensemble: SeriesReadout | null;
  airmass: string | null;
}

export function flagWords(f: number): string[] {
  const out: string[] = [];
  if (f & FLAG_SATURATED) out.push('saturated');
  if (f & FLAG_SUSPECT) out.push('suspect (hot pixel?)');
  return out;
}

/** Row of `s` at time t within `tol` seconds, or -1. */
function rowAt(s: StarCurve | null, t: number, tol: number): number {
  if (!s || !s.n) return -1;
  const i = s.cols.nearest(t);
  return i >= 0 && Math.abs(s.cols.t[i] - t) <= tol ? i : -1;
}

const fluxText = (v: number, e: number) => (Number.isFinite(e) ? `${fixed(v, 4)} ± ${fixed(e, 4)}` : fixed(v, 4));

export function readoutAt(
  store: LiveCurveStore,
  t: number,
  mode: YMode,
  keys: { target?: string | null; check?: string | null } = {},
  tol = 1,
): PointReadout | null {
  const tgt = store.primary('target', keys.target);
  const chk = store.primary('check', keys.check);
  const it = rowAt(tgt, t, tol);
  const ic = rowAt(chk, t, tol);
  const anchor = it >= 0 ? tgt!.cols : ic >= 0 ? chk!.cols : null;
  const ia = it >= 0 ? it : ic;
  if (!anchor) return null;
  const tt = anchor.t[ia];
  const jd = anchor.jd[ia];
  const bjd = anchor.bjd[ia];

  let target: SeriesReadout | null = null;
  if (it >= 0) {
    const c = tgt!.cols;
    if (mode === 'mag') target = { value: Number.isFinite(c.mag[it]) ? mag(c.mag[it], c.err[it]) : DASH, what: store.band ?? 'mag', flags: flagWords(c.flags[it]) };
    else {
      const b = baselineOf(tgt!);
      target = { value: b > 0 && Number.isFinite(c.flux[it]) ? fluxText(c.flux[it] / b, c.fluxErr[it] / b) : DASH, what: 'rel. flux', flags: flagWords(c.flags[it]) };
    }
  }
  let check: SeriesReadout | null = null;
  if (ic >= 0) {
    const s = chk!;
    const c = s.cols;
    if (mode === 'mag') {
      const v = c.mag[ic];
      const d = s.catalogue !== null ? v - s.catalogue : NaN;
      check =
        s.catalogue !== null
          ? { value: Number.isFinite(d) ? `${signed(d, 3)} ± ${fixed(c.err[ic], 3)}` : DASH, what: `check − V ${fixed(s.catalogue, 3)}`, flags: flagWords(c.flags[ic]) }
          : { value: Number.isFinite(v) ? mag(v, c.err[ic]) : DASH, what: 'check, no catalogue mag', flags: flagWords(c.flags[ic]) };
    } else {
      const b = baselineOf(s);
      check = { value: b > 0 && Number.isFinite(c.flux[ic]) ? fluxText(c.flux[ic] / b, c.fluxErr[ic] / b) : DASH, what: 'check rel. flux', flags: flagWords(c.flags[ic]) };
    }
  }
  let ensemble: SeriesReadout | null = null;
  if (it >= 0 && Number.isFinite(tgt!.cols.zp[it])) {
    // The target's ensemble zero point on that frame, and the comparisons it used.
    const c = tgt!.cols;
    const total = store.comparisons().length;
    const used = Number.isFinite(c.comps[it]) ? `${c.comps[it]}${total ? ` of ${total}` : ''} comparisons` : 'comparisons';
    const rms = Number.isFinite(c.zpRms[it]) ? ` · σ ${fixed(c.zpRms[it], 3)}` : '';
    ensemble = { value: `ZP ${fixed(c.zp[it], 3)}${rms}`, what: used, flags: [] };
  }
  const am = it >= 0 ? tgt!.cols.airmass[it] : ic >= 0 ? chk!.cols.airmass[ic] : NaN;
  return {
    t: tt,
    utc: clockUtc(tt),
    jd: julian(jd),
    bjd: Number.isFinite(bjd) ? julian(bjd) : null,
    checkBjd: it >= 0 && ic >= 0 && Number.isFinite(chk!.cols.bjd[ic]) && julian(chk!.cols.bjd[ic]) !== (Number.isFinite(bjd) ? julian(bjd) : null) ? julian(chk!.cols.bjd[ic]) : null,
    point: it >= 0 ? it + 1 : null,
    frameSeq: anchor && Number.isFinite(anchor.frameSeq[ia]) ? anchor.frameSeq[ia] : null,
    target,
    check,
    ensemble,
    airmass: Number.isFinite(am) ? fixed(am, 3) : null,
  };
}

// -- TSV ------------------------------------------------------------------------------------

export const TSV_HEADER = [
  'utc',
  'jd_utc',
  'bjd_tdb',
  'frame_seq',
  'target_mag',
  'target_mag_err',
  'target_formal_mag_err',
  'target_sigma_syst',
  'target_relative_flux',
  'target_relative_flux_err',
  'target_flags',
  'check_mag',
  'check_mag_err',
  'check_minus_catalogue',
  'check_flags',
  'zero_point',
  'zp_rms',
  'airmass',
  'comps_used',
  // The check star's own BJD_TDB (`bjd_tdb` is the target's, else the check's): last, so the
  // columns before it keep their places.
  'check_bjd_tdb',
] as const;

const full = (v: number) => (Number.isFinite(v) ? String(v) : '');
const flagCell = (f: number) => [f & FLAG_SUSPECT ? 'suspect' : '', f & FLAG_SATURATED ? 'saturated' : ''].filter(Boolean).join(',');

/** ISO 8601 UTC with milliseconds ("2026-08-29T21:34:05.123Z"). */
export function isoMs(t: number): string {
  return Number.isFinite(t) ? new Date(Math.round(t * 1000)).toISOString() : '';
}

/**
 * One row per measured frame (target and check merged by JD), oldest first. A
 * frame measured twice (two solutions) has two rows, its k-th target point
 * beside its k-th check point, as the CSVs keep both.
 */
export function curveTsv(store: LiveCurveStore, keys: { target?: string | null; check?: string | null } = {}): { text: string; rows: number } {
  const tgt = store.primary('target', keys.target);
  const chk = store.primary('check', keys.check);
  const jds = new Set<number>();
  for (const s of [tgt, chk]) if (s) for (let i = 0; i < s.n; i++) jds.add(s.cols.jd[i]);
  const lines: string[] = [TSV_HEADER.join('\t')];
  const pairs: [number, number][] = [];
  for (const jd of [...jds].sort((a, b) => a - b)) {
    const ts = tgt ? tgt.cols.rowsOfJd(jd) : [];
    const cs = chk ? chk.cols.rowsOfJd(jd) : [];
    for (let k = 0; k < Math.max(ts.length, cs.length); k++) pairs.push([ts[k] ?? -1, cs[k] ?? -1]);
  }
  for (const [it, ic] of pairs) {
    const tc = tgt?.cols;
    const cc = chk?.cols;
    const anchor = it >= 0 ? tc! : cc!;
    const ia = it >= 0 ? it : ic;
    const jd = anchor.jd[ia];
    const t = (jd - 2440587.5) * 86400;
    const cells = [
      isoMs(t),
      String(jd),
      full(anchor.bjd[ia]),
      full(anchor.frameSeq[ia]),
      it >= 0 ? full(tc!.mag[it]) : '',
      it >= 0 ? full(tc!.err[it]) : '',
      it >= 0 ? full(tc!.formal[it]) : '',
      it >= 0 ? full(tc!.syst[it]) : '',
      it >= 0 ? full(tc!.flux[it]) : '',
      it >= 0 ? full(tc!.fluxErr[it]) : '',
      it >= 0 ? flagCell(tc!.flags[it]) : '',
      ic >= 0 ? full(cc!.mag[ic]) : '',
      ic >= 0 ? full(cc!.err[ic]) : '',
      ic >= 0 && chk!.catalogue !== null ? full(cc!.mag[ic] - chk!.catalogue) : '',
      ic >= 0 ? flagCell(cc!.flags[ic]) : '',
      it >= 0 ? full(tc!.zp[it]) : '',
      it >= 0 ? full(tc!.zpRms[it]) : '',
      full(anchor.airmass[ia]),
      it >= 0 ? full(tc!.comps[it]) : '',
      ic >= 0 ? full(cc!.bjd[ic]) : '',
    ];
    lines.push(cells.join('\t'));
  }
  return { text: lines.join('\n') + '\n', rows: pairs.length };
}

/**
 * The comparison candidates table of the Field band, as data (promoted from
 * src/lab/workspace/observe/bands/FieldBand.svelte, web/lab/PROPOSAL.md 3.1 "Comparison
 * workspace" and 6, W4). Choosing comparisons is a comparison BETWEEN stars, so the guide's
 * rules are columns, never a verdict badge:
 *
 * - colour: Δ(B−V) against the target, flagged beyond 0.3 mag;
 * - distance: separation from the target, flagged beyond the observer's limit
 *   (`photometry.comparison_max_separation_arcmin`, sent with the layers; 25′ by default);
 * - linearity: the peak on the solved frame ("clipped" at the ADC's top code, "non-linear"
 *   at or above the profile's linearity / full-well threshold, the server's `saturated`;
 *   never "saturated" as a word);
 * - blending: catalogue stars inside the aperture brighter than V + 3 (`neighbours_in_aperture`);
 * - a VSX entry at the star's position: "variable?".
 *
 * A flagged cell is underlined in --warning AND says the word in the status column (never
 * colour alone); a flag most rows share is stated once in the band's note instead of
 * underlining every row (`commonFlags`). Pure, tested.
 */

import { asRole } from '../../viewer/overlay/layers';
import type { Candidate, CandidateLimits, Role, TargetStar } from './types';

/** The guide's limits (PROPOSAL 3.1; argos/core comparison rules). */
export const MAX_DELTA_BV = 0.3;
/** `photometry.comparison_max_separation_arcmin` when the layers do not say. */
export const MAX_SEP_ARCMIN = 25;
/** A set star and a candidate this close are one star (two catalogue identities). */
export const SAME_STAR_ARCSEC = 2;
/** A flag shared by more than this fraction of the rows is stated once, not underlined. */
export const COMMON_FLAG_FRACTION = 1 / 3;

/** The separation limit in force: the observer's, sent with the layers. */
export function maxSepArcmin(limits: CandidateLimits | null | undefined): number {
  const v = limits?.comparison_max_separation_arcmin;
  return typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : MAX_SEP_ARCMIN;
}
/** The ADC's top code when the frame does not say (16-bit full scale). */
export const TOP_CODE = 65535;

export type CandidateKey = 'role' | 'name' | 'v' | 'bv' | 'dbv' | 'sep' | 'peak' | 'snr' | 'nbr' | 'status';

export interface CandidateRow {
  key: string;
  name: string;
  role: Role | null;
  v: number | null;
  bv: number | null;
  /** B−V of the star minus the target's (the server's; null without the target's B−V). */
  dbv: number | null;
  sep: number | null;
  peak: number | null;
  snr: number | null;
  nbr: number | null;
  clipped: boolean;
  /** At or above the linearity / full-well threshold (not clipped). */
  nonlinear: boolean;
  /** The rules this star breaks, as words (the status column). */
  flags: string[];
  status: string;
  x: number | null;
  y: number | null;
  source: Candidate;
}

const finite = (v: number | null | undefined): v is number => typeof v === 'number' && Number.isFinite(v);

/** The star's name in the table: its AUID, else the VSP label, else its key. */
export function candidateName(c: Candidate): string {
  return c.auid?.trim() || c.label?.trim() || c.key;
}

export function candidateRow(c: Candidate, topCode: number | null = TOP_CODE, maxSep: number = MAX_SEP_ARCMIN): CandidateRow {
  const bv = finite(c.b_minus_v) ? c.b_minus_v : null;
  const dbv = finite(c.delta_b_minus_v) ? c.delta_b_minus_v : null;
  const peak = finite(c.peak_adu) ? c.peak_adu : null;
  const clipped = peak !== null && peak >= (topCode ?? TOP_CODE);
  const nonlinear = !clipped && c.saturated === true;
  const nbr = finite(c.neighbours_in_aperture) ? c.neighbours_in_aperture : null;
  const sep = finite(c.sep_arcmin) ? c.sep_arcmin : null;
  const role = asRole(c.role);
  const flags: string[] = [];
  if (clipped) flags.push('clipped');
  else if (nonlinear) flags.push('non-linear');
  if (nbr !== null && nbr > 0) flags.push('blend risk');
  if (dbv !== null && Math.abs(dbv) > MAX_DELTA_BV) flags.push('colour');
  if (sep !== null && sep > maxSep) flags.push('far');
  if (c.detected === false) flags.push('not detected');
  if (c.vsx) flags.push('variable?');
  const status = c.status?.trim() || flags.join(' · ') || '—';
  return {
    key: c.key,
    name: candidateName(c),
    role,
    v: finite(c.v_mag) ? c.v_mag : null,
    bv,
    dbv,
    sep,
    peak,
    snr: clipped ? null : finite(c.snr) ? c.snr : null,
    nbr,
    clipped,
    nonlinear,
    flags,
    status,
    x: finite(c.x) ? c.x : null,
    y: finite(c.y) ? c.y : null,
    source: c,
  };
}

export type CandidateTab = 'candidates' | 'ensemble';

/** Angular separation in arcseconds (small angles; RA in hours). */
function sepArcsec(raH1: number, dec1: number, raH2: number, dec2: number): number {
  const d2r = Math.PI / 180;
  const dRa = ((((raH1 - raH2) * 15 + 540) % 360) + 360) % 360 - 180;
  const x = dRa * Math.cos(((dec1 + dec2) / 2) * d2r);
  return Math.hypot(x, dec1 - dec2) * 3600;
}

/**
 * The role a set star gives a candidate stored under another identity (a VSP comparison given
 * its role from its VSX card is stored with the VSX name): the same position within
 * SAME_STAR_ARCSEC is the same star.
 */
export function roleByPosition(c: Candidate, stars: readonly TargetStar[]): Role | null {
  if (typeof c.ra_hours !== 'number' || typeof c.dec_deg !== 'number') return null;
  for (const s of stars) {
    const ra = typeof s.ra_hours === 'number' ? s.ra_hours : typeof s.ra_deg === 'number' ? s.ra_deg / 15 : null;
    if (ra === null || typeof s.dec_deg !== 'number') continue;
    if (sepArcsec(c.ra_hours, c.dec_deg, ra, s.dec_deg) <= SAME_STAR_ARCSEC) return asRole(s.role);
  }
  return null;
}

/** Rows of a tab: every candidate but the target, or the set's comparisons and check. */
export function candidateRows(
  list: readonly Candidate[] | null,
  tab: CandidateTab,
  topCode: number | null = TOP_CODE,
  options: { limits?: CandidateLimits | null; stars?: readonly TargetStar[] } = {},
): CandidateRow[] {
  if (!list) return [];
  const maxSep = maxSepArcmin(options.limits);
  const stars = options.stars ?? [];
  const rows = list
    .map((c) => (c.role || !stars.length ? c : { ...c, role: roleByPosition(c, stars) }))
    .filter((c) => c.role !== 'target')
    .map((c) => candidateRow(c, topCode, maxSep));
  return tab === 'candidates' ? rows : rows.filter((r) => r.role === 'comparison' || r.role === 'check');
}

/**
 * Flags shared by more than COMMON_FLAG_FRACTION of the rows (with at least three rows): the
 * band states them once ("48 of 49 beyond 60′ from the target") rather than underlining
 * almost every row, which would make the flag mean nothing.
 */
export function commonFlags(rows: readonly CandidateRow[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const r of rows) for (const f of r.flags) counts.set(f, (counts.get(f) ?? 0) + 1);
  const common = new Map<string, number>();
  if (rows.length < 3) return common;
  for (const [f, n] of counts) if (n > rows.length * COMMON_FLAG_FRACTION) common.set(f, n);
  return common;
}

/**
 * The Ensemble tab: the set's comparisons and check. A set star that is not a VSP candidate
 * (a Gaia star given a role from the image) still gets its row, with what the set knows.
 */
export function ensembleRows(
  list: readonly Candidate[] | null,
  stars: readonly TargetStar[],
  topCode: number | null = TOP_CODE,
  limits: CandidateLimits | null = null,
): CandidateRow[] {
  const rows = candidateRows(list, 'ensemble', topCode, { limits, stars });
  const have = new Set(rows.map((r) => r.key));
  const listed = rows.map((r) => r.source);
  for (const s of stars) {
    if ((s.role !== 'comparison' && s.role !== 'check') || have.has(s.key)) continue;
    // Already listed under its VSP identity (the same position).
    if (listed.some((c) => roleByPosition(c, [s]) !== null)) continue;
    const v = s.mags?.V ?? s.mags?.v ?? null;
    rows.push(
      candidateRow(
        { key: s.key, auid: s.auid, label: s.display_name ?? s.name, x: s.x ?? null, y: s.y ?? null, v_mag: v, b_minus_v: null, delta_b_minus_v: null, sep_arcmin: null, peak_adu: null, snr: null, saturated: null, neighbours_in_aperture: null, role: s.role },
        topCode,
        maxSepArcmin(limits),
      ),
    );
  }
  return rows;
}

const ROLE_ORDER: Record<string, number> = { comparison: 0, check: 1 };

function sortValue(r: CandidateRow, k: CandidateKey): number | string | null {
  switch (k) {
    case 'role':
      return r.role ? ROLE_ORDER[r.role] ?? 2 : 3;
    case 'name':
      return r.name;
    case 'dbv':
      return r.dbv === null ? null : Math.abs(r.dbv);
    case 'peak':
      // Clipped stars sort as the brightest.
      return r.clipped ? Infinity : r.peak;
    case 'status':
      return r.flags.length ? r.flags.join(' ') : null;
    default:
      return r[k];
  }
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

/** Stable sort; missing values last whatever the direction (Table rule, README 3.5). */
export function sortCandidates(rows: readonly CandidateRow[], key: CandidateKey, asc: boolean): CandidateRow[] {
  const dir = asc ? 1 : -1;
  return rows
    .map((r, i) => ({ r, i, v: sortValue(r, key) }))
    .sort((a, b) => {
      const ma = a.v === null || (typeof a.v === 'number' && Number.isNaN(a.v));
      const mb = b.v === null || (typeof b.v === 'number' && Number.isNaN(b.v));
      if (ma || mb) return ma === mb ? a.i - b.i : ma ? 1 : -1;
      const c = typeof a.v === 'number' && typeof b.v === 'number' ? a.v - b.v : collator.compare(String(a.v), String(b.v));
      return c !== 0 ? c * dir : a.i - b.i;
    })
    .map((e) => e.r);
}

/** One-row summary of the band below 150 px (the set's stars, VSP or not). */
export function ensembleSummary(
  list: readonly Candidate[] | null,
  stars: readonly TargetStar[] = [],
  limits: CandidateLimits | null = null,
): { candidates: number; comparisons: number; check: string | null; flagged: number } {
  const rows = ensembleRows(list, stars, TOP_CODE, limits);
  const comps = rows.filter((r) => r.role === 'comparison');
  const check = rows.find((r) => r.role === 'check');
  return { candidates: candidateRows(list, 'candidates').length, comparisons: comps.length, check: check?.name ?? null, flagged: comps.filter((r) => r.flags.length > 0).length };
}

/**
 * The live photometry curves, fed by the server (argos/server/protocol.md,
 * "API 2 routes, wave 5": A54 `GET /api/photometry/live`, A55
 * `photometry_point`, A56 `photometry_reset`) and read by LightCurvePlot.
 * Framework-free (vitest in node); the plot subscribes with onChange() and
 * redraws once per animation frame.
 *
 * Stream: points and resets share the server's `seq`; `revision` is the reset
 * generation. A point whose seq the snapshot covers is ignored ('stale'); a
 * missed seq, a revision the store does not hold or a point at an unexpected
 * index (the count of points received for that curve) answers 'gap', and the
 * caller re-reads A54 and calls load().
 *
 * Science rules, all from the fixed 0.5.0 Qt code:
 * - every `LcPoint` field is kept as sent; a point with neither a magnitude
 *   nor a relative flux is skipped (lightcurve_panel.py:127-128; S18: a
 *   ratio-only point is kept and drawn in the relative-flux view);
 * - a point carries its curve's systematic floor (`sigma_syst`); when it
 *   changes, every earlier bar becomes hypot(formal, sigma) row by row
 *   (uncertainty.py:95-98, pyHypot: the Python bits), as the server rewrites
 *   them (S19);
 * - the check star is drawn as check − its catalogue V (`catalogue_v`, D10);
 * - the ensemble facet is the target's ensemble zero point per frame (mean of
 *   catalogue − instrumental over the comparisons it used) ± its rms: the
 *   night's extinction and transparency (the comparisons' own leave-one-out
 *   curves are in the Ensemble tab).
 *
 * The wire adapter is this file alone: a renamed field is one edit here.
 */

import { CurveColumns, drawable, type LcPoint } from './columns';
import { FLAG_SATURATED } from '../uplot/markers';
import { TrailingBand } from './trailing';

export type Role = 'target' | 'check' | 'comparison';

/** Window of the check star's stability band (BRAND 10, D10). */
export const CHECK_WINDOW = 15;

/** One curve of the A54 snapshot (protocol `Curve`). */
export interface CurveWire {
  key: string;
  /** The TargetStar key in the set (null: no longer in it). */
  star_key?: string | null;
  role: Role | string;
  name?: string;
  auid?: string | null;
  /** Catalogue magnitudes by band (VSP). */
  mags?: Record<string, number | null> | null;
  /** D10: the check is plotted as check − this. */
  catalogue_v?: number | null;
  /** The curve's current systematic floor. */
  sigma_syst?: number | null;
  points: LcPoint[];
}

/** A54 `GET /api/photometry/live` (protocol `LivePhotometry`; the fields the curves need). */
export interface LiveSnapshot {
  object_name?: string | null;
  band?: string | null;
  site_set?: boolean;
  /** +1 at every reset. */
  revision?: number | null;
  /** The newest point / reset seq the snapshot covers. */
  seq?: number | null;
  curves: CurveWire[];
}

/** A55 WS `photometry_point` (protocol `PhotometryPoint`). */
export interface PointEvent {
  seq?: number | null;
  revision?: number | null;
  frame_seq?: number | null;
  key: string;
  star_key?: string | null;
  role: Role | string;
  name?: string;
  auid?: string | null;
  /** Position of the point in its curve. */
  index?: number | null;
  point: LcPoint;
  /** The curve's floor after this point. */
  sigma_syst?: number | null;
}

/** A56 WS `photometry_reset` (protocol `PhotometryReset`). */
export interface ResetEvent {
  seq?: number | null;
  revision?: number | null;
  reason?: string;
}

/** A target-set star (A51), for the catalogue magnitudes. */
export interface TargetStarLike {
  key: string;
  role?: string;
  name?: string;
  display_name?: string;
  auid?: string | null;
  mags?: Record<string, number | null> | null;
}

/** The catalogue magnitude the ensemble calibrates with: `band`, else V (session.py `_cat_mag`). */
export function catalogueMag(mags: Record<string, number | null> | null | undefined, band: string | null | undefined): number | null {
  if (!mags) return null;
  const v = band && band in mags ? mags[band] : mags.V;
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

const asRole = (r: string): Role => (r === 'target' || r === 'check' || r === 'comparison' ? r : 'target');
const finiteOrNull = (v: number | null | undefined): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/**
 * The magnitude a star's offset is taken from: a comparison's calibration
 * magnitude (band, else V), the check's (and target's) catalogue V (D10).
 */
export function offsetMag(role: Role, src: { mags?: Record<string, number | null> | null; catalogue_v?: number | null }, band: string | null): number | null {
  const v = finiteOrNull(src.catalogue_v) ?? catalogueMag(src.mags, 'V');
  return role === 'comparison' ? (catalogueMag(src.mags, band) ?? v) : (v ?? catalogueMag(src.mags, band));
}

export class StarCurve {
  readonly cols = new CurveColumns();
  role: Role;
  name: string;
  auid: string;
  /** The curve's run-level systematic floor (mag), once the server has one. */
  sigma: number | null = null;
  /** Its TargetStar key in the set, when the server says. */
  starKey: string | null = null;
  /** Catalogue magnitude (D10 offset), null when unknown. */
  catalogue: number | null = null;
  /** Points received for this curve (the server's index of the next one), drawn or not. */
  received = 0;
  /** mag − catalogue (or mag when the catalogue is unknown), aligned with cols. */
  delta = new Float64Array(0);
  /** Trailing band of `delta`, and of the relative flux (the flux view). */
  readonly band = new TrailingBand(CHECK_WINDOW);
  readonly fluxBand = new TrailingBand(CHECK_WINDOW);
  private derivedN = 0;
  private derivedEdits = -1;
  private derivedCat: number | null = null;

  constructor(
    readonly key: string,
    role: Role,
    name = key,
    auid = '',
  ) {
    this.role = role;
    this.name = name;
    this.auid = auid;
  }

  get n(): number {
    return this.cols.n;
  }

  /** Bring delta and the bands up to date: incremental on appends, full after an edit. */
  derive(): void {
    const c = this.cols;
    if (c.edits !== this.derivedEdits || this.catalogue !== this.derivedCat) {
      this.derivedN = 0;
      this.band.truncate(0);
      this.fluxBand.truncate(0);
      this.derivedEdits = c.edits;
      this.derivedCat = this.catalogue;
    }
    if (this.derivedN === c.n) return;
    if (this.delta.length < c.n) {
      const d = new Float64Array(Math.max(c.capacity, 256));
      d.set(this.delta.subarray(0, this.derivedN));
      this.delta = d;
    }
    const off = this.catalogue ?? 0;
    for (let i = this.derivedN; i < c.n; i++) this.delta[i] = c.mag[i] - off;
    const sat = (i: number) => (c.flags[i] & FLAG_SATURATED) !== 0;
    this.band.extend(this.delta, c.n, sat);
    this.fluxBand.extend(c.flux, c.n, sat);
    this.derivedN = c.n;
  }
}

export type ApplyResult = 'applied' | 'skipped' | 'stale' | 'gap';

export class LiveCurveStore {
  readonly stars = new Map<string, StarCurve>();
  object: string | null = null;
  /** The run's photometric band (photometry.default_band, e.g. "TG"). */
  band: string | null = null;
  /** Reset generation held (A54 / A56); null before the first snapshot. */
  revision: number | null = null;
  /** Newest stream seq applied; null before the first snapshot. */
  seq: number | null = null;
  /** Local change counter: every change bumps it (the plot's cache key). */
  version = 0;
  /** Bumped when a change touched rows already drawn (not a plain append). */
  edits = 0;
  private listeners = new Set<() => void>();
  private targetStars: readonly TargetStarLike[] = [];

  onChange(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private changed(edit = false): void {
    this.version++;
    if (edit) this.edits++;
    for (const fn of this.listeners) fn();
  }

  /** The first star of a role (measurement order), or a named one. */
  primary(role: Role, key?: string | null): StarCurve | null {
    if (key) {
      const s = this.stars.get(key) ?? [...this.stars.values()].find((c) => c.starKey === key);
      if (s && s.role === role) return s;
    }
    for (const s of this.stars.values()) if (s.role === role) return s;
    return null;
  }

  comparisons(): StarCurve[] {
    return [...this.stars.values()].filter((s) => s.role === 'comparison');
  }

  private star(key: string, role: Role, name?: string, auid?: string | null, starKey?: string | null): StarCurve {
    let s = this.stars.get(key);
    if (!s) {
      s = new StarCurve(key, role, name || key, auid ?? '');
      this.stars.set(key, s);
      if (starKey !== undefined) s.starKey = starKey;
      const t = this.matchTarget(s);
      if (t) s.catalogue = offsetMag(role, { mags: t.mags }, this.band);
    } else {
      if (s.role !== role) s.role = role;
      if (name) s.name = name;
      if (auid != null) s.auid = auid;
    }
    if (starKey !== undefined) s.starKey = starKey;
    return s;
  }

  private matchTarget(s: StarCurve): TargetStarLike | undefined {
    return this.targetStars.find(
      (t) => (s.starKey !== null && t.key === s.starKey) || t.key === s.key || (!!t.auid && t.auid === s.auid) || t.display_name === s.name || t.name === s.name,
    );
  }

  /** Replace everything with a snapshot (A54; also after a gap). */
  load(snap: LiveSnapshot): void {
    this.stars.clear();
    this.object = snap.object_name ?? null;
    if (snap.band) this.band = snap.band;
    this.revision = snap.revision ?? null;
    this.seq = snap.seq ?? null;
    for (const c of snap.curves ?? []) {
      const role = asRole(c.role);
      const s = this.star(c.key, role, c.name, c.auid, c.star_key);
      // A curve the stream created has no catalogue magnitudes yet: keep what the set gave.
      const mag = c.catalogue_v !== undefined || c.mags ? offsetMag(role, c, this.band) : null;
      if (mag !== null) s.catalogue = mag;
      for (const p of c.points ?? []) if (drawable(p)) s.cols.put(p);
      s.received = (c.points ?? []).length;
      s.sigma = finiteOrNull(c.sigma_syst);
    }
    this.changed(true);
  }

  /** How an event's seq and revision compare with what the store holds. */
  private check(seq: number | null | undefined): 'ok' | 'stale' | 'gap' {
    if (typeof seq === 'number' && this.seq !== null) {
      if (seq <= this.seq) return 'stale';
      if (seq > this.seq + 1) return 'gap';
    }
    return 'ok';
  }

  /**
   * A56: every curve starts again (object changed, a star under a new role, cleared). Events
   * missed before a reset do not matter (it clears them all): only a reset the store already
   * holds is refused ('stale').
   */
  reset(ev: ResetEvent = {}): ApplyResult {
    if (this.check(ev.seq) === 'stale') return 'stale';
    this.stars.clear();
    if (typeof ev.seq === 'number') this.seq = ev.seq;
    if (typeof ev.revision === 'number') this.revision = ev.revision;
    this.changed(true);
    return 'applied';
  }

  /**
   * One A55 point. 'stale': the snapshot holds it; 'gap': the caller re-reads
   * A54 and calls load() (nothing applied); 'skipped': nothing to draw (Qt
   * skips it too; the server never sends one).
   */
  apply(ev: PointEvent): ApplyResult {
    const c = this.check(ev.seq);
    if (c !== 'ok') return c;
    if (typeof ev.revision === 'number' && this.revision !== null && ev.revision !== this.revision) return 'gap';
    const known = this.stars.get(ev.key);
    if (typeof ev.index === 'number' && ev.index !== (known?.received ?? 0)) return 'gap';
    if (typeof ev.seq === 'number') this.seq = ev.seq;
    if (typeof ev.revision === 'number' && this.revision === null) this.revision = ev.revision;
    const p = ev.point;
    if (!p || !drawable(p)) {
      if (known) known.received++;
      return 'skipped';
    }
    const s = this.star(ev.key, asRole(ev.role), ev.name, ev.auid, ev.star_key);
    s.received++;
    const { how } = s.cols.put(p);
    let edit = how !== 'appended';
    const sigma = finiteOrNull(ev.sigma_syst) ?? finiteOrNull(p.sigma_syst);
    if (sigma !== null && sigma !== s.sigma) {
      // The floor moved: every bar of the curve, row by row (S19; A55 sends no column).
      s.sigma = sigma;
      if (s.cols.applyFloor(sigma)) edit = true;
    }
    this.changed(edit);
    return 'applied';
  }

  /**
   * Catalogue magnitudes from the target set (A51 `targets`), for curves the
   * snapshot gave none: matched by star key, key, AUID, then name.
   */
  applyTargets(stars: readonly TargetStarLike[], band?: string | null): void {
    if (band) this.band = band;
    this.targetStars = stars;
    let touched = false;
    for (const s of this.stars.values()) {
      if (s.catalogue !== null) continue;
      const t = this.matchTarget(s);
      const mag = t ? offsetMag(s.role, { mags: t.mags }, this.band) : null;
      if (mag !== null) {
        s.catalogue = mag;
        touched = true;
      }
    }
    if (touched) this.changed(true);
  }

  /** Set one star's offset magnitude (gallery, tests). */
  setCatalogue(key: string, mag: number | null): void {
    const s = this.stars.get(key);
    if (s && s.catalogue !== mag) {
      s.catalogue = mag;
      this.changed(true);
    }
  }

  /** Total points held (the plot's stress readout). */
  get points(): number {
    let n = 0;
    for (const s of this.stars.values()) n += s.n;
    return n;
  }
}

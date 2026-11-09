/**
 * Live photometry on the client (wave 5): the server's live store (A54 snapshot, A55 points,
 * A56 resets, A57 leave-one-out report, the `photometry` status), the field's VSX variables
 * (A50) and the comparison recommendation (A58), as Svelte 5 reactive state
 * (argos/server/protocol.md "API 2 routes, wave 5").
 *
 * - One point stream: every kept point arrives once with every LcPoint field (fixes Qt's S18;
 *   no whole-store re-render when the systematic floor changes, S19: each point carries its
 *   curve's floor, and every earlier bar becomes hypot(formal, floor) here, the Python bits).
 * - Points and resets share a `seq`; the snapshot says which `seq` and `revision` it holds.
 *   An event at or below the held `seq` is in the snapshot already (dropped); a jump past
 *   seq + 1, a `revision` the client does not hold or a point whose `index` is not the
 *   curve's length means something was missed: the snapshot is read again (README 4.1).
 * - Records are replaced, not proxied ($state.raw): a curve gains a new points array per
 *   point (a few thousand numbers per frame at most). The client never recomputes a
 *   magnitude or a verdict; the only error it computes is the floor's hypot (uncertainty.py).
 *
 *   const phot = new PhotometryStore();
 *   phot.attach(events, client);         // returns the unsubscribe
 *   await phot.refresh();                // after each (re)connection
 */

import { pyHypot } from '../../charts/lightcurve/columns';
import type { Curve, FieldVariable, FieldVariables, LcPoint, LiveSnapshot, LiveStatus, PointEvent, QualityReport, RecommendMode, RecommendResult } from './types';

export interface PhotClient {
  request<T>(method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE', path: string, body?: unknown): Promise<T>;
}

/**
 * A consumer of the validated stream (the light-curve plot's store): the store hands it every
 * snapshot, every point it applied (in order, gaps already resolved by a snapshot, so the
 * point goes without its `revision`) and every reset.
 */
export interface CurveSink {
  load(snap: LiveSnapshot): void;
  /** 'gap' when the sink's own count disagrees: the store reads the snapshot again. */
  apply(ev: Omit<PointEvent, 'revision'> & { revision?: undefined }): unknown;
  /** `seq` and `revision` of the reset: the sink's stream position follows the store's. */
  reset(ev: { seq?: number; revision?: number; reason?: string }): void;
}

export interface PhotEventSource {
  on(type: string, fn: (msg: Record<string, unknown>) => void): () => void;
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);
const ROLES = new Set(['target', 'comparison', 'check']);

// -- Message checks ---------------------------------------------------------------------------

/** A wire LcPoint: NaN travels as null; booleans and counts default as in lightcurve.py. */
export function checkPoint(m: unknown): LcPoint | null {
  if (!isObj(m)) return null;
  const jd = num(m.jd_utc);
  if (jd === null) return null;
  return {
    ...(m as unknown as LcPoint),
    jd_utc: jd,
    bjd_tdb: num(m.bjd_tdb),
    mag: num(m.mag),
    mag_err: num(m.mag_err),
    formal_mag_err: num(m.formal_mag_err),
    sigma_syst: num(m.sigma_syst),
    airmass: num(m.airmass),
    fwhm: num(m.fwhm),
    sky_adu: num(m.sky_adu),
    comps_used: num(m.comps_used) ?? 0,
    relative_flux: num(m.relative_flux),
    relative_flux_err: num(m.relative_flux_err),
    relative_comps_used: num(m.relative_comps_used) ?? 0,
    saturated: m.saturated === true,
    suspect: m.suspect === true,
    zero_point: num(m.zero_point),
    zp_rms: num(m.zp_rms),
  };
}

export function checkCurve(m: unknown): Curve | null {
  if (!isObj(m) || typeof m.key !== 'string' || typeof m.role !== 'string' || !ROLES.has(m.role)) return null;
  const pts = Array.isArray(m.points) ? m.points.map(checkPoint).filter((p): p is LcPoint => p !== null) : [];
  return {
    ...(m as unknown as Curve),
    star_key: str(m.star_key),
    name: str(m.name) ?? m.key,
    auid: str(m.auid),
    mags: isObj(m.mags) ? (m.mags as Record<string, number>) : {},
    catalogue_v: num(m.catalogue_v),
    sigma_syst: num(m.sigma_syst),
    points: pts,
  };
}

export function checkQuality(m: unknown): QualityReport | null {
  if (!isObj(m) || typeof m.selection_status !== 'string' || !Array.isArray(m.comparison_stars)) return null;
  const c = isObj(m.criteria) ? m.criteria : {};
  return {
    ...(m as unknown as QualityReport),
    scientific_note: typeof m.scientific_note === 'string' ? m.scientific_note : '',
    criteria: {
      min_points: num(c.min_points) ?? 10,
      max_scatter_mag: num(c.max_scatter_mag) ?? 0.1,
      max_formal_error_mag: num(c.max_formal_error_mag) ?? 0.1,
    },
    comparison_stars: m.comparison_stars.filter((e) => isObj(e) && typeof e.status === 'string') as QualityReport['comparison_stars'],
  };
}

export function checkStatus(m: unknown): LiveStatus | null {
  if (!isObj(m) || typeof m.state !== 'string') return null;
  return {
    ...(m as unknown as LiveStatus),
    reason: str(m.reason),
    message: str(m.message),
    frames: num(m.frames) ?? 0,
    points: num(m.points) ?? 0,
    last: isObj(m.last) && num(m.last.jd_utc) !== null ? (m.last as unknown as LiveStatus['last']) : null,
  };
}

export function checkSnapshot(m: unknown): LiveSnapshot | null {
  if (!isObj(m) || !Array.isArray(m.curves)) return null;
  return {
    ...(m as unknown as LiveSnapshot),
    object_name: typeof m.object_name === 'string' ? m.object_name : '',
    run_root: str(m.run_root),
    sequence_running: m.sequence_running === true,
    band: str(m.band),
    obscode: str(m.obscode),
    chart_id: str(m.chart_id),
    site_set: m.site_set === true,
    curves: m.curves.map(checkCurve).filter((c): c is Curve => c !== null),
    quality: checkQuality(m.quality),
    geometry: isObj(m.geometry) ? (m.geometry as unknown as LiveSnapshot['geometry']) : null,
    status: checkStatus(m.status),
    revision: num(m.revision) ?? 0,
    seq: num(m.seq) ?? 0,
  };
}

export function checkVariables(m: unknown): FieldVariables | null {
  if (!isObj(m) || !Array.isArray(m.rows)) return null;
  const rows = m.rows
    .filter((r): r is Record<string, unknown> => isObj(r) && num(r.index) !== null && typeof r.name === 'string')
    .map(
      (r): FieldVariable => ({
        ...(r as unknown as FieldVariable),
        var_type: str(r.var_type),
        mag_text: str(r.mag_text),
        brightest_mag: num(r.brightest_mag),
        period_d: num(r.period_d),
        sep_arcmin: num(r.sep_arcmin),
        in_set_role: typeof r.in_set_role === 'string' && ROLES.has(r.in_set_role) ? (r.in_set_role as FieldVariable['in_set_role']) : null,
        suspected: r.suspected === true,
        auid: str(r.auid),
        key: typeof r.key === 'string' ? r.key : `vsx:${r.index}`,
        x: num(r.x),
        y: num(r.y),
      }),
    );
  return { available: m.available === true, generation: num(m.generation) ?? 0, rows };
}

// -- The store --------------------------------------------------------------------------------

export class PhotometryStore {
  /** The snapshot's run facts (object, band, run folder, geometry), without the curves. */
  live: Omit<LiveSnapshot, 'curves' | 'quality' | 'status'> | null = $state.raw(null);
  /** Every star's curve (target, comparisons' leave-one-out, check), in measurement order. */
  curves: Curve[] = $state.raw([]);
  quality: QualityReport | null = $state.raw(null);
  /** WS `photometry`: why the last attempt gave points or not. */
  status: LiveStatus | null = $state.raw(null);
  /** The stream position held (A54 `seq`) and the reset generation (`revision`). */
  seq = $state(0);
  revision = $state(0);
  /** A50: the field's VSX variables (null before a solve, or when the route failed). */
  variables: FieldVariables | null = $state.raw(null);
  variablesError: string | null = $state(null);
  /** The snapshot route answered (false: an older server, or not read yet). */
  available = $state(false);
  /** Snapshots read because of a gap (for the tests and the support bundle). */
  refetches = 0;

  private client: PhotClient | null = null;
  private readonly sinks = new Set<CurveSink>();
  private refetching: Promise<void> | null = null;
  private variablesFetch: Promise<void> | null = null;
  private variablesAgain = false;

  /** Feed a curve store (the plot's) from now on, starting with what is held; returns the unsubscribe. */
  feed(sink: CurveSink): () => void {
    this.sinks.add(sink);
    // The position held now, not the snapshot's: points applied since are in `curves`.
    if (this.live) sink.load({ ...this.live, seq: this.seq, revision: this.revision, curves: this.curves, quality: this.quality, status: this.status });
    return () => this.sinks.delete(sink);
  }

  /** A new server process (boot_id changed): its stream starts again; the next snapshot is taken whole. */
  restart(): void {
    this.available = false;
    this.seq = 0;
    this.revision = 0;
    this.curves = [];
    this.quality = null;
    this.status = null;
  }

  get running(): boolean {
    return !!this.live?.sequence_running;
  }

  /** Subscribe to the server's photometry events; returns the unsubscribe. */
  attach(events: PhotEventSource, client: PhotClient | null = null): () => void {
    this.client = client;
    const offs = [
      events.on('photometry_point', (m) => this.ingest('photometry_point', m)),
      events.on('photometry_reset', (m) => this.ingest('photometry_reset', m)),
      events.on('comparison_quality', (m) => this.ingest('comparison_quality', m)),
      events.on('photometry', (m) => this.ingest('photometry', m)),
      // The variables list follows the catalogue (a new generation) and the set (in_set_role).
      events.on('field_layers', () => void this.reloadVariables()),
      events.on('targets', () => void this.reloadVariables()),
      events.on('field', (m) => {
        if (m.state === 'invalidated' || m.state === 'none') this.variables = null;
      }),
    ];
    return () => offs.forEach((off) => off());
  }

  /** One message or snapshot; returns whether it was kept. */
  ingest(type: string, m: unknown): boolean {
    switch (type) {
      case 'snapshot': {
        const s = checkSnapshot(m);
        if (!s) return false;
        // A snapshot read before events this client already applied would take them back.
        if (this.available && s.revision === this.revision && s.seq < this.seq) return false;
        const { curves, quality, status, ...rest } = s;
        this.live = rest;
        this.curves = curves;
        this.quality = quality;
        if (status) this.status = status;
        this.seq = s.seq;
        this.revision = s.revision;
        this.available = true;
        for (const k of this.sinks) k.load(s);
        return true;
      }
      case 'photometry_point': {
        if (!isObj(m) || typeof m.key !== 'string') return false;
        const point = checkPoint(m.point);
        const seq = num(m.seq);
        if (!point || seq === null) return false;
        if (!this.available) {
          // The snapshot is on its way (or failed): it will hold this point.
          void this.refetch();
          return false;
        }
        if (seq <= this.seq) return false; // in the snapshot already
        const ev = m as unknown as PointEvent;
        const curve = this.curves.find((c) => c.key === ev.key);
        const index = num(m.index);
        if (seq > this.seq + 1 || num(m.revision) !== this.revision || (index !== null && index !== (curve?.points.length ?? 0))) {
          // Missed points or a reset: the snapshot holds them all, in order.
          void this.refetch(true);
          return false;
        }
        this.append(ev, point);
        this.seq = seq;
        if (this.sinks.size) {
          const { revision: _r, ...rest } = ev;
          let gap = false;
          for (const k of this.sinks) if (k.apply({ ...rest, point }) === 'gap') gap = true;
          // A sink that missed something (it never should) is not left frozen: it reloads.
          if (gap) void this.refetch(true);
        }
        return true;
      }
      case 'photometry_reset': {
        if (!isObj(m)) return false;
        const seq = num(m.seq);
        if (seq !== null && this.available && seq <= this.seq) return false;
        this.curves = [];
        this.quality = null;
        if (seq !== null) this.seq = seq;
        const rev = num(m.revision);
        if (rev !== null) this.revision = rev;
        const reason = typeof m.reason === 'string' ? m.reason : undefined;
        for (const k of this.sinks) k.reset({ seq: this.seq, revision: this.revision, reason });
        void this.refetch();
        return true;
      }
      case 'comparison_quality': {
        if (!isObj(m)) return false;
        const raw = 'report' in m ? m.report : m;
        if (raw === null) {
          this.quality = null;
          return true;
        }
        const q = checkQuality(raw);
        if (q) this.quality = q;
        return !!q;
      }
      case 'photometry': {
        const st = checkStatus(m);
        if (st) this.status = st;
        return !!st;
      }
      case 'variables': {
        const v = checkVariables(m);
        if (v) this.variables = v;
        return !!v;
      }
      default:
        return false;
    }
  }

  private append(ev: PointEvent, point: LcPoint): void {
    const i = this.curves.findIndex((c) => c.key === ev.key);
    const sigma = num(ev.sigma_syst);
    if (i < 0) {
      const curve: Curve = {
        key: ev.key,
        star_key: str(ev.star_key),
        role: ROLES.has(ev.role) ? ev.role : 'target',
        name: ev.name || ev.key,
        auid: str(ev.auid),
        mags: {},
        catalogue_v: null,
        sigma_syst: sigma,
        points: [point],
      };
      // Its catalogue V comes with the next snapshot; the set star's mags have it meanwhile.
      this.curves = [...this.curves, curve];
      return;
    }
    const c = this.curves[i];
    let points = [...c.points, point];
    if (sigma !== null && sigma !== c.sigma_syst) {
      // The point moved the curve's floor: every point with a magnitude gets
      // hypot(max(0, formal), floor), as the server's _apply_systematic_floor rewrote them
      // (S19; uncertainty.py:95-98). The new point arrived with its own.
      points = points.map((p) => {
        if (p === point || p.mag === null || p.formal_mag_err === null) return p;
        return { ...p, mag_err: pyHypot(Math.max(0, p.formal_mag_err), sigma), sigma_syst: sigma };
      });
    }
    const curves = this.curves.slice();
    curves[i] = { ...c, sigma_syst: sigma ?? c.sigma_syst, points };
    this.curves = curves;
  }

  // -- Calls ------------------------------------------------------------------------------

  /** Every snapshot (on load and after each reconnection). */
  async refresh(client: PhotClient | null = this.client): Promise<void> {
    if (client) this.client = client;
    await Promise.all([this.refetch(), this.reloadVariables()]);
  }

  /** A54: the whole live store again (a gap, a reset, a reconnection). */
  refetch(gap = false): Promise<void> {
    const client = this.client;
    if (!client) return Promise.resolve();
    if (gap) this.refetches += 1;
    this.refetching ??= client
      .request<unknown>('GET', '/api/photometry/live')
      .then((s) => {
        this.ingest('snapshot', s);
      })
      .catch(() => {
        /* an older server, or the link dropped: the next (re)connection reads it */
      })
      .finally(() => (this.refetching = null));
    return this.refetching;
  }

  /** A50: the field's VSX variables (`available: false` before a solution). */
  reloadVariables(): Promise<void> {
    const client = this.client;
    if (!client) return Promise.resolve();
    if (this.variablesFetch) {
      // A change during the request: read once more when it ends.
      this.variablesAgain = true;
      return this.variablesFetch;
    }
    this.variablesFetch = client
      .request<unknown>('GET', '/api/field/variables')
      .then((v) => {
        this.variablesError = null;
        if (!this.ingest('variables', v)) this.variables = null;
      })
      .catch((err: unknown) => {
        this.variables = null;
        const status = isObj(err) && typeof err.status === 'number' ? err.status : null;
        this.variablesError = status === 404 ? null : err instanceof Error ? err.message : String(err);
      })
      .finally(() => {
        this.variablesFetch = null;
        if (this.variablesAgain) {
          this.variablesAgain = false;
          void this.reloadVariables();
        }
      });
    return this.variablesFetch;
  }

  /** A58: complete the ensemble, or replace the VSP picks (manual choices stay). */
  async recommend(mode: RecommendMode, count?: number | null, client: PhotClient | null = this.client): Promise<RecommendResult> {
    if (!client) throw new Error('Not connected to the ARGOS server');
    const body: Record<string, unknown> = { mode };
    if (typeof count === 'number' && Number.isFinite(count)) body.count = Math.round(count);
    return client.request<RecommendResult>('POST', '/api/photometry/comparisons/recommend', body);
  }
}

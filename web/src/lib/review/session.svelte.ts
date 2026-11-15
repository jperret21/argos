/**
 * The R1 source under review (spec 07 §2.1, README R1, D3): a saved session (A68 + A69), an
 * imported CSV (A70, a pseudo-session with no frames) or the live run (the Observe store,
 * read-only). One object per Review screen; the plot wall, the rail cards and the drawer
 * read it, the integrator feeds it.
 *
 * - The curves live in a LiveCurveStore (outside the reactive graph); `version` is the one
 *   reactive number the components follow.
 * - The display (time axis, U error bars, M relative flux, the filter shown) is one
 *   CurveDisplay for every cell: the global U / M toggles (README M96).
 * - The link (CurveLink) is the wall's one time axis and selected time: the Selected point
 *   card, the Frames table and R2 read the same selection.
 * - Opening is atomic (07 P13): the whole session or an error, the previous one kept until
 *   the new one is complete.
 */

import { CurveDisplay } from '../charts/lightcurve/view.svelte';
import { CurveLink } from '../charts/lightcurve/link.svelte';
import { LiveCurveStore, type TargetStarLike } from '../charts/lightcurve/store';
import { reducedMotion } from '../components/motion.svelte';
import { fixed, int } from '../format/number';
import { frameRows, isoSeconds, type FrameRow } from './frames/frames';
import { curveFilters, parseCurves, parseQualityBlock, qualityFor, storeFromCurves, type CurveExtras, type QualityReport, type ReviewCurveWire } from './source';
import { wallExtent, type WallFrame } from './wall';

/** The source of the exports and the re-run (protocol "Sources"; the dialogs' `Source`). */
export type SourceRef = { kind: 'session'; path: string } | { kind: 'import'; path: string } | { kind: 'live' };

/** A curve as the export dialogs list it (front-end B's `CurveRef`: A68-A70 `curves[]`). */
export interface CurveRefLike {
  key: string;
  role: string;
  name: string;
  /** Filter token ("" when nothing says, a pre-0.5.0 name). */
  filter: string;
  n: number;
  exportable?: boolean;
  problem?: string | null;
}

/**
 * A68 frames as the wall reads them: mid-exposure from the FITS header (`header.mid_utc`) when
 * it was read, else the logged start + exposure / 2; the header AIRMASS (the mount's).
 */
export function wallFramesOf(rows: readonly FrameRow[]): WallFrame[] {
  return rows.map((f) => {
    const hm = isoSeconds(f.header?.mid_utc ?? null);
    return {
      t: f.t,
      mid: hm ?? (f.t === null ? null : f.t + (f.exposure_s ?? 0) / 2),
      exposure_s: f.exposure_s,
      light: f.light,
      missing: f.missing,
      hfd: f.hfd,
      fwhm: f.fwhm,
      star_count: f.star_count,
      sky_adu: f.sky_adu,
      eccentricity: f.eccentricity,
      ccd_temp: f.ccd_temp,
      airmass: f.header?.airmass ?? null,
    };
  });
}

/** How the R1 data are fetched (the integrator binds it to the client; tests pass a fake). */
export interface ReviewLoader {
  /** A68 `GET /api/review/session?path=` (after its job, when it runs as one). */
  session(path: string, signal?: AbortSignal): Promise<unknown>;
  /** A69 `GET /api/review/session/curves?path=`. */
  curves(path: string, signal?: AbortSignal): Promise<unknown>;
}

/** The request function of the shared client (ArgosClient.request). */
export interface ReviewRequest {
  request<T>(method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE', path: string, body?: unknown, options?: { signal?: AbortSignal; timeoutMs?: number }): Promise<T>;
}

/** A68 and A69 as plain GETs (the session scan may take a few seconds: 60 s timeout). */
export function httpLoader(client: ReviewRequest): ReviewLoader {
  const q = (path: string) => `path=${encodeURIComponent(path)}`;
  return {
    session: (path, signal) => client.request('GET', `/api/review/session?${q(path)}`, undefined, { signal, timeoutMs: 60_000 }),
    curves: (path, signal) => client.request('GET', `/api/review/session/curves?${q(path)}`, undefined, { signal, timeoutMs: 60_000 }),
  };
}

/** One readiness issue of A68 (`readiness.issues[]`). */
export interface ReadinessIssue {
  code: string;
  level: 'error' | 'warn' | 'info';
  message: string;
  count?: number;
}

/** What R1 shows of the session besides the curves (A68, read tolerantly). */
/** Each frame with its target point's flags and comparison count (the Frames table's ⚑ and Comps). */
function withTargetFlags(frames: FrameRow[], curves: readonly ReviewCurveWire[]): FrameRow[] {
  const flags = new Map<number, Set<string>>();
  const comps = new Map<number, number>();
  for (const c of curves) {
    if (c.role !== 'target') continue;
    const p = c.points;
    if (!p.frame) continue;
    p.frame.forEach((f, i) => {
      if (typeof f !== 'number') return;
      const set = flags.get(f) ?? new Set<string>();
      for (const w of p.flags?.[i] ?? []) if (w !== 'no_frame') set.add(w);
      if (p.suspect?.[i]) set.add('suspect');
      if (p.saturated?.[i]) set.add('saturated');
      flags.set(f, set);
      const k = p.comps_used?.[i];
      if (typeof k === 'number' && Number.isFinite(k)) comps.set(f, k);
    });
  }
  if (!flags.size) return frames;
  return frames.map((r) => ({ ...r, flags: [...(flags.get(r.index) ?? [])], comps: comps.get(r.index) ?? null }));
}

/** A session.json summary row: a known key with its label and unit, or an unknown key as written. */
export interface SummaryRow {
  label: string;
  value: string;
  known: boolean;
}

/** session.json `summary` keys the Session card names (the frame counts are its Lights row already). */
const SUMMARY_KEYS: Record<string, { label: string; digits: number; unit: string } | null> = {
  frame_count: null,
  light_count: null,
  mean_hfd: { label: 'Mean HFD', digits: 2, unit: 'px' },
  mean_fwhm: { label: 'Mean FWHM', digits: 2, unit: 'px' },
  mean_sky_adu: { label: 'Mean sky', digits: 0, unit: 'ADU' },
  mean_star_count: { label: 'Mean stars', digits: 0, unit: '' },
};

export function summaryRows(raw: unknown): SummaryRow[] {
  if (typeof raw === 'string' && raw) return [{ label: 'Summary', value: raw, known: true }];
  if (!isObj(raw)) return [];
  const rows: SummaryRow[] = [];
  const extra: SummaryRow[] = [];
  for (const [k, v] of Object.entries(raw)) {
    const def = SUMMARY_KEYS[k];
    if (def === null) continue;
    if (def && typeof v === 'number') {
      const text = def.digits === 0 ? int(v) : fixed(v, def.digits, { group: true });
      rows.push({ label: def.label, value: def.unit ? `${text}\u202f${def.unit}` : text, known: true });
    } else extra.push({ label: k, value: isObj(v) || Array.isArray(v) ? JSON.stringify(v) : String(v), known: false });
  }
  return [...rows, ...extra];
}

export interface SessionInfo {
  path: string;
  folder: string;
  object: string;
  startedUtc: string | null;
  software: string | null;
  /** session.json `summary` (P20) as labelled rows, known keys first (unknown ones keep their key). */
  summary: SummaryRow[];
  /** Metadata rows (key, value) for the Session card. */
  metadata: [string, string][];
  warnings: string[];
  /** The readiness issues' texts (A68 `readiness.issues[].message`). */
  issues: string[];
  /** A68 `readiness`: "ready" (Complete), "warnings", "blocked" (no light, no FITS). */
  readiness: 'ready' | 'warnings' | 'blocked';
  readinessIssues: ReadinessIssue[];
  /**
   * Which airmass is right (A68 `airmass_source`): "header" when the header site check found
   * the Settings site wrong (RR Lyr 2026-09-25): the CSV's airmass is wrong, the FITS header
   * AIRMASS (the mount's) right.
   */
  airmassSource: 'csv' | 'header';
  /** The header site check's sentence when it is not "ok" (A68 `site_check.message`). */
  siteNote: string | null;
  targets: TargetStarLike[];
  chartId: string | null;
  band: string | null;
  obscode: string | null;
  /** Frame filters by count ("IR": 195). */
  filters: Record<string, number>;
}

export type SourceKind = 'session' | 'import' | 'live';

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === 'string' && v !== '' ? v : null);
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []);
const basename = (p: string) => p.replace(/[\\/]+$/, '').split(/[\\/]/).pop() ?? p;

function flatten(prefix: string, v: unknown, out: [string, string][]): void {
  if (v === null || v === undefined) return;
  if (isObj(v)) {
    for (const [k, x] of Object.entries(v)) flatten(prefix ? `${prefix}.${k}` : k, x, out);
  } else if (Array.isArray(v)) out.push([prefix, v.map((x) => (isObj(x) ? JSON.stringify(x) : String(x))).join(', ')]);
  else out.push([prefix, String(v)]);
}

/** A68's record (or an import's), tolerant of absent keys. */
export function parseSession(raw: unknown, path: string): SessionInfo {
  if (!isObj(raw)) throw new Error('Session: the answer is not an object');
  const metadata: [string, string][] = [];
  flatten('', raw.metadata, metadata);
  const tset = isObj(raw.targets) ? raw.targets : null;
  const targets = (Array.isArray(raw.targets) ? raw.targets : tset && Array.isArray(tset.stars) ? tset.stars : []).filter(isObj).map((t) => ({
    key: str(t.key) ?? str(t.auid) ?? str(t.name) ?? '',
    role: str(t.role) ?? undefined,
    name: str(t.name) ?? undefined,
    display_name: str(t.display_name) ?? undefined,
    auid: str(t.auid),
    mags: isObj(t.mags) ? (t.mags as Record<string, number | null>) : null,
  }));
  // Frames by filter name: A68 `counts.filters` (a bare `filters` object is read too).
  const filters: Record<string, number> = {};
  const fc = isObj(raw.counts) && isObj(raw.counts.filters) ? raw.counts.filters : isObj(raw.filters) ? raw.filters : {};
  for (const [k, v] of Object.entries(fc)) if (typeof v === 'number') filters[k] = v;
  const summary = summaryRows(raw.summary);
  const rd = isObj(raw.readiness) ? raw.readiness : null;
  const readinessIssues: ReadinessIssue[] = (rd && Array.isArray(rd.issues) ? rd.issues : []).filter(isObj).map((i) => ({
    code: str(i.code) ?? '',
    level: i.level === 'error' ? 'error' : i.level === 'info' ? 'info' : 'warn',
    message: str(i.message) ?? str(i.code) ?? '',
    ...(typeof i.count === 'number' ? { count: i.count } : {}),
  }));
  const issues = rd ? readinessIssues.map((i) => i.message) : strs(raw.readiness_issues ?? raw.issues);
  const state = rd && (rd.state === 'ready' || rd.state === 'warnings' || rd.state === 'blocked') ? rd.state : issues.length ? 'warnings' : 'ready';
  const site = isObj(raw.site_check) ? raw.site_check : null;
  return {
    path: str(raw.root) ?? str(raw.path) ?? path,
    folder: str(raw.folder) ?? basename(str(raw.root) ?? path),
    object: str(raw.object) ?? str(raw.object_name) ?? (tset ? str(tset.object_name) : null) ?? '',
    startedUtc: str(raw.started_utc),
    software: str(raw.software),
    summary,
    metadata,
    warnings: strs(raw.warnings),
    issues,
    readiness: state,
    readinessIssues,
    airmassSource: raw.airmass_source === 'header' ? 'header' : 'csv',
    siteNote: site && site.state === 'mismatch' ? str(site.message) : null,
    targets,
    chartId: str(raw.chart_id) ?? (tset ? str(tset.chart_id) : null),
    band: str(raw.band),
    obscode: str(raw.obscode),
    filters,
  };
}

export class ReviewSource {
  /** The curves (replaced as a whole by every opening: plots follow the new object). */
  store: LiveCurveStore = $state.raw(new LiveCurveStore());
  readonly display: CurveDisplay;
  readonly link: CurveLink;
  kind: SourceKind | null = $state(null);
  status: 'idle' | 'loading' | 'ready' | 'error' = $state('idle');
  /** The folder or file being opened (the toolbar's "Opening {folder}…"). */
  opening: string | null = $state(null);
  error: string | null = $state(null);
  info: SessionInfo | null = $state.raw(null);
  frames: FrameRow[] = $state.raw([]);
  quality: QualityReport[] = $state.raw([]);
  /** Problems met reading the curves (server's, and the curves the client left out). */
  problems: string[] = $state.raw([]);
  /** S49: the filters the curves name (empty before S49). */
  filters: string[] = $state.raw([]);
  /** A69 columns the store does not keep (header airmass, display flags), by curve key. */
  extras: Map<string, CurveExtras> = $state.raw(new Map());
  /** The curves as A69 listed them (the export dialogs' list). */
  curveList: CurveRefLike[] = $state.raw([]);
  /** The frames as the wall reads them (header mid-exposure and AIRMASS). */
  wallRows: WallFrame[] = $state.raw([]);
  /** Bumped at every change of the store (the components' reactive key). */
  version = $state(0);
  private abort: AbortController | null = null;
  private unlisten: (() => void) | null = null;

  constructor(display = new CurveDisplay()) {
    this.display = display;
    this.link = new CurveLink({
      extent: () => wallExtent(this.store, this.shownFilter(), this.frames),
      minSpan: 300,
      padLeft: 0.012,
      padRight: 0.012,
      anchor: () => 'center',
      wheel: 'modifier',
      reducedMotion,
    });
    this.setStore(this.store);
  }

  private setStore(s: LiveCurveStore): void {
    this.unlisten?.();
    this.store = s;
    this.unlisten = s.onChange(() => (this.version = s.version));
    this.version = s.version;
  }

  /** The filter drawn: the display's while the curves have it, else the newest frame's. */
  shownFilter(): string | null {
    const want = this.display.filter;
    return want && this.store.filters().includes(want) ? want : this.store.newestFilter();
  }

  /** The vetting report of the filter shown (S57). */
  report(): QualityReport | null {
    return qualityFor(this.quality, this.shownFilter());
  }

  /** The frames as the wall reads them. */
  wallFrames(): WallFrame[] {
    return this.wallRows;
  }

  /** Which airmass is right: "header" when the Settings site was wrong (A68 `airmass_source`). */
  airmassSource(): 'csv' | 'header' {
    return this.info?.airmassSource ?? 'csv';
  }

  /** The source as the exports and the re-run name it (the dialogs' `source`). */
  ref(): SourceRef | null {
    if (this.kind === 'live') return { kind: 'live' };
    if ((this.kind === 'session' || this.kind === 'import') && this.info?.path) return { kind: this.kind, path: this.info.path };
    return null;
  }

  /** The curves for the export dialogs (A69's list; the live store's curves for the live run). */
  curveRefs(): CurveRefLike[] {
    if (this.kind !== 'live') return this.curveList;
    return [...this.store.stars.values()].map((s) => ({ key: s.key, role: s.role, name: s.name, filter: s.filter ?? '', n: s.n }));
  }

  /** Open a saved session folder (A68 + A69): atomic, cancels an opening in progress. */
  async open(loader: ReviewLoader, path: string): Promise<void> {
    this.abort?.abort();
    const ac = new AbortController();
    this.abort = ac;
    this.status = 'loading';
    this.opening = basename(path);
    this.error = null;
    try {
      const [rawSession, rawCurves] = await Promise.all([loader.session(path, ac.signal), loader.curves(path, ac.signal)]);
      if (ac.signal.aborted) return;
      const info = parseSession(rawSession, path);
      const curves = parseCurves(rawCurves);
      const s = rawSession as Record<string, unknown>;
      if (curves.airmass_source === 'header' && info.airmassSource !== 'header') info.airmassSource = 'header';
      this.apply('session', info, curves.curves, frameRows(Array.isArray(s.frames) ? s.frames : []), parseQualityBlock(s.quality ?? s.comparison_quality ?? null), curves.problems ?? []);
    } catch (e) {
      if (ac.signal.aborted) return;
      this.status = this.info ? 'ready' : 'error';
      this.error = e instanceof Error ? e.message : String(e);
      throw e;
    } finally {
      if (this.abort === ac) {
        this.abort = null;
        this.opening = null;
      }
    }
  }

  /**
   * An imported CSV (A70 answer: curves + targets + inferred roles): a pseudo-session with
   * no frames and no quality report (07 WF-G).
   */
  openImport(raw: unknown, file: string): void {
    const curves = parseCurves(raw);
    const r = isObj(raw) ? raw : {};
    // The source is the CSV file (protocol Source "import"), not the CurveSet's `root` folder.
    const info = { ...parseSession({ ...r, folder: basename(file), object: str(r.object) ?? str(r.object_name) ?? '' }, file), path: file };
    if (curves.airmass_source === 'header') info.airmassSource = 'header';
    this.apply('import', info, curves.curves, [], [], curves.problems ?? []);
  }

  /**
   * The live run (D3): the Observe store itself, read-only (its points keep arriving); the
   * frames are not listed (the live run has no session folder yet).
   */
  openLive(live: LiveCurveStore, info: Partial<SessionInfo> = {}): void {
    this.abort?.abort();
    this.setStore(live);
    this.kind = 'live';
    this.info = {
      path: '',
      folder: 'Live run',
      object: live.object ?? '',
      startedUtc: null,
      software: null,
      summary: [],
      metadata: [],
      warnings: [],
      issues: [],
      readiness: 'ready',
      readinessIssues: [],
      airmassSource: 'csv',
      siteNote: null,
      targets: [],
      chartId: null,
      band: live.band,
      obscode: null,
      filters: {},
      ...info,
    };
    this.frames = [];
    this.wallRows = [];
    this.extras = new Map();
    this.curveList = [];
    this.quality = [];
    this.problems = [];
    this.filters = live.filters();
    this.link.reset();
    this.status = 'ready';
    this.error = null;
  }

  private apply(kind: SourceKind, info: SessionInfo, curves: ReviewCurveWire[], frames: FrameRow[], quality: QualityReport[], problems: string[]): void {
    // Build into a fresh store first: the screen keeps the old session until this one is whole.
    const { store: fresh, skipped, extras } = storeFromCurves({ curves, targets: info.targets, band: info.band, object: info.object });
    this.kind = kind;
    this.info = info;
    frames = withTargetFlags(frames, curves);
    this.frames = frames;
    this.wallRows = wallFramesOf(frames);
    this.extras = extras;
    this.curveList = curves.map((c) => ({ key: c.key, role: c.role, name: c.name ?? c.key, filter: c.filter ?? '', n: c.points.jd_utc.length, exportable: c.exportable !== false, problem: c.problem ?? null }));
    this.quality = quality;
    this.problems = [...problems, ...skipped];
    this.filters = curveFilters(curves);
    this.link.reset();
    // The curves in one step: the plots follow the new store (one rebuild).
    this.setStore(fresh);
    this.status = 'ready';
    this.error = null;
  }

  /** Forget the source (R0 shows again). */
  close(): void {
    this.abort?.abort();
    this.kind = null;
    this.info = null;
    this.frames = [];
    this.wallRows = [];
    this.extras = new Map();
    this.curveList = [];
    this.quality = [];
    this.problems = [];
    this.filters = [];
    this.status = 'idle';
    this.error = null;
    this.link.reset();
    this.setStore(new LiveCurveStore());
  }

  destroy(): void {
    this.abort?.abort();
    this.unlisten?.();
  }
}

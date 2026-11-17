/**
 * R2 frame inspector state (web/spec/07-review-analysis.md 1.11, WF-D, 2.4; README M100-M102;
 * protocol.md A71-A75). One per app; the screen shows it, the Frames table and the selected
 * point open frames into it.
 *
 *   const r2 = new InspectorStore(new InspectorApi(app.client, binaryFetch(app.config)), app.jobs);
 *   r2.setSession(frames.lights, 'RR Lyr · 2026-09-25');   // previous / next walk these
 *   await r2.open(path);                                     // A71 + A72 + the kept solution
 *   r2.identify();  r2.measureAt(x, y);  r2.step(+1);
 *
 * Rules (07 2.4): a failed open keeps the previous frame on screen and says why (P28); a solve
 * is cancellable (kills ASTAP); the catalogue follows a solve; a click measures (A73) and never
 * assigns a role (Review never edits the target set); stepping to another frame keeps the
 * layers wanted, fetched again around that frame's own solution when the server kept one.
 */

import type { DecodedFrame } from '../../api/frames';
import { isActive, type Job, type JobEntry } from '../../app/jobs';
import { loadPref, savePref } from '../../app/prefs';
import { defaultVisibility, isVisibility, type DisplayToggle, type LayerId, type Visibility } from '../../viewer/overlay/layers';
import { NEUTRAL_STRETCH, type StretchParams } from '../../viewer/stretch';
import { ViewerTools } from '../../viewer/tools/tools.svelte';
import type { FrameRow } from '../frames/frames';
import {
  fileFrameInfo,
  parseFileLayers,
  parseFileSolution,
  type FileFrameInfo,
  type FileLayers,
  type FileSolution,
  type FitsHeader,
  type InspectorApi,
  type StarMeasure,
} from './api';
import { APERTURE_DEFAULT, isAperture, neighbours } from './inspect';

/** What the store needs of the app's JobStore. */
export interface JobsLike {
  get(id: string): JobEntry | null;
  ingest(raw: unknown): Job | null;
  cancel(id: string): Promise<void>;
}

export const PREF_APERTURE = 'argos.review.r2.aperture';
export const PREF_LAYERS = 'argos.review.r2.layers';
export const PREF_RAIL = 'argos.review.r2.rail';

const errText = (err: unknown) => (err instanceof Error ? err.message : String(err));

export class InspectorStore {
  // -- The file ------------------------------------------------------------------------------
  path: string | null = $state(null);
  frame: DecodedFrame | null = $state.raw(null);
  info: FileFrameInfo | null = $state.raw(null);
  /** The file being read (its name shows "Loading …"); the previous frame stays meanwhile. */
  loading: string | null = $state(null);
  error: string | null = $state(null);
  header: FitsHeader | null = $state.raw(null);
  headerError: string | null = $state(null);

  // -- The session it belongs to (previous / next) -------------------------------------------
  lights: FrameRow[] = $state.raw([]);
  sessionLabel: string | null = $state(null);
  readonly near = $derived(neighbours(this.lights, this.path));
  readonly row = $derived(this.path ? (this.lights.find((r) => r.path === this.path) ?? null) : null);

  // -- Identification (A74) and catalogue (A75) -------------------------------------------------
  solution: FileSolution | null = $state.raw(null);
  solveJobId: string | null = $state(null);
  solveError: string | null = $state(null);
  layers: FileLayers | null = $state.raw(null);
  catalogueJobId: string | null = $state(null);
  catalogueError: string | null = $state(null);
  /** The observer asked for the field (S): stepping keeps fetching it. */
  wantField = $state(false);
  visibility: Visibility = $state(defaultVisibility());
  gLimit: number | null = $state(null);

  readonly solveJob = $derived.by(() => (this.solveJobId ? this.jobs.get(this.solveJobId) : null));
  readonly catalogueJob = $derived.by(() => (this.catalogueJobId ? this.jobs.get(this.catalogueJobId) : null));
  readonly solving = $derived(!!this.solveJob && isActive(this.solveJob));
  readonly fetching = $derived(!!this.catalogueJob && isActive(this.catalogueJob));

  // -- Measure (A73) ---------------------------------------------------------------------------
  measure: StarMeasure | null = $state.raw(null);
  /** Where the observer clicked (frame px), until the answer replaces it. */
  measureAt_: { x: number; y: number } | null = $state(null);
  measuring = $state(false);
  measureError: string | null = $state(null);
  aperture: number = $state(APERTURE_DEFAULT);

  // -- Display ---------------------------------------------------------------------------------
  autoStretch = $state(true);
  manual: StretchParams | null = $state(null);
  autoLevels: StretchParams | null = $state.raw(null);
  readonly levels = $derived(this.autoStretch ? this.autoLevels : (this.manual ?? NEUTRAL_STRETCH));
  crosshair = $state(false);
  railOpen = $state(true);

  private openController: AbortController | null = null;
  private measureController: AbortController | null = null;
  private openSeq = 0;

  constructor(
    private readonly api: InspectorApi,
    private readonly jobs: JobsLike,
    load = true,
  ) {
    if (!load) return;
    this.aperture = loadPref(PREF_APERTURE, isAperture, APERTURE_DEFAULT);
    this.visibility = { ...defaultVisibility(), ...loadPref(PREF_LAYERS, isVisibility, {}) };
    this.railOpen = loadPref(PREF_RAIL, (v): v is boolean => typeof v === 'boolean', true);
  }

  setSession(lights: readonly FrameRow[], label: string | null): void {
    this.lights = [...lights];
    this.sessionLabel = label;
  }

  /**
   * Show a file (A71), its header (A72) and the solution the server kept (A74). Resolves with
   * null, or the reason it could not be opened (the previous frame stays on screen).
   */
  async open(path: string): Promise<string | null> {
    this.openController?.abort();
    const controller = new AbortController();
    this.openController = controller;
    const seq = ++this.openSeq;
    this.loading = path;
    this.error = null;
    try {
      const [frame, header, solution] = await Promise.all([
        this.api.frame(path, controller.signal),
        this.api.header(path, controller.signal).catch((err: unknown) => errText(err)),
        this.api.solution(path, controller.signal).catch(() => null),
      ]);
      if (seq !== this.openSeq) return null;
      const changed = this.path !== path;
      this.path = path;
      this.frame = frame;
      this.info = fileFrameInfo(frame.header);
      this.header = typeof header === 'string' ? null : header;
      this.headerError = typeof header === 'string' ? header : null;
      if (changed) {
        this.measure = null;
        this.measureAt_ = null;
        this.measureError = null;
        this.layers = null;
        this.catalogueError = null;
        this.solveError = null;
        this.catalogueJobId = null;
        this.solveJobId = null;
      }
      this.solution = solution;
      if (solution && this.wantField) void this.fetchCatalogue();
      // The observer asked for the field (S) on an earlier frame: identify this one too (ASTAP
      // with the header hint takes about 0.1 s), rather than "Not identified" until S again.
      else if (!solution && changed && this.wantField) void this.identify();
      return null;
    } catch (err) {
      if (seq !== this.openSeq || controller.signal.aborted) return null;
      const why = errText(err);
      this.error = `Could not open ${path.slice(path.lastIndexOf('/') + 1)}: ${why}`;
      return why;
    } finally {
      if (seq === this.openSeq) {
        this.loading = null;
        this.openController = null;
      }
    }
  }

  /** Previous (-1) or next (+1) light frame of the session. */
  async step(delta: -1 | 1): Promise<string | null> {
    const target = delta < 0 ? this.near.prev : this.near.next;
    if (!target?.path) return null;
    return this.open(target.path);
  }

  // -- Identify ---------------------------------------------------------------------------------

  async identify(): Promise<string | null> {
    if (!this.path || this.solving) return null;
    this.wantField = true;
    this.solveError = null;
    try {
      const start = await this.api.solve(this.path);
      this.jobs.ingest(start.job);
      this.solveJobId = start.job_id;
      return null;
    } catch (err) {
      this.solveError = errText(err);
      return this.solveError;
    }
  }

  cancelSolve(): void {
    if (this.solveJobId) void this.jobs.cancel(this.solveJobId);
  }

  /** A solve job ended (the screen's effect calls this when solveJob leaves the active states). */
  finishSolve(job: JobEntry): void {
    if (job.id !== this.solveJobId) return;
    if (job.state === 'done') {
      const sol = parseFileSolution(job.result);
      if (sol && sol.path === this.path) {
        this.solution = sol;
        void this.fetchCatalogue();
      } else if (!sol) this.solveError = 'The solve finished without a solution.';
    } else if (job.state === 'failed') {
      this.solveError = job.error?.message ?? 'The field was not identified.';
    } else if (job.state === 'cancelled') {
      this.solveError = 'Identification cancelled.';
    }
  }

  async fetchCatalogue(): Promise<void> {
    if (!this.path || !this.solution) return;
    this.catalogueError = null;
    try {
      const start = await this.api.catalogue(this.path);
      this.jobs.ingest(start.job);
      this.catalogueJobId = start.job_id;
    } catch (err) {
      this.catalogueError = errText(err);
    }
  }

  finishCatalogue(job: JobEntry): void {
    if (job.id !== this.catalogueJobId) return;
    if (job.state === 'done') {
      const layers = parseFileLayers(job.result);
      if (layers && (!layers.path || layers.path === this.path)) {
        this.layers = layers;
        if (this.gLimit === null && layers.display_mag_limit !== null) this.gLimit = layers.display_mag_limit;
      }
    } else if (job.state === 'failed') {
      this.catalogueError = job.error?.message ?? 'Catalogues unavailable.';
    }
  }

  setVisible(id: LayerId | DisplayToggle, on: boolean): void {
    this.visibility = { ...this.visibility, [id]: on };
    savePref(PREF_LAYERS, this.visibility);
  }

  // -- Measure ----------------------------------------------------------------------------------

  /** Measure the star near a frame pixel (A73; snaps to the peak within 6 green px). */
  async measureAt(x: number, y: number, snap = true): Promise<void> {
    if (!this.path) return;
    this.measureController?.abort();
    const controller = new AbortController();
    this.measureController = controller;
    this.measureAt_ = { x, y };
    this.measuring = true;
    this.measureError = null;
    try {
      const m = await this.api.measure({ path: this.path, x, y, radius: this.aperture, snap }, controller.signal);
      if (controller.signal.aborted) return;
      this.measure = m;
    } catch (err) {
      if (controller.signal.aborted) return;
      this.measureError = errText(err);
    } finally {
      if (this.measureController === controller) {
        this.measuring = false;
        this.measureController = null;
      }
    }
  }

  /** A new aperture re-measures the star on screen (no snap: the same star). */
  setAperture(r: number): void {
    if (!isAperture(r)) return;
    this.aperture = r;
    savePref(PREF_APERTURE, r);
    const m = this.measure;
    if (m?.found && m.x !== null && m.y !== null) void this.measureAt(m.x, m.y, false);
  }

  clearMeasure(): void {
    this.measureController?.abort();
    this.measure = null;
    this.measureAt_ = null;
    this.measuring = false;
    this.measureError = null;
  }

  // -- Display ------------------------------------------------------------------------------------

  setLevel(patch: Partial<Omit<StretchParams, 'mode'>>): void {
    const base = this.levels ?? NEUTRAL_STRETCH;
    this.manual = { ...base, ...patch };
    this.autoStretch = false;
  }

  toggleAuto(): void {
    this.autoStretch = !this.autoStretch;
    if (!this.autoStretch && !this.manual) this.manual = this.autoLevels ?? NEUTRAL_STRETCH;
  }

  resetStretch(): void {
    this.manual = { ...NEUTRAL_STRETCH };
    this.autoStretch = false;
  }

  toggleRail(): void {
    this.railOpen = !this.railOpen;
    savePref(PREF_RAIL, this.railOpen);
  }

  dispose(): void {
    this.openController?.abort();
    this.measureController?.abort();
  }
}

/**
 * R2's own viewer tools (CFA preview, palette, crosshair mode, loupe, saturation, region):
 * remembered per viewer under `argos.review.r2.view.*`, apart from Observe's `argos.view.*`
 * (07 2.4 "Persistence": R2 preview mode, palette, loupe, saturation are R2's).
 */
export function r2ViewerTools(): ViewerTools {
  let ls: Storage | null = null;
  try {
    ls = globalThis.localStorage ?? null;
  } catch {
    ls = null;
  }
  const map = (k: string) => k.replace(/^argos\.view\./, 'argos.review.r2.view.');
  const store = ls
    ? {
        getItem: (k: string) => {
          try {
            return ls!.getItem(map(k));
          } catch {
            return null;
          }
        },
        setItem: (k: string, v: string) => {
          try {
            ls!.setItem(map(k), v);
          } catch {
            /* storage full or blocked */
          }
        },
      }
    : null;
  return new ViewerTools(store);
}

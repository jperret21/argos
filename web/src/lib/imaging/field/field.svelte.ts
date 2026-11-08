/**
 * Field identification on the client (wave 4): the server's field, catalogue, layers,
 * tracking, selection and target set as Svelte 5 reactive state, the observer's layer
 * choices (per viewer, Q5), the hover link between the lists and the image, and the calls
 * that change them (protocol.md "API 2 routes, wave 4"; README 4.3 A32-A33, A43-A49,
 * A51-A53).
 *
 * Events arrive through ArgosEvents.on(type) (raw listeners), so api/events.svelte.ts needs
 * no new field; every message is checked before it replaces the held record (an unknown or
 * malformed message is dropped, never fatal). Records are replaced wholesale ($state.raw:
 * the Gaia layer can hold thousands of markers; no deep proxy on them, PROPOSAL 3.4).
 *
 *   const field = new FieldStore();
 *   $effect(() => field.attach(events));      // returns the unsubscribe
 *   field.refresh(client);                     // REST snapshots after each (re)connection
 *   await field.select(client, { x, y, seq, tol_px });
 */

import { loadPref, savePref } from '../../app/prefs';
import { defaultVisibility, isVisibility, LAYER_IDS, type DisplayToggle, type LayerId, type Visibility } from '../../viewer/overlay/layers';
import type { Point } from '../../viewer/overlay/project';
import type {
  Candidate,
  CatalogState,
  FieldLayers,
  FieldState,
  FieldTransform,
  PendingStar,
  Role,
  SelectRequest,
  SelectionEvent,
  TargetSet,
  TargetStar,
} from './types';

/** The client of api/client.ts, reduced to what the field needs (tests pass a fake). */
export interface FieldClient {
  request<T>(method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE', path: string, body?: unknown): Promise<T>;
}

/** ArgosEvents, reduced to its raw listeners. */
export interface FieldEventSource {
  on(type: string, fn: (msg: Record<string, unknown>) => void): () => void;
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

// -- Message checks (the shape the UI relies on; extra fields pass through) ------------------

const FIELD_STATES = new Set(['none', 'solving', 'solved', 'failed', 'invalidated']);
const CATALOG_STATES = new Set(['idle', 'fetching', 'ready', 'error']);
const SELECTION_STATES = new Set(['identifying', 'resolved', 'no_match', 'failed', 'tracking']);
const ROLE_SET = new Set(['target', 'comparison', 'check']);

export function checkField(m: unknown): FieldState | null {
  if (!isObj(m) || typeof m.state !== 'string' || !FIELD_STATES.has(m.state)) return null;
  const grid = isObj(m.grid) && Array.isArray(m.grid.lines) ? (m.grid as unknown as FieldState['grid']) : null;
  return {
    ...(m as unknown as FieldState),
    auto: m.auto === true,
    reason: typeof m.reason === 'string' ? m.reason : null,
    solution: isObj(m.solution) && isNum(m.solution.ra_hours) ? (m.solution as unknown as FieldState['solution']) : null,
    wcs: isObj(m.wcs) && Array.isArray(m.wcs.cd) ? (m.wcs as unknown as FieldState['wcs']) : null,
    grid: grid ? { ...grid, labels: Array.isArray(grid.labels) ? grid.labels : [] } : null,
    target_reticle: isObj(m.target_reticle) && isNum(m.target_reticle.x) && isNum(m.target_reticle.y) ? (m.target_reticle as unknown as FieldState['target_reticle']) : null,
  };
}

export function checkCatalog(m: unknown): CatalogState | null {
  if (!isObj(m) || typeof m.state !== 'string' || !CATALOG_STATES.has(m.state)) return null;
  return {
    ...(m as unknown as CatalogState),
    counts: isObj(m.counts) ? (m.counts as CatalogState['counts']) : {},
    warnings: Array.isArray(m.warnings) ? m.warnings.filter((w): w is string => typeof w === 'string') : [],
    error: typeof m.error === 'string' ? m.error : null,
  };
}

export function checkLayers(m: unknown): FieldLayers | null {
  if (!isObj(m) || !isNum(m.generation) || !isObj(m.layers)) return null;
  const layers: FieldLayers['layers'] = {};
  for (const id of LAYER_IDS) {
    const list = m.layers[id];
    if (Array.isArray(list)) layers[id] = list.filter((p) => isObj(p) && isNum(p.x) && isNum(p.y)) as FieldLayers['layers'][LayerId];
  }
  const cands = Array.isArray(m.candidates) ? m.candidates.filter((c) => isObj(c) && typeof c.key === 'string') : [];
  return {
    ...(m as unknown as FieldLayers),
    available: m.available === true,
    layers,
    counts: isObj(m.counts) ? (m.counts as FieldLayers['counts']) : {},
    candidates: cands as unknown as Candidate[],
  };
}

export function checkTransform(m: unknown): FieldTransform | null {
  if (!isObj(m) || !isNum(m.generation) || !isNum(m.dx) || !isNum(m.dy) || !isNum(m.rot_deg)) return null;
  return m as unknown as FieldTransform;
}

/** A SelectionEvent; `{id: null, selection: null}` (nothing selected) is valid. */
export function checkSelection(m: unknown): SelectionEvent | null {
  if (!isObj(m)) return null;
  if (m.state !== undefined && (typeof m.state !== 'string' || !SELECTION_STATES.has(m.state))) return null;
  const sel = isObj(m.selection) && typeof m.selection.title === 'string' && Array.isArray(m.selection.rows) ? (m.selection as unknown as SelectionEvent['selection']) : null;
  const id = isNum(m.id) ? m.id : (sel?.id ?? null);
  if (id === null && sel === null && !('selection' in m)) return null;
  return { ...(m as unknown as SelectionEvent), id, selection: sel, message: typeof m.message === 'string' ? m.message : null };
}

export function checkTargets(m: unknown): TargetSet | null {
  if (!isObj(m) || typeof m.object_name !== 'string' || !Array.isArray(m.stars)) return null;
  const stars = m.stars.filter((s) => isObj(s) && typeof s.key === 'string' && typeof s.role === 'string' && ROLE_SET.has(s.role));
  return {
    ...(m as unknown as TargetSet),
    stars: stars as unknown as TargetStar[],
    summary: isObj(m.summary) ? m.summary : null,
    geometry: isObj(m.geometry) ? (m.geometry as unknown as TargetSet['geometry']) : null,
  };
}

/** The A52 body that puts a set star back as it was (Undo of a removal or a role change). */
export function pendingFrom(s: TargetStar): PendingStar {
  return {
    ra_deg: s.ra_deg ?? s.ra_hours * 15,
    dec_deg: s.dec_deg,
    ra_hours: s.ra_hours,
    auid: s.auid,
    name: s.name,
    source: s.source,
    mags: s.mags,
    chart_id: s.chart_id,
  };
}

// -- The hover link --------------------------------------------------------------------------

/** What is hovered and where it is, so the other views can mark it. */
export interface HoverMark {
  /** Who hovered: a list row marks the image; the image marks the list row. */
  source: 'image' | 'candidates' | 'exposure' | 'list';
  /** Target-set / candidate key (the image hover sets the marker's key). */
  key: string | null;
  /** Marker row id in the virtual lists (markerRowId). */
  id?: string | null;
  /** Frame px to ring on the image. */
  points: readonly Point[];
  /** `points` are reference-solve px (catalogue positions: the tracking moves them). */
  reference?: boolean;
}

/** The id of a marker's row in the Variables / Stars lists, and of its hover from the image. */
export function markerRowId(layer: string, m: { id?: string; x: number; y: number }): string {
  return m.id ? `${layer}:${m.id}` : `${layer}@${m.x.toFixed(1)},${m.y.toFixed(1)}`;
}

/** Undo of a role change: what to call to put the set back. */
export interface RoleUndo {
  label: string;
  run: () => Promise<TargetSet | null>;
}

/** Which star a role is for: the current selection, a set star, a variable, or a star record. */
export type RoleSubject =
  | { selection: number; key?: string | null }
  | { star: PendingStar; key?: string | null }
  | { variableIndex: number; key?: string | null };

const LAYERS_PREF = 'argos.field.layers';
/** Framing and Focus keep their own layer choices (the image is the hero there). */
const QUIET_MODES = ['framing', 'focus'] as const;
type LayerScope = 'field' | (typeof QUIET_MODES)[number];
const scopeOf = (mode: string): LayerScope => ((QUIET_MODES as readonly string[]).includes(mode) ? (mode as LayerScope) : 'field');
const prefKey = (scope: LayerScope) => (scope === 'field' ? LAYERS_PREF : `${LAYERS_PREF}.${scope}`);

/** Framing and Focus by default: the grid and the target set only. */
export function quietVisibility(): Visibility {
  const v = defaultVisibility();
  for (const k of Object.keys(v) as (keyof Visibility)[]) v[k] = k === 'grid' || k === 'selected';
  return v;
}
const HISTORY = 5;

type Store = Parameters<typeof savePref>[2];

export class FieldStore {
  field: FieldState | null = $state.raw(null);
  catalog: CatalogState | null = $state.raw(null);
  layers: FieldLayers | null = $state.raw(null);
  transform: FieldTransform | null = $state.raw(null);
  selection: SelectionEvent | null = $state.raw(null);
  targets: TargetSet | null = $state.raw(null);

  /** The Observe mode on screen: Framing and Focus have their own layer toggles. */
  mode: string = $state('field');
  /** Layer and display toggles per mode scope (localStorage, Q5). */
  private byScope: Record<LayerScope, Visibility> = $state({ field: defaultVisibility(), framing: quietVisibility(), focus: quietVisibility() });
  /** Gaia display depth (`catalog.display_mag_limit`): the layers' value until the config says. */
  gLimit: number | null = $state(null);
  /** Current hover link. */
  hover: HoverMark | null = $state.raw(null);
  /** The Inspector's star (candidate key), and the last five for comparing. */
  inspected: string | null = $state(null);
  history: string[] = $state([]);
  /** A select request is on the way (the card says so at once). */
  selecting = $state(false);

  private readonly superseded = new Set<number>();
  private readonly store: Store | undefined;

  constructor(options: { storage?: Store } = {}) {
    this.store = options.storage;
    const field = { ...defaultVisibility(), ...loadPref(LAYERS_PREF, isVisibility, {}, this.store) };
    const framing = { ...quietVisibility(), ...loadPref(prefKey('framing'), isVisibility, {}, this.store) };
    const focus = { ...quietVisibility(), ...loadPref(prefKey('focus'), isVisibility, {}, this.store) };
    this.byScope = { field, framing, focus };
  }

  /** Layer and display toggles of the mode on screen. */
  get visibility(): Visibility {
    return this.byScope[scopeOf(this.mode)];
  }

  // -- Derived ------------------------------------------------------------------------------

  /** A solution exists (a failed attempt keeps the last one). */
  get solved(): boolean {
    const s = this.field?.state;
    return !!this.field?.solution && (s === 'solved' || s === 'failed' || s === 'solving');
  }

  get solving(): boolean {
    return this.field?.state === 'solving';
  }

  /** The solution is an opened file's: never a reference for the mount (Centre, Sync). */
  get fileSolution(): boolean {
    return this.solved && this.field?.solution?.frame_origin === 'file';
  }

  /** The tracking lock is lost: the overlays stand where the field was last seen. */
  get trackingLost(): boolean {
    return this.activeTransform?.tracking === 'lost';
  }

  /** The tracking correction of the layers on screen (ignored when it belongs to another generation). */
  get activeTransform(): FieldTransform | null {
    const t = this.transform;
    return t && this.layers && t.generation === this.layers.generation ? t : null;
  }

  get fetching(): boolean {
    return this.catalog?.state === 'fetching';
  }

  /** The catalogue layers belong to a solved field. */
  get layersAvailable(): boolean {
    return !!this.layers?.available && this.solved;
  }

  get candidates(): readonly Candidate[] {
    return this.layers?.candidates ?? [];
  }

  /** Photometry aperture radius, frame px. */
  get apertureR(): number | null {
    return this.layers?.aperture_r_px ?? this.targets?.geometry?.aperture_r_px ?? null;
  }

  /** The depth in force: the observer's, else the one the layers were counted with. */
  get depth(): number | null {
    return this.gLimit ?? this.layers?.display_mag_limit ?? null;
  }

  count(id: LayerId): number | null {
    if (!this.layersAvailable || !this.layers) return null;
    const c = this.layers.counts[id];
    return typeof c === 'number' ? c : (this.layers.layers[id]?.length ?? 0);
  }

  /** The set's star with this key. */
  targetStar(key: string | null | undefined): TargetStar | null {
    if (!key || !this.targets) return null;
    return this.targets.stars.find((s) => s.key === key) ?? null;
  }

  // -- Events -------------------------------------------------------------------------------

  /** Subscribe to the server's field events; returns the unsubscribe. */
  attach(events: FieldEventSource): () => void {
    const types = ['field', 'catalog', 'field_layers', 'field_transform', 'selection', 'targets'];
    const offs = types.map((t) => events.on(t, (m) => this.ingest(t, m)));
    return () => offs.forEach((off) => off());
  }

  /** One message or REST snapshot. Returns whether it was kept. */
  ingest(type: string, m: unknown): boolean {
    switch (type) {
      case 'field': {
        const f = checkField(m);
        if (!f) return false;
        this.field = f;
        // The server drops the layers, transform and selection with the field (P24); so do we,
        // without waiting for their own events.
        if (f.state === 'invalidated' || f.state === 'none') this.clearField();
        return true;
      }
      case 'catalog': {
        const c = checkCatalog(m);
        if (c) this.catalog = c;
        return !!c;
      }
      case 'field_layers': {
        const l = checkLayers(m);
        if (l) this.layers = l;
        return !!l;
      }
      case 'field_transform': {
        const t = checkTransform(m);
        if (t) this.transform = t;
        return !!t;
      }
      case 'selection': {
        const s = checkSelection(m);
        if (!s) return false;
        if (s.id !== null && this.superseded.has(s.id)) return false; // a late answer to a replaced click
        this.selection = s.selection ? s : null;
        return true;
      }
      case 'targets': {
        const t = checkTargets(m);
        if (t) this.targets = t;
        return !!t;
      }
      default:
        return false;
    }
  }

  /**
   * A new server process (boot_id changed): its selection ids start at 1 again, so the
   * ids superseded under the old process would hide its first selections.
   */
  restart(): void {
    this.superseded.clear();
    this.selection = null;
  }

  private clearField(): void {
    this.layers = null;
    this.transform = null;
    this.selection = null;
    this.hover = null;
  }

  // -- Viewer choices -----------------------------------------------------------------------

  setVisible(id: LayerId | DisplayToggle, on: boolean): void {
    const scope = scopeOf(this.mode);
    const next = { ...this.byScope[scope], [id]: on };
    this.byScope = { ...this.byScope, [scope]: next };
    savePref(prefKey(scope), next, this.store);
  }

  toggle(id: LayerId | DisplayToggle): void {
    this.setVisible(id, !this.visibility[id]);
  }

  /** Mark something hovered; a null from one source never clears another source's mark. */
  setHover(mark: HoverMark | null, source?: HoverMark['source']): void {
    if (mark === null && source && this.hover && this.hover.source !== source) return;
    this.hover = mark;
  }

  /** The image hovers a marker (FieldOverlay onhover): its list row is marked. */
  hoverMarker(hit: { layer: string; marker: { id?: string; key?: string | null; x: number; y: number } } | null): void {
    if (!hit) return this.setHover(null, 'image');
    const m = hit.marker;
    this.setHover({ source: 'image', key: m.key ?? null, id: markerRowId(hit.layer, m), points: [{ x: m.x, y: m.y }], reference: true });
  }

  /** What a list hovers, for the overlay's rings (the image's own hover draws the marker hot instead). */
  get listMark(): HoverMark | null {
    return this.hover && this.hover.source !== 'image' ? this.hover : null;
  }

  /** Put a star in the Inspector and its short history (last five). */
  inspect(key: string | null): void {
    this.inspected = key;
    if (key === null) return;
    this.history = [key, ...this.history.filter((k) => k !== key)].slice(0, HISTORY);
  }

  // -- Calls --------------------------------------------------------------------------------

  /** Every snapshot (on load and after a reconnection; a failing route waits for its event). */
  async refresh(client: FieldClient): Promise<void> {
    const get = async (path: string, type: string) => {
      try {
        this.ingest(type, await client.request<unknown>('GET', path));
      } catch {
        /* the event stream will bring it */
      }
    };
    await Promise.all([
      get('/api/field', 'field'),
      get('/api/field/catalog', 'catalog'),
      get('/api/field/layers', 'field_layers'),
      get('/api/field/transform', 'field_transform'),
      get('/api/field/select', 'selection'),
      get('/api/targets', 'targets'),
    ]);
  }

  /** A43: identify the field (202 {job_id, field}; the result comes as `field` events). */
  async solve(client: FieldClient): Promise<string | null> {
    const r = await client.request<{ job_id?: string; field?: unknown }>('POST', '/api/field/solve', {});
    if (r && r.field) this.ingest('field', r.field);
    return typeof r?.job_id === 'string' ? r.job_id : null;
  }

  /** A43: cancel the running solve (manual or automatic); the previous solution stays. */
  async cancelSolve(client: FieldClient): Promise<void> {
    this.ingest('field', await client.request<unknown>('DELETE', '/api/field/solve'));
  }

  /** A44: keep the field identified automatically. */
  async setAuto(client: FieldClient, enabled: boolean): Promise<void> {
    this.ingest('field', await client.request<unknown>('PUT', '/api/field/auto', { enabled }));
  }

  /** A46: fetch the catalogues again (409 not_solved before a solve). */
  async refetch(client: FieldClient): Promise<void> {
    this.ingest('catalog', await client.request<unknown>('POST', '/api/field/catalog/refetch'));
  }

  /**
   * A49: identify or measure what is under a click. A new click replaces the running
   * lookup (P10, P21): the late events of the previous one are dropped here, the server
   * drops its answer.
   */
  async select(client: FieldClient, req: SelectRequest): Promise<SelectionEvent | null> {
    const previous = this.selection?.id ?? null;
    if (previous !== null) this.superseded.add(previous);
    this.selecting = true;
    try {
      const ev = checkSelection(await client.request<unknown>('POST', '/api/field/select', req));
      // An event for this id may already have arrived (the socket can beat the reply): keep the newer state.
      if (ev && (this.selection?.id !== ev.id || this.selection === null)) this.selection = ev.selection ? ev : null;
      return ev;
    } finally {
      this.selecting = false;
    }
  }

  /** A49 DELETE: close the card and drop the ring. */
  async clearSelection(client: FieldClient | null): Promise<void> {
    const id = this.selection?.id;
    if (id !== null && id !== undefined) this.superseded.add(id);
    this.selection = null;
    if (!client) return;
    try {
      await client.request('DELETE', '/api/field/select');
    } catch {
      /* nothing selected on the server any more: same result */
    }
  }

  /**
   * A52: give a star a role; the server writes targets/<object>.json. Returns the new set
   * and how to undo it (README 3.8 toasts): a star that had another role gets it back, a
   * star that was not in the set is taken out again.
   */
  async setRole(client: FieldClient, role: Role, subject: RoleSubject): Promise<{ set: TargetSet | null; undo: RoleUndo | null }> {
    const before = this.targetStar(subject.key);
    const keysBefore = new Set((this.targets?.stars ?? []).map((s) => s.key));
    const body =
      'selection' in subject
        ? { role, selection: subject.selection }
        : 'variableIndex' in subject
          ? { role, variable_index: subject.variableIndex }
          : { role, star: subject.star };
    const set = checkTargets(await client.request<unknown>('POST', '/api/targets', body));
    if (set) this.targets = set;
    let undo: RoleUndo | null = null;
    if (before) {
      if (before.role !== role) undo = { label: 'Undo', run: () => this.restore(client, before) };
    } else {
      const added = set?.stars.find((s) => !keysBefore.has(s.key) && s.role === role) ?? null;
      if (added) undo = { label: 'Undo', run: () => this.remove(client, added.key).then((r) => r.set) };
    }
    return { set, undo };
  }

  private async restore(client: FieldClient, star: TargetStar): Promise<TargetSet | null> {
    const set = checkTargets(await client.request<unknown>('POST', '/api/targets', { role: star.role, star: pendingFrom(star) }));
    if (set) this.targets = set;
    return set;
  }

  /** A53: take a star out of the set; Undo puts it back with its role (A52 with `removed`). */
  async remove(client: FieldClient, key: string): Promise<{ set: TargetSet | null; undo: RoleUndo | null }> {
    const known = this.targetStar(key);
    const set = checkTargets(await client.request<unknown>('DELETE', `/api/targets/${encodeURIComponent(key)}`));
    if (set) this.targets = set;
    const removed = set?.removed ?? known;
    return { set, undo: removed ? { label: 'Undo', run: () => this.restore(client, removed) } : null };
  }

  /** A32: centre the mount on the target (body's, else the set's target, else the last GoTo). */
  center(client: FieldClient, target?: { ra_hours: number; dec_deg: number; name?: string }): Promise<unknown> {
    return client.request('POST', '/api/mount/center', target ? { target } : {});
  }

  /** A33: sync the mount on the current frame's solved centre (no slew). */
  sync(client: FieldClient): Promise<unknown> {
    return client.request('POST', '/api/mount/sync', { source: 'solution' });
  }
}

/**
 * The Observe workspace: the task mode (D1) and the layout each mode
 * remembers (rail open and width, card states, band shown and height, drawer
 * open, tab and height), per viewer. Promoted from
 * src/lab/workspace/model/workspace.svelte.ts.
 *
 * - Keys: argos.observe.mode, argos.layout.observe.<mode> (prefs.ts, wrapped
 *   in try / catch: the UI works the same without storage). "Reset all
 *   layouts" (Settings › Appearance) removes argos.layout.*; reload() then
 *   brings the presets back (ImagingScreen calls it on app.layoutGeneration).
 * - A mode marks itself when its layout differs from its preset (`modified`,
 *   `changedKeys`), and Arrange resets it (with Undo, through `onreset`).
 * - The mode never changes by itself; an unavailable mode (Field, Run in this
 *   version) is refused with its reason.
 * - The switch cross-fades through a View Transition when the engine has one
 *   and motion is allowed (BRAND 9: task-mode switches only, `--duration-base`);
 *   otherwise it is instant.
 */

import { loadPref, removePref, savePref } from '../../app/prefs';
import {
  arrangementChanged,
  changedKeys,
  clonePreset,
  isMode,
  MODE_KEY,
  modeDef,
  modeLayoutKey,
  MODES,
  RAIL,
  sanitize,
  type CardId,
  type CardState,
  type DrawerTab,
  type Mode,
  type ModeLayout,
} from './layout';

/** Storage the workspace may use (a Map-backed fake in tests; null = none). */
export type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export interface WorkspaceOptions {
  /** undefined: the browser's localStorage (prefs.ts); null: nothing is remembered. */
  store?: StorageLike | null;
  /** A reset happened: offer Undo (the caller owns the toast queue). */
  onreset?: (what: string, undo: () => void) => void;
  /** Run a mode switch (a View Transition wrapper); default: at once. */
  transition?: (apply: () => void) => void;
}

const isModeValue = (v: unknown): v is Mode => isMode(v) && !modeDef(v).unavailable;

export class ObserveWorkspace {
  mode: Mode = $state('framing');
  layouts: Record<Mode, ModeLayout> = $state({} as Record<Mode, ModeLayout>);
  /** While a separator is dragged: what the layout costs, shown on the image. */
  dragReadout: string | null = $state(null);
  /** The Arrange popover is open. */
  arrangeOpen = $state(false);

  readonly layout: ModeLayout = $derived(this.layouts[this.mode]);
  readonly changed: string[] = $derived(changedKeys(this.mode, this.layouts[this.mode]));
  /** The mark on the Arrange icon: arrangement choices only, never the drawer or H. */
  readonly modified: boolean = $derived(arrangementChanged(this.mode, this.layouts[this.mode]).length > 0);

  private readonly store: StorageLike | null | undefined;
  private readonly onreset: WorkspaceOptions['onreset'];
  private readonly transition: (apply: () => void) => void;

  constructor(options: WorkspaceOptions = {}) {
    this.store = options.store;
    this.onreset = options.onreset;
    this.transition = options.transition ?? ((apply) => apply());
    this.mode = loadPref(MODE_KEY, isModeValue, 'framing', this.storeArg());
    this.layouts = this.loadAll();
  }

  /** prefs.ts takes `undefined` as "the browser's localStorage". */
  private storeArg(): StorageLike | null | undefined {
    return this.store;
  }

  private loadAll(): Record<Mode, ModeLayout> {
    const out = {} as Record<Mode, ModeLayout>;
    for (const m of MODES) out[m.id] = sanitize(m.id, loadPref(modeLayoutKey(m.id), isAny, undefined, this.storeArg()));
    return out;
  }

  /** Re-read every layout from storage (after "Reset all layouts" elsewhere). */
  reload(): void {
    this.layouts = this.loadAll();
  }

  /** Whether a mode can be chosen, and why not. */
  reason(mode: Mode): string | null {
    return modeDef(mode).unavailable;
  }

  modifiedMode(mode: Mode): boolean {
    return arrangementChanged(mode, this.layouts[mode]).length > 0;
  }

  /** Switch the task mode (never automatic). Returns the refusal reason, if any. */
  setMode(mode: Mode): string | null {
    const why = this.reason(mode);
    if (why) return why;
    if (mode === this.mode) return null;
    this.transition(() => {
      this.mode = mode;
      this.dragReadout = null;
      savePref(MODE_KEY, mode, this.storeArg());
    });
    return null;
  }

  /** Change the current mode's layout and remember it. */
  edit(fn: (l: ModeLayout) => void): void {
    const l = this.layouts[this.mode];
    fn(l);
    savePref(modeLayoutKey(this.mode), $state.snapshot(l), this.storeArg());
  }

  setCard(id: CardId, state: CardState): void {
    this.edit((l) => (l.cards[id] = state));
  }

  /** A card's own fold (its header): open <-> folded, in this mode. */
  setCardOpen(id: CardId, open: boolean): void {
    if (this.layout.cards[id] === 'hidden') return;
    this.setCard(id, open ? 'open' : 'folded');
  }

  toggleRail(): void {
    this.edit((l) => (l.railOpen = !l.railOpen));
  }

  setRailWidth(px: number): void {
    const w = Math.round(Math.min(RAIL.max, Math.max(RAIL.min, px)));
    this.edit((l) => (l.railW = w));
  }

  toggleBand(): void {
    this.edit((l) => (l.bandOpen = !l.bandOpen));
  }

  /** A dragged band height, or null for "fits the image" (BRAND 11.1). */
  setBandHeight(px: number | null): void {
    this.edit((l) => (l.bandH = px === null ? null : Math.round(px)));
  }

  /** D (or L for the Log tab): open on `tab`, or close when it is already the open tab. */
  toggleDrawer(tab?: DrawerTab): void {
    this.edit((l) => {
      if (tab && (!l.drawerOpen || l.drawerTab !== tab)) {
        l.drawerOpen = true;
        l.drawerTab = tab;
      } else l.drawerOpen = !l.drawerOpen;
    });
  }

  setDrawer(patch: Partial<Pick<ModeLayout, 'drawerOpen' | 'drawerTab' | 'drawerH'>>): void {
    this.edit((l) => Object.assign(l, patch));
  }

  /** Back to the mode's preset, at once; Undo through `onreset`. */
  resetMode(mode: Mode = this.mode): void {
    const before = $state.snapshot(this.layouts[mode]) as ModeLayout;
    this.layouts[mode] = clonePreset(mode);
    removePref(modeLayoutKey(mode), this.storeArg());
    this.onreset?.(`${modeDef(mode).label} layout reset`, () => {
      this.layouts[mode] = sanitize(mode, before);
      savePref(modeLayoutKey(mode), before, this.storeArg());
    });
  }

  /** Every mode back to its preset (Arrange › Reset all modes). */
  resetAll(): void {
    const before = Object.fromEntries(MODES.map((m) => [m.id, $state.snapshot(this.layouts[m.id])])) as Record<
      Mode,
      ModeLayout
    >;
    for (const m of MODES) {
      this.layouts[m.id] = clonePreset(m.id);
      removePref(modeLayoutKey(m.id), this.storeArg());
    }
    this.onreset?.('Every Observe mode back to its layout', () => {
      for (const m of MODES) {
        this.layouts[m.id] = sanitize(m.id, before[m.id]);
        savePref(modeLayoutKey(m.id), before[m.id], this.storeArg());
      }
    });
  }
}

const isAny = (v: unknown): v is unknown => v !== undefined;

/** A View Transition for the mode switch, skipped under reduced motion (BRAND 9). */
export function viewTransition(apply: () => void): void {
  const doc = globalThis.document as (Document & { startViewTransition?: (cb: () => void) => unknown }) | undefined;
  const root = doc?.documentElement;
  const motion = root?.getAttribute('data-motion');
  const reduced =
    motion === 'reduced' ||
    (motion !== 'full' && typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches);
  if (!doc?.startViewTransition || reduced) {
    apply();
    return;
  }
  try {
    const t = doc.startViewTransition(apply) as
      | { skipTransition?: () => void; finished?: Promise<unknown>; ready?: Promise<unknown>; updateCallbackDone?: Promise<unknown> }
      | undefined;
    // A skipped transition rejects `ready` (AbortError): expected, not an error.
    void t?.ready?.catch(() => undefined);
    void t?.updateCallbackDone?.catch(() => undefined);
    // While a transition runs the page takes no pointer input. On a slow GPU (a
    // software renderer measured 3.5 s) that would freeze the toolbar after a mode
    // switch: never let it last longer than TRANSITION_CAP_MS.
    const cap = setTimeout(() => t?.skipTransition?.(), TRANSITION_CAP_MS);
    void t?.finished?.finally(() => clearTimeout(cap)).catch(() => undefined);
  } catch {
    apply();
  }
}

/** The longest a mode-switch transition may hold the page (PROPOSAL 3.4: 180 ms animations). */
export const TRANSITION_CAP_MS = 400;

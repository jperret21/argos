/**
 * Workspace state of the prototype: the active section and Observe mode, the
 * per-mode layouts (remembered per viewer), the overlays (palette, Watch,
 * attention, arrange, lab panel), the selection and the viewer tools.
 *
 * Layouts persist under the LAB's own keys (argos.lab.workspace.*), wrapped
 * in try / catch, never under the app's argos.* keys. In the app they would
 * become argos.layout.observe.<mode>.* through lib/app/prefs.ts.
 */

import type { StretchParams } from '../../../lib/viewer/stretch';
import type { DisplayInfo } from '../../../lib/viewer/types';
import { changedKeys, clonePreset, MODES, sanitize, type CardId, type CardState, type DrawerTab, type Mode, type ModeLayout } from './layout';

export type Section = 'connection' | 'observe' | 'plan' | 'review' | 'settings';
export type Overlay = 'none' | 'palette' | 'watch' | 'overview';
export type Tool = 'none' | 'region';

const KEY = 'argos.lab.workspace';

function load(key: string): unknown {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? undefined : JSON.parse(raw);
  } catch {
    return undefined;
  }
}

function save(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* private window or blocked storage: the layout simply is not remembered */
  }
}

function remove(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

export interface Toast {
  id: number;
  text: string;
  tone: 'info' | 'ok' | 'warn';
  action?: { label: string; run: () => void };
}

export class Workspace {
  section: Section = $state('observe');
  mode: Mode = $state('run');
  overlay: Overlay = $state('none');
  attentionOpen = $state(false);
  arrangeOpen = $state(false);
  labOpen = $state(false);
  layouts: Record<Mode, ModeLayout> = $state({
    framing: sanitize('framing', load(`${KEY}.layout.framing`)),
    focus: sanitize('focus', load(`${KEY}.layout.focus`)),
    field: sanitize('field', load(`${KEY}.layout.field`)),
    run: sanitize('run', load(`${KEY}.layout.run`)),
  });
  /** Selected star id (Inspector), and the last five selections. */
  selected: number | null = $state(null);
  history: number[] = $state([]);
  /** Star id hovered in a table: ringed on the image. */
  hovered: number | null = $state(null);
  tool: Tool = $state('none');
  crosshair = $state(false);
  grid = $state(false);
  labels = $state(true);
  autoStretch = $state(true);
  fitMode: 'fit' | 'fill' = $state('fit');
  timeAxis: 'utc' | 'jd' = $state('utc');
  errorBars = $state(true);
  watchDim: 100 | 60 | 30 = $state(100);
  toasts: Toast[] = $state([]);
  /** Mode suggestion chip on the image ("Run started · Run view Alt+4"). */
  suggestion: { text: string; mode: Mode } | null = $state(null);
  /** While a separator is dragged: its live readout. */
  dragReadout: string | null = $state(null);
  /** Manual display levels when auto stretch is off. */
  stretch: StretchParams | null = $state(null);
  /** Histogram and auto levels of the frame on screen (from the viewer). */
  display: DisplayInfo | null = $state.raw(null);
  /** Zoom of the viewer, device px per image px (1 = 1:1). */
  zoom = $state(1);
  /** Imperative viewer API, set by the viewer while it is mounted. */
  viewer: { fit(): void; oneToOne(): void; zoomBy(f: number): void } | null = null;

  layout: ModeLayout = $derived(this.layouts[this.mode]);
  modified = $derived(changedKeys(this.mode, this.layouts[this.mode]).length > 0);

  private toastId = 0;

  setMode(mode: Mode, viaTransition = true): void {
    if (mode === this.mode && this.section === 'observe') return;
    const apply = () => {
      this.section = 'observe';
      this.mode = mode;
      this.suggestion = null;
      save(`${KEY}.mode`, mode);
    };
    const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
    const reduced =
      document.documentElement.getAttribute('data-motion') === 'reduced' ||
      (document.documentElement.getAttribute('data-motion') !== 'full' &&
        matchMedia('(prefers-reduced-motion: reduce)').matches);
    if (viaTransition && !reduced && doc.startViewTransition) doc.startViewTransition(apply);
    else apply();
  }

  /** Mutate the current mode's layout and remember it. */
  edit(fn: (l: ModeLayout) => void): void {
    fn(this.layouts[this.mode]);
    save(`${KEY}.layout.${this.mode}`, this.layouts[this.mode]);
  }

  setCard(id: CardId, state: CardState): void {
    this.edit((l) => (l.cards[id] = state));
  }

  toggleRail(): void {
    this.edit((l) => (l.railOpen = !l.railOpen));
  }

  toggleBand(): void {
    this.edit((l) => (l.bandOpen = !l.bandOpen));
  }

  toggleDrawer(tab?: DrawerTab): void {
    this.edit((l) => {
      if (tab && (!l.drawerOpen || l.drawerTab !== tab)) {
        l.drawerOpen = true;
        l.drawerTab = tab;
      } else l.drawerOpen = !l.drawerOpen;
    });
  }

  resetMode(mode: Mode = this.mode): void {
    this.layouts[mode] = clonePreset(mode);
    remove(`${KEY}.layout.${mode}`);
    this.toast(`${MODES.find((m) => m.id === mode)?.label} layout reset`, 'info');
  }

  resetAll(): void {
    for (const m of MODES) {
      this.layouts[m.id] = clonePreset(m.id);
      remove(`${KEY}.layout.${m.id}`);
    }
    this.toast('All four layouts reset', 'info');
  }

  select(id: number | null): void {
    this.selected = id;
    if (id !== null) this.history = [id, ...this.history.filter((h) => h !== id)].slice(0, 5);
  }

  toast(text: string, tone: Toast['tone'] = 'info', action?: Toast['action']): void {
    const id = ++this.toastId;
    this.toasts = [...this.toasts, { id, text, tone, action }].slice(-3);
    setTimeout(() => (this.toasts = this.toasts.filter((t) => t.id !== id)), 6000);
  }
}

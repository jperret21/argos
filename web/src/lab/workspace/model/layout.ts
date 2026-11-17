/**
 * Task modes and their layout presets (functional-spaces.md P1, P10), as
 * plain data plus pure functions, so they can be unit-tested and promoted
 * to lib/app as they are.
 *
 * A mode is a named layout of the SAME regions: which rail cards are open,
 * folded or hidden, what the band under the image shows, which tool group
 * the toolbar adds, and the drawer's default tab. No data or hardware state
 * depends on the mode, and the app never switches mode by itself.
 */

import { stripLayout, type Size } from '../../../lib/imaging/layout';

export type Mode = 'framing' | 'focus' | 'field' | 'run';

export interface ModeDef {
  id: Mode;
  label: string;
  icon: string;
  /** Matched on KeyboardEvent.code (Digit1-4) so it works on AZERTY and macOS. */
  key: string;
  task: string;
  band: string;
}

export const MODES: readonly ModeDef[] = [
  { id: 'framing', label: 'Framing', icon: 'goto', key: 'Alt+1', task: 'Point, frame and check the exposure', band: 'Levels and exposure check' },
  { id: 'focus', label: 'Focus', icon: 'focuser', key: 'Alt+2', task: 'Focus and autofocus', band: 'V-curve and HFD trend' },
  { id: 'field', label: 'Field', icon: 'plate-solve', key: 'Alt+3', task: 'Identify the field, choose the stars', band: 'Comparison candidates' },
  { id: 'run', label: 'Run', icon: 'light-curve', key: 'Alt+4', task: 'Watch a run at the table', band: 'Live light curve' },
];

export type CardId = 'run' | 'inspector' | 'mount' | 'camera' | 'focuser' | 'photometry' | 'conditions' | 'field';
export type CardState = 'open' | 'folded' | 'hidden';
export type DrawerTab = 'log' | 'curve' | 'conditions' | 'ensemble';

export const CARD_LABELS: Record<CardId, { title: string; icon: string }> = {
  run: { title: 'Run', icon: 'nav-sequencer' },
  inspector: { title: 'Inspector', icon: 'lab-inspector' },
  mount: { title: 'Mount', icon: 'mount' },
  camera: { title: 'Camera', icon: 'camera' },
  focuser: { title: 'Focuser', icon: 'focuser' },
  photometry: { title: 'Photometry', icon: 'photometry' },
  conditions: { title: 'Conditions', icon: 'session-metrics' },
  field: { title: 'Field', icon: 'plate-solve' },
};

export const DRAWER_TABS: readonly { id: DrawerTab; label: string; icon: string }[] = [
  { id: 'log', label: 'Log', icon: 'log' },
  { id: 'curve', label: 'Light curve', icon: 'light-curve' },
  { id: 'conditions', label: 'Conditions', icon: 'session-metrics' },
  { id: 'ensemble', label: 'Ensemble', icon: 'comparison-quality' },
];

export interface ModeLayout {
  railOpen: boolean;
  railW: number;
  bandOpen: boolean;
  /** null: the band takes exactly the space the fitted image leaves (BRAND 11.1). */
  bandH: number | null;
  drawerOpen: boolean;
  drawerTab: DrawerTab;
  drawerH: number;
  /** Card order is fixed per mode; this gives each card's state. */
  cards: Record<CardId, CardState>;
}

export const CARD_ORDER: Record<Mode, readonly CardId[]> = {
  framing: ['mount', 'camera', 'focuser', 'photometry', 'inspector', 'field', 'run', 'conditions'],
  focus: ['focuser', 'camera', 'mount', 'photometry', 'inspector', 'field', 'run', 'conditions'],
  field: ['inspector', 'photometry', 'field', 'camera', 'mount', 'focuser', 'run', 'conditions'],
  run: ['run', 'photometry', 'conditions', 'mount', 'camera', 'inspector', 'field', 'focuser'],
};

const hidden = (): Record<CardId, CardState> => ({
  run: 'hidden',
  inspector: 'hidden',
  mount: 'hidden',
  camera: 'hidden',
  focuser: 'hidden',
  photometry: 'hidden',
  conditions: 'hidden',
  field: 'hidden',
});

const base = { railOpen: true, railW: 400, bandOpen: true, bandH: null, drawerOpen: false, drawerH: 216 } as const;

export const PRESETS: Record<Mode, ModeLayout> = {
  framing: { ...base, drawerTab: 'log', cards: { ...hidden(), mount: 'open', camera: 'open', focuser: 'folded', photometry: 'folded' } },
  focus: { ...base, drawerTab: 'log', cards: { ...hidden(), focuser: 'open', camera: 'open', mount: 'folded', photometry: 'folded' } },
  field: { ...base, drawerTab: 'log', cards: { ...hidden(), inspector: 'open', photometry: 'open', field: 'open', camera: 'folded', mount: 'folded' } },
  run: { ...base, drawerTab: 'curve', cards: { ...hidden(), run: 'open', photometry: 'open', conditions: 'open', mount: 'folded', camera: 'folded' } },
};

export function clonePreset(mode: Mode): ModeLayout {
  const p = PRESETS[mode];
  return { ...p, cards: { ...p.cards } };
}

/** Fields of a layout that differ from its mode's preset (for the "modified" mark). */
export function changedKeys(mode: Mode, l: ModeLayout): string[] {
  const p = PRESETS[mode];
  const out: string[] = [];
  for (const k of ['railOpen', 'railW', 'bandOpen', 'bandH', 'drawerOpen', 'drawerTab', 'drawerH'] as const) {
    if (l[k] !== p[k]) out.push(k);
  }
  for (const id of Object.keys(p.cards) as CardId[]) if (l.cards[id] !== p.cards[id]) out.push(`card.${id}`);
  return out;
}

/** A stored layout is trusted only field by field (storage can hold anything). */
export function sanitize(mode: Mode, raw: unknown): ModeLayout {
  const out = clonePreset(mode);
  if (typeof raw !== 'object' || raw === null) return out;
  const r = raw as Record<string, unknown>;
  if (typeof r.railOpen === 'boolean') out.railOpen = r.railOpen;
  if (typeof r.railW === 'number' && r.railW >= 340 && r.railW <= 580) out.railW = Math.round(r.railW);
  if (typeof r.bandOpen === 'boolean') out.bandOpen = r.bandOpen;
  if (r.bandH === null || (typeof r.bandH === 'number' && r.bandH >= 36 && r.bandH <= 900)) out.bandH = r.bandH as number | null;
  if (typeof r.drawerOpen === 'boolean') out.drawerOpen = r.drawerOpen;
  if (typeof r.drawerH === 'number' && r.drawerH >= 120 && r.drawerH <= 900) out.drawerH = Math.round(r.drawerH);
  if (DRAWER_TABS.some((t) => t.id === r.drawerTab)) out.drawerTab = r.drawerTab as DrawerTab;
  if (typeof r.cards === 'object' && r.cards !== null) {
    const c = r.cards as Record<string, unknown>;
    for (const id of Object.keys(out.cards) as CardId[]) {
      if (c[id] === 'open' || c[id] === 'folded' || c[id] === 'hidden') out.cards[id] = c[id] as CardState;
    }
  }
  return out;
}

// -- Band under the image ---------------------------------------------------------------

export const BAND = { compactBelow: 120, compactH: 36, minViewer: 200 } as const;

export interface BandLayout {
  /** Band height, CSS px (0 when closed). */
  height: number;
  /** One summary row instead of the full content. */
  compact: boolean;
  /** Viewer height left above the band. */
  viewer: number;
  /** Black margins of the fitted image in the viewer (cost of the layout). */
  sideBands: { x: number; y: number };
  /** Displayed image size at fit. */
  image: Size;
}

/**
 * Band height: by default exactly the space the fitted image leaves
 * (lib/imaging/layout.ts stripLayout, BRAND 11.1); a dragged height
 * overrides it, clamped so the viewer keeps BAND.minViewer px.
 */
export function bandLayout(center: Size, frame: Size, drawer: number, open: boolean, userH: number | null): BandLayout {
  const avail = Math.max(0, center.height - drawer);
  let height = 0;
  let compact = false;
  if (open && center.width > 0 && avail > 0) {
    if (userH === null) {
      // The compact row still takes the whole band, so no black margin
      // appears around the fitted image (BRAND 11.1).
      const s = stripLayout(center, frame, drawer, true);
      height = Math.min(s.height, Math.max(0, avail - BAND.minViewer));
      compact = height < BAND.compactBelow;
      if (compact) height = Math.min(Math.max(BAND.compactH, height), avail);
    } else {
      height = Math.max(BAND.compactH, Math.min(userH, avail - BAND.minViewer));
      compact = height < BAND.compactBelow;
      if (compact) height = BAND.compactH;
    }
  }
  const viewer = Math.max(0, avail - height);
  const scale = frame.width > 0 && viewer > 0 ? Math.min(center.width / frame.width, viewer / frame.height) : 0;
  const image = { width: frame.width * scale, height: frame.height * scale };
  return {
    height,
    compact,
    viewer,
    image,
    sideBands: { x: Math.max(0, (center.width - image.width) / 2), y: Math.max(0, (viewer - image.height) / 2) },
  };
}

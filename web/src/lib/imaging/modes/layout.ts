/**
 * Observe task modes and their layouts (owner decision D1, web/lab/PROPOSAL.md
 * sections 3.1 and 10; BRAND 2 principle 8 and 11.1), as plain data plus pure
 * functions. Promoted from src/lab/workspace/model/layout.ts.
 *
 * A mode is a named layout of the SAME regions: which rail cards are open,
 * folded or hidden, the right panel's width, the band under the image (shown
 * or not, its height), and the drawer (open, tab, height). No data or hardware
 * state depends on the mode, and the app never switches mode by itself.
 *
 * Differences from the lab, and why:
 * - The rail keeps ONE card order in every mode, the order of decision D10
 *   (Camera, Mount, Focuser among the cards of wave 3); a mode changes the
 *   states only. D10 is a decision in force; the lab reordered per mode.
 * - Field is available from wave 4 (its band hosts the comparison candidates,
 *   imaging/field); Run (waves 5 and 6) is listed but not available: its band
 *   needs live photometry and the sequencer.
 * - Wave 4 adds the Statistics card (D9: hidden by default in every mode, I
 *   shows it), in its D10 place after Camera.
 * - The band turns into its one-row summary below 150 px (BRAND 11.1,
 *   STRIP.min), not 120 px as in the lab; the right panel is 360-580 px with
 *   400 px by default (D8); the drawer 160 px to half the section (README 1.1).
 */

import { clampDrawerHeight, DRAWER_DEFAULT_HEIGHT, DRAWER_MIN_HEIGHT } from '../../app/panels';
import { STRIP, stripLayout, type Size } from '../layout';

export type Mode = 'framing' | 'focus' | 'field' | 'run';

export interface ModeDef {
  id: Mode;
  label: string;
  icon: string;
  /** Registry id of its shortcut (Alt+1-4, matched on the physical key). */
  shortcut: string;
  /** What the observer does in this mode (tooltip). */
  task: string;
  /** What the band under the image shows. */
  band: string;
  /** Why the mode cannot be chosen in this version (null: available). */
  unavailable: string | null;
}

export const MODES: readonly ModeDef[] = [
  {
    id: 'framing',
    label: 'Framing',
    icon: 'goto',
    shortcut: 'observe.mode.framing',
    task: 'Point, frame and check the exposure',
    band: 'Levels and exposure check',
    unavailable: null,
  },
  {
    id: 'focus',
    label: 'Focus',
    icon: 'focuser',
    shortcut: 'observe.mode.focus',
    task: 'Focus and autofocus',
    band: 'V-curve and HFD trend',
    unavailable: null,
  },
  {
    id: 'field',
    label: 'Field',
    icon: 'plate-solve',
    shortcut: 'observe.mode.field',
    task: 'Identify the field, choose the stars',
    band: 'Comparison candidates',
    unavailable: null,
  },
  {
    id: 'run',
    label: 'Run',
    icon: 'light-curve',
    shortcut: 'observe.mode.run',
    task: 'Watch a run',
    band: 'Live light curve',
    unavailable: 'not in this version: it comes with live photometry and sequences (waves 5 and 6)',
  },
];

export const AVAILABLE_MODES: readonly Mode[] = MODES.filter((m) => !m.unavailable).map((m) => m.id);

export function modeDef(id: Mode): ModeDef {
  return MODES.find((m) => m.id === id) ?? MODES[0];
}

export function isMode(v: unknown): v is Mode {
  return MODES.some((m) => m.id === v);
}

/** The rail cards of this version, in the one order of decision D10 (README 1.3). */
export const CARD_IDS = ['camera', 'statistics', 'inspector', 'mount', 'focuser'] as const;
export type CardId = (typeof CARD_IDS)[number];
export type CardState = 'open' | 'folded' | 'hidden';
export const CARD_STATES: readonly CardState[] = ['open', 'folded', 'hidden'];

export const CARD_LABELS: Record<CardId, { title: string; icon: string }> = {
  camera: { title: 'Camera', icon: 'camera' },
  statistics: { title: 'Statistics', icon: 'statistics' },
  inspector: { title: 'Inspector', icon: 'inspector' },
  mount: { title: 'Mount', icon: 'mount' },
  focuser: { title: 'Focuser', icon: 'focuser' },
};

/** Drawer tabs of this version; the Log tab is always last (LogDrawer, 01 2.3.9). */
export const DRAWER_TABS = [
  { id: 'conditions', label: 'Conditions', icon: 'session-metrics' },
  { id: 'log', label: 'Log', icon: 'log' },
] as const;
export type DrawerTab = (typeof DRAWER_TABS)[number]['id'];

export interface ModeLayout {
  railOpen: boolean;
  /** Right panel width, CSS px (D8: 360-580, 400 by default). */
  railW: number;
  bandOpen: boolean;
  /** null: the band takes exactly the space the fitted image leaves (BRAND 11.1). */
  bandH: number | null;
  drawerOpen: boolean;
  drawerTab: DrawerTab;
  drawerH: number;
  cards: Record<CardId, CardState>;
}

export const RAIL = { min: 360, max: 580, default: 400 } as const;

const base = {
  railOpen: true,
  railW: RAIL.default,
  bandOpen: true,
  bandH: null,
  drawerOpen: false,
  drawerH: DRAWER_DEFAULT_HEIGHT,
} as const;

export const PRESETS: Record<Mode, ModeLayout> = {
  framing: { ...base, drawerTab: 'log', cards: { camera: 'open', statistics: 'hidden', inspector: 'hidden', mount: 'open', focuser: 'folded' } },
  focus: { ...base, drawerTab: 'conditions', cards: { camera: 'open', statistics: 'hidden', inspector: 'hidden', mount: 'folded', focuser: 'open' } },
  // Field: the band holds the candidates, the Inspector the picked star; the Mount card
  // (Centre target, Sync) stays open.
  field: { ...base, drawerTab: 'log', cards: { camera: 'folded', statistics: 'hidden', inspector: 'open', mount: 'open', focuser: 'hidden' } },
  run: { ...base, drawerTab: 'log', cards: { camera: 'folded', statistics: 'hidden', inspector: 'hidden', mount: 'folded', focuser: 'hidden' } },
};

export function clonePreset(mode: Mode): ModeLayout {
  const p = PRESETS[mode];
  return { ...p, cards: { ...p.cards } };
}

const FIELDS = ['railOpen', 'railW', 'bandOpen', 'bandH', 'drawerOpen', 'drawerTab', 'drawerH'] as const;

/** Fields of a layout that differ from its mode's preset (the "changed" mark, what Reset undoes). */
export function changedKeys(mode: Mode, l: ModeLayout): string[] {
  const p = PRESETS[mode];
  const out: string[] = [];
  for (const k of FIELDS) if (l[k] !== p[k]) out.push(k);
  for (const id of CARD_IDS) if (l.cards[id] !== p.cards[id]) out.push(`card.${id}`);
  return out;
}

/**
 * The momentary toggles (the drawer open or closed and its tab, the band shown
 * or hidden with H, the Statistics card shown with I) are not an arrangement:
 * they never light the "layout changed" mark, or it would be on most of the
 * time (design review W3).
 */
export const MOMENTARY: readonly string[] = ['drawerOpen', 'drawerTab', 'bandOpen', 'card.statistics'];

/** The arrangement choices that differ from the preset (cards, band height, rail width…). */
export function arrangementChanged(mode: Mode, l: ModeLayout): string[] {
  return changedKeys(mode, l).filter((k) => !MOMENTARY.includes(k));
}

/** A stored layout is trusted field by field (storage can hold anything, or an older shape). */
export function sanitize(mode: Mode, raw: unknown): ModeLayout {
  const out = clonePreset(mode);
  if (typeof raw !== 'object' || raw === null) return out;
  const r = raw as Record<string, unknown>;
  const num = (v: unknown, lo: number, hi: number) => typeof v === 'number' && Number.isFinite(v) && v >= lo && v <= hi;
  if (typeof r.railOpen === 'boolean') out.railOpen = r.railOpen;
  if (num(r.railW, RAIL.min, RAIL.max)) out.railW = Math.round(r.railW as number);
  if (typeof r.bandOpen === 'boolean') out.bandOpen = r.bandOpen;
  if (r.bandH === null || num(r.bandH, BAND.compactH, 2000)) out.bandH = r.bandH === null ? null : Math.round(r.bandH as number);
  if (typeof r.drawerOpen === 'boolean') out.drawerOpen = r.drawerOpen;
  if (num(r.drawerH, DRAWER_MIN_HEIGHT, 2000)) out.drawerH = Math.round(r.drawerH as number);
  if (DRAWER_TABS.some((t) => t.id === r.drawerTab)) out.drawerTab = r.drawerTab as DrawerTab;
  if (typeof r.cards === 'object' && r.cards !== null) {
    const c = r.cards as Record<string, unknown>;
    for (const id of CARD_IDS) {
      if (CARD_STATES.includes(c[id] as CardState)) out.cards[id] = c[id] as CardState;
    }
  }
  return out;
}

/** Storage key of a mode's layout ("Reset all layouts" clears argos.layout.*). */
export const modeLayoutKey = (mode: Mode) => `argos.layout.observe.${mode}`;
export const MODE_KEY = 'argos.observe.mode';

// -- Band under the image ---------------------------------------------------------------

export const BAND = {
  /** Below this the band is its one-row summary (BRAND 11.1). */
  compactBelow: STRIP.min,
  /** Height of the one-row summary when the observer dragged the band that low. */
  compactH: 36,
  /** The viewer always keeps this much height. */
  minViewer: 200,
  /** The band's header row (title, size, Fit to image, hide). */
  headerH: 28,
} as const;

export interface BandLayout {
  /** Band height, CSS px, its top separator included (0 when closed). */
  height: number;
  /** One summary row instead of the full content. */
  compact: boolean;
  /** Viewer height left above the band. */
  viewer: number;
  /** Displayed image size at fit. */
  image: Size;
  /** Black margins of the fitted image in the viewer: what the layout costs. */
  sideBands: { x: number; y: number };
}

/**
 * Band height: by default exactly the space the fitted image leaves
 * (stripLayout, unchanged); a dragged height overrides it, kept so the viewer
 * has at least BAND.minViewer px. `frame` is the DISPLAYED (rotated) size.
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
      compact = s.compact || height < BAND.compactBelow;
      if (compact) height = Math.min(Math.max(STRIP.compact, height), avail);
    } else {
      height = Math.max(BAND.compactH, Math.min(userH, avail - BAND.minViewer));
      compact = height < BAND.compactBelow;
      if (compact) height = Math.min(BAND.compactH, avail);
    }
  }
  const viewer = Math.max(0, avail - height);
  const scale = frame.width > 0 && frame.height > 0 && viewer > 0 ? Math.min(center.width / frame.width, viewer / frame.height) : 0;
  const image = { width: frame.width * scale, height: frame.height * scale };
  return {
    height,
    compact,
    viewer,
    image,
    sideBands: { x: Math.max(0, (center.width - image.width) / 2), y: Math.max(0, (viewer - image.height) / 2) },
  };
}

/** Largest band height a drag may set (the viewer keeps BAND.minViewer). */
export function bandMax(center: Size, drawer: number): number {
  return Math.max(BAND.compactH, Math.floor(center.height - drawer - BAND.minViewer));
}

/** Drawer height on screen: the remembered one, kept within 160 px and half the section. */
export function drawerHeight(l: Pick<ModeLayout, 'drawerOpen' | 'drawerH'>, centreH: number): number {
  if (!l.drawerOpen || centreH <= 0) return 0;
  return clampDrawerHeight(l.drawerH, Math.floor(centreH / 2));
}

/**
 * What a layout change costs, in words (shown on the image while a separator
 * is dragged, PROPOSAL 2.5): "Band 445 px · image 681 × 383 · side margins 133 px".
 */
export function layoutCost(what: 'band' | 'drawer' | 'rail', b: BandLayout, extra: { drawer?: number; rail?: number; fits?: boolean }): string {
  const img = `image ${Math.round(b.image.width)} × ${Math.round(b.image.height)}`;
  const margins =
    b.sideBands.x >= 1
      ? `side margins ${Math.round(b.sideBands.x)} px`
      : b.sideBands.y >= 1
        ? `top and bottom margins ${Math.round(b.sideBands.y)} px`
        : 'no black margin';
  if (what === 'rail') return `Right panel ${extra.rail ?? 0} px · ${img} · ${margins}`;
  if (what === 'drawer') {
    return `Drawer ${extra.drawer ?? 0} px · band ${b.compact ? 'one row' : `${b.height} px`} · ${img} · ${margins}`;
  }
  return `Band ${b.height} px${extra.fits ? ' (fits the image)' : ''} · ${img} · ${margins}`;
}

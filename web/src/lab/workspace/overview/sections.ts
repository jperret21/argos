/**
 * How every section inherits the same regions (the Observe workspace's
 * grammar), as data in the 1440 x 900 reference frame. Region kinds:
 *
 * - toolbar: one 44 px row; section actions on the left, then the same
 *   right end everywhere (command field Mod+K, Watch, Arrange, Panels);
 * - hero: the section's main content (image, steps, plot wall, form);
 * - band: a mode- or task-dependent strip docked to the hero;
 * - rail: the right panel of foldable cards (per mode / view);
 * - drawer: tabs under the hero, Log in every section;
 * - strip: a thin status strip (run strip, health strip, night checklist).
 *
 * Sources: spec README 1.1 / 1.2 and functional-spaces.md (P1-P13).
 */

import type { Section } from '../model/workspace.svelte';

export type RegionKind = 'toolbar' | 'hero' | 'band' | 'rail' | 'drawer' | 'strip' | 'column';

export interface Region {
  kind: RegionKind;
  x: number;
  y: number;
  w: number;
  h: number;
  title: string;
  /** Short lines shown inside the region (full size only, or in mini when `mini`). */
  lines?: string[];
  /** New in this proposal (drawn with a marker). */
  isNew?: boolean;
}

export interface SectionDef {
  id: Section;
  label: string;
  icon: string;
  key: string;
  /** One line: what the section is for. */
  role: string;
  /** Toolbar left items (icon ids with a label). */
  actions: { icon: string; label: string }[];
  /** Views or modes inside the section, if any. */
  views?: string[];
  regions: Region[];
  /** What it inherits / what changes, for the overview captions. */
  notes: string[];
}

const TOP = 44;
const BOTTOM = 872; // status bar from 872 to 900
const L = 92;
const R = 1440;
const RAIL = 400;
const RX = R - RAIL;

export const SECTIONS: readonly SectionDef[] = [
  {
    id: 'connection',
    label: 'Connection',
    icon: 'nav-connection',
    key: 'F1',
    role: 'Link, devices, instrument; the night checklist',
    actions: [
      { icon: 'connect', label: 'Connect all' },
      { icon: 'disconnect', label: 'Disconnect all' },
      { icon: 'discover', label: 'Discover' },
    ],
    regions: [
      { kind: 'strip', x: L, y: TOP, w: R - L, h: 64, title: 'Night checklist', lines: ['devices · clock · site vs mount · disk · field · roles · calibration'], isNew: true },
      { kind: 'column', x: L, y: TOP + 64, w: 520, h: 480, title: 'Instrument · Link', lines: ['profile, specs, caveats', 'Simulator | Seestar, discovery'] },
      { kind: 'hero', x: L + 520, y: TOP + 64, w: R - L - 520, h: 480, title: 'Devices', lines: ['mount, camera, filter wheel, focuser', 'state, full reason, retry', 'Planetarium bridge'] },
      { kind: 'drawer', x: L, y: TOP + 544, w: R - L, h: BOTTOM - TOP - 544, title: 'Connection log', lines: ['the Log, filtered on connection topics'] },
    ],
    notes: ['No right panel: one screen, nothing scrolls but the log', 'New: the night checklist strip (site against mount, disk, calibration)'],
  },
  {
    id: 'observe',
    label: 'Observe',
    icon: 'nav-imaging',
    key: 'F2',
    role: 'The cockpit: image, band, cards, in four task modes',
    actions: [
      { icon: 'capture', label: '' },
      { icon: 'live', label: '' },
      { icon: 'zoom-fit', label: '' },
    ],
    views: ['Framing', 'Focus', 'Field', 'Run'],
    regions: [
      { kind: 'hero', x: L, y: TOP, w: RX - L, h: 533, title: 'Image', lines: ['HUD: chips, field, compass, scale, cursor, histogram', 'roles, star card, region statistics'] },
      { kind: 'band', x: L, y: TOP + 533, w: RX - L, h: BOTTOM - TOP - 533, title: 'Task band', lines: ['Framing: levels + exposure check', 'Focus: V-curve + HFD', 'Field: candidates', 'Run: live light curve'], isNew: true },
      { kind: 'rail', x: RX, y: TOP, w: RAIL, h: BOTTOM - TOP, title: 'Mode cards', lines: ['Run · Inspector · Photometry', 'Conditions · Mount', 'Camera · Focuser · Field', 'open / folded / hidden per mode'] },
    ],
    notes: ['Modes re-arrange the same regions (Alt+1-4)', 'Drawer on demand: Log · Light curve · Conditions · Ensemble'],
  },
  {
    id: 'plan',
    label: 'Plan',
    icon: 'nav-sequencer',
    key: 'F3',
    role: 'Steps and time: build, check and run the sequence',
    actions: [
      { icon: 'bookmark', label: 'Presets' },
      { icon: 'save', label: 'Save' },
      { icon: 'start', label: 'Start sequence' },
    ],
    regions: [
      { kind: 'strip', x: L, y: TOP, w: RX - L, h: 40, title: 'Run strip', lines: ['REC 160/195 · last frame 12 s · ETA 30m'] },
      { kind: 'hero', x: L, y: TOP + 40, w: RX - L, h: 420, title: 'Steps', lines: ['type, filter, exposure, gain, count, cadence', 'totals and end time'] },
      { kind: 'band', x: L, y: TOP + 460, w: RX - L, h: 190, title: 'Visibility', lines: ['altitude, limit, now, run band, transit'] },
      { kind: 'drawer', x: L, y: TOP + 650, w: RX - L, h: BOTTOM - TOP - 650, title: 'Log', lines: [] },
      { kind: 'rail', x: RX, y: TOP, w: RAIL, h: BOTTOM - TOP, title: 'Plan cards', lines: ['Source · Run options', 'Target set (shared)', 'repeat, autofocus, end of run'] },
    ],
    notes: ['Preflight popover gains disk, site and calibration lines', 'Start / Pause / Stop also in Observe › Run'],
  },
  {
    id: 'review',
    label: 'Review',
    icon: 'nav-analyze',
    key: 'F4',
    role: 'Sessions by night, the plot wall, frames, export',
    actions: [
      { icon: 'open-session', label: 'RR Lyr · 2026-09-25' },
      { icon: 'rerun-photometry', label: 'Re-run' },
      { icon: 'export-aavso', label: 'Export AAVSO' },
    ],
    views: ['Sessions', 'Session', 'Frame'],
    regions: [
      { kind: 'strip', x: L, y: TOP, w: RX - L, h: 56, title: 'Health strip', lines: ['frames and gaps · HFD > 1.5× baseline · comps used · site check'], isNew: true },
      { kind: 'hero', x: L, y: TOP + 56, w: RX - L, h: 556, title: 'Plot wall', lines: ['target · check · one facet per comparison', 'conditions · one time axis, one crosshair'] },
      { kind: 'drawer', x: L, y: TOP + 612, w: RX - L, h: BOTTOM - TOP - 612, title: 'Frames · Ensemble · Log', lines: ['virtual table, 10 000 rows'] },
      { kind: 'rail', x: RX, y: TOP, w: RAIL, h: BOTTOM - TOP, title: 'Review cards', lines: ['Selected point · Ensemble', 'Session · AAVSO export', 'point UTC / JD / BJD, frame'] },
    ],
    notes: ['Same light-curve component as Observe › Run', 'Sessions grouped by night; trial runs folded'],
  },
  {
    id: 'settings',
    label: 'Settings',
    icon: 'nav-configuration',
    key: 'F5',
    role: 'Persistent parameters, one form per key',
    actions: [{ icon: 'search', label: 'Filter settings' }],
    regions: [
      { kind: 'column', x: L, y: TOP, w: 240, h: BOTTOM - TOP, title: 'Categories', lines: ['Observer & site', 'Instrument', 'Plate solving', 'Catalogues', 'Photometry', 'Alerts (new)', 'Appearance'] },
      { kind: 'hero', x: L + 240, y: TOP, w: 880, h: BOTTOM - TOP, title: 'Form', lines: ['max 880 px, immediate apply', 'the same forms open as sheets elsewhere'] },
      { kind: 'column', x: L + 1120, y: TOP, w: R - L - 1120, h: BOTTOM - TOP, title: 'Help', lines: ['at 1440 px and wider'] },
    ],
    notes: ['No right panel, no drawer (L still opens the Log)', 'New categories proposed: Alerts; Appearance › Density'],
  },
];

export const COMMON = [
  { title: 'Navigation rail', text: '92 px, five sections, state dots; theme and overview at the foot' },
  { title: 'Toolbar, one row', text: 'section actions left; command field (Mod+K), Watch (W), Arrange, Panels (P) at the right end, same place everywhere' },
  { title: 'Hero region', text: 'the section’s content gets the largest area; no dead bands' },
  { title: 'Right panel', text: 'foldable cards; a folded card keeps a one-line summary; open / folded / hidden remembered per view' },
  { title: 'Drawer', text: 'tabs under the hero, Log in every section (L); shrinks the band first, never the image' },
  { title: 'Status bar', text: 'devices, mount, run chip, attention chip, activity, Log: identical in every section' },
] as const;

/**
 * The keyboard map of the whole UI (web/spec/README.md section 3.10, decisions
 * D19, D21, D22): one table that the registry checks for conflicts, the "?"
 * sheet lists and tooltips read.
 *
 * Status of each row in this build:
 * - no flag: works today, dispatched by the registry (a handler is bound
 *   with registry.handle: the global keys in ArgosApp.bindShortcuts, the
 *   Observe keys by ImagingScreen while it is mounted);
 * - `planned`: specified, not built yet; kept here so the conflict check
 *   covers the full map, never listed in the sheet nor dispatched;
 * - `local`: handled by the focused component (tables, the jog pad).
 *
 * Not bound on purpose (BRAND 7, Q-O7): tracking (T), autofocus, focus steps
 * ([ ]), roles on the star card, start / pause / stop sequence, connect /
 * disconnect: they move or release hardware.
 */

import type { ShortcutDef } from './shortcuts';

/** Sheet group titles, by scope (sub-scopes fall back to their section). */
export const SCOPE_TITLES: Record<string, string> = {
  global: 'Global',
  connection: 'Connection',
  imaging: 'Observe',
  sequencer: 'Plan',
  analyze: 'Review',
  configuration: 'Settings',
  table: 'Tables',
  menu: 'Menus and lists',
};

const OBSERVE = 'imaging';
const R2 = 'analyze.r2';

/** Viewer tools shared by Observe and the Review frame inspector (R2). */
const VIEWER: ShortcutDef[] = [
  { id: 'view.zoom-in', keys: ['+'], label: 'Zoom in', scope: OBSERVE, repeat: true },
  { id: 'view.zoom-out', keys: ['-'], label: 'Zoom out', scope: OBSERVE, repeat: true },
  { id: 'view.fit', keys: ['F'], label: 'Fit the whole frame', scope: OBSERVE },
  { id: 'view.fill', keys: ['Shift+F'], label: 'Fill the viewer (crops)', scope: OBSERVE },
  { id: 'view.one-to-one', keys: ['1'], label: 'Actual pixels (1:1)', scope: OBSERVE },
  { id: 'view.stretch-auto', keys: ['A'], label: 'Auto stretch on / off', scope: OBSERVE },
  { id: 'view.stretch-reset', keys: ['Shift+A'], label: 'Reset stretch (linear)', scope: OBSERVE },
  { id: 'view.levels', keys: ['H'], label: 'Levels strip / Display card', scope: OBSERVE },
  { id: 'view.crosshair', keys: ['X'], label: 'Crosshair', scope: OBSERVE },
  { id: 'view.loupe', keys: ['Z'], label: 'Loupe', scope: OBSERVE, planned: true },
  { id: 'view.saturation', keys: ['C'], label: 'Saturation highlight', scope: OBSERVE, planned: true },
  { id: 'view.region', keys: ['R'], label: 'Region statistics', scope: OBSERVE, planned: true },
  { id: 'view.statistics', keys: ['I'], label: 'Statistics card', scope: OBSERVE, planned: true },
  { id: 'field.solve', keys: ['S'], label: 'Identify field', scope: OBSERVE, planned: true },
  { id: 'field.grid', keys: ['G'], label: 'Coordinate grid', scope: OBSERVE, planned: true },
  { id: 'field.labels', keys: ['N'], label: 'Object labels', scope: OBSERVE, planned: true },
  { id: 'field.catalogue', keys: ['O'], label: 'Catalogue layers', scope: OBSERVE, planned: true },
];

export const KEYMAP: readonly ShortcutDef[] = [
  // -- Global ----------------------------------------------------------------
  { id: 'nav.connection', keys: ['F1'], label: 'Connection', scope: 'global', inText: true },
  { id: 'nav.observe', keys: ['F2'], label: 'Observe', scope: 'global', inText: true },
  { id: 'nav.plan', keys: ['F3'], label: 'Plan', scope: 'global', inText: true },
  { id: 'nav.review', keys: ['F4'], label: 'Review', scope: 'global', inText: true },
  { id: 'nav.settings', keys: ['F5'], label: 'Settings', scope: 'global', inText: true },
  // Q-G9: macOS needs Fn for F-keys; in a browser Cmd+1…5 switch tabs, so desktop only.
  { id: 'nav.connection.desktop', keys: ['Mod+1'], label: 'Connection', scope: 'global', desktopOnly: true },
  { id: 'nav.observe.desktop', keys: ['Mod+2'], label: 'Observe', scope: 'global', desktopOnly: true },
  { id: 'nav.plan.desktop', keys: ['Mod+3'], label: 'Plan', scope: 'global', desktopOnly: true },
  { id: 'nav.review.desktop', keys: ['Mod+4'], label: 'Review', scope: 'global', desktopOnly: true },
  { id: 'nav.settings.desktop', keys: ['Mod+5'], label: 'Settings', scope: 'global', desktopOnly: true },
  { id: 'nav.settings.mod', keys: ['Mod+,'], label: 'Settings', scope: 'global' },
  { id: 'file.open-fits', keys: ['Mod+O'], label: 'Open FITS image', scope: 'global', planned: true },
  { id: 'review.sessions', keys: ['Mod+Shift+O'], label: 'Review sessions', scope: 'global', planned: true },
  { id: 'app.quit', keys: ['Mod+Q'], label: 'Quit ARGOS', scope: 'global', desktopOnly: true, planned: true },
  { id: 'help.shortcuts', keys: ['?'], label: 'Keyboard shortcuts', scope: 'global' },
  // Command palette (PROPOSAL 3.1, W2 end): every action with its key or its
  // unavailable reason; a hardware action opens its confirmation, never runs on Enter.
  { id: 'palette.open', keys: ['Mod+K'], label: 'Command palette', scope: 'global' },
  { id: 'log.toggle', keys: ['L'], label: 'Activity log', scope: 'global' },
  {
    id: 'motion.abort',
    keys: ['Escape'],
    label: 'Abort a slew; close the top menu, popover or dialog',
    scope: 'global',
    inText: true,
    evenIfHandled: true,
  },

  // -- Sections ----------------------------------------------------------------
  { id: 'drawer.toggle', keys: ['D'], label: 'Bottom drawer', scope: [OBSERVE, 'sequencer', 'analyze'], planned: true },
  { id: 'rail.toggle', keys: ['P'], label: 'Instrument rail', scope: OBSERVE },
  { id: 'rail.toggle.other', keys: ['P'], label: 'Right rail', scope: ['sequencer', 'analyze.r1', R2], planned: true },
  {
    id: 'search.focus',
    keys: ['/'],
    label: 'Focus the search field',
    scope: ['sequencer', 'analyze.r0'],
    planned: true,
  },
  { id: 'settings.filter', keys: ['/'], label: 'Filter the settings', scope: 'configuration' },

  // -- Observe -------------------------------------------------------------------
  { id: 'observe.capture', keys: ['E'], label: 'One exposure', scope: OBSERVE },
  { id: 'observe.live', keys: ['V'], label: 'Live view on / off', scope: OBSERVE },
  // Task modes (owner D1; BRAND 2 principle 8): Alt+digit, matched on the
  // physical key (macOS Option+1 types "¡"). The observer chooses; never automatic.
  { id: 'observe.mode.framing', keys: ['Alt+1'], label: 'Framing mode', scope: OBSERVE, planned: true },
  { id: 'observe.mode.focus', keys: ['Alt+2'], label: 'Focus mode', scope: OBSERVE, planned: true },
  { id: 'observe.mode.field', keys: ['Alt+3'], label: 'Field mode', scope: OBSERVE, planned: true },
  { id: 'observe.mode.run', keys: ['Alt+4'], label: 'Run mode', scope: OBSERVE, planned: true },
  // Watch view (owner D3): while it is open only W, Esc, ? and Mod+K act.
  { id: 'observe.watch', keys: ['W'], label: 'Watch view on / off', scope: OBSERVE, planned: true },
  ...VIEWER,
  { id: 'observe.jog-arm', keys: ['J'], label: 'Arm keyboard jogging', scope: OBSERVE, planned: true },
  {
    id: 'observe.jog',
    keys: ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'],
    label: 'Jog N / S / W / E (hold; jog pad focused or armed)',
    scope: 'imaging.jog',
    local: true,
    planned: true,
  },

  // -- Review ----------------------------------------------------------------------
  ...VIEWER.map((d) => ({ ...d, id: `r2.${d.id}`, scope: R2, planned: true })),
  { id: 'r1.zoom-in', keys: ['+'], label: 'Zoom the time axis in', scope: 'analyze.r1', planned: true },
  { id: 'r1.zoom-out', keys: ['-'], label: 'Zoom the time axis out', scope: 'analyze.r1', planned: true },
  { id: 'r1.fit', keys: ['F'], label: 'Fit all plots', scope: 'analyze.r1', planned: true },
  { id: 'r1.error-bars', keys: ['U'], label: 'Error bars', scope: 'analyze.r1', planned: true },
  { id: 'r1.flux', keys: ['M'], label: 'Magnitude / relative flux', scope: 'analyze.r1', planned: true },
  { id: 'r1.point', keys: ['ArrowLeft', 'ArrowRight'], label: 'Previous / next point', scope: 'analyze.r1', planned: true },
  { id: 'r1.open-frame', keys: ['Enter'], label: 'Open the frame of the selected point', scope: 'analyze.r1', planned: true },
  { id: 'r0.open', keys: ['Enter'], label: 'Open the selected session', scope: 'analyze.r0', planned: true },
  { id: 'r2.frame-prev', keys: ['PageUp'], label: 'Previous frame', scope: R2, planned: true },
  { id: 'r2.frame-next', keys: ['PageDown'], label: 'Next frame', scope: R2, planned: true },
  { id: 'r2.back', keys: ['Alt+ArrowLeft'], label: 'Back to the session', scope: R2, planned: true },

  // -- Plan --------------------------------------------------------------------------
  { id: 'plan.save', keys: ['Mod+S'], label: 'Save preset', scope: 'sequencer', planned: true },
  {
    id: 'plan.steps',
    keys: ['Insert', 'Mod+D', 'Delete', 'Alt+ArrowUp', 'Alt+ArrowDown', 'Space'],
    label: 'Add, duplicate, remove, move, enable a step',
    scope: 'sequencer.steps',
    local: true,
    planned: true,
  },

  // -- Components (handled where the focus is) ------------------------------------------
  {
    id: 'table.navigate',
    keys: ['ArrowUp', 'ArrowDown', 'Home', 'End'],
    label: 'Move the selected row',
    scope: 'table',
    local: true,
  },
  { id: 'table.activate', keys: ['Enter'], label: 'Open the selected row', scope: 'table', local: true },
  { id: 'table.copy', keys: ['Mod+C'], label: 'Copy the rows as TSV', scope: 'table', local: true },
  {
    id: 'menu.navigate',
    keys: ['ArrowUp', 'ArrowDown', 'Home', 'End'],
    label: 'Move in a menu or list; type letters to jump',
    scope: 'menu',
    local: true,
  },
  { id: 'menu.activate', keys: ['Enter', 'Space'], label: 'Choose the item', scope: 'menu', local: true },
];

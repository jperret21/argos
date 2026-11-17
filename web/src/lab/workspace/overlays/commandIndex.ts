/**
 * The palette's index: the app's shortcut registry (lib/app/keymap.ts, the
 * one table that already feeds tooltips and the "?" sheet) plus the
 * workspace's modes, views, panels, hardware actions, stars and settings.
 * Hardware actions carry their confirmation and, when the server would
 * refuse, the reason (the same words as the button's tooltip).
 */

import { KEYMAP } from '../../../lib/app/keymap';
import type { Command } from '../model/commands';
import { CARD_LABELS, CARD_ORDER, MODES, type CardId } from '../model/layout';
import { NAMED_STARS } from '../model/field';
import type { Sim } from '../model/sim.svelte';
import type { Workspace } from '../model/workspace.svelte';

export function buildIndex(ws: Workspace, sim: Sim): Command[] {
  const out: Command[] = [];
  const runLock = sim.running ? 'not now: the sequence is running (pause it first)' : null;

  for (const m of MODES) {
    out.push({
      id: `mode.${m.id}`,
      title: `Observe · ${m.label}`,
      group: 'Modes and views',
      icon: m.icon,
      keys: m.key,
      keywords: `${m.task} ${m.band} mode`,
      hint: m.task,
      run: () => ws.setMode(m.id),
    });
  }
  out.push(
    {
      id: 'view.watch',
      title: 'Watch the run from a distance',
      group: 'Modes and views',
      icon: 'lab-watch',
      keys: 'W',
      keywords: 'glance big night monitor distance',
      run: () => {
        sim.armSound();
        ws.overlay = 'watch';
      },
    },
    {
      id: 'view.overview',
      title: 'Sections overview',
      group: 'Modes and views',
      icon: 'layout-tile',
      keywords: 'structure regions connection plan review settings',
      run: () => (ws.overlay = 'overview'),
    },
    {
      id: 'view.attention',
      title: 'Attention list',
      group: 'Modes and views',
      icon: 'lab-attention',
      keywords: 'alerts alarm notifications acknowledge ack',
      hint: `${sim.unacked.length} open`,
      run: () => (ws.attentionOpen = true),
    },
  );

  // Hardware (BRAND 7: never on a single key; Enter opens the confirmation).
  out.push(
    {
      id: 'hw.park',
      title: 'Park the mount',
      group: 'Hardware',
      icon: 'park',
      keywords: 'close arm stop tracking end of night',
      hint: 'Mount',
      hardware: { question: 'Park the mount?', consequence: 'Parking closes the Seestar arm and stops tracking.', confirm: 'Park' },
      disabled: runLock,
      run: () => sim.park(),
    },
    {
      id: 'hw.slew',
      title: 'Slew to RR Lyr',
      group: 'Hardware',
      icon: 'goto',
      keywords: 'goto point mount target',
      hint: 'Mount',
      hardware: { question: 'Slew to RR Lyr?', consequence: 'The mount moves to 19h 25m 27.9s +42° 47′ 04″.', confirm: 'Slew' },
      disabled: runLock,
      run: () => ws.toast('Slewing to RR Lyr', 'info'),
    },
    {
      id: 'hw.pause',
      title: sim.runState === 'paused' ? 'Resume the run' : 'Pause the run',
      group: 'Hardware',
      icon: sim.runState === 'paused' ? 'start' : 'pause',
      keywords: 'sequence hold',
      hint: 'at the end of this frame',
      disabled: sim.inRun && (sim.running || sim.runState === 'paused') ? null : 'no run in progress',
      run: () => (sim.runState === 'paused' ? sim.resume() : sim.pause()),
    },
    {
      id: 'hw.stop',
      title: 'Stop the run…',
      group: 'Hardware',
      icon: 'stop',
      keywords: 'sequence end abort',
      hint: 'frames so far stay saved',
      hardware: { question: 'Stop the run?', consequence: 'Frames saved so far stay in the session; the frame being exposed is discarded.', confirm: 'Stop' },
      disabled: sim.running ? null : 'no run in progress',
      run: () => sim.stop(),
    },
    {
      id: 'hw.autofocus',
      title: 'Start autofocus',
      group: 'Hardware',
      icon: 'autofocus',
      keywords: 'focus v-curve hfd',
      hint: 'Focuser',
      hardware: { question: 'Start autofocus?', consequence: 'The focuser scans 14 positions; live frames are used.', confirm: 'Start' },
      disabled: runLock,
      run: () => ws.setMode('focus'),
    },
    {
      id: 'hw.darks',
      title: 'Take 20 darks for tonight',
      group: 'Hardware',
      icon: 'start',
      keywords: 'calibration dark bias wrap up end',
      hint: '10 s · gain 80 · about 17 min',
      hardware: { question: 'Take 20 darks?', consequence: 'A one-step sequence: 20 × 10 s, gain 80, Dark slot.', confirm: 'Start' },
      disabled: runLock,
      run: () => ws.toast('Darks started', 'info'),
    },
  );

  // Panels of the current mode.
  out.push(
    { id: 'panel.rail', title: 'Right panel', group: 'Panels', icon: 'panels', keys: 'P', run: () => ws.toggleRail() },
    { id: 'panel.band', title: 'Band under the image', group: 'Panels', icon: 'histogram', keys: 'H', run: () => ws.toggleBand() },
    { id: 'panel.drawer', title: 'Drawer', group: 'Panels', icon: 'arrange', keys: 'D', run: () => ws.toggleDrawer() },
    { id: 'panel.conditions', title: 'Drawer · Conditions timeline', group: 'Panels', icon: 'session-metrics', keywords: 'hfd stars sky trend', run: () => ws.toggleDrawer('conditions') },
    { id: 'panel.reset', title: 'Reset the layout of this mode', group: 'Panels', icon: 'layout-reset', run: () => ws.resetMode() },
  );
  for (const id of CARD_ORDER[ws.mode] as readonly CardId[]) {
    const state = ws.layout.cards[id];
    out.push({
      id: `card.${id}`,
      title: `${state === 'hidden' ? 'Show' : 'Hide'} the ${CARD_LABELS[id].title} card`,
      group: 'Panels',
      icon: id === 'inspector' ? 'metadata' : CARD_LABELS[id].icon,
      keywords: 'card panel rail',
      run: () => ws.setCard(id, state === 'hidden' ? 'open' : 'hidden'),
    });
  }

  // The app's registry: every Observe and global shortcut, by its label.
  const mapped: Record<string, () => void> = {
    'view.zoom-in': () => ws.viewer?.zoomBy(1.25),
    'view.zoom-out': () => ws.viewer?.zoomBy(0.8),
    'view.fit': () => ws.viewer?.fit(),
    'view.fill': () => (ws.fitMode = ws.fitMode === 'fill' ? 'fit' : 'fill'),
    'view.one-to-one': () => ws.viewer?.oneToOne(),
    'view.stretch-auto': () => (ws.autoStretch = !ws.autoStretch),
    'view.levels': () => ws.toggleBand(),
    'view.crosshair': () => (ws.crosshair = !ws.crosshair),
    'view.region': () => (ws.tool = ws.tool === 'region' ? 'none' : 'region'),
    'field.grid': () => (ws.grid = !ws.grid),
    'field.labels': () => (ws.labels = !ws.labels),
    'field.solve': () => ws.toast('Identify field (ASTAP)', 'info'),
    'log.toggle': () => ws.toggleDrawer('log'),
    'observe.live': () => sim.setLive(!sim.live),
    'observe.capture': () => ws.toast('Shot', 'info'),
    'nav.connection': () => (ws.section = 'connection'),
    'nav.observe': () => (ws.section = 'observe'),
    'nav.plan': () => (ws.section = 'plan'),
    'nav.review': () => (ws.section = 'review'),
    'nav.settings': () => (ws.section = 'settings'),
  };
  const ICON: Record<string, string> = {
    'view.zoom-in': 'zoom-in',
    'view.zoom-out': 'zoom-out',
    'view.fit': 'zoom-fit',
    'view.fill': 'zoom-fill',
    'view.one-to-one': 'zoom-1to1',
    'view.stretch-auto': 'stretch-auto',
    'view.stretch-reset': 'stretch-reset',
    'view.levels': 'histogram',
    'view.crosshair': 'crosshair',
    'view.loupe': 'loupe',
    'view.saturation': 'saturation',
    'view.region': 'region-stats',
    'view.statistics': 'statistics',
    'field.solve': 'plate-solve',
    'field.grid': 'sky-grid',
    'field.labels': 'labels',
    'field.catalogue': 'catalogue',
    'log.toggle': 'log',
    'observe.live': 'live',
    'observe.capture': 'capture',
    'help.shortcuts': 'help',
    'nav.connection': 'nav-connection',
    'nav.observe': 'nav-imaging',
    'nav.plan': 'nav-sequencer',
    'nav.review': 'nav-analyze',
    'nav.settings': 'nav-configuration',
  };
  const seen = new Set<string>();
  for (const d of KEYMAP) {
    const scopes = Array.isArray(d.scope) ? d.scope : [d.scope];
    if (d.local || d.desktopOnly || !scopes.some((s) => s === 'global' || s === 'imaging')) continue;
    if (d.id === 'motion.abort' || seen.has(d.label)) continue;
    seen.add(d.label);
    const isNav = d.id.startsWith('nav.');
    out.push({
      id: `km.${d.id}`,
      title: d.label,
      group: isNav ? 'Sections' : 'Actions',
      icon: ICON[d.id],
      keys: d.keys[0],
      hint: d.planned ? 'planned in the app' : undefined,
      run: mapped[d.id] ?? (() => ws.toast(`${d.label} (from the app's shortcut registry)`, 'info')),
    });
  }

  for (const s of NAMED_STARS) {
    out.push({
      id: `star.${s.id}`,
      title: s.name ?? `Star ${s.id}`,
      group: 'Stars',
      icon: s.role === 'target' ? 'target-star' : s.role === 'check' ? 'check-star' : 'comparison-star',
      keywords: `${s.role ?? 'candidate'} V ${s.v.toFixed(2)}`,
      hint: `${s.role ?? 'candidate'} · V ${s.v.toFixed(2)}`,
      run: () => {
        ws.select(s.id);
        if (ws.mode !== 'field' && ws.mode !== 'run') ws.setMode('field');
      },
    });
  }

  const SETTINGS: [string, string][] = [
    ['Observer & site › Site latitude and longitude', 'location place coordinates'],
    ['Observer & site › Observer code (AAVSO)', 'obscode'],
    ['Photometry › Aperture radius', 'fwhm annulus'],
    ['Photometry › Number of comparisons', 'ensemble auto 5'],
    ['Plate solving › ASTAP executable', 'solver path'],
    ['Alerts › HFD rule threshold (proposed)', 'attention focus factor 1.5'],
    ['Alerts › Sound (proposed)', 'beep audio volume'],
    ['Appearance › Density (proposed)', 'comfortable compact size'],
    ['Appearance › Theme', 'night red observatory charcoal'],
  ];
  for (const [title, keywords] of SETTINGS) {
    out.push({
      id: `set.${title}`,
      title,
      group: 'Settings',
      icon: 'settings',
      keywords,
      hint: 'opens the sheet at the field',
      run: () => ws.toast(`Settings sheet at "${title}"`, 'info'),
    });
  }

  out.push({
    id: 'help.night-end',
    title: 'Guide: end of the night (darks, biases, park)',
    group: 'Help',
    icon: 'help',
    keywords: 'calibration wrap up documentation',
    run: () => ws.toast('Opens the guide at "End of the night"', 'info'),
  });
  return out;
}

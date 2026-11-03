/**
 * The command palette's index (Mod+K; PROPOSAL 3.1 and 6, BRAND 7), promoted
 * from src/lab/workspace/overlays/commandIndex.ts and fed by the app:
 *
 * - the shortcut registry (lib/app/keymap.ts: the one table that already
 *   feeds tooltips and the "?" sheet), every built, non-local binding by its
 *   label and key; an Observe key opens Observe first;
 * - the sections and the nine Settings categories;
 * - every Settings key of the server's config meta ("Observer & site ›
 *   Latitude"), which opens Settings at that field;
 * - the actions that have no key on purpose: equipment and mount (Connect
 *   all, Disconnect all, Park, Unpark, Tracking): these are `hardware`, so
 *   Enter opens their confirmation in place and never runs them alone;
 *   their unavailable reason uses the same words as the buttons;
 * - Help (shortcuts, documentation, support bundle, About) and Appearance.
 *
 * `IndexSource` is the slice of the app it reads (ArgosApp satisfies it),
 * so the index is unit-tested without a server.
 */

import type { ConfigValue, KeyMeta, MountState } from '../api/types';
import type { Section } from '../app/state.svelte';
import type { ShortcutDef } from '../app/shortcuts';
import { THEME_LABELS, THEMES, type Theme } from '../app/theme';
import { DENSITY_LABELS, DENSITIES, type Density } from '../app/viewerprefs';
import { formatValue } from '../components/settings';
import { CATEGORIES, CATEGORY_BY_ID, homeCategory, type SettingsCategoryId } from '../settings/categories';
import type { Command } from './commands';

export interface IndexSource {
  section: Section;
  configMeta: Record<string, KeyMeta> | null;
  configValues: Record<string, ConfigValue> | null;
  mount: MountState | null;
  theme: Theme;
  density: Density;
  linkOpen: boolean;
  canMount: boolean;
  canCamera: boolean;
  live: boolean;
  slewing: boolean;
  cameraBusy: boolean;
  equipment: { ready: number; anyLinked: boolean };
  appInfo: { docs_url: string } | null;
  shortcuts: {
    list(): ShortcutDef[];
    canTrigger(id: string, scopes?: readonly string[]): boolean;
    trigger(id: string, scopes?: readonly string[]): boolean;
    desktop: boolean;
  };
  connectProblem(): string | null;
  exposureProblem(): string | null;
  go(section: Section): void;
  openSettings(category: SettingsCategoryId, key?: string): void;
  connectAll(): Promise<unknown>;
  disconnectAll(): Promise<unknown>;
  park(): Promise<unknown>;
  unpark(): Promise<unknown>;
  setTracking(on: boolean): Promise<unknown>;
  stopMount(): Promise<unknown>;
  capture(): Promise<unknown>;
  toggleLive(): Promise<unknown>;
  startDiscovery(): Promise<unknown>;
  checkSite(): Promise<unknown>;
  setTheme(t: Theme): void;
  setDensity(d: Density): void;
  resetAllLayouts(): void;
  shortcutSheetOpen: boolean;
  supportBundleOpen: boolean;
}

/** After a section change, the screen binds its keys once it is mounted. */
export type AfterMount = () => Promise<void>;

const SECTION_ICONS: Record<Section, string> = {
  connection: 'nav-connection',
  imaging: 'nav-imaging',
  sequencer: 'nav-sequencer',
  analyze: 'nav-analyze',
  configuration: 'nav-configuration',
};

const NAV: Record<string, Section> = {
  'nav.connection': 'connection',
  'nav.observe': 'imaging',
  'nav.plan': 'sequencer',
  'nav.review': 'analyze',
  'nav.settings': 'configuration',
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
  'log.toggle': 'log',
  'observe.live': 'live',
  'observe.capture': 'capture',
  'help.shortcuts': 'help',
  'rail.toggle': 'panels',
  'settings.filter': 'search',
};

/** Bindings the palette does not list: Escape is not a command, the palette is itself. */
const SKIP = new Set(['motion.abort', 'palette.open', 'nav.settings.mod']);

/** The scope a binding needs, mapped to the section that provides it. */
function sectionOf(def: ShortcutDef): Section | null {
  const scopes = typeof def.scope === 'string' ? [def.scope] : def.scope;
  if (scopes.includes('global')) return null;
  const first = scopes[0].split('.')[0];
  return (['connection', 'imaging', 'sequencer', 'analyze', 'configuration'] as const).find((s) => s === first) ?? null;
}

const SECTION_WORDS: Record<Section, string> = {
  connection: 'Connection',
  imaging: 'Observe',
  sequencer: 'Plan',
  analyze: 'Review',
  configuration: 'Settings',
};

export function buildIndex(app: IndexSource, afterMount: AfterMount): Command[] {
  const out: Command[] = [];
  const serverDown = app.linkOpen ? null : 'the ARGOS server is not reachable';
  const mountReason = serverDown ?? (app.canMount ? null : 'connect the mount first (Connection, F1)');

  // -- Hardware (BRAND 7: no single key; Enter opens the confirmation) ------------------
  const parked = app.mount?.state === 'parked';
  out.push(
    {
      id: 'hw.connect-all',
      title: 'Connect all equipment',
      group: 'Hardware',
      icon: 'connect',
      keywords: 'devices mount camera seestar link',
      hint: 'Connection',
      hardware: {
        question: 'Connect the equipment?',
        consequence: 'Connects every device not connected yet, with the link chosen on the Connection screen.',
        confirm: 'Connect all',
      },
      disabled: app.connectProblem() ?? (app.equipment.ready >= 4 ? 'the four devices are ready already' : null),
      run: () => app.connectAll(),
    },
    {
      id: 'hw.disconnect-all',
      title: 'Disconnect all equipment',
      group: 'Hardware',
      icon: 'disconnect',
      keywords: 'devices release link',
      hint: 'Connection',
      hardware: {
        question: 'Disconnect the equipment?',
        consequence:
          app.cameraBusy || app.slewing
            ? 'Something is running: the exposure, live view or slew stops and is lost.'
            : 'Releases the four devices; nothing is running.',
        confirm: 'Disconnect all',
      },
      disabled: serverDown ?? (app.equipment.anyLinked ? null : 'no device is connected'),
      run: () => app.disconnectAll(),
    },
    {
      id: 'hw.park',
      title: 'Park the mount',
      group: 'Hardware',
      icon: 'park',
      keywords: 'close arm stop tracking end of night',
      hint: 'Mount',
      hardware: { question: 'Park the mount?', consequence: 'Parking physically closes the Seestar arm and stops tracking.', confirm: 'Park' },
      disabled: mountReason ?? (parked ? 'the mount is parked already' : app.slewing ? 'the mount is slewing (Esc aborts)' : null),
      run: () => app.park(),
    },
    {
      id: 'hw.unpark',
      title: 'Unpark the mount',
      group: 'Hardware',
      icon: 'unpark',
      keywords: 'open arm start',
      hint: 'Mount',
      hardware: { question: 'Unpark the mount?', consequence: 'The Seestar arm opens and the mount can slew again.', confirm: 'Unpark' },
      disabled: mountReason ?? (parked ? null : 'the mount is not parked'),
      run: () => app.unpark(),
    },
    {
      id: 'hw.tracking',
      title: app.mount?.tracking ? 'Stop tracking' : 'Start tracking',
      group: 'Hardware',
      icon: 'tracking',
      keywords: 'sidereal follow stars',
      hint: 'Mount',
      hardware: app.mount?.tracking
        ? { question: 'Stop tracking?', consequence: 'Stars drift out of the field until tracking starts again.', confirm: 'Stop tracking' }
        : { question: 'Start tracking?', consequence: 'The mount follows the sky at the sidereal rate.', confirm: 'Start tracking' },
      disabled: mountReason ?? (parked ? 'unpark the mount first' : null),
      run: () => app.setTracking(!app.mount?.tracking),
    },
  );
  if (app.slewing) {
    // Stopping motion is the safe direction: it runs at once (and Esc does the same from anywhere).
    out.push({ id: 'hw.abort', title: 'Abort the slew', group: 'Hardware', icon: 'abort', keys: 'Escape', run: () => app.stopMount() });
  }

  // -- Actions that work from any section ---------------------------------------------
  const cameraReason = serverDown ?? (app.canCamera ? null : 'connect the camera first (Connection, F1)');
  const direct: Record<string, Pick<Command, 'disabled' | 'run'> & { title?: string }> = {
    'observe.capture': {
      disabled: cameraReason ?? (app.cameraBusy ? 'the camera is busy' : app.exposureProblem()),
      run: () => app.capture(),
    },
    'observe.live': {
      title: app.live ? 'Stop live view' : 'Start live view',
      disabled: cameraReason ?? (!app.live && app.cameraBusy ? 'the camera is busy' : app.live ? null : app.exposureProblem()),
      run: () => app.toggleLive(),
    },
    'help.shortcuts': {
      disabled: null,
      run: () => {
        app.shortcutSheetOpen = true;
      },
    },
  };

  // -- The registry: every built binding, by its label -------------------------------------
  const seen = new Set<string>();
  for (const d of app.shortcuts.list()) {
    if (d.planned || d.local || SKIP.has(d.id) || (d.desktopOnly && !app.shortcuts.desktop)) continue;
    const nav = NAV[d.id];
    if (nav) {
      out.push({
        id: `nav.${nav}`,
        title: SECTION_WORDS[nav],
        group: 'Sections',
        icon: SECTION_ICONS[nav],
        keys: d.keys[0],
        keywords: d.label,
        hint: app.section === nav ? 'you are here' : undefined,
        run: () => app.go(nav),
      });
      continue;
    }
    if (seen.has(d.label)) continue;
    seen.add(d.label);
    const own = direct[d.id];
    if (own) {
      out.push({ id: `km.${d.id}`, title: own.title ?? d.label, group: d.id.startsWith('help.') ? 'Help' : 'Actions', icon: ICON[d.id], keys: d.keys[0], disabled: own.disabled, run: own.run });
      continue;
    }
    const section = sectionOf(d);
    const scopes = section ? [section] : undefined;
    const here = !section || app.section === section;
    out.push({
      id: `km.${d.id}`,
      title: d.label,
      group: 'Actions',
      icon: ICON[d.id],
      keys: d.keys[0],
      hint: here ? undefined : `opens ${SECTION_WORDS[section!]}`,
      disabled: here && !app.shortcuts.canTrigger(d.id, scopes) ? 'not available right now' : null,
      run: async () => {
        if (!here && section) {
          app.go(section);
          await afterMount();
        }
        app.shortcuts.trigger(d.id, scopes);
      },
    });
  }

  out.push(
    {
      id: 'act.discover',
      title: 'Discover Seestar devices on the network',
      group: 'Actions',
      icon: 'discover',
      keywords: 'alpaca search find address',
      hint: 'Connection',
      disabled: serverDown,
      run: () => {
        app.go('connection');
        return app.startDiscovery();
      },
    },
    {
      id: 'act.site-check',
      title: 'Check the site against the mount now',
      group: 'Actions',
      icon: 'site',
      keywords: 'location latitude longitude altitude airmass wrong site',
      hint: 'Observer & site',
      disabled: mountReason,
      run: () => {
        app.openSettings('observer_site');
        return app.checkSite();
      },
    },
  );

  // -- Settings: categories, then every key of the config meta ------------------------------
  for (const c of CATEGORIES) {
    out.push({
      id: `cat.${c.id}`,
      title: `Settings › ${c.label}`,
      group: 'Settings',
      icon: c.icon,
      keywords: c.intro,
      run: () => app.openSettings(c.id),
    });
  }
  const meta = app.configMeta ?? {};
  for (const [key, m] of Object.entries(meta)) {
    const home = homeCategory(key, m);
    const where = home ? CATEGORY_BY_ID[home].label : 'Connection';
    const value = app.configValues?.[key];
    out.push({
      id: `set.${key}`,
      title: `${where} › ${m.label}`,
      group: 'Settings',
      icon: home ? CATEGORY_BY_ID[home].icon : 'nav-connection',
      keywords: `${key} ${m.help} ${m.unit ?? ''} ${m.used_by.join(' ')}`,
      hint: value === undefined ? undefined : formatValue(value, m, key),
      run: () => (home ? app.openSettings(home, key) : app.go('connection')),
    });
  }

  // -- Appearance ---------------------------------------------------------------------------
  for (const t of THEMES) {
    out.push({
      id: `theme.${t}`,
      title: `Theme: ${THEME_LABELS[t]}`,
      group: 'Appearance',
      icon: 'theme',
      keywords: 'colour color dark red night',
      hint: app.theme === t ? 'current' : undefined,
      run: () => app.setTheme(t),
    });
  }
  for (const d of DENSITIES) {
    out.push({
      id: `density.${d}`,
      title: `Density: ${DENSITY_LABELS[d]}`,
      group: 'Appearance',
      icon: 'layout-tile',
      keywords: 'size large readable distance',
      hint: app.density === d ? 'current' : undefined,
      run: () => app.setDensity(d),
    });
  }
  out.push({
    id: 'layout.reset-all',
    title: 'Reset all layouts',
    group: 'Appearance',
    icon: 'layout-reset',
    keywords: 'panels drawer rail cards default',
    hint: 'Undo for 6 s',
    run: () => app.resetAllLayouts(),
  });

  // -- Help -----------------------------------------------------------------------------------
  out.push(
    {
      id: 'help.docs',
      title: 'Documentation & website',
      group: 'Help',
      icon: 'help',
      keywords: 'manual guide web',
      hint: 'opens in your browser',
      run: () => void window.open(app.appInfo?.docs_url ?? 'https://perretjules.com/argos/', '_blank', 'noopener,noreferrer'),
    },
    {
      id: 'help.bundle',
      title: 'Create a support bundle…',
      group: 'Help',
      icon: 'support-bundle',
      keywords: 'bug report logs zip diagnostics',
      disabled: serverDown,
      run: () => {
        app.supportBundleOpen = true;
      },
    },
    {
      id: 'help.about',
      title: 'About ARGOS',
      group: 'Help',
      icon: 'about',
      keywords: 'version credits licence',
      run: () => app.openSettings('about'),
    },
  );
  return out;
}

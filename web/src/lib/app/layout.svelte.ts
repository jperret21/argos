/**
 * Reactive layout of one section: panel visibility and the drawer, remembered
 * per viewer (see panels.ts for the keys). The Panels popover and the Drawer
 * of a section read and write one SectionLayout.
 *
 *   const layout = new SectionLayout('imaging', {
 *     panels: { camera: true, display: true, statistics: false, log: true },
 *     drawer: { tab: 'log' },
 *   });
 *   layout.visible('statistics'); layout.setVisible('statistics', true);
 *   layout.setDrawer({ open: true, tab: 'log' });
 *   layout.reset();   // Panels popover "Reset layout": defaults, live
 */

import {
  clearSectionLayout,
  DRAWER_DEFAULT_HEIGHT,
  drawerKey,
  type DrawerPrefs,
  isDrawerPrefs,
  layoutKey,
} from './panels';
import { isBoolean, loadPref, savePref } from './prefs';

export interface SectionLayoutDefaults {
  panels: Record<string, boolean>;
  drawer?: Partial<DrawerPrefs>;
  /** Other per-viewer keys "Reset layout" also clears (e.g. argos.card.<id> fold states). */
  extraKeys?: readonly string[];
}

function storage(): Storage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

export class SectionLayout {
  readonly section: string;
  panels: Record<string, boolean> = $state({});
  drawer: DrawerPrefs = $state({ open: false, tab: '', height: DRAWER_DEFAULT_HEIGHT });
  /** Bumped by reset(): components holding their own copy of a value re-read it. */
  generation = $state(0);
  private readonly defaults: SectionLayoutDefaults;
  private readonly store: Storage | null;

  constructor(section: string, defaults: SectionLayoutDefaults, store: Storage | null = storage()) {
    this.section = section;
    this.defaults = defaults;
    this.store = store;
    this.load();
  }

  private defaultDrawer(): DrawerPrefs {
    return {
      open: this.defaults.drawer?.open ?? false,
      // The Log tab exists in every section's drawer (D17).
      tab: this.defaults.drawer?.tab ?? 'log',
      height: this.defaults.drawer?.height ?? DRAWER_DEFAULT_HEIGHT,
    };
  }

  private load(): void {
    const panels: Record<string, boolean> = {};
    for (const [id, on] of Object.entries(this.defaults.panels)) {
      panels[id] = loadPref(layoutKey(this.section, id), isBoolean, on, this.store);
    }
    this.panels = panels;
    this.drawer = loadPref(drawerKey(this.section), isDrawerPrefs, this.defaultDrawer(), this.store);
  }

  visible(id: string): boolean {
    return this.panels[id] ?? this.defaults.panels[id] ?? true;
  }

  setVisible(id: string, on: boolean): void {
    this.panels[id] = on;
    savePref(layoutKey(this.section, id), on, this.store);
  }

  setDrawer(patch: Partial<DrawerPrefs>): void {
    this.drawer = { ...this.drawer, ...patch };
    savePref(drawerKey(this.section), this.drawer, this.store);
  }

  /** Back to the defaults, at once, and forget the remembered keys. */
  reset(): string[] {
    const removed = clearSectionLayout(this.store, this.section, this.defaults.extraKeys ?? []);
    this.panels = { ...this.defaults.panels };
    this.drawer = this.defaultDrawer();
    this.generation++;
    return removed;
  }
}

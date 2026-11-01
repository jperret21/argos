/**
 * Per-viewer layout of a section (web/spec/README.md sections 3.11, D16;
 * 01 section 2.4.7): which rail cards and drawer tabs are shown, and the
 * drawer (open, tab, height). Pure helpers over a Storage-like object, so
 * "Reset layout" can be tested without a browser.
 *
 * Keys:
 *   argos.layout.<section>.<panel>   boolean, panel shown
 *   argos.drawer.<section>           {open, tab, height}
 *   argos.rail-width.<section>       number (px)
 * "Reset layout" removes those of one section; "Reset all layouts" those of
 * every section plus argos.rail-open, keeping theme, rotation and science
 * settings.
 */

export interface DrawerPrefs {
  open: boolean;
  tab: string;
  height: number;
}

export const DRAWER_DEFAULT_HEIGHT = 216;
export const DRAWER_MIN_HEIGHT = 160;

export const layoutKey = (section: string, panel: string) => `argos.layout.${section}.${panel}`;
export const drawerKey = (section: string) => `argos.drawer.${section}`;
export const railWidthKey = (section: string) => `argos.rail-width.${section}`;

export function isDrawerPrefs(v: unknown): v is DrawerPrefs {
  if (typeof v !== 'object' || v === null) return false;
  const o = v as Record<string, unknown>;
  return (
    typeof o.open === 'boolean' &&
    typeof o.tab === 'string' &&
    typeof o.height === 'number' &&
    Number.isFinite(o.height)
  );
}

/** Clamp a drawer height to [min, max] (max = half the section, README 1.1). */
export function clampDrawerHeight(height: number, max: number, min: number = DRAWER_MIN_HEIGHT): number {
  const hi = Math.max(min, max);
  if (!Number.isFinite(height)) return Math.min(DRAWER_DEFAULT_HEIGHT, hi);
  return Math.round(Math.min(hi, Math.max(min, height)));
}

type StorageLike = Pick<Storage, 'removeItem' | 'key' | 'length'>;

function keysWithPrefix(store: StorageLike, prefix: string): string[] {
  const out: string[] = [];
  for (let i = 0; i < store.length; i++) {
    const k = store.key(i);
    if (k !== null && k.startsWith(prefix)) out.push(k);
  }
  return out;
}

/** Remove the layout keys of one section (+ `extra` keys); returns what was removed. */
export function clearSectionLayout(
  store: StorageLike | null,
  section: string,
  extra: readonly string[] = [],
): string[] {
  if (!store) return [];
  try {
    const keys = [
      ...keysWithPrefix(store, `argos.layout.${section}.`),
      drawerKey(section),
      railWidthKey(section),
      ...extra,
    ];
    const removed: string[] = [];
    for (const k of new Set(keys)) {
      for (let i = 0; i < store.length; i++) {
        if (store.key(i) === k) {
          store.removeItem(k);
          removed.push(k);
          break;
        }
      }
    }
    return removed;
  } catch {
    return [];
  }
}

/** "Reset all layouts" (Settings › Appearance): every section, and the rail open state. */
export function clearAllLayouts(store: StorageLike | null): string[] {
  if (!store) return [];
  try {
    const keys = [
      ...keysWithPrefix(store, 'argos.layout.'),
      ...keysWithPrefix(store, 'argos.drawer.'),
      ...keysWithPrefix(store, 'argos.rail-width.'),
      ...keysWithPrefix(store, 'argos.rail-open'),
    ];
    for (const k of keys) store.removeItem(k);
    return keys;
  } catch {
    return [];
  }
}

/**
 * Per-viewer display preferences of Settings › Appearance (web/spec/README.md
 * 3.11, Q-G6; owner decision D7 of web/lab/PROPOSAL.md section 10).
 *
 * - Density: Compact (default) or Comfortable. Comfortable is a token set
 *   (`<html data-density="comfortable">`, tokens.css), never a page zoom:
 *   readouts 20 px, key readouts 26 px, rows 28 px; toolbar, icons and the
 *   image keep their size. Stored raw under `argos.density` (as the theme),
 *   so index.html applies it before the first paint.
 * - Seeding (Q-G6): theme and rotation are per viewer, seeded ONCE from the
 *   Qt app's keys `ui.theme.preset` and `ui.display.rotation` when this
 *   browser has no choice of its own; afterwards the Qt keys never override
 *   the viewer's choice.
 *
 * Pure helpers over a Storage-like object (every access wrapped: storage can
 * be missing or throw); unit-tested in viewerprefs.test.ts.
 */

import type { RotationMode } from '../viewer/rotation';
import { isRotationMode } from '../viewer/rotation';
import { isTheme, type Theme } from './theme';

export const DENSITIES = ['compact', 'comfortable'] as const;
export type Density = (typeof DENSITIES)[number];
export const DENSITY_STORAGE_KEY = 'argos.density';
export const DENSITY_LABELS: Record<Density, string> = { compact: 'Compact', comfortable: 'Comfortable' };

export function isDensity(v: unknown): v is Density {
  return v === 'compact' || v === 'comfortable';
}

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>;

function defaultStorage(): StorageLike | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

export function loadDensity(store: StorageLike | null = defaultStorage()): Density {
  try {
    const v = store?.getItem(DENSITY_STORAGE_KEY);
    return isDensity(v) ? v : 'compact';
  } catch {
    return 'compact';
  }
}

export function saveDensity(d: Density, store: StorageLike | null = defaultStorage()): void {
  try {
    store?.setItem(DENSITY_STORAGE_KEY, d);
  } catch {
    /* blocked storage: the choice lasts for this page only */
  }
}

/** Set (or clear) the density attribute on <html>: the tokens follow. */
export function applyDensity(d: Density, root: HTMLElement | null = globalThis.document?.documentElement ?? null): void {
  if (!root) return;
  if (d === 'comfortable') root.dataset.density = 'comfortable';
  else delete root.dataset.density;
}

/** The Qt app's palette names (argos/ui/palettes.py:74, 100, 136) to the web themes. */
const QT_THEMES: Record<string, Theme> = {
  Observatory: 'observatory',
  Charcoal: 'charcoal',
  'Night (Red)': 'night-red',
  'Night Red': 'night-red',
};

export function themeFromQt(preset: unknown): Theme | null {
  if (typeof preset !== 'string') return null;
  const t = QT_THEMES[preset] ?? preset.toLowerCase().replace(/[^a-z]+/g, '-');
  return isTheme(t) ? t : null;
}

export function rotationFromQt(value: unknown): RotationMode | null {
  const v = typeof value === 'number' ? String(value) : value;
  return isRotationMode(v) ? v : null;
}

export const SEEDED_KEY = 'argos.seeded';

export interface Seed {
  theme: Theme | null;
  rotation: RotationMode | null;
}

/**
 * What to adopt from the Qt keys, once per browser (Q-G6): only for the
 * preferences this viewer never chose (no stored value) and only the first
 * time a configuration is read (the `argos.seeded` marker is then set).
 */
export function seedFromQt(
  values: Record<string, unknown>,
  stored: { theme: boolean; rotation: boolean },
  store: StorageLike | null = defaultStorage(),
): Seed {
  const none: Seed = { theme: null, rotation: null };
  try {
    if (!store || store.getItem(SEEDED_KEY) !== null) return none;
    store.setItem(SEEDED_KEY, '1');
  } catch {
    return none;
  }
  return {
    theme: stored.theme ? null : themeFromQt(values['ui.theme.preset']),
    rotation: stored.rotation ? null : rotationFromQt(values['ui.display.rotation']),
  };
}

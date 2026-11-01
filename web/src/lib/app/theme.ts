/**
 * Colour themes (tokens.css): Observatory (default) -> Charcoal -> Night Red.
 *
 * The choice is a per-viewer convenience kept in localStorage. Storage can be
 * missing or throw (private window, blocked site data, WebKit quirks), so
 * every access is wrapped and the app falls back to Observatory. index.html
 * applies the stored theme before the first paint (no white or graphite
 * flash when Night Red is active); keep THEME_STORAGE_KEY in sync with it.
 */

export const THEMES = ['observatory', 'charcoal', 'night-red'] as const;
export type Theme = (typeof THEMES)[number];

export const DEFAULT_THEME: Theme = 'observatory';
export const THEME_STORAGE_KEY = 'argos.theme';

export const THEME_LABELS: Record<Theme, string> = {
  observatory: 'Observatory',
  charcoal: 'Charcoal',
  'night-red': 'Night Red',
};

export function isTheme(value: unknown): value is Theme {
  return typeof value === 'string' && (THEMES as readonly string[]).includes(value);
}

export function nextTheme(theme: Theme): Theme {
  return THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
}

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>;

function defaultStorage(): StorageLike | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null; // accessing localStorage itself can throw (blocked site data)
  }
}

export function loadTheme(storage: StorageLike | null = defaultStorage()): Theme {
  try {
    const value = storage?.getItem(THEME_STORAGE_KEY);
    return isTheme(value) ? value : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

export function saveTheme(theme: Theme, storage: StorageLike | null = defaultStorage()): boolean {
  try {
    storage?.setItem(THEME_STORAGE_KEY, theme);
    return !!storage;
  } catch {
    return false;
  }
}

/** Parse a CSS colour token ("#d80000", "#fff", "rgb(216, 0, 0)") to linear-free 0..1 RGB. */
export function parseCssColor(value: string): [number, number, number] | null {
  const text = value.trim().toLowerCase();
  let m = /^#([0-9a-f]{3})$/.exec(text);
  if (m) {
    const [r, g, b] = m[1].split('').map((c) => parseInt(c + c, 16) / 255);
    return [r, g, b];
  }
  m = /^#([0-9a-f]{6})$/.exec(text);
  if (m) {
    const n = parseInt(m[1], 16);
    return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
  }
  m = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/.exec(text);
  if (m) return [Number(m[1]) / 255, Number(m[2]) / 255, Number(m[3]) / 255];
  return null;
}

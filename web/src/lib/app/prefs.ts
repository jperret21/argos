/**
 * Per-viewer conveniences kept in localStorage (rotation, rail open, ...).
 *
 * Storage can be missing or throw (private window, blocked site data), so
 * every access is wrapped and falls back to the default: the UI must work
 * the same without it. Nothing that must persist reliably lives here.
 */

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>;

function storage(): StorageLike | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

export function loadPref<T>(
  key: string,
  valid: (v: unknown) => v is T,
  fallback: T,
  store: StorageLike | null = storage(),
): T {
  try {
    const raw = store?.getItem(key);
    if (raw === null || raw === undefined) return fallback;
    const value: unknown = JSON.parse(raw);
    return valid(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

export function savePref(key: string, value: unknown, store: StorageLike | null = storage()): void {
  try {
    store?.setItem(key, JSON.stringify(value));
  } catch {
    /* storage full or blocked: the preference just is not remembered */
  }
}

export const isBoolean = (v: unknown): v is boolean => typeof v === 'boolean';

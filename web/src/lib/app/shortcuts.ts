/**
 * Keyboard shortcuts: one spec string per action ("E", "Shift+A", "Escape",
 * "F2", "+"), shown in tooltips and matched against key events.
 *
 * Rules (BRAND.md section 7): single-key shortcuts only fire when focus is not
 * in a text field, and they never move hardware, except Escape (stop). Keys
 * are matched on KeyboardEvent.key, so letters follow the keyboard layout
 * (the "A" key of an AZERTY keyboard is A); digits and symbols ignore Shift
 * because AZERTY types them shifted.
 */

export interface KeyLike {
  key: string;
  code?: string;
  shiftKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
}

interface ParsedShortcut {
  key: string;
  shift: boolean;
}

const KEY_NAMES: Record<string, string> = {
  Escape: 'Esc',
  ArrowUp: '↑',
  ArrowDown: '↓',
  ArrowLeft: '←',
  ArrowRight: '→',
};

export function parseShortcut(spec: string): ParsedShortcut {
  const parts = spec.split('+');
  // "+" alone, or "Shift++": the last empty part is the plus key itself.
  if (spec === '+') return { key: '+', shift: false };
  const shift = parts.slice(0, -1).some((p) => p.toLowerCase() === 'shift');
  const key = parts[parts.length - 1] || '+';
  return { key, shift };
}

/** Platform check, injectable for tests. */
export function detectMac(platform: string = globalThis.navigator?.platform ?? ''): boolean {
  return /mac|iphone|ipad/i.test(platform);
}

/** "Shift+A" -> "⇧A" on macOS, "Shift+A" elsewhere; "Escape" -> "Esc". */
export function formatShortcut(spec: string, mac: boolean = detectMac()): string {
  const { key, shift } = parseShortcut(spec);
  const name = KEY_NAMES[key] ?? (key.length === 1 ? key.toUpperCase() : key);
  if (!shift) return name;
  return mac ? `⇧${name}` : `Shift+${name}`;
}

/** The value for aria-keyshortcuts ("Shift+A", "Escape", "Plus" for "+"). */
export function ariaShortcut(spec: string): string {
  const { key, shift } = parseShortcut(spec);
  const name = key === '+' ? 'Plus' : key === '-' ? 'Minus' : key;
  return shift ? `Shift+${name}` : name;
}

export function matchesShortcut(e: KeyLike, spec: string): boolean {
  if (e.ctrlKey || e.metaKey || e.altKey) return false;
  const { key, shift } = parseShortcut(spec);
  if (key.length === 1 && /[a-z]/i.test(key)) {
    return e.key.toLowerCase() === key.toLowerCase() && e.shiftKey === shift;
  }
  if (key.length === 1 && /\d/.test(key)) {
    return e.key === key || e.code === `Numpad${key}`;
  }
  if (key.length === 1) {
    // Symbols: "+" is shifted "=" on US layouts, so accept both.
    if (key === '+') return e.key === '+' || (e.key === '=' && !e.shiftKey);
    return e.key === key;
  }
  return e.key === key && e.shiftKey === shift;
}

/** True when the event target is a text field (single-key shortcuts stay off). */
export function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as { closest?: (s: string) => unknown } | null;
  if (!el || typeof el.closest !== 'function') return false;
  return !!el.closest(
    'input:not([type="range"]):not([type="checkbox"]):not([type="radio"]):not([type="button"]), textarea, select, [contenteditable=""], [contenteditable="true"]',
  );
}

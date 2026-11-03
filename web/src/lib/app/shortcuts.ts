/**
 * Keyboard shortcuts: one spec string per binding ("E", "Shift+A", "Escape",
 * "F2", "+", "Mod+O", "Mod+Shift+O", "Alt+ArrowLeft"), shown in tooltips,
 * exposed as aria-keyshortcuts and matched against key events; plus the one
 * registry (web/spec/README.md section 3.10) that feeds the "?" sheet and
 * dispatches the shortcuts that are not handled locally by a component.
 *
 * Spec grammar: modifiers then the key, joined by "+". Modifiers: "Mod" (Cmd
 * on macOS, Ctrl elsewhere; "Cmd", "Ctrl", "Meta" are aliases of it),
 * "Shift", "Alt" (Option on macOS). A trailing "+" is the plus key ("+",
 * "Mod++").
 *
 * Matching rules (BRAND.md section 7, README section 3.10):
 * - Modifiers are exact: "E" never fires with Cmd, Ctrl or Alt held, and
 *   "Mod+O" never fires without it.
 * - Letters match KeyboardEvent.key, so they follow the keyboard layout (the
 *   "A" key of an AZERTY keyboard is A). When the layout or Alt (Option on
 *   macOS) turns the key into something that is not a Latin letter, the
 *   physical KeyboardEvent.code ("KeyA") is used instead. Shift is exact.
 * - Digits match the key or the physical code (Digit1, Numpad1), and ignore
 *   Shift, because AZERTY types digits shifted ("&" is the unshifted 1 key).
 * - Symbols ("+", "-", "?", "/", ",") match the key and ignore Shift: they
 *   are typed shifted on some layouts and not on others.
 * - Named keys (Escape, F1, ArrowLeft, Enter, Delete, PageUp, Space…) match
 *   the key; Shift is exact.
 * - Single-key shortcuts only fire when focus is not in a text field, and
 *   never move hardware (exceptions: Escape = abort motion, the jog arrows).
 */

export interface KeyLike {
  key: string;
  code?: string;
  shiftKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
}

export interface ParsedShortcut {
  /** Canonical key: "A" (letters upper-case), "1", "+", "Escape", "F2", "ArrowLeft", " " (Space). */
  key: string;
  /** Cmd on macOS, Ctrl elsewhere. */
  mod: boolean;
  shift: boolean;
  alt: boolean;
}

type KeyKind = 'letter' | 'digit' | 'symbol' | 'named';

const KEY_ALIASES: Record<string, string> = {
  esc: 'Escape',
  escape: 'Escape',
  space: ' ',
  spacebar: ' ',
  left: 'ArrowLeft',
  right: 'ArrowRight',
  up: 'ArrowUp',
  down: 'ArrowDown',
  del: 'Delete',
  ins: 'Insert',
  return: 'Enter',
  pgup: 'PageUp',
  pgdn: 'PageDown',
  plus: '+',
  minus: '-',
};

const MOD_NAMES = new Set(['mod', 'cmd', 'command', 'ctrl', 'control', 'meta']);

function canonicalKey(raw: string): string {
  if (raw.length === 1) return /[a-z]/i.test(raw) ? raw.toUpperCase() : raw;
  const alias = KEY_ALIASES[raw.toLowerCase()];
  if (alias) return alias;
  // Named keys keep the KeyboardEvent.key spelling: "F2", "ArrowLeft", "PageUp".
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

function kindOf(key: string): KeyKind {
  if (key.length === 1 && /[A-Z]/.test(key)) return 'letter';
  if (key.length === 1 && /\d/.test(key)) return 'digit';
  if (key.length === 1 && key !== ' ') return 'symbol';
  return 'named';
}

export function parseShortcut(spec: string): ParsedShortcut {
  let keyPart: string;
  let modPart: string[];
  if (spec === '+') {
    keyPart = '+';
    modPart = [];
  } else if (spec.endsWith('++')) {
    keyPart = '+';
    modPart = spec.slice(0, -2).split('+');
  } else {
    const parts = spec.split('+');
    keyPart = parts[parts.length - 1] || '+';
    modPart = parts.slice(0, -1);
  }
  const mods = modPart.map((p) => p.trim().toLowerCase()).filter(Boolean);
  return {
    key: canonicalKey(keyPart.trim() || keyPart),
    mod: mods.some((m) => MOD_NAMES.has(m)),
    shift: mods.includes('shift'),
    alt: mods.includes('alt') || mods.includes('option'),
  };
}

/** Platform check, injectable for tests. */
export function detectMac(platform: string = globalThis.navigator?.platform ?? ''): boolean {
  return /mac|iphone|ipad/i.test(platform);
}

/** True inside the Tauri desktop shell (desktop-only bindings such as Mod+Q, Mod+1…5). */
export function isDesktopApp(): boolean {
  return typeof globalThis === 'object' && '__TAURI_INTERNALS__' in globalThis;
}

/**
 * A normalised identity of what the binding listens to: two specs with the
 * same chord can never both be active in overlapping scopes. Shift does not
 * count for digits and symbols (they ignore it when matching).
 */
export function chordOf(spec: string): string {
  const p = parseShortcut(spec);
  const kind = kindOf(p.key);
  const shift = p.shift && (kind === 'letter' || kind === 'named');
  return `${p.mod ? 'Mod+' : ''}${p.alt ? 'Alt+' : ''}${shift ? 'Shift+' : ''}${p.key}`;
}

const KEY_NAMES: Record<string, string> = {
  Escape: 'Esc',
  ArrowUp: '↑',
  ArrowDown: '↓',
  ArrowLeft: '←',
  ArrowRight: '→',
  ' ': 'Space',
  PageUp: 'PgUp',
  PageDown: 'PgDn',
  Delete: 'Del',
  Insert: 'Ins',
};

/**
 * "Mod+Shift+O" -> "⇧⌘O" on macOS (Apple order: Control, Option, Shift,
 * Command), "Ctrl+Shift+O" elsewhere; "Escape" -> "Esc"; "Shift+A" -> "⇧A".
 */
export function formatShortcut(spec: string, mac: boolean = detectMac()): string {
  const p = parseShortcut(spec);
  const name = KEY_NAMES[p.key] ?? p.key;
  if (mac) return `${p.alt ? '⌥' : ''}${p.shift ? '⇧' : ''}${p.mod ? '⌘' : ''}${name}`;
  const mods = [p.mod ? 'Ctrl' : '', p.alt ? 'Alt' : '', p.shift ? 'Shift' : ''].filter(Boolean);
  return [...mods, name].join('+');
}

/**
 * The value for aria-keyshortcuts: modifiers by their UI Events names
 * ("Meta" on macOS, "Control" elsewhere), "Plus" / "Minus" / "Space" for
 * the keys whose character would be ambiguous.
 */
export function ariaShortcut(spec: string, mac: boolean = detectMac()): string {
  const p = parseShortcut(spec);
  const name = p.key === '+' ? 'Plus' : p.key === '-' ? 'Minus' : p.key === ' ' ? 'Space' : p.key;
  const mods = [p.mod ? (mac ? 'Meta' : 'Control') : '', p.alt ? 'Alt' : '', p.shift ? 'Shift' : ''];
  return [...mods.filter(Boolean), name].join('+');
}

function keyMatches(e: KeyLike, p: ParsedShortcut, kind: KeyKind): boolean {
  switch (kind) {
    case 'letter':
      if (e.key.length === 1 && /[a-z]/i.test(e.key)) return e.key.toUpperCase() === p.key;
      // Alt (Option) or a non-Latin layout changed the character: physical key.
      return e.code === `Key${p.key}`;
    case 'digit':
      return e.key === p.key || e.code === `Digit${p.key}` || e.code === `Numpad${p.key}`;
    case 'symbol':
      // "+" is the shifted "=" on US layouts: accept the unshifted "=" too.
      if (p.key === '+') return e.key === '+' || (e.key === '=' && !e.shiftKey);
      return e.key === p.key;
    default:
      return e.key === p.key;
  }
}

export function matchesShortcut(e: KeyLike, spec: string, mac: boolean = detectMac()): boolean {
  const p = parseShortcut(spec);
  const primary = mac ? e.metaKey : e.ctrlKey;
  const other = mac ? e.ctrlKey : e.metaKey;
  if (p.mod !== primary || other || p.alt !== e.altKey) return false;
  const kind = kindOf(p.key);
  if ((kind === 'letter' || kind === 'named') && p.shift !== e.shiftKey) return false;
  return keyMatches(e, p, kind);
}

/** True when the event target is a text field (single-key shortcuts stay off). */
export function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as { closest?: (s: string) => unknown } | null;
  if (!el || typeof el.closest !== 'function') return false;
  return !!el.closest(
    'input:not([type="range"]):not([type="checkbox"]):not([type="radio"]):not([type="button"]), textarea, select, [contenteditable=""], [contenteditable="true"]',
  );
}

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

/** Editing chords a text field keeps for itself even with a modifier. */
const TEXT_EDITING = new Set(['A', 'C', 'V', 'X', 'Z', 'Y']);

export interface ShortcutDef {
  /** Stable id ("nav.observe", "log.toggle", "observe.capture"). */
  id: string;
  /** One or more specs; the first is the one shown in tooltips. */
  keys: readonly string[];
  /** What it does, in the observer's words ("Activity log"). */
  label: string;
  /**
   * Where it is active: "global", a section ("imaging"), or a sub-scope
   * ("analyze.r1"). A scope is active when the active list holds it or one
   * of its sub-scopes. Several scopes may share one definition.
   */
  scope: string | readonly string[];
  /** Fires from a text field too (F-keys, Escape). Default: only chords with Mod. */
  inText?: boolean;
  /** Fires even when an earlier listener already handled the key (Escape = abort motion). */
  evenIfHandled?: boolean;
  /** Fires on auto-repeat (held key). Default false. */
  repeat?: boolean;
  /** Only in the desktop app (Mod+Q, Mod+1…5: the browser owns them). */
  desktopOnly?: boolean;
  /** Specified (README 3.10) but not built yet: checked for conflicts, never listed or dispatched. */
  planned?: boolean;
  /** Handled by the component that owns the focus (tables, the jog pad): listed, not dispatched here. */
  local?: boolean;
}

export interface ShortcutConflict {
  chord: string;
  a: string;
  b: string;
  scopes: [string, string];
}

export class ShortcutConflictError extends Error {
  readonly conflicts: ShortcutConflict[];
  constructor(conflicts: ShortcutConflict[]) {
    super(
      `Shortcut conflict: ${conflicts
        .map((c) => `${c.chord} is both "${c.a}" (${c.scopes[0]}) and "${c.b}" (${c.scopes[1]})`)
        .join('; ')}`,
    );
    this.name = 'ShortcutConflictError';
    this.conflicts = conflicts;
  }
}

export type ShortcutAction = (e: KeyLike) => void;

interface Handler {
  action: ShortcutAction;
  when?: () => boolean;
}

/** Event fields the dispatcher reads (a KeyboardEvent has them all). */
export interface DispatchEvent extends KeyLike {
  target?: EventTarget | null;
  defaultPrevented?: boolean;
  repeat?: boolean;
  isComposing?: boolean;
  preventDefault?: () => void;
}

function scopesOf(def: ShortcutDef): readonly string[] {
  return typeof def.scope === 'string' ? [def.scope] : def.scope;
}

/** Two scopes overlap when either is global or one contains the other. */
export function scopesOverlap(a: string, b: string): boolean {
  return a === 'global' || b === 'global' || a === b || a.startsWith(`${b}.`) || b.startsWith(`${a}.`);
}

/** Is a definition's scope active for this list of active scopes? */
export function scopeActive(scope: string, active: readonly string[]): boolean {
  return scope === 'global' || active.some((s) => s === scope || s.startsWith(`${scope}.`));
}

function depth(scope: string): number {
  return scope === 'global' ? -1 : scope.split('.').length;
}

export interface ShortcutSheetGroup {
  scope: string;
  title: string;
  rows: { id: string; label: string; keys: readonly string[] }[];
}

export interface RegistryOptions {
  mac?: boolean;
  desktop?: boolean;
  /**
   * True while a modal layer is open: only the safety bindings
   * (`evenIfHandled`, Escape = abort motion) still fire.
   */
  blocked?: () => boolean;
}

/**
 * The single shortcut registry: definitions (with conflict detection), the
 * handlers bound to them, the active scopes and the dispatcher.
 *
 * - define() throws ShortcutConflictError when a chord is already used in
 *   an overlapping scope (bindings are static code: fail early).
 * - handle(id, fn) binds an action and returns its unbinding; the newest
 *   handler wins while several are bound (a screen remounted).
 * - dispatch() runs the most specific active binding that matches, and
 *   only it. A definition without a bound handler does nothing here (it may
 *   be local to a component, or not built yet).
 */
export class ShortcutRegistry {
  readonly mac: boolean;
  readonly desktop: boolean;
  private readonly blocked: (() => boolean) | null;
  private readonly defs = new Map<string, ShortcutDef>();
  private readonly handlers = new Map<string, Handler[]>();
  private active: readonly string[] = ['global'];
  private listeners = new Set<() => void>();

  constructor(defs: readonly ShortcutDef[] = [], options: RegistryOptions = {}) {
    this.mac = options.mac ?? detectMac();
    this.desktop = options.desktop ?? isDesktopApp();
    this.blocked = options.blocked ?? null;
    for (const def of defs) this.define(def);
  }

  /** Every pair of definitions that listen to the same chord in overlapping scopes. */
  static conflictsOf(defs: readonly ShortcutDef[]): ShortcutConflict[] {
    const out: ShortcutConflict[] = [];
    const flat = defs.flatMap((d) =>
      d.keys.flatMap((k) => scopesOf(d).map((s) => ({ id: d.id, chord: chordOf(k), scope: s }))),
    );
    for (let i = 0; i < flat.length; i++) {
      for (let j = i + 1; j < flat.length; j++) {
        const a = flat[i];
        const b = flat[j];
        if (a.id !== b.id && a.chord === b.chord && scopesOverlap(a.scope, b.scope)) {
          out.push({ chord: a.chord, a: a.id, b: b.id, scopes: [a.scope, b.scope] });
        }
      }
    }
    return out;
  }

  define(def: ShortcutDef): void {
    const others = [...this.defs.values()].filter((d) => d.id !== def.id);
    const conflicts = ShortcutRegistry.conflictsOf([...others, def]).filter(
      (c) => c.a === def.id || c.b === def.id,
    );
    if (conflicts.length) throw new ShortcutConflictError(conflicts);
    this.defs.set(def.id, def);
    this.changed();
  }

  get(id: string): ShortcutDef | undefined {
    return this.defs.get(id);
  }

  /** The spec shown for an id (tooltips, aria-keyshortcuts), if it is available here. */
  keyFor(id: string): string | undefined {
    const def = this.defs.get(id);
    if (!def || def.planned || (def.desktopOnly && !this.desktop)) return undefined;
    return def.keys[0];
  }

  handle(id: string, action: ShortcutAction, when?: () => boolean): () => void {
    if (!this.defs.has(id)) throw new Error(`Shortcut "${id}" is not defined in the keymap`);
    const handler: Handler = { action, when };
    const list = this.handlers.get(id) ?? [];
    list.unshift(handler);
    this.handlers.set(id, list);
    this.changed();
    return () => {
      const current = this.handlers.get(id);
      if (!current) return;
      const i = current.indexOf(handler);
      if (i >= 0) current.splice(i, 1);
      if (!current.length) this.handlers.delete(id);
      this.changed();
    };
  }

  isBound(id: string): boolean {
    return (this.handlers.get(id)?.length ?? 0) > 0;
  }

  /**
   * Can `trigger(id)` run it now: defined, built, bound, its scope active
   * and its guard (`when`) true. The command palette lists the others with
   * the reason.
   */
  canTrigger(id: string, scopes: readonly string[] = this.active): boolean {
    const def = this.defs.get(id);
    if (!def || def.planned || def.local || (def.desktopOnly && !this.desktop)) return false;
    if (!scopesOf(def).some((s) => scopeActive(s, scopes))) return false;
    return (this.handlers.get(id) ?? []).some((h) => !h.when || h.when());
  }

  /**
   * Run a binding's action as if its key had been pressed (the command
   * palette): same handler, same guard. Returns true when an action ran.
   */
  trigger(id: string, scopes: readonly string[] = this.active): boolean {
    if (!this.canTrigger(id, scopes)) return false;
    const def = this.defs.get(id)!;
    const handler = this.handlers.get(id)!.find((h) => !h.when || h.when());
    if (!handler) return false;
    const p = parseShortcut(def.keys[0]);
    handler.action({
      key: p.key,
      shiftKey: p.shift,
      altKey: p.alt,
      ctrlKey: p.mod && !this.mac,
      metaKey: p.mod && this.mac,
    });
    return true;
  }

  setScopes(scopes: readonly string[]): void {
    this.active = scopes.includes('global') ? [...scopes] : ['global', ...scopes];
  }

  get scopes(): readonly string[] {
    return this.active;
  }

  /** Can this definition fire from a text field? */
  private allowedInText(def: ShortcutDef, spec: string): boolean {
    if (def.inText !== undefined) return def.inText;
    const p = parseShortcut(spec);
    if (/^F\d{1,2}$/.test(p.key)) return true;
    return p.mod && !TEXT_EDITING.has(p.key);
  }

  /**
   * Run the binding this key event selects, if any. Returns true when an
   * action ran (the event's default is then prevented).
   */
  dispatch(e: DispatchEvent, scopes: readonly string[] = this.active): boolean {
    if (e.isComposing) return false;
    const typing = isTypingTarget(e.target ?? null);
    const blocked = this.blocked?.() ?? false;
    const candidates: { def: ShortcutDef; spec: string; depth: number }[] = [];
    for (const def of this.defs.values()) {
      if (def.planned || def.local || (def.desktopOnly && !this.desktop)) continue;
      const handlers = this.handlers.get(def.id);
      if (!handlers?.length) continue;
      const activeScopes = scopesOf(def).filter((s) => scopeActive(s, scopes));
      if (!activeScopes.length) continue;
      const spec = def.keys.find((k) => matchesShortcut(e, k, this.mac));
      if (!spec) continue;
      candidates.push({ def, spec, depth: Math.max(...activeScopes.map(depth)) });
    }
    candidates.sort((a, b) => b.depth - a.depth);
    for (const { def, spec } of candidates) {
      if ((e.defaultPrevented || blocked) && !def.evenIfHandled) continue;
      if (e.repeat && !def.repeat) continue;
      if (typing && !this.allowedInText(def, spec)) continue;
      const handler = this.handlers.get(def.id)!.find((h) => !h.when || h.when());
      if (!handler) continue;
      e.preventDefault?.();
      handler.action(e);
      return true;
    }
    return false;
  }

  /**
   * The event is a function key or a Mod chord the app binds (F1-F5,
   * Mod+,…; never the text-editing chords): while a dialog or a menu holds
   * the keys, its browser default must still not run (F5 reloads the page,
   * F1 opens the browser's help), even though no action runs.
   */
  reserves(e: KeyLike): boolean {
    for (const def of this.defs.values()) {
      if (def.planned || (def.desktopOnly && !this.desktop)) continue;
      if (!this.handlers.get(def.id)?.length) continue;
      for (const spec of def.keys) {
        const p = parseShortcut(spec);
        const fn = /^F\d{1,2}$/.test(p.key);
        if (!fn && !(p.mod && !TEXT_EDITING.has(p.key))) continue;
        if (matchesShortcut(e, spec, this.mac)) return true;
      }
    }
    return false;
  }

  /** Listen on a window (or any target) with the current scopes; returns the detach. */
  attach(target: Pick<Window, 'addEventListener' | 'removeEventListener'>): () => void {
    const listener = (e: Event) => void this.dispatch(e as KeyboardEvent);
    target.addEventListener('keydown', listener);
    return () => target.removeEventListener('keydown', listener);
  }

  /** Definitions an observer can use in this build, grouped by scope for the "?" sheet. */
  sheet(titles: Record<string, string> = {}): ShortcutSheetGroup[] {
    const groups = new Map<string, ShortcutSheetGroup>();
    for (const def of this.defs.values()) {
      if (def.planned || (def.desktopOnly && !this.desktop)) continue;
      const scope = scopesOf(def)[0];
      const title = titles[scope] ?? titles[scope.split('.')[0]] ?? scope;
      const group = groups.get(title) ?? { scope, title, rows: [] };
      group.rows.push({ id: def.id, label: def.label, keys: def.keys });
      groups.set(title, group);
    }
    return [...groups.values()];
  }

  list(): ShortcutDef[] {
    return [...this.defs.values()];
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private changed(): void {
    for (const fn of this.listeners) fn();
  }
}

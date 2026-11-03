/**
 * SettingsForm model (web/spec/README.md 3.1 and 3.4; 02 section 2 and
 * appendix A): which control a configuration key gets, how its value reads,
 * which keys a form shows, and what a refusal says. Generated from the
 * server's config meta (`GET /api/config`, A8: type, default, min, max, step,
 * options, unit, label, help, category, advanced, read_only), so a key added
 * on the server appears in Settings without front-end work. Pure functions;
 * unit-tested (settings.test.ts).
 */

import type { ConfigValue, KeyMeta } from '../api/types';
import { decimalsOf } from './values';
import { DASH, fixed, int, signed, withUnit } from '../format/number';

export type FieldKind = 'switch' | 'number' | 'segmented' | 'select' | 'text' | 'path' | 'list' | 'object';

/** Options short enough to stand side by side (Segmented): at most 5, about 44 characters in all. */
export function segmentable(options: readonly { label: string }[]): boolean {
  if (options.length < 2 || options.length > 5) return false;
  return options.reduce((n, o) => n + o.label.length, 0) <= 44;
}

/** The control of a key (BRAND 8: token-drawn, never a native select or range). */
export function fieldKind(meta: KeyMeta): FieldKind {
  if (meta.options && meta.options.length) return segmentable(meta.options) ? 'segmented' : 'select';
  switch (meta.type) {
    case 'bool':
      return 'switch';
    case 'int':
    case 'float':
      return 'number';
    case 'path':
      return 'path';
    case 'list':
      return 'list';
    case 'object':
      return 'object';
    default:
      return 'text';
  }
}

/** Deep equality of config values (lists of sites, gain tables). */
export function sameValue(a: ConfigValue | undefined, b: ConfigValue | undefined): boolean {
  if (a === b) return true;
  if (typeof a === 'number' && typeof b === 'number') return Math.abs(a - b) < 1e-12;
  if (a === null || b === null || a === undefined || b === undefined) return false;
  if (typeof a !== 'object' || typeof b !== 'object') return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((x, i) => sameValue(x as ConfigValue, b[i] as ConfigValue));
  }
  const ka = Object.keys(a).sort();
  const kb = Object.keys(b).sort();
  return (
    ka.length === kb.length &&
    ka.every(
      (k, i) =>
        k === kb[i] &&
        sameValue((a as Record<string, unknown>)[k] as ConfigValue, (b as Record<string, unknown>)[k] as ConfigValue),
    )
  );
}

/** The "changed from default" mark (and the Reset it offers). */
export function isDefault(value: ConfigValue | undefined, meta: KeyMeta): boolean {
  return sameValue(value, meta.default);
}

/** Digits a number key shows: from its step (0.00001 -> 5), none for an int. */
export function decimalsFor(meta: KeyMeta): number | undefined {
  if (meta.type === 'int') return 0;
  if (meta.step !== null && meta.step > 0) return decimalsOf(meta.step);
  return undefined;
}

/**
 * Thousands grouping (BRAND 5, D5) for every quantity from 1 000 up, integer
 * or decimal ("9 000.0 m", "3 600 s"); ports are identifiers and never grouped.
 */
export function groupFor(key: string, meta: KeyMeta): boolean {
  return (meta.type === 'int' || meta.type === 'float') && !/(^|\.)port$/.test(key);
}

/** Signed display for coordinates (02 1.7 #4: "sign always shown"). */
export function signedFor(key: string): boolean {
  return /(^|\.)(latitude|longitude)$/.test(key);
}

/** A value in words, as a read-only fact or in a default / undo line. */
export function formatValue(value: ConfigValue | undefined, meta: KeyMeta, key = ''): string {
  if (value === undefined) return DASH;
  if (meta.options) {
    const o = meta.options.find((x) => sameValue(x.value, value));
    if (o) return o.label;
  }
  if (value === null) return meta.nullable ? 'not set' : DASH;
  switch (meta.type) {
    case 'bool':
      return value ? 'On' : 'Off';
    case 'int':
    case 'float': {
      if (typeof value !== 'number') return String(value);
      const digits = decimalsFor(meta);
      let text: string;
      const group = groupFor(key, meta);
      if (meta.type === 'int') text = group ? int(value) : String(Math.round(value));
      else if (digits === undefined) text = fixed(value, Math.min(6, (String(value).split('.')[1] ?? '').length), { group });
      else text = signedFor(key) ? signed(value, digits, { group }) : fixed(value, digits, { group });
      // ° ′ ″ against the number, any other unit after a space (BRAND 5).
      return withUnit(text, meta.unit);
    }
    case 'list':
      return Array.isArray(value) ? `${int(value.length)} ${value.length === 1 ? 'item' : 'items'}` : DASH;
    case 'object': {
      const n = value && typeof value === 'object' ? Object.keys(value).length : 0;
      return n ? `${int(n)} ${n === 1 ? 'entry' : 'entries'}` : 'empty';
    }
    default:
      return value === '' ? 'empty' : String(value);
  }
}

export interface KeySelection {
  /** Keys of one category, in the server's order. */
  category?: string;
  /** Or an explicit ordered list (a sheet's subset, a group). */
  keys?: readonly string[];
  /** Only the advanced keys (true), only the others (false), or both (undefined). */
  advanced?: boolean;
  /** Settings filter ("radius", "gaia"): label, help, key, unit, used_by. */
  query?: string;
}

/** Does a key match the Settings filter? Case-insensitive, every word must match. */
export function matchesQuery(key: string, meta: KeyMeta, query: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const hay = [key, meta.label, meta.help, meta.unit ?? '', ...(meta.used_by ?? [])].join(' ').toLowerCase();
  return words.every((w) => hay.includes(w));
}

/** The keys a form renders, in order. Unknown keys of `keys` are dropped. */
export function selectKeys(meta: Record<string, KeyMeta>, sel: KeySelection): string[] {
  const order = sel.keys ? sel.keys.filter((k) => k in meta) : Object.keys(meta);
  return order.filter((k) => {
    const m = meta[k];
    if (sel.category !== undefined && m.category !== sel.category) return false;
    if (sel.advanced !== undefined && m.advanced !== sel.advanced) return false;
    if (sel.query && !matchesQuery(k, m, sel.query)) return false;
    return true;
  });
}

/** Segmented options keyed by text (the control's values are strings). */
export function optionKey(v: ConfigValue): string {
  return JSON.stringify(v);
}

/**
 * The server's words for one key of a refused PATCH (`400 invalid_argument`
 * with `fields`), else the error's message.
 */
export function refusalFor(err: unknown, key: string): string {
  if (err && typeof err === 'object' && 'fields' in err) {
    const fields = (err as { fields: Record<string, string> | null }).fields;
    if (fields && typeof fields[key] === 'string') return fields[key];
  }
  if (err instanceof Error && err.message) return err.message;
  if (typeof err === 'string' && err) return err;
  return 'The server refused this value';
}

/** One commit of a Settings field: a PATCH of one key, refused with that key's words. */
export type SettingsPatch = (
  changes: Record<string, ConfigValue>,
) => Promise<{ warnings?: { key: string; message: string }[] } | unknown>;

export interface FieldCommit {
  /** Warnings the server attached to this key ("does not exist, it will be created"). */
  warnings: string[];
}

/** Send one key; resolve with its warnings, reject with its own words. */
export async function commitKey(patch: SettingsPatch, key: string, value: ConfigValue): Promise<FieldCommit> {
  try {
    const r = (await patch({ [key]: value })) as { warnings?: { key: string; message: string }[] } | null;
    return { warnings: (r?.warnings ?? []).filter((w) => w.key === key).map((w) => w.message) };
  } catch (err) {
    throw new Error(refusalFor(err, key));
  }
}

/** A path key's empty value means "auto" (ASTAP auto-detect) when the help says so. */
export function emptyMeansAuto(meta: KeyMeta): boolean {
  return /auto-detect|empty/i.test(meta.help) && meta.type === 'path';
}

/**
 * Dependent controls (README 3.4): a key that does nothing while its parent
 * is off (or set) is unavailable with the reason, never hidden. The values
 * decide; `null` = available.
 */
export function dependencyReason(key: string, values: Record<string, ConfigValue>): string | null {
  const off = (k: string) => values[k] === false;
  switch (key) {
    case 'catalog.field_stars_mag_limit':
    case 'catalog.field_stars_detected_only':
      return off('catalog.field_stars_enabled') ? 'Turn on Gaia DR3 identification first' : null;
    case 'catalog.named_objects_allow_network':
      return off('catalog.named_objects_enabled') ? 'Turn on SIMBAD named objects first' : null;
    case 'catalog.exoplanet_hosts_allow_network':
      return off('catalog.exoplanet_hosts_enabled') ? 'Turn on exoplanet hosts first' : null;
    case 'astrometry.database':
      // Q-C9: ASTAP ignores the set while a database folder is given (astrometry_session.py:64).
      return typeof values['astrometry.database_path'] === 'string' && values['astrometry.database_path'] !== ''
        ? 'Ignored while a star database folder is set'
        : null;
    default:
      return null;
  }
}

/**
 * What the FilePicker of a path key picks. The server's meta says it when it
 * carries `path_kind` (dir, file, exe); otherwise it is read from the key.
 */
export function pathMode(key: string, meta: KeyMeta): 'open-folder' | 'open-file' | 'executable' {
  const kind = (meta as KeyMeta & { path_kind?: string }).path_kind;
  if (kind === 'exe') return 'executable';
  if (kind === 'file') return 'open-file';
  if (kind === 'dir') return 'open-folder';
  if (/astap_path$/.test(key)) return 'executable';
  if (/\(file\)/i.test(meta.help) || /_cache$/.test(key)) return 'open-file';
  return 'open-folder';
}

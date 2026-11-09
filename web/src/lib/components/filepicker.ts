/**
 * In-app file picker model (web/spec/README.md 3.6, D20, Q-G7): one picker in
 * every build and theme (Night Red safe, works in the browser), served by
 * the server's read-only listing `GET /api/fs/list` (A11), which only lists
 * the observer's home and the ARGOS data folders. Pure functions, no DOM;
 * unit-tested (filepicker.test.ts). FilePicker.svelte draws it.
 *
 * The listing shape is the server's (argos/server/protocol.md, "File
 * listing (A11)"):
 *   GET /api/fs/list?path=&kind=any|dir|file&ext=.fits,.fit,.fts&counts=fits&hidden=false
 *   -> {path, parent, root, places[{id, label, path, exists}],
 *       entries[{name, kind, size, mtime (ISO), symlink, fits_count}], truncated}
 * `parent` is null at the top of an allowed root. Places given as bare paths
 * and mtimes in unix seconds are also accepted (normalised here).
 */

import { fixed, int } from '../format/number';

export type PickerMode = 'open-file' | 'open-folder' | 'save-file' | 'executable';

export interface FsEntry {
  name: string;
  kind: 'dir' | 'file';
  /** Bytes; null for a folder. */
  size?: number | null;
  /** ISO text (the server), or unix seconds / ms. */
  mtime?: number | string | null;
  symlink?: boolean;
  /** FITS files directly inside a folder (`counts=fits`). */
  fits_count?: number | null;
}

export interface FsPlace {
  id?: string;
  label: string;
  path: string;
  /** False for a data folder that does not exist yet. */
  exists?: boolean;
}

export interface FsListing {
  path: string;
  parent: string | null;
  /** The allowed root that contains `path`. */
  root?: string;
  places: (FsPlace | string)[];
  entries: FsEntry[];
  /** More than 5 000 entries: only the first 5 000 are listed. */
  truncated?: boolean;
  /** API 2, wave 5: `path` named a file; its folder is listed and this is the file's name. */
  selected?: string | null;
}

export interface FsListRequest {
  /** null: the server's default (sessions_path, else home). */
  path: string | null;
  kind: 'any' | 'dir' | 'file';
  ext: string[] | null;
  counts: 'fits' | null;
  /** Names starting with "." (left out by the server unless asked). */
  hidden: boolean;
}

/** The server's listing route, injected (the picker never builds URLs). */
export type FsLister = (req: FsListRequest, signal?: AbortSignal) => Promise<FsListing>;

export interface FileFilter {
  label: string;
  /** Lower-case suffixes with the dot (".fits"); empty = every file. */
  ext: readonly string[];
}

export const FITS_FILTER: FileFilter = { label: 'FITS (.fits .fit .fts)', ext: ['.fits', '.fit', '.fts'] };
export const ZIP_FILTER: FileFilter = { label: 'ZIP archive (.zip)', ext: ['.zip'] };
export const ANY_FILTER: FileFilter = { label: 'All files', ext: [] };

/** The separator a server path uses ("\\" for a Windows drive path). */
export function separatorOf(path: string): '/' | '\\' {
  return /^[A-Za-z]:\\/.test(path) || (path.includes('\\') && !path.includes('/')) ? '\\' : '/';
}

export function joinPath(dir: string, name: string): string {
  const sep = separatorOf(dir);
  return dir.endsWith(sep) ? `${dir}${name}` : `${dir}${sep}${name}`;
}

export function baseName(path: string): string {
  const sep = separatorOf(path);
  const trimmed = path.length > 1 && path.endsWith(sep) ? path.slice(0, -1) : path;
  const i = trimmed.lastIndexOf(sep);
  return i < 0 ? trimmed : trimmed.slice(i + 1) || trimmed;
}

export function parentOf(path: string): string | null {
  const sep = separatorOf(path);
  const trimmed = path.length > 1 && path.endsWith(sep) ? path.slice(0, -1) : path;
  const i = trimmed.lastIndexOf(sep);
  if (i < 0) return null;
  if (i === 0) return trimmed === sep ? null : sep;
  if (sep === '\\' && i === 2 && /^[A-Za-z]:/.test(trimmed)) return trimmed.slice(0, 3);
  return trimmed.slice(0, i);
}

/** Absolute (POSIX "/…", "~…" or a Windows drive "C:\…"). */
export function isAbsolute(path: string): boolean {
  return path.startsWith('/') || path.startsWith('~') || /^[A-Za-z]:[\\/]/.test(path);
}

export interface Crumb {
  label: string;
  path: string;
}

/**
 * Breadcrumb segments of a folder path. The home folder reads "~" (the
 * observer's own words for it); above home, segments are kept (the server
 * refuses them anyway when they are outside the allowed roots).
 */
export function breadcrumbs(path: string, home: string | null = null): Crumb[] {
  const sep = separatorOf(path);
  const out: Crumb[] = [];
  let rest = path;
  let prefix = '';
  if (home && (path === home || path.startsWith(home + sep))) {
    out.push({ label: '~', path: home });
    prefix = home;
    rest = path.slice(home.length);
  } else if (sep === '/') {
    out.push({ label: '/', path: '/' });
    prefix = '';
  } else {
    const drive = path.slice(0, 3);
    out.push({ label: drive.slice(0, 2), path: drive });
    prefix = drive.slice(0, 2);
    rest = path.slice(2);
  }
  for (const part of rest.split(sep).filter(Boolean)) {
    prefix = `${prefix}${sep}${part}`;
    out.push({ label: part, path: prefix });
  }
  return out;
}

/**
 * The side list's places, one per folder: two places can name the same
 * folder (the presets folder set to the Desktop, the sessions folder set to
 * home); the first one is kept, so the list never shows a folder twice.
 */
export function normalizePlaces(raw: readonly (FsPlace | string)[] | null | undefined): FsPlace[] {
  const out: FsPlace[] = [];
  const seen = new Set<string>();
  for (const p of raw ?? []) {
    let place: FsPlace | null = null;
    if (typeof p === 'string') {
      if (p) place = { label: baseName(p), path: p, exists: true };
    } else if (p && typeof p.path === 'string' && p.path) {
      place = { id: p.id, label: p.label || baseName(p.path), path: p.path, exists: p.exists ?? true };
    }
    if (place && !seen.has(place.path)) {
      seen.add(place.path);
      out.push(place);
    }
  }
  return out;
}

const hasExt = (name: string, ext: readonly string[]) =>
  !ext.length || ext.some((x) => name.toLowerCase().endsWith(x.toLowerCase()));

/** Folders first, then names in natural order ("frame_2" before "frame_10"), case-insensitive. */
export function sortEntries(entries: readonly FsEntry[]): FsEntry[] {
  const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
  return [...entries].sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === 'dir' ? -1 : 1;
    return collator.compare(a.name, b.name);
  });
}

/** What a mode shows: folders always (to walk), files only when they can be chosen. */
export function visibleEntries(
  entries: readonly FsEntry[],
  mode: PickerMode,
  filter: FileFilter,
  showHidden: boolean,
): FsEntry[] {
  return sortEntries(
    entries.filter((e) => {
      if (!showHidden && e.name.startsWith('.')) return false;
      if (e.kind === 'dir') return true;
      if (mode === 'open-folder') return false;
      if (mode === 'executable') return true; // the server checks the executable bit
      return hasExt(e.name, filter.ext);
    }),
  );
}

/** "4.0 MB", "812 kB", "0 B": decimal units, as the Finder and the OS file tools. */
export function formatSize(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes) || bytes < 0) return '';
  if (bytes < 1000) return `${int(bytes)} B`;
  if (bytes < 1e6) return `${fixed(bytes / 1e3, bytes < 1e4 ? 1 : 0)} kB`;
  if (bytes < 1e9) return `${fixed(bytes / 1e6, bytes < 1e7 ? 1 : 0)} MB`;
  return `${fixed(bytes / 1e9, 1)} GB`;
}

/** mtime as unix ms, from seconds, ms or ISO text; null when unknown. */
export function mtimeMs(m: number | string | null | undefined): number | null {
  if (m === null || m === undefined) return null;
  if (typeof m === 'number') return Number.isFinite(m) ? (m > 1e11 ? m : m * 1000) : null;
  const t = Date.parse(m);
  return Number.isFinite(t) ? t : null;
}

const pad = (n: number) => String(n).padStart(2, '0');

/** "2026-10-31 21:04" in UTC (BRAND 5: UTC is named in the column header). */
export function formatMtime(m: number | string | null | undefined): string {
  const t = mtimeMs(m);
  if (t === null) return '';
  const d = new Date(t);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

/** A file name the observer may type in save mode (no folder separators, not "." or ".."). */
export function nameProblem(name: string): string | null {
  const t = name.trim();
  if (!t) return 'Enter a file name';
  if (/[\\/]/.test(t)) return 'A file name cannot contain / or \\';
  if (t === '.' || t === '..') return 'Choose another name';
  return null;
}

/** Add the filter's first suffix when the name has none of them ("bundle" -> "bundle.zip"). */
export function withSuffix(name: string, filter: FileFilter): string {
  const t = name.trim();
  if (!filter.ext.length || hasExt(t, filter.ext)) return t;
  return `${t}${filter.ext[0]}`;
}

export interface PickerChoice {
  /** The absolute path the primary button returns, or null. */
  path: string | null;
  /** Why the primary button cannot act (aria-disabled reason), or null. */
  reason: string | null;
  /** Save mode: the name exists in this folder (ask "Replace?" first). */
  exists: boolean;
}

/** What the primary button would choose now. */
export function pickerChoice(
  mode: PickerMode,
  listing: FsListing | null,
  selected: FsEntry | null,
  saveName: string,
  filter: FileFilter,
): PickerChoice {
  if (!listing) return { path: null, reason: 'the folder is still loading', exists: false };
  if (mode === 'open-folder') {
    const path = selected?.kind === 'dir' ? joinPath(listing.path, selected.name) : listing.path;
    return { path, reason: null, exists: false };
  }
  if (mode === 'save-file') {
    const problem = nameProblem(saveName);
    if (problem) return { path: null, reason: problem.toLowerCase(), exists: false };
    const name = withSuffix(saveName, filter);
    const exists = listing.entries.some((e) => e.kind === 'file' && e.name === name);
    return { path: joinPath(listing.path, name), reason: null, exists };
  }
  if (!selected || selected.kind !== 'file') {
    return { path: null, reason: mode === 'executable' ? 'choose the program' : 'choose a file', exists: false };
  }
  return { path: joinPath(listing.path, selected.name), reason: null, exists: false };
}

export const PRIMARY_LABEL: Record<PickerMode, string> = {
  'open-file': 'Open',
  'open-folder': 'Choose folder',
  'save-file': 'Save',
  executable: 'Choose',
};

/** A folder's detail column: "412 FITS" when counted, else nothing. */
export function folderDetail(e: FsEntry): string {
  if (e.kind !== 'dir' || e.fits_count === null || e.fits_count === undefined) return '';
  return `${int(e.fits_count)} FITS`;
}

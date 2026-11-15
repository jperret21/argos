/**
 * Review R0, the landing (web/spec/07-review-analysis.md 2.1, WF-A, 2.4; README M94, M103, D3,
 * D19, Q-R4, Q-R5): what can be reviewed, as one list, and the recent items. Pure, tested
 * without a browser.
 *
 * - Sources: a session folder (A67 lists the ones under `sessions_path`; any other folder by
 *   an explicit pick, Q-R4), a curve CSV (A70 import, kind "import", a pseudo-session), one
 *   FITS (R2), and the
 *   live run while one is under way (D3: read-only, the same plot wall).
 * - The list: newest first (the server's order); filtered by a free text (object, date,
 *   folder, filter) and a scope (all, with photometry, with issues).
 * - Recent items: the last few sources opened, per viewer (localStorage, Q-R5 "folders opened
 *   explicitly, remembered"), newest first, one entry per path.
 */

import type { SessionSummary } from '../../api/types';
import { int } from '../../format/number';

/** A curve source of the server (protocol.md "Sources", A68-A79). */
export type Source = { kind: 'session'; path: string } | { kind: 'import'; path: string } | { kind: 'live' };

/** What Review can open: a curve source (R1), or one FITS (R2). The integrator maps each kind. */
export type ReviewSource = Source | { kind: 'fits'; path: string };

export type RecentKind = 'session' | 'import' | 'fits';

export interface RecentItem {
  kind: RecentKind;
  path: string;
  /** What the observer reads ("RR Lyr · 2026-09-25 20:04", "target_RR_Lyr_….csv"). */
  label: string;
  /** When it was last opened, ms since the epoch. */
  t: number;
}

/** The live run as R0 lists it (D3), when a sequence is under way. */
export interface LiveSource {
  object: string;
  started_utc: string | null;
  frames: number;
  state: string;
}

export const MAX_RECENT = 8;
export const PREF_RECENT = 'argos.review.recent';
export const PREF_SCOPE = 'argos.review.sessions.scope';

export type Scope = 'all' | 'photometry' | 'issues';
export const SCOPES: readonly { value: Scope; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'photometry', label: 'Photometry' },
  { value: 'issues', label: 'Issues' },
];
export const isScope = (v: unknown): v is Scope => v === 'all' || v === 'photometry' || v === 'issues';

export function isRecentItem(v: unknown): v is RecentItem {
  if (typeof v !== 'object' || v === null) return false;
  const o = v as Record<string, unknown>;
  return (o.kind === 'session' || o.kind === 'import' || o.kind === 'fits') && typeof o.path === 'string' && !!o.path && typeof o.label === 'string' && typeof o.t === 'number';
}

export const isRecentList = (v: unknown): v is RecentItem[] => Array.isArray(v) && v.every(isRecentItem);

/** Add (or move to the top) a source; at most MAX_RECENT, one per (kind, path). */
export function remember(list: readonly RecentItem[], item: RecentItem): RecentItem[] {
  return [item, ...list.filter((r) => !(r.kind === item.kind && r.path === item.path))].slice(0, MAX_RECENT);
}

export function forget(list: readonly RecentItem[], item: Pick<RecentItem, 'kind' | 'path'>): RecentItem[] {
  return list.filter((r) => !(r.kind === item.kind && r.path === item.path));
}

/** The last path segment ("…/20260925T200453Z_RR_Lyr" → "20260925T200453Z_RR_Lyr"). */
export function baseName(path: string): string {
  const p = path.replace(/[\\/]+$/, '');
  const i = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'));
  return i >= 0 ? p.slice(i + 1) : p;
}

/** The parent folder of a path ("" at the root). */
export function parentPath(path: string): string {
  const p = path.replace(/[\\/]+$/, '');
  const i = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'));
  return i > 0 ? p.slice(0, i) : '';
}

/** "2026-09-25 20:04:56" from the session's start (ISO, any zone written as UTC); "—" when unknown. */
export function startedText(iso: string | null | undefined): string {
  if (!iso) return '—';
  const s = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`;
  const ms = Date.parse(s);
  if (!Number.isFinite(ms)) return iso;
  return new Date(Math.floor(ms / 1000) * 1000).toISOString().slice(0, 19).replace('T', ' ');
}

/** Unix ms of the start, for sorting (NaN when unknown). */
export function startedMs(iso: string | null | undefined): number {
  if (!iso) return NaN;
  const s = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`;
  return Date.parse(s);
}

/** "IR" or "IR · LP" (frames without a filter are "—" on the server: dropped when others exist). */
export function filtersText(filters: Readonly<Record<string, number>>): string {
  const names = Object.entries(filters)
    .sort((a, b) => b[1] - a[1])
    .map(([k]) => k);
  const named = names.filter((n) => n && n !== '—');
  return (named.length ? named : names).join(' · ') || '—';
}

/** "1 T · 6 C · 1 K" (targets, comparisons, check stars); "none" without photometry. */
export function curvesText(c: SessionSummary['curves']): string {
  if (!c.target && !c.comparison && !c.check) return 'none';
  const bits = [`${int(c.target)} T`, `${int(c.comparison)} C`];
  if (c.check) bits.push(`${int(c.check)} K`);
  return bits.join(' · ');
}

/** Spoken form of curvesText (screen readers). */
export function curvesSpoken(c: SessionSummary['curves']): string {
  if (!c.target && !c.comparison && !c.check) return 'no photometry';
  const n = (v: number, one: string, many: string) => `${v} ${v === 1 ? one : many}`;
  const bits = [n(c.target, 'target', 'targets'), n(c.comparison, 'comparison', 'comparisons')];
  if (c.check) bits.push(n(c.check, 'check star', 'check stars'));
  return bits.join(', ');
}

export function hasPhotometry(s: SessionSummary): boolean {
  return s.curves.target + s.curves.comparison + s.curves.check > 0;
}

/** Issues of a session: the server's lines (missing frames already counted in one line). */
export function issueCount(s: SessionSummary): number {
  return s.issues.length;
}

/** Sessions matching the scope and every word of the query (object, start date, folder, filters). */
export function filterSessions(sessions: readonly SessionSummary[], query: string, scope: Scope = 'all'): SessionSummary[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return sessions.filter((s) => {
    if (scope === 'photometry' && !hasPhotometry(s)) return false;
    if (scope === 'issues' && !issueCount(s)) return false;
    if (!words.length) return true;
    const hay = `${s.object} ${startedText(s.started_utc)} ${s.folder} ${Object.keys(s.filters).join(' ')}`.toLowerCase();
    return words.every((w) => hay.includes(w));
  });
}

/** The recent entry for a session of the list (label: object and start). */
export function sessionRecent(s: Pick<SessionSummary, 'path' | 'object' | 'started_utc' | 'folder'>, t: number = Date.now()): RecentItem {
  const when = startedText(s.started_utc);
  const label = s.object ? `${s.object} · ${when === '—' ? s.folder : when.slice(0, 16)}` : s.folder;
  return { kind: 'session', path: s.path, label, t };
}

/** The recent entry for a source picked by path (a folder, a CSV, a FITS). */
export function pathRecent(kind: RecentKind, path: string, t: number = Date.now()): RecentItem {
  return { kind, path, label: baseName(path), t };
}

export const KIND_ICON: Record<RecentKind | 'live', string> = {
  session: 'open-session',
  import: 'open-file',
  fits: 'open-image',
  live: 'live',
};

export const KIND_WORD: Record<RecentKind | 'live', string> = {
  session: 'Session',
  import: 'Curve CSV',
  fits: 'FITS frame',
  live: 'Live run',
};

/** "Showing 500 of 812 sessions" when the server paged the list, else null. */
export function pagingNote(total: number, shown: number): string | null {
  return total > shown ? `Showing the newest ${int(shown)} of ${int(total)} sessions` : null;
}

/** The empty-state title for the list. */
export function emptyText(root: string | null, exists: boolean, filtered: boolean): string {
  if (filtered) return 'No session matches the filter.';
  if (root && !exists) return `The sessions folder ${root} does not exist`;
  return root ? `No sessions in ${root}` : 'No sessions folder is set';
}

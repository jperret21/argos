/**
 * Support bundle dialog model (01 2.3.6, README A5, D14, Q-G17). What the
 * bundle holds is stated from the server's contract
 * (argos/server/protocol.md, "Support bundle (A5) and crash reports (A6)",
 * a port of argos/core/support_bundle.py create_support_bundle), so the
 * dialog never promises more privacy than the ZIP has. Pure; unit-tested.
 */

import { int } from '../format/number';
import { isAbsolute } from './filepicker';

export type BundlePart = 'base' | 'logs' | 'crash' | 'session';

/** One line per part of the ZIP, in the order the server writes them. */
export const BUNDLE_CONTENTS: readonly { part: BundlePart; title: string; detail: string }[] = [
  {
    part: 'base',
    title: 'README.txt and manifest.json',
    detail:
      'ARGOS version, API, creation time (UTC), platform, the privacy choices below, and a configuration summary: telescope profile, log level, diagnostics on or off, whether ASTAP is set.',
  },
  { part: 'logs', title: 'ARGOS logs', detail: 'argos.log and its rotations, up to 10 MB each.' },
  { part: 'crash', title: 'Crash reports', detail: 'The 20 newest crash reports, up to 1 MB each.' },
  {
    part: 'session',
    title: "One session's metadata",
    detail: 'Its JSON, JSONL and CSV files (10 MB each, 50 MB in all). Never FITS frames, never links.',
  },
];

/** Replaced in every file of the ZIP (protocol.md, "Redaction"). */
export const BUNDLE_REDACTION =
  'Replaced in every file: the server token, IPv4 addresses, your home folder (written ~) and, unless you include them, the site coordinates. In session files the observer, the observer code, host names, addresses and target RA / Dec are always replaced.';

/** A session of `GET /api/sessions` (A67 SessionSummary), the fields the chooser shows. */
export interface BundleSession {
  path: string;
  folder?: string;
  object?: string | null;
  started_utc?: string | null;
  frames?: number | null;
}

/** SupportBundleBody (`POST /api/support-bundle`). */
export interface BundleRequest {
  destination: string | null;
  include_session: boolean;
  session_dir: string | null;
  include_site: boolean;
  include_crash_reports: boolean;
  overwrite: boolean;
}

/** The job result. */
export interface BundleResult {
  path: string | null;
  name?: string;
  bytes?: number;
  files: string[];
  /** True: the browser fetches it with GET /api/jobs/{id}/download. */
  download?: boolean;
  session_included?: boolean;
  site_included?: boolean;
}

const pad = (n: number) => String(n).padStart(2, '0');

/** "20261102T193405Z" (UTC). */
export function utcStamp(d: Date): string {
  return (
    `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}` +
    `T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`
  );
}

/**
 * The proposed file name: version + UTC time, so a second bundle of the same
 * version never meets the overwrite prompt (fixes 01 P35).
 */
export function defaultBundleName(version: string, now: Date = new Date()): string {
  const v = version.replace(/[^0-9A-Za-z.+-]/g, '') || 'unknown';
  return `argos-support-${v}-${utcStamp(now)}.zip`;
}

/** "2026-10-31 · SS Cyg · 412 frames" for the chooser. */
export function sessionLabel(s: BundleSession): string {
  const parts: string[] = [];
  if (s.started_utc) parts.push(s.started_utc.slice(0, 10));
  parts.push(s.object || s.folder || s.path.split(/[\\/]/).filter(Boolean).pop() || s.path);
  if (typeof s.frames === 'number') parts.push(`${int(s.frames)} ${s.frames === 1 ? 'frame' : 'frames'}`);
  return parts.join(' · ');
}

/** Force the .zip suffix, as create_support_bundle does (support_bundle.py:178-180). */
/** The destination with ".zip" appended when missing (never swapped: "a.tar.gz" -> "a.tar.gz.zip", as the server). */
export function zipPath(path: string): string {
  const t = path.trim();
  return /\.zip$/i.test(t) ? t : `${t}.zip`;
}

export interface BundleForm {
  /** null in the browser build: the ZIP is downloaded instead of written. */
  destination: string | null;
  includeSession: boolean;
  sessionDir: string | null;
  /** Default false: the site coordinates are redacted everywhere. */
  includeSite?: boolean;
  /** Default true. */
  includeCrashReports?: boolean;
  /** The observer confirmed replacing an existing file (409 file_exists). */
  overwrite?: boolean;
}

/** Why "Create bundle" cannot act, or null. */
export function bundleProblem(f: BundleForm): string | null {
  if (f.destination !== null) {
    if (!f.destination.trim()) return 'choose where to save the ZIP';
    if (!isAbsolute(f.destination.trim())) return 'type an absolute path (starting with / or ~)';
  }
  if (f.includeSession && !f.sessionDir) return 'choose the session to include';
  return null;
}

/** The request body of `POST /api/support-bundle` (session metadata off by default, Q-G17). */
export function bundleRequest(f: BundleForm): BundleRequest {
  return {
    destination: f.destination === null ? null : zipPath(f.destination),
    include_session: f.includeSession && !!f.sessionDir,
    session_dir: f.includeSession ? f.sessionDir : null,
    include_site: f.includeSite ?? false,
    include_crash_reports: f.includeCrashReports ?? true,
    overwrite: f.overwrite ?? false,
  };
}

/** The toast after success (01 2.3.6). */
export function bundleCreatedText(r: BundleResult): string {
  const name = r.name || (r.path ? r.path.split(/[\\/]/).pop() || r.path : 'argos-support.zip');
  return `Support bundle created: ${name}, ${int(r.files.length)} ${r.files.length === 1 ? 'file' : 'files'}. ARGOS did not upload it.`;
}

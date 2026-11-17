/**
 * The Review Frames table (web/spec/07-review-analysis.md 1.6, 2.2 row 1.6, WF-C; README M90,
 * 3.5): the session's frames as A68 returns them, the columns, the text filter, the counts,
 * and the frame a plot time falls on. Pure, tested without a browser.
 *
 * - Read-only (fixes 07 P11: the Qt cells were editable).
 * - A frame whose FITS is not found (`path` null) stays listed, dimmed, "missing", and never
 *   opens the inspector: its reason is said instead (07 2.2 row 1.9 #5).
 * - Numbers right-aligned with fixed decimals so the points line up (BRAND 5): exposure 1,
 *   FWHM / HFD 2, eccentricity 2, sensor temperature 1 (true minus); counts and ADU grouped
 *   with U+202F. A missing value is "—".
 */

import type { Column } from '../../components/table';
import { DASH, fixed, int } from '../../format/number';

/** What A68 read in the frame's primary header (null: no file or an unreadable header). */
export interface FrameHeaderInfo {
  date_obs: string | null;
  /** Exposure midpoint, ISO UTC. */
  mid_utc: string | null;
  jd_mid: number | null;
  /** AIRMASS as the mount wrote it (right even when the Settings site was wrong). */
  airmass: number | null;
  altitude: number | null;
  azimuth: number | null;
  width: number | null;
  height: number | null;
  bayer: string | null;
}

/** One frame of the session (protocol.md "Open a session (A68)", ReviewFrame). */
export interface ReviewFrame {
  /** The server's index: the curves' `frame` column points at it. */
  index: number;
  filename: string;
  image_type: string;
  filter_name: string;
  /** The filter token (S49: "ir", "lp"). */
  filter: string;
  exposure_s: number | null;
  gain: number | null;
  /** DATE-OBS, ISO 8601 UTC (exposure start), or null. */
  timestamp: string | null;
  hfd: number | null;
  fwhm: number | null;
  star_count: number | null;
  sky_adu: number | null;
  peak_adu: number | null;
  eccentricity: number | null;
  ccd_temp: number | null;
  /** Absolute path of the FITS on the server; null when it is not found. */
  path: string | null;
  /** A light frame as the core says (`light_frames`); null: not sent (read from the type). */
  light: boolean | null;
  header: FrameHeaderInfo | null;
}

/** A table row: the frame plus what the table derives once. */
export interface FrameRow extends Omit<ReviewFrame, 'light'> {
  /** Unique within the session: "f" + the server's index. */
  key: string;
  /** Exposure start, unix seconds (null when DATE-OBS is unknown). */
  t: number | null;
  missing: boolean;
  light: boolean;
  /** The target's flags on this frame (A69 recorder words, "suspect", "saturated"); [] clean. */
  flags?: readonly string[];
  /** Comparisons the target's point of this frame used (A69 `comps_used`). */
  comps?: number | null;
}

/** The status column's glyph: ▮ recorder flag (no detection, zero point off), ▯ suspect or unverified lock, × saturated. */
export function statusGlyph(r: FrameRow): string {
  const f = r.flags ?? [];
  if (f.includes('low_snr') || f.includes('zp_outlier')) return '▮';
  if (f.includes('saturated')) return '×';
  if (f.includes('suspect') || f.includes('few_anchors')) return '▯';
  return '';
}
const statusRank = (r: FrameRow) => ({ '▮': 3, '×': 2, '▯': 1 })[statusGlyph(r)] ?? 0;

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);

function parseHeader(raw: unknown): FrameHeaderInfo | null {
  if (!isObj(raw)) return null;
  return {
    date_obs: str(raw.date_obs),
    mid_utc: str(raw.mid_utc),
    jd_mid: num(raw.jd_mid),
    airmass: num(raw.airmass),
    altitude: num(raw.altitude),
    azimuth: num(raw.azimuth),
    width: num(raw.width),
    height: num(raw.height),
    bayer: str(raw.bayer),
  };
}

/** One A68 frame record (`fallbackIndex` when it carries none), or null without a file name. */
export function parseFrame(raw: unknown, fallbackIndex = 0): ReviewFrame | null {
  if (!isObj(raw)) return null;
  const filename = str(raw.filename);
  if (!filename) return null;
  const index = num(raw.index);
  return {
    index: index !== null && Number.isInteger(index) && index >= 0 ? index : fallbackIndex,
    filename,
    image_type: str(raw.image_type) ?? '',
    filter_name: str(raw.filter_name) ?? '',
    filter: str(raw.filter) ?? '',
    exposure_s: num(raw.exposure_s),
    gain: num(raw.gain),
    timestamp: str(raw.timestamp),
    hfd: num(raw.hfd),
    fwhm: num(raw.fwhm),
    star_count: num(raw.star_count),
    sky_adu: num(raw.sky_adu),
    peak_adu: num(raw.peak_adu),
    eccentricity: num(raw.eccentricity),
    ccd_temp: num(raw.ccd_temp),
    path: str(raw.path),
    light: typeof raw.light === 'boolean' ? raw.light : null,
    header: parseHeader(raw.header),
  };
}

/** Unix seconds of an ISO time; a time without a zone is UTC (DATE-OBS carries none). */
export function isoSeconds(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const s = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`;
  const ms = Date.parse(s);
  return Number.isFinite(ms) ? ms / 1000 : null;
}

export function isLight(imageType: string): boolean {
  return /light/i.test(imageType);
}

/** Rows for the table, in the session's order, keyed by the server's index (unique). */
export function frameRows(frames: readonly unknown[]): FrameRow[] {
  const seen = new Set<number>();
  const rows: FrameRow[] = [];
  frames.forEach((raw, i) => {
    const f = parseFrame(raw, i);
    if (!f) return;
    let index = f.index;
    while (seen.has(index)) index += frames.length;
    seen.add(index);
    rows.push({
      ...f,
      index,
      key: `f${index}`,
      t: isoSeconds(f.timestamp),
      missing: !f.path,
      light: f.light ?? isLight(f.image_type),
    });
  });
  return rows;
}

/** "2026-09-07 04:07:25" (UTC is named in the column header). */
export function utcText(t: number | null): string {
  if (t === null) return DASH;
  return new Date(Math.round(t) * 1000).toISOString().slice(0, 19).replace('T', ' ');
}

export type FrameColumnId =
  | 'status'
  | 'utc'
  | 'type'
  | 'filter'
  | 'exposure'
  | 'gain'
  | 'fwhm'
  | 'hfd'
  | 'stars'
  | 'sky'
  | 'peak'
  | 'ecc'
  | 'temp'
  | 'airmass'
  | 'comps'
  | 'file';

/**
 * Columns hidden until the observer shows them (the column menu). Widths are in the table's
 * ch (its sans font) for mono values plus the cell padding: about 1.1 ch per character + 4.
 */
export const DEFAULT_HIDDEN: readonly FrameColumnId[] = ['peak'];

export const FRAME_COLUMNS: readonly (Column<FrameRow> & { id: FrameColumnId })[] = [
  {
    id: 'status',
    label: '⚑',
    title: 'The target’s point on this frame: ▮ flagged by the flight recorder (no detection, zero point off), ▯ suspect or lock not verified (S56), × saturated (sort to bring them up)',
    value: (r) => statusRank(r),
    format: (r) => statusGlyph(r),
    width: '4ch',
  },
  { id: 'utc', label: 'UTC', title: 'Exposure start (DATE-OBS), UTC', value: (r) => r.t, format: (r) => utcText(r.t), numeric: true, width: '25ch' },
  { id: 'type', label: 'Type', value: (r) => r.image_type || null, width: '14ch' },
  { id: 'filter', label: 'Filter', value: (r) => r.filter_name || null, width: '8ch' },
  { id: 'exposure', label: 'Exp (s)', title: 'Exposure, seconds', value: (r) => r.exposure_s, format: (r) => fixed(r.exposure_s, 1), numeric: true, width: '10ch' },
  { id: 'gain', label: 'Gain', value: (r) => r.gain, format: (r) => int(r.gain), numeric: true, width: '7ch' },
  { id: 'fwhm', label: 'FWHM', title: 'FWHM, px (green plane)', value: (r) => r.fwhm, format: (r) => fixed(r.fwhm, 2), numeric: true, width: '8ch' },
  { id: 'hfd', label: 'HFD', title: 'Half-flux diameter, px', value: (r) => r.hfd, format: (r) => fixed(r.hfd, 2), numeric: true, width: '8ch' },
  { id: 'stars', label: 'Stars', title: 'Stars detected', value: (r) => r.star_count, format: (r) => int(r.star_count), numeric: true, width: '9ch' },
  { id: 'sky', label: 'Sky (ADU)', title: 'Sky background, ADU', value: (r) => r.sky_adu, format: (r) => int(r.sky_adu), numeric: true, width: '11ch' },
  { id: 'peak', label: 'Peak (ADU)', title: 'Brightest pixel, ADU', value: (r) => r.peak_adu, format: (r) => int(r.peak_adu), numeric: true, width: '12ch' },
  { id: 'ecc', label: 'Ecc', title: 'Star eccentricity (0 round)', value: (r) => r.eccentricity, format: (r) => fixed(r.eccentricity, 2), numeric: true, width: '7ch' },
  { id: 'airmass', label: 'Airmass', title: 'AIRMASS of the FITS header (the mount\'s)', value: (r) => r.header?.airmass ?? null, format: (r) => fixed(r.header?.airmass ?? null, 3), numeric: true, width: '10ch' },
  { id: 'temp', label: 'Temp (°C)', title: 'Sensor temperature, °C', value: (r) => r.ccd_temp, format: (r) => fixed(r.ccd_temp, 1), numeric: true, width: '11ch' },
  { id: 'comps', label: 'Comps', title: 'Comparisons the target’s point of this frame used', value: (r) => r.comps ?? null, format: (r) => (r.comps === null || r.comps === undefined ? DASH : int(r.comps)), numeric: true, width: '7ch' },
  { id: 'file', label: 'File', value: (r) => r.filename, format: (r) => (r.missing ? `${r.filename} (missing)` : r.filename), width: 'minmax(16ch, 1fr)' },
];

export function isColumnId(v: unknown): v is FrameColumnId {
  return typeof v === 'string' && FRAME_COLUMNS.some((c) => c.id === v);
}

/** The columns shown, in order; UTC and File never hide (the row's identity). */
export function visibleColumns(hidden: ReadonlySet<string>): (Column<FrameRow> & { id: FrameColumnId })[] {
  return FRAME_COLUMNS.filter((c) => c.id === 'utc' || c.id === 'file' || !hidden.has(c.id));
}

/** Rows matching a free-text query (file name, type, filter, "missing", "flagged"; several words all match). */
export function filterRows(rows: readonly FrameRow[], query: string): FrameRow[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return [...rows];
  return rows.filter((r) => {
    const hay = `${r.filename} ${r.image_type} ${r.filter_name} ${r.missing ? 'missing' : ''} ${statusGlyph(r) ? 'flagged' : ''}`.toLowerCase();
    return words.every((w) => hay.includes(w));
  });
}

export interface FrameCounts {
  total: number;
  lights: number;
  missing: number;
}

export function frameCounts(rows: readonly FrameRow[]): FrameCounts {
  let lights = 0;
  let missing = 0;
  for (const r of rows) {
    if (r.light) lights++;
    if (r.missing) missing++;
  }
  return { total: rows.length, lights, missing };
}

/** "195 lights · 0 missing" (the tab's count line); other frame types named when present. */
export function countsText(c: FrameCounts): string {
  const others = c.total - c.lights;
  const parts = [`${int(c.lights)} ${c.lights === 1 ? 'light' : 'lights'}`];
  if (others > 0) parts.push(`${int(others)} other`);
  parts.push(`${int(c.missing)} missing`);
  return parts.join(' · ');
}

/**
 * The frame a plot time falls on (a light-curve point is dated at mid-exposure): the frame
 * whose exposure contains it, else the nearest exposure middle within `tolerance_s` (default
 * the longer of the frame's exposure and 5 s). Missing frames count (the row is shown);
 * frames without a time never match.
 */
export function frameAt(rows: readonly FrameRow[], t: number, tolerance_s: number | null = null): FrameRow | null {
  let best: FrameRow | null = null;
  let bestD = Infinity;
  for (const r of rows) {
    if (r.t === null) continue;
    const exp = r.exposure_s ?? 0;
    if (t >= r.t && t <= r.t + exp) return r;
    const d = Math.abs(t - (r.t + exp / 2));
    const tol = tolerance_s ?? Math.max(exp, 5);
    if (d <= tol && d < bestD) {
      best = r;
      bestD = d;
    }
  }
  return best;
}

/** The light frames that can be opened (a FITS on disk), in time order: R2's previous / next. */
export function openableLights(rows: readonly FrameRow[]): FrameRow[] {
  return rows
    .filter((r) => r.light && !r.missing)
    .sort((a, b) => (a.t ?? Infinity) - (b.t ?? Infinity) || a.index - b.index);
}

/** Why a row cannot open the inspector, or null. */
export function openReason(row: FrameRow): string | null {
  return row.missing ? `File not found: ${row.filename}` : null;
}

/**
 * R2 frame inspector, the pure part (web/spec/07-review-analysis.md 1.11, 2.2 rows 1.11, WF-D,
 * 2.4; README M100-M102; protocol.md A71-A75): stepping through the session's frames, the
 * FITS header filter, and the words of the Frame, Selected star and Identification cards.
 */

import { formatDec, formatRA } from '../../format/astro';
import { DASH, fixed, int, signed } from '../../format/number';
import type { FrameRow } from '../frames/frames';
import { utcText } from '../frames/frames';
import type { FileFrameInfo, FileSolution, FitsCard, StarMeasure } from './api';

// -- Previous / next ---------------------------------------------------------------------------

export interface Neighbours {
  /** Position of the frame in the list (0-based), -1 when it is not one of the session's. */
  index: number;
  prev: FrameRow | null;
  next: FrameRow | null;
  /** "7 / 195", or null outside a session. */
  position: string | null;
}

/** Where a file sits among the session's openable light frames (FramesView.lights). */
export function neighbours(lights: readonly FrameRow[], path: string | null): Neighbours {
  const i = path ? lights.findIndex((r) => r.path === path) : -1;
  if (i < 0) return { index: -1, prev: null, next: null, position: null };
  return {
    index: i,
    prev: i > 0 ? lights[i - 1] : null,
    next: i < lights.length - 1 ? lights[i + 1] : null,
    position: `${int(i + 1)} / ${int(lights.length)}`,
  };
}

export function prevReason(n: Neighbours): string | null {
  if (n.index < 0) return 'this file is not one of the session’s light frames';
  return n.prev ? null : 'this is the first light frame';
}

export function nextReason(n: Neighbours): string | null {
  if (n.index < 0) return 'this file is not one of the session’s light frames';
  return n.next ? null : 'this is the last light frame';
}

// -- FITS header -------------------------------------------------------------------------------

/** Cards matching every word of the query (key, value or comment). */
export function filterCards(cards: readonly FitsCard[], query: string): FitsCard[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return [...cards];
  return cards.filter((c) => {
    const hay = `${c.key} ${c.value} ${c.comment}`.toLowerCase();
    return words.every((w) => hay.includes(w));
  });
}

/** The header as text for Copy: the cards shown, one per line, "KEY = value / comment". */
export function cardsText(cards: readonly FitsCard[]): string {
  return cards.map((c) => (c.key === 'COMMENT' || c.key === 'HISTORY' ? `${c.key} ${c.value}` : `${c.key.padEnd(8)}= ${c.value}${c.comment ? ` / ${c.comment}` : ''}`)).join('\n') + '\n';
}

// -- Frame card --------------------------------------------------------------------------------

/** Lines of the Frame card, from A71's header, the A72 keywords and the session's row. */
export function frameLines(
  size: { width: number; height: number } | null,
  info: FileFrameInfo | null,
  keywords: Readonly<Record<string, string>> | null,
  row: FrameRow | null,
): string[] {
  const lines: string[] = [];
  const kw = (k: string) => keywords?.[k] ?? null;
  const type = row?.image_type || info?.image_type || kw('IMAGETYP');
  const filter = row?.filter_name || info?.filter || kw('FILTER');
  const dims = size ? `${int(size.width)} × ${int(size.height)} px` : null;
  lines.push([dims, type, filter].filter(Boolean).join(' · ') || DASH);
  const exp = row?.exposure_s ?? numOf(kw('EXPTIME') ?? kw('EXPOSURE'));
  const gain = row?.gain ?? numOf(kw('GAIN'));
  const temp = row?.ccd_temp ?? numOf(kw('CCD-TEMP'));
  const bits: string[] = [];
  if (exp !== null) bits.push(`${fixed(exp, exp < 1 ? 3 : 1)} s`);
  if (gain !== null) bits.push(`gain ${int(gain)}`);
  if (temp !== null) bits.push(`${fixed(temp, 1)} °C`);
  if (bits.length) lines.push(bits.join(' · '));
  const when = row?.t ?? isoToSeconds(info?.date_obs ?? kw('DATE-OBS'));
  const airmass = row?.header?.airmass ?? numOf(kw('AIRMASS'));
  const tail: string[] = [];
  if (when !== null) tail.push(`${utcText(when)} UTC`);
  if (airmass !== null) tail.push(`X ${fixed(airmass, 3)}`);
  if (tail.length) lines.push(tail.join(' · '));
  return lines;
}

function numOf(v: string | null | undefined): number | null {
  if (v === null || v === undefined || v.trim() === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function isoToSeconds(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const s = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`;
  const ms = Date.parse(s);
  return Number.isFinite(ms) ? ms / 1000 : null;
}

// -- Selected star card --------------------------------------------------------------------------

/** "2.21 px (3.20″)" — the arcsec only when known. */
function pxArcsec(px: number | null, arcsec: number | null): string {
  if (px === null) return DASH;
  return arcsec === null ? `${fixed(px, 2)} px` : `${fixed(px, 2)} px (${fixed(arcsec, 2)}″)`;
}

export interface MeasureView {
  /** The headline: the star's centroid ("x 1024.3 · y 2210.8"), or the core's message. */
  title: string;
  rows: { label: string; value: string; title?: string }[];
  /** RA / Dec when the file is identified, else the reason it is not given. */
  sky: string;
}

export function measureView(m: StarMeasure): MeasureView {
  if (!m.found) return { title: m.message ?? 'No star here.', rows: [], sky: '' };
  const scale = m.scale_arcsec_px === null ? DASH : `${fixed(m.scale_arcsec_px, 2)}″/px`;
  const rows = [
    { label: 'FWHM', value: pxArcsec(m.fwhm_px, m.fwhm_arcsec) },
    { label: 'HFD', value: pxArcsec(m.hfd_px, m.hfd_arcsec) },
    { label: 'Ecc', value: fixed(m.eccentricity, 2), title: 'Eccentricity (0 = round)' },
    // Peak above sky over the sky's σ (measure_star_at), not the photometric SNR of the
    // curves: the same star reads 1 090 here and 148 in R1 (science review).
    { label: 'Peak/σ', value: m.snr === null ? DASH : int(m.snr), title: 'Peak above the sky over the sky’s σ (a detection measure), not the aperture photometry SNR of the curves' },
    { label: 'Peak', value: m.peak_adu === null ? DASH : `${int(m.peak_adu)} ADU` },
    { label: 'Sky', value: m.sky_adu === null ? DASH : `${int(m.sky_adu)} ADU` },
    {
      label: 'Scale',
      value: m.scale_source === 'profile' ? `${scale} (profile)` : scale,
      title: m.scale_source === 'solution' ? 'From this file’s plate solution' : 'From the telescope profile: identify the field for the measured scale',
    },
  ];
  const sky = m.ra_hours !== null && m.dec_deg !== null ? `RA ${formatRA(m.ra_hours)}  Dec ${formatDec(m.dec_deg, 1)}` : 'Identify the field (S) for RA / Dec';
  // Pixel coordinates grouped from 1 000, as the HUD writes them (BRAND 5).
  return { title: `x ${fixed(m.x, 1, { group: true })} · y ${fixed(m.y, 1, { group: true })}`, rows, sky };
}

/**
 * A catalogue failure in one line (design review: raw Python exceptions filled the card):
 * "Gaia DR3 unreachable (timeout)"; the full text stays in the tooltip and the Log.
 */
export function catalogueWarning(text: string): { short: string; full: string } {
  const head = /^(.+?)\s+(?:unavailable|failed|unreachable)\b/i.exec(text)?.[1] ?? /^([^:]{1,40}):/.exec(text)?.[1] ?? 'Catalogue';
  const reason = /timed? ?out|timeout/i.test(text)
    ? 'timeout'
    : /max retries|connection|resolv|unreachable|offline|network/i.test(text)
      ? 'offline'
      : /\b(?:HTTP|status)\D{0,3}([45]\d\d)\b/i.exec(text)?.[1]
        ? `HTTP ${/\b(?:HTTP|status)\D{0,3}([45]\d\d)\b/i.exec(text)![1]}`
        : 'failed';
  return { short: `${head.trim()} unreachable (${reason})`, full: text };
}

// -- Identification card -----------------------------------------------------------------------

export function solutionLines(s: FileSolution['solution']): string[] {
  const lines = [`RA ${formatRA(s.ra_hours)}  Dec ${formatDec(s.dec_deg)}`];
  const bits: string[] = [];
  if (s.scale_arcsec_px !== null) bits.push(`${fixed(s.scale_arcsec_px, 2)}″/px`);
  if (s.rotation_deg !== null) bits.push(`rot ${signed(s.rotation_deg, 1)}°`);
  if (s.mirrored) bits.push('mirrored');
  if (s.frame_shape) bits.push(`${int(s.frame_shape[1])} × ${int(s.frame_shape[0])} px`);
  if (bits.length) lines.push(bits.join(' · '));
  return lines;
}

/** The aperture radius the observer sets for a measure (green px), 2-30 (Qt's range). */
export const APERTURE_MIN = 2;
export const APERTURE_MAX = 30;
export const APERTURE_DEFAULT = 5;

export function isAperture(v: unknown): v is number {
  return typeof v === 'number' && Number.isInteger(v) && v >= APERTURE_MIN && v <= APERTURE_MAX;
}

/** Layer counts as the popover reads them (null before the field is identified). */
export function countsFor<K extends string>(ids: readonly K[], counts: Partial<Record<K, number>> | null): Partial<Record<K, number | null>> {
  return Object.fromEntries(ids.map((id) => [id, counts ? (counts[id] ?? 0) : null])) as Partial<Record<K, number | null>>;
}

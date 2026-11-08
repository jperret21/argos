/**
 * What the image HUD says (Hud.svelte), as pure functions: the frame chips,
 * the cursor readout and the 64-bin mini histogram. Promoted from the HUD of
 * src/lab/workspace/observe/Viewer.svelte (web/lab/PROPOSAL.md section 6, W3:
 * chips and cursor; the compass and the arcminute scale bar wait for field
 * identification, W4).
 *
 * - The HUD lives in SCREEN space over the viewer: the image rotation stays
 *   a display choice, the chips never turn with it.
 * - Owner decision D6: the cursor readout (X, Y, value, and RA / Dec when a
 *   WCS exists) sits on the image, where the eye is; the status bar no longer
 *   repeats it (BRAND 11.1 "one home per value").
 * - The frame chips describe the frame ON SCREEN (its header, A25), never the
 *   settings for the next one: what was exposed, with which filter and type,
 *   when. A frame that is not current says so ("Last frame · 21:34:05 UTC").
 */

import type { FrameHeader } from '../api/types';
import { int } from '../format/number';
import { binHistogram } from './histogram';
import type { Histogram16, StretchParams } from './stretch';
import type { PointerInfo } from './types';

/** The wave-3 header fields (A25), optional so an older server still reads. */
export interface FrameHeaderV3 extends FrameHeader {
  bayer?: string | null;
  origin?: 'single' | 'live' | 'autofocus' | 'file' | string;
  frame_type?: string | null;
  gain?: number | null;
  filter?: string | null;
  started_utc?: string | null;
  save?: boolean;
  path?: string | null;
  file_name?: string | null;
  date_obs?: string | null;
  epoch_utc?: string | null;
}

export interface HudChip {
  id: string;
  text: string;
  /** Tooltip / accessible description. */
  title?: string;
  /** mono numbers; `state` = the caps state chip; `muted` = not current. */
  kind?: 'state' | 'num' | 'text';
  muted?: boolean;
  icon?: string;
  /** The live dot (brass: the one live thing), a busy dot, or none. */
  dot?: 'live' | 'busy' | null;
}

export interface HudContext {
  header: FrameHeaderV3 | null;
  /** The camera is in live view and the frame is current. */
  live: boolean;
  /** An exposure (single) is in progress now. */
  exposing: boolean;
  /** No new frame for a while, or the link / equipment is gone. */
  stale: boolean;
  /** Observation object name (A38), when set. */
  object?: string | null;
  /** The frame on screen was saved as a FITS file (frame_saved.frame_seq === seq). */
  savedName?: string | null;
  /** Fill mode crops the frame (BRAND 11.1: never hidden). */
  cropped?: boolean;
  /** "1.0 → 2.0 s" while a live change waits for the next frame. */
  exposureText?: string;
  /** An autofocus sweep runs now (its sample frames are current only while it does). */
  afRunning?: boolean;
}

const TYPE_WORDS: Record<string, string> = { light: 'Light', dark: 'Dark', flat: 'Flat', bias: 'Bias' };

/** Clock time of an ISO instant, UTC, "21:34:05". */
export function utcTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const t = Date.parse(iso);
  return Number.isFinite(t) ? new Date(t).toISOString().slice(11, 19) : '—';
}

export function frameChips(c: HudContext, fmtSeconds: (s: number) => string): HudChip[] {
  const h = c.header;
  if (!h) return [];
  const out: HudChip[] = [];
  const origin = h.origin ?? (h.source === 'file' ? 'file' : undefined);
  if (c.stale) {
    out.push({ id: 'state', text: 'Last frame', kind: 'state', muted: true, title: 'Not current: no new frame, or the equipment or the server link is gone' });
  } else if (origin === 'file') {
    out.push({ id: 'state', text: 'File', kind: 'state', title: 'Opened from a FITS file' });
  } else if (origin === 'autofocus') {
    // The dot only while the sweep runs: after it, the frame is the last AF sample (review W3).
    out.push(
      c.afRunning
        ? { id: 'state', text: 'AF', kind: 'state', dot: 'busy', title: 'Autofocus sample frame' }
        : { id: 'state', text: 'AF', kind: 'state', muted: true, title: 'The last autofocus sample frame (the sweep has ended)' },
    );
  } else if (c.live) {
    out.push({ id: 'state', text: 'Live', kind: 'state', dot: 'live', title: 'Live view' });
  } else if (c.exposing) {
    out.push({ id: 'state', text: 'Exposing', kind: 'state', dot: 'busy', title: 'An exposure is in progress; this is the previous frame' });
  } else {
    out.push({ id: 'state', text: 'Shot', kind: 'state', title: 'Single exposure' });
  }
  out.push({ id: 'seq', text: `#${int(h.seq)}`, kind: 'num', muted: c.stale, title: 'Frame number' });
  out.push({ id: 'exposure', text: c.exposureText ?? fmtSeconds(h.exposure_s), kind: 'num', muted: c.stale, title: 'Exposure of this frame' });
  if (h.filter) out.push({ id: 'filter', text: h.filter, kind: 'text', muted: c.stale, icon: 'filter-wheel', title: 'Filter of this frame' });
  const type = h.frame_type ? (TYPE_WORDS[h.frame_type] ?? h.frame_type) : null;
  // "Dark frame", so the type never reads as a second filter chip ("Dark · Dark").
  if (type && type !== 'Light') out.push({ id: 'type', text: `${type} frame`, kind: 'text', muted: c.stale, title: 'Frame type' });
  if (origin === 'file') {
    if (h.file_name) out.push({ id: 'file', text: h.file_name, kind: 'text', title: h.path ?? h.file_name });
  } else if (c.object) {
    out.push({ id: 'object', text: c.object, kind: 'text', muted: c.stale, title: 'Observation (FITS OBJECT)' });
  }
  const when = origin === 'file' ? (h.epoch_utc ?? h.date_obs ?? null) : h.timestamp;
  if (when) out.push({ id: 'time', text: `${utcTime(when)} UTC`, kind: 'num', muted: true, title: origin === 'file' ? 'Exposure midpoint (DATE-AVG, or DATE-OBS + EXPTIME / 2)' : 'End of the exposure' });
  if (c.savedName) out.push({ id: 'saved', text: 'Saved', kind: 'text', icon: 'save', title: c.savedName });
  if (c.cropped) out.push({ id: 'crop', text: 'Fill · cropped', kind: 'text', title: 'Fill mode crops the long sides; F fits the whole frame' });
  return out;
}

export interface CursorReadout {
  x: string;
  y: string;
  /** "1 834" or "R 1 820 · G 1 834 · B 1 790". */
  value: string;
  ra: string | null;
  dec: string | null;
}

/** The cursor readout, in frame px (un-rotated) and raw ADU; RA / Dec only with a WCS (W4). */
export function cursorReadout(
  p: PointerInfo | null,
  sky: { ra: string; dec: string } | null = null,
): CursorReadout | null {
  if (!p) return null;
  const v = p.value;
  const value = typeof v === 'number' ? int(v) : `R ${int(v[0])} · G ${int(v[1])} · B ${int(v[2])}`;
  return { x: int(p.x), y: int(p.y), value, ra: sky?.ra ?? null, dec: sky?.dec ?? null };
}

export interface MiniHistogram {
  counts: Float64Array;
  /** Black and white levels as fractions of the plotted range (may fall outside 0..1). */
  black: number;
  white: number;
  lo: number;
  hi: number;
}

/** 64 bins over the preview range [min, p99.8] (viewer/histogram.ts), with the levels marked. */
export function miniHistogram(h: Histogram16 | null, levels: StretchParams | null, bins = 64): MiniHistogram | null {
  if (!h || h.n === 0) return null;
  const b = binHistogram(h, bins);
  const span = b.edges[b.edges.length - 1] - b.edges[0] || 1;
  const f = (v: number) => (v - b.edges[0]) / span;
  return {
    counts: b.counts,
    black: levels ? f(levels.black) : NaN,
    white: levels ? f(levels.white) : NaN,
    lo: b.lo,
    hi: b.hi,
  };
}

/** The mini histogram belongs on the HUD only when the band does not show the levels (D6). */
export function showMiniHistogram(mode: string, bandOpen: boolean): boolean {
  return !(mode === 'framing' && bandOpen);
}

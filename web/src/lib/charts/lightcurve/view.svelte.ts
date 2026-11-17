/**
 * The light curve's view state, lifted out of LightCurvePlot (wave 5 carry-over, wave 6b) so
 * its tools can sit in the drawer's tab row or the Run band's header instead of a 32 px row
 * of the plot's own (BRAND 11.1 "no dead bands"; README 3.13 plot rules).
 *
 * - CurveDisplay: what every view of the curve shares (time axis, error bars, relative flux,
 *   the filter shown, S49). One per app: the Run band and the drawer tab show the same axis.
 * - CurveView: one per plot. The zoom state the plot publishes (Whole run / Following / Zoom
 *   kept, the span, the frames after a kept zoom), what its tools may do (any data, BJD on
 *   every point, the filters present) and the commands the tools send (fit, follow, zoom,
 *   copy), which the plot attaches while it is mounted. The zoom itself stays in the plot
 *   (TimeZoom needs the facets' extent); the band and the drawer keep their own zoom, as the
 *   spec asks for no link between them.
 * - curveToolsLayout: which tools fit a width (pure; the row drops the least needed first,
 *   and every dropped tool keeps its key: + / −, U, M; the time axis turns into one button
 *   that cycles it).
 */

import { duration } from '../../format/time';
import type { TimeAxisMode } from '../uplot/axes';
import type { ZoomMode } from '../uplot/zoom';

export interface CurveDisplayLike {
  axis: TimeAxisMode;
  errors: boolean;
  flux: boolean;
  /** S49: the filter whose curves are drawn; null: the filter of the newest frame. */
  filter: string | null;
}

export class CurveDisplay implements CurveDisplayLike {
  axis: TimeAxisMode = $state('utc');
  errors = $state(true);
  flux = $state(false);
  filter: string | null = $state(null);

  constructor(init: Partial<CurveDisplayLike> = {}) {
    if (init.axis) this.axis = init.axis;
    if (typeof init.errors === 'boolean') this.errors = init.errors;
    if (typeof init.flux === 'boolean') this.flux = init.flux;
    if (init.filter !== undefined) this.filter = init.filter;
  }
}

/** What the tools ask of the plot (attached by the plot while it is mounted). */
export interface CurveControls {
  fit: () => void;
  follow: () => void;
  /** factor > 1 zooms out, < 1 zooms in, about the view's anchor. */
  zoomBy: (factor: number) => void;
  copy: () => void;
}

/** The zoom step of the tools and of + / − (the plot's keys use the same). */
export const ZOOM_STEP = 1.6;

export class CurveView {
  readonly display: CurveDisplayLike;
  mode: ZoomMode = $state('fit');
  /** Width of the view, s (0 before data). */
  span = $state(0);
  /** The shown time range, unix s (null before data). */
  range: [number, number] | null = $state.raw(null);
  /** Frames after a kept zoom's right edge (they never move it). */
  newer = $state(0);
  anyData = $state(false);
  /** Every anchor point has a BJD_TDB (the site is set). */
  bjdOk = $state(true);
  /** S49: the filters the curves name, and the one drawn. */
  filters: readonly string[] = $state.raw([]);
  shownFilter: string | null = $state(null);
  /** A plot is attached (the tools act). */
  attached = $state(false);
  private ctrl: CurveControls | null = null;

  constructor(display: CurveDisplayLike = new CurveDisplay()) {
    this.display = display;
  }

  attach(c: CurveControls): () => void {
    this.ctrl = c;
    this.attached = true;
    return () => {
      if (this.ctrl !== c) return;
      this.ctrl = null;
      this.attached = false;
    };
  }

  /** The plot's zoom changed (TimeZoom onChange). */
  setZoom(mode: ZoomMode, view: [number, number] | null): void {
    if (this.mode !== mode) this.mode = mode;
    const span = view ? view[1] - view[0] : 0;
    if (this.span !== span) this.span = span;
    if (!sameRange(this.range, view)) this.range = view ? [view[0], view[1]] : null;
  }

  fit(): void {
    this.ctrl?.fit();
  }
  follow(): void {
    this.ctrl?.follow();
  }
  zoomIn(): void {
    this.ctrl?.zoomBy(1 / ZOOM_STEP);
  }
  zoomOut(): void {
    this.ctrl?.zoomBy(ZOOM_STEP);
  }
  copy(): void {
    this.ctrl?.copy();
  }

  /** The time axis after `a` (UTC → JD → BJD → UTC; BJD skipped without a site). */
  cycleAxis(): void {
    this.display.axis = nextAxis(this.display.axis, this.bjdOk);
  }
}

const sameRange = (a: [number, number] | null, b: [number, number] | null) => (a === null || b === null ? a === b : a[0] === b[0] && a[1] === b[1]);

/** The zoom state's name (BRAND 10: Whole run, Following, Zoom kept). */
export function zoomText(mode: ZoomMode, span: number): string {
  return mode === 'fit' ? 'Whole run' : mode === 'follow' ? `Following · ${duration(span)}` : 'Zoom kept';
}

export const AXIS_LABEL: Record<TimeAxisMode, string> = { utc: 'UTC', jd: 'JD', bjd: 'BJD' };

export function nextAxis(a: TimeAxisMode, bjdOk: boolean): TimeAxisMode {
  if (a === 'utc') return 'jd';
  if (a === 'jd') return bjdOk ? 'bjd' : 'utc';
  return 'utc';
}

export interface ToolsLayout {
  /** The time axis as a segmented choice, one button that cycles it, or not shown. */
  axis: 'segmented' | 'cycle' | 'none';
  /** − / + buttons (the keys and the wheel always zoom). */
  steps: boolean;
  /** Error bars (U) and relative flux (M). */
  toggles: boolean;
  copy: boolean;
  /** "· F" after the zoom state's name. */
  hint: boolean;
}

/**
 * Natural widths (CSS px, measured on the 2026-11-12 build at text-xs, IBM Plex Sans): the
 * zoom state's name is reserved at its widest ("Following · 59 min"), Fit and Follow are
 * never dropped.
 */
export const TOOL_W = {
  core: 2 * 24 + 4 + 118,
  hint: 22,
  steps: 2 * 24 + 2 + 9,
  toggles: 2 * 24 + 2 + 9,
  copy: 26,
  segmented: 104 + 9,
  cycle: 40 + 9,
  filter: 0,
} as const;

/** Which tools fit `width` px, dropping the least needed first. */
export function curveToolsLayout(width: number, opts: { copy: boolean; filterW?: number } = { copy: true }): ToolsLayout {
  const copyW = opts.copy ? TOOL_W.copy : 0;
  const base = TOOL_W.core + (opts.filterW ?? 0);
  const all = base + TOOL_W.hint + TOOL_W.steps + TOOL_W.toggles + copyW + TOOL_W.segmented;
  if (width >= all) return { axis: 'segmented', steps: true, toggles: true, copy: opts.copy, hint: true };
  const noSteps = all - TOOL_W.steps - TOOL_W.hint;
  if (width >= noSteps) return { axis: 'segmented', steps: false, toggles: true, copy: opts.copy, hint: false };
  const cycle = noSteps - TOOL_W.segmented + TOOL_W.cycle;
  if (width >= cycle) return { axis: 'cycle', steps: false, toggles: true, copy: opts.copy, hint: false };
  const noToggles = cycle - TOOL_W.toggles;
  if (width >= noToggles) return { axis: 'cycle', steps: false, toggles: false, copy: opts.copy, hint: false };
  const noCopy = noToggles - copyW;
  if (width >= noCopy) return { axis: 'cycle', steps: false, toggles: false, copy: false, hint: false };
  return { axis: 'none', steps: false, toggles: false, copy: false, hint: false };
}

/**
 * One time axis for several plots (the Review wall, wave 7; spec 07 §2.4 "X linked across
 * all cells"): every LightCurvePlot given the same CurveLink, and any other uPlot cell that
 * joins `zoom.plugin()` and `syncKey`, shares
 * - the zoom (one TimeZoom: drag, Ctrl / Cmd + wheel, + / −, F and double-click act on
 *   every cell at once; its extent is the wall's, so a comparison with fewer frames still
 *   lines up with the target),
 * - the crosshair (uPlot cursor sync on `syncKey`),
 * - the selected time (`selection.t`, unix s): a click on any cell rings that frame on
 *   every cell and fills the Selected point card.
 * The wall owns the zoom's resets (a new source fits again); a linked plot never resets the
 * group on its own mount, so expanding or showing a cell keeps the zoom.
 */

import { TimeZoom, type TimeZoomOptions, type ZoomMode } from '../uplot/zoom';

export type ZoomListener = (mode: ZoomMode, view: [number, number] | null) => void;

export class CurveLink {
  readonly zoom: TimeZoom;
  readonly syncKey: string;
  /** The selected time (unix s), shared by every plot of the group; null: none. */
  readonly selection: { t: number | null } = $state({ t: null });
  /** The zoom state, for the host's chip (Whole session / Zoom kept). */
  mode: ZoomMode = $state('fit');
  view: [number, number] | null = $state.raw(null);
  private listeners = new Set<ZoomListener>();

  constructor(opts: Omit<TimeZoomOptions, 'onChange'> & { onChange?: ZoomListener; syncKey?: string }) {
    const { onChange, syncKey, ...rest } = opts;
    this.syncKey = syncKey ?? `link-${Math.random().toString(36).slice(2, 8)}`;
    this.zoom = new TimeZoom({
      ...rest,
      onChange: (m, v) => {
        if (this.mode !== m) this.mode = m;
        if (!sameView(this.view, v)) this.view = v ? [v[0], v[1]] : null;
        onChange?.(m, v);
        for (const fn of this.listeners) fn(m, v);
      },
    });
  }

  /** A plot of the group hears every zoom change (its chip, its "newer" count). */
  onZoom(fn: ZoomListener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  select(t: number | null): void {
    if (this.selection.t !== t) this.selection.t = t;
  }

  /** A new source: forget the zoom and the selection; the next update fits. */
  reset(): void {
    this.zoom.reset();
    this.selection.t = null;
  }
}

const sameView = (a: [number, number] | null, b: [number, number] | null) => (a === null || b === null ? a === b : a[0] === b[0] && a[1] === b[1]);

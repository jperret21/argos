/**
 * Time zoom shared by a group of uPlot charts (the light-curve facets; later
 * the Review wall and the Conditions multiples). Promoted from
 * src/lab/charts/core/uplot/zoom.ts (web/lab/PROPOSAL.md 3.2, wave 5).
 *
 * Three modes, always named by a chip (BRAND 10 "Zoom states"):
 * - fit ("Whole run"): the whole run is in view; new data widens the view.
 * - follow ("Following"): a fixed-width window whose right edge is the
 *   newest frame (or now, on a live chart); new data slides it. A zoom whose
 *   right edge reaches the end becomes "follow".
 * - manual ("Zoom kept"): the observer looks at the past; new data never
 *   moves the view (README 3.13). F or a double-click fits again, End follows.
 *
 * Interactions: drag = box zoom (uPlot select), wheel or pinch = zoom time
 * about the pointer, horizontal swipe or Shift+wheel = pan, double-click =
 * fit; keyboard through zoomBy / panBy / fit / follow. In a scrolling
 * container (the Review wall) plain wheel scrolls the page and Ctrl / Cmd +
 * wheel zooms (wheel: 'modifier').
 *
 * Motion: keyboard and button zooms glide for --duration-base (orientation:
 * the eye follows where the view went); instant with reduced motion. The
 * data never moves relative to its axis, and pointer zooms are immediate.
 *
 * The logic (fitView, update, setUser, zoomBy, panBy, follow) needs no plot
 * and no DOM: lightcurve tests drive it directly.
 */

import uPlot from 'uplot';

export type ZoomMode = 'fit' | 'follow' | 'manual';

export interface TimeZoomOptions {
  /** [first, last] x of the data, or null when there is none. */
  extent: () => [number, number] | null;
  /** Extra room after the newest point (fraction of the span), e.g. for a now-line. */
  padRight?: number;
  padLeft?: number;
  /** Narrowest window, x units. */
  minSpan?: number;
  /**
   * Where a run shorter than minSpan sits in the fitted view: centred (an
   * archived run), or against the right edge (a live run: the right edge is
   * now, the empty part is the time before the first frame).
   */
  anchor?: () => 'center' | 'right';
  wheel?: 'zoom' | 'modifier';
  reducedMotion: () => boolean;
  durationMs?: number;
  onChange?: (mode: ZoomMode, view: [number, number] | null) => void;
  /** Plain wheel in 'modifier' mode: the caller may hint "Ctrl + wheel zooms". */
  onWheelHint?: () => void;
}

export class TimeZoom {
  readonly plots = new Set<uPlot>();
  mode: ZoomMode = 'fit';
  view: [number, number] | null = null;
  private applying = false;
  private anim = 0;

  constructor(private o: TimeZoomOptions) {}

  /** The view that "fit" means for the current data. */
  fitView(): [number, number] | null {
    const e = this.o.extent();
    if (!e) return null;
    let [a, b] = e;
    const minSpan = this.o.minSpan ?? 60;
    if (b - a < minSpan) {
      if (this.o.anchor?.() === 'right') a = b - minSpan;
      else {
        const mid = (a + b) / 2;
        a = mid - minSpan / 2;
        b = mid + minSpan / 2;
      }
    }
    const span = b - a;
    return [a - span * (this.o.padLeft ?? 0.012), b + span * (this.o.padRight ?? 0.012)];
  }

  /** Re-derive the view for the current data and mode, without drawing. */
  update(): [number, number] | null {
    if (this.mode === 'fit' || !this.view) {
      this.view = this.fitView();
    } else if (this.mode === 'follow') {
      const f = this.fitView();
      if (f) {
        const w = this.view[1] - this.view[0];
        this.view = [f[1] - w, f[1]];
      }
    }
    return this.view;
  }

  /** Re-derive the view after new data and push it (unbatched callers). */
  refresh(): void {
    this.update();
    this.apply();
  }

  /**
   * One synchronous draw per plot for a live append: `fn` (setData with
   * resetScales = false) and the x view in the same uPlot batch.
   */
  batch(u: uPlot, fn: () => void): void {
    this.applying = true;
    try {
      u.batch(() => {
        fn();
        const v = this.view;
        if (v) u.setScale('x', { min: v[0], max: v[1] });
      });
    } finally {
      this.applying = false;
    }
  }

  /** Tell the listener the mode / view after a batched append. */
  notify(): void {
    this.o.onChange?.(this.mode, this.view);
  }

  /** Push the view to every plot of the group (one batch per plot). */
  apply(): void {
    const v = this.view;
    if (!v) return;
    this.applying = true;
    for (const u of this.plots) {
      const s = u.scales.x;
      if (s.min !== v[0] || s.max !== v[1]) u.setScale('x', { min: v[0], max: v[1] });
    }
    this.applying = false;
    this.o.onChange?.(this.mode, v);
  }

  /** Classify a user-chosen view as fit, follow or manual, then apply it. */
  setUser(min: number, max: number, animate = false): void {
    const f = this.fitView();
    const minSpan = this.o.minSpan ?? 60;
    if (max - min < minSpan) {
      const mid = (min + max) / 2;
      min = mid - minSpan / 2;
      max = mid + minSpan / 2;
    }
    if (f) {
      const fw = f[1] - f[0];
      if (max - min >= fw * 0.995) {
        this.fit(animate);
        return;
      }
      // Keep the window inside the data (a little slack at both ends).
      if (min < f[0]) [min, max] = [f[0], f[0] + (max - min)];
      if (max > f[1]) [min, max] = [f[1] - (max - min), f[1]];
      this.mode = max >= f[1] - fw * 0.002 ? 'follow' : 'manual';
    } else this.mode = 'manual';
    this.go([min, max], animate);
  }

  fit(animate = false): void {
    this.mode = 'fit';
    const f = this.fitView();
    if (f) this.go(f, animate);
    else this.o.onChange?.(this.mode, null);
  }

  /** Zoom by `factor` (> 1 zooms out) about x = `at` (default: the centre). */
  zoomBy(factor: number, at?: number, animate = false): void {
    const v = this.view ?? this.fitView();
    if (!v) return;
    const c = at ?? (this.mode === 'follow' ? v[1] : (v[0] + v[1]) / 2);
    this.setUser(c - (c - v[0]) * factor, c + (v[1] - c) * factor, animate);
  }

  /** Pan by a fraction of the current span (negative = towards the past). */
  panBy(fraction: number, animate = false): void {
    const v = this.view ?? this.fitView();
    if (!v) return;
    const d = (v[1] - v[0]) * fraction;
    this.setUser(v[0] + d, v[1] + d, animate);
  }

  /** Follow the newest frame: keep the current width, or a third of the run when everything is in view. */
  follow(animate = false): void {
    const v = this.view ?? this.fitView();
    const f = this.fitView();
    if (!v || !f) return;
    let w = v[1] - v[0];
    if (w >= (f[1] - f[0]) * 0.995) w = (f[1] - f[0]) / 3;
    this.setUser(f[1] - w, f[1], animate);
  }

  /** Keep the current width and jump to the newest frame (follow). */
  toNewest(animate = false): void {
    const v = this.view;
    const f = this.fitView();
    if (!v || !f) return;
    const w = v[1] - v[0];
    this.setUser(f[1] - w, f[1], animate);
  }

  /** Forget the view (new run, cleared curves): the next update fits. */
  reset(): void {
    if (this.anim) cancelAnimationFrame(this.anim);
    this.anim = 0;
    this.mode = 'fit';
    this.view = null;
  }

  private go(target: [number, number], animate: boolean): void {
    if (this.anim) cancelAnimationFrame(this.anim);
    this.anim = 0;
    const from = this.view;
    const dur = this.o.durationMs ?? 180;
    if (!animate || !from || this.o.reducedMotion() || dur <= 0 || typeof requestAnimationFrame === 'undefined') {
      this.view = target;
      this.apply();
      return;
    }
    const t0 = performance.now();
    const step = (now: number) => {
      const k = Math.min(1, (now - t0) / dur);
      const e = 1 - Math.pow(1 - k, 3); // ease-out cubic
      this.view = [from[0] + (target[0] - from[0]) * e, from[1] + (target[1] - from[1]) * e];
      this.apply();
      if (k < 1) this.anim = requestAnimationFrame(step);
    };
    this.anim = requestAnimationFrame(step);
  }

  /** The uPlot plugin: joins the group, binds wheel and dblclick, catches drag zooms. */
  plugin(): uPlot.Plugin {
    let wheel: ((e: WheelEvent) => void) | null = null;
    let selectAt = -Infinity;
    return {
      hooks: {
        init: [
          (u) => {
            this.plots.add(u);
            wheel = (e: WheelEvent) => this.onWheel(u, e);
            u.over.addEventListener('wheel', wheel, { passive: false });
            u.over.addEventListener('dblclick', () => this.fit(true));
          },
        ],
        ready: [
          (u) => {
            if (this.view) u.setScale('x', { min: this.view[0], max: this.view[1] });
          },
        ],
        // uPlot's mouseUp calls setSelect (hook fires, width > 0) and then
        // sets the x scale itself; the hook of that scale change can come after
        // the selection is hidden, so the drag is remembered for 250 ms.
        setSelect: [
          (u) => {
            if (u.select.width > 0) selectAt = performance.now();
          },
        ],
        setScale: [
          (u, key) => {
            if (key !== 'x' || this.applying) return;
            const s = u.scales.x;
            if (s.min == null || s.max == null) return;
            if (performance.now() - selectAt < 250) {
              selectAt = -Infinity;
              this.setUser(s.min, s.max);
            } else if (this.view && (s.min !== this.view[0] || s.max !== this.view[1])) {
              // uPlot re-ranged x on its own (first data): put our view back.
              this.applying = true;
              u.setScale('x', { min: this.view[0], max: this.view[1] });
              this.applying = false;
            }
          },
        ],
        destroy: [
          (u) => {
            this.plots.delete(u);
            if (wheel) u.over.removeEventListener('wheel', wheel);
          },
        ],
      },
    };
  }

  /** Cursor options that hand the double-click to fit(). */
  static cursorBind(): uPlot.Cursor.Bind {
    return { dblclick: () => () => null };
  }

  private onWheel(u: uPlot, e: WheelEvent): void {
    const modifier = e.ctrlKey || e.metaKey;
    if (this.o.wheel === 'modifier' && !modifier) {
      this.o.onWheelHint?.();
      return; // the container scrolls
    }
    e.preventDefault();
    const v = this.view ?? this.fitView();
    if (!v) return;
    const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1;
    const dx = e.deltaX * unit;
    const dy = e.deltaY * unit;
    const w = u.over.clientWidth || 1;
    if (Math.abs(dx) > Math.abs(dy) || (e.shiftKey && !modifier)) {
      const d = (Math.abs(dx) > Math.abs(dy) ? dx : dy) / w;
      this.setUser(v[0] + d * (v[1] - v[0]), v[1] + d * (v[1] - v[0]));
      return;
    }
    const rect = u.over.getBoundingClientRect();
    const at = u.posToVal(e.clientX - rect.left, 'x');
    const k = e.ctrlKey ? 0.01 : 0.0018; // trackpad pinch arrives as ctrl+wheel with small deltas
    this.zoomBy(Math.exp(dy * k), at);
  }
}

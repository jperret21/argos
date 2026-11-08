/**
 * One uPlot instance bound to a host element. Promoted from
 * src/lab/charts/core/uplot/host.ts (web/lab/PROPOSAL.md section 6, W3).
 *
 * - The plot is sized from the host's content box (ResizeObserver) and its
 *   root is absolutely positioned (`.plot-host` in the component), so a plot
 *   can never grow its own container: no resize feedback loop in a flex or
 *   grid layout.
 * - build() is for what lives in the options (colours, axes): a theme
 *   switch. A resize is setSize(); new data is setData().
 * - Plex Mono may still be loading when the first plot draws (the ticks
 *   would use the fallback face): the host rebuilds once document.fonts is
 *   ready.
 */

import uPlot from 'uplot';

export type PlotFactory = (width: number, height: number) => { opts: uPlot.Options; data: uPlot.AlignedData };

/** Below this size (CSS px) no plot is built: a band in its one-row summary. */
export const MIN_PLOT_PX = 20;

export class PlotHost {
  u: uPlot | null = null;
  width = 0;
  height = 0;
  private readonly ro: ResizeObserver;
  private disposed = false;

  constructor(
    readonly el: HTMLElement,
    private readonly make: PlotFactory,
    private readonly onBuild?: (u: uPlot) => void,
    private readonly onResize?: (u: uPlot) => void,
  ) {
    this.ro = new ResizeObserver((entries) => {
      const r = entries[entries.length - 1].contentRect;
      const w = Math.floor(r.width);
      const h = Math.floor(r.height);
      if (w === this.width && h === this.height) return;
      this.width = w;
      this.height = h;
      if (!this.u) this.build();
      else if (w >= MIN_PLOT_PX && h >= MIN_PLOT_PX) {
        this.u.setSize({ width: w, height: h });
        this.onResize?.(this.u);
      }
    });
    this.ro.observe(el);
    void document.fonts?.ready.then(() => {
      if (!this.disposed && this.u) this.build();
    });
  }

  build(): void {
    if (this.disposed) return;
    this.u?.destroy();
    this.u = null;
    if (this.width < MIN_PLOT_PX || this.height < MIN_PLOT_PX) return;
    const { opts, data } = this.make(this.width, this.height);
    this.u = new uPlot({ ...opts, width: this.width, height: this.height }, data, this.el);
    this.onBuild?.(this.u);
  }

  destroy(): void {
    this.disposed = true;
    this.ro.disconnect();
    this.u?.destroy();
    this.u = null;
  }
}

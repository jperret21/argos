/**
 * One uPlot instance bound to a host element.
 *
 * - The plot is sized from the host's content box (ResizeObserver) and its
 *   root is absolutely positioned (lab.css .lab-plot-host), so a plot can
 *   never grow its own container: no resize feedback loop in a flex or grid
 *   layout.
 * - build() is for what lives in the options (colours, axis type): theme
 *   switch, UTC / JD change. A resize is setSize(); new data is setData().
 *   Callers keep the x range across a rebuild through `make`.
 * - Plex Mono may still be loading when the first plot draws (axis ticks
 *   would use the fallback face): the host rebuilds once document.fonts is
 *   ready.
 */

import uPlot from 'uplot';

export type PlotFactory = (width: number, height: number) => { opts: uPlot.Options; data: uPlot.AlignedData };

export class PlotHost {
  u: uPlot | null = null;
  width = 0;
  height = 0;
  private ro: ResizeObserver;
  private disposed = false;

  constructor(
    readonly el: HTMLElement,
    private make: PlotFactory,
    private onBuild?: (u: uPlot) => void,
    private onResize?: (u: uPlot) => void,
  ) {
    this.ro = new ResizeObserver((entries) => {
      const r = entries[entries.length - 1].contentRect;
      const w = Math.floor(r.width);
      const h = Math.floor(r.height);
      if (w === this.width && h === this.height) return;
      this.width = w;
      this.height = h;
      if (!this.u) this.build();
      else if (w > 20 && h > 20) {
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
    if (this.width < 20 || this.height < 20) return;
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

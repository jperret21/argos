<!--
  Autofocus V-curve: HFD against focuser position. Measured steps as dots
  (--fg, neutral: not a photometric role), the fitted hyperbola dashed in
  --chart-reference, the best-focus position as a vertical line with its
  value, and the step being measured ringed (static). Steps still to come are
  shown as empty ticks on the x axis so the scan's extent is known.
-->
<script lang="ts">
  import uPlot from 'uplot';
  import { onMount, untrack } from 'svelte';
  import { env } from '../model/env.svelte';
  import type { FocusStep } from '../model/night';
  import { chartPalette, yAxis } from './axes';
  import { roleMarkers } from './plugins';

  interface Props {
    steps: readonly FocusStep[];
    done: number;
    best: number | null;
    bestHfd: number | null;
  }

  let { steps, done, best, bestHfd }: Props = $props();

  let host: HTMLDivElement;
  let plot: uPlot | null = null;
  let size = $state({ w: 0, h: 0 });

  function fitCurve(x: number): number {
    // Hyperbola through the minimum (the AF fit); shown only once steps exist.
    const b = best ?? 1305;
    const m = bestHfd ?? 5.8;
    return Math.sqrt(m * m + (2.15 * ((x - b) / 52)) ** 2);
  }

  function build(): void {
    plot?.destroy();
    plot = null;
    if (size.w <= 0 || size.h <= 0) return;
    const p = chartPalette(host);
    const xs = steps.map((s) => s.position);
    const lo = xs[0] - 25;
    const hi = xs[xs.length - 1] + 25;
    plot = new uPlot(
      {
        width: size.w,
        height: size.h,
        padding: [10, 12, 0, 0],
        legend: { show: false },
        cursor: { show: false },
        scales: { x: { time: false, range: () => [lo, hi] }, y: { range: (_u, a, b) => [Math.min(a, 5) - 0.5, Math.max(b, 9) + 0.8] } },
        axes: [
          {
            stroke: p.text,
            font: `10px ${p.mono}`,
            size: 22,
            grid: { stroke: p.grid, width: 1 },
            ticks: { stroke: p.axis, width: 1, size: 4 },
            border: { show: true, stroke: p.axis, width: 1 },
            splits: () => xs.filter((_, i) => i % 2 === 0),
            values: (_u, s) => s.map((v) => String(v)),
          },
          yAxis(p, { font: 10, ySize: 40 }, 0, 3),
        ],
        series: [{}, { stroke: 'transparent', width: 0, points: { show: false }, paths: () => null }],
        plugins: [
          {
            hooks: {
              drawAxes: [
                (u) => {
                  const { ctx } = u;
                  const dpr = uPlot.pxRatio;
                  const { left, top, width, height } = u.bbox;
                  ctx.save();
                  ctx.beginPath();
                  ctx.rect(left, top, width, height);
                  ctx.clip();
                  // Fitted curve, once there are steps on both sides of the minimum.
                  if (done >= 9) {
                    ctx.setLineDash([4 * dpr, 3 * dpr]);
                    ctx.strokeStyle = p.reference;
                    ctx.lineWidth = dpr;
                    ctx.beginPath();
                    for (let x = lo; x <= hi; x += 5) ctx.lineTo(u.valToPos(x, 'x', true), u.valToPos(fitCurve(x), 'y', true));
                    ctx.stroke();
                    ctx.setLineDash([]);
                  }
                  // Positions still to measure: open ticks on the axis.
                  ctx.strokeStyle = p.axis;
                  ctx.lineWidth = dpr;
                  for (let i = done; i < steps.length; i++) {
                    const x = Math.round(u.valToPos(steps[i].position, 'x', true)) + 0.5;
                    ctx.beginPath();
                    ctx.moveTo(x, top + height);
                    ctx.lineTo(x, top + height - 8 * dpr);
                    ctx.stroke();
                  }
                  ctx.restore();
                },
              ],
              draw: [
                (u) => {
                  if (best === null || done < steps.length) return;
                  const { ctx } = u;
                  const dpr = uPlot.pxRatio;
                  const { top, height } = u.bbox;
                  const x = Math.round(u.valToPos(best, 'x', true)) + 0.5;
                  ctx.save();
                  ctx.strokeStyle = p.highlight;
                  ctx.lineWidth = 1.5 * dpr;
                  ctx.beginPath();
                  ctx.moveTo(x, top);
                  ctx.lineTo(x, top + height);
                  ctx.stroke();
                  ctx.font = `${10 * dpr}px ${p.mono}`;
                  // uPlot leaves its own textAlign / baseline on the context.
                  ctx.textAlign = 'left';
                  ctx.textBaseline = 'alphabetic';
                  ctx.fillStyle = p.text;
                  ctx.fillText(`best ${best}`, x + 5 * dpr, top + 12 * dpr);
                  ctx.restore();
                },
              ],
            },
          },
          roleMarkers({ shape: 'circle', color: () => p.fg, size: 7, latest: () => p.highlight }),
        ],
      },
      [xs.slice(0, done), steps.slice(0, done).map((s) => s.hfd)],
      host,
    );
  }

  $effect(() => {
    void env.theme;
    void done;
    void steps;
    void best;
    untrack(build);
  });

  $effect(() => {
    const { w, h } = size;
    untrack(() => {
      if (!plot) return build();
      plot.setSize({ width: w, height: h });
    });
  });

  onMount(() => {
    const ro = new ResizeObserver(() => {
      const r = host.getBoundingClientRect();
      size = { w: Math.floor(r.width), h: Math.floor(r.height) };
    });
    ro.observe(host);
    return () => {
      ro.disconnect();
      plot?.destroy();
    };
  });
</script>

<div class="vc" role="img" aria-label="Autofocus V-curve: {done} of {steps.length} steps measured">
  <div class="plot" bind:this={host}></div>
</div>

<style>
  .vc {
    position: relative;
    height: 100%;
    min-height: 0;
    background: var(--chart-surface);
  }
  .plot {
    position: absolute;
    inset: 0;
  }
</style>

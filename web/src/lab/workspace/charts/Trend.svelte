<!--
  One conditions metric over time (HFD, stars, sky): small multiple of the
  Conditions timeline (spec D6). Points in --fg-muted (a condition is not a
  photometric role, so no role colour), the baseline (median of the first 20
  frames) dashed in --chart-reference, the rule's threshold dashed in
  --warning with its words, and the period where the rule holds hatched.
  Shares the run window and a cursor sync key with the light curve when one
  is given, so one crosshair runs through every facet.
-->
<script lang="ts">
  import uPlot from 'uplot';
  import { onMount, untrack } from 'svelte';
  import { withAlpha } from '../../research/tokens';
  import { env } from '../model/env.svelte';
  import { chartPalette, padRange, xAxis, yAxis, type ChartPalette } from './axes';
  import { hlines, periods, roleMarkers } from './plugins';

  interface Props {
    xs: ArrayLike<number>;
    ys: ArrayLike<number>;
    start: number;
    end: number;
    now?: number | null;
    digits?: number;
    baseline?: number | null;
    threshold?: { y: number; label: string } | null;
    flagged?: readonly [number, number][];
    /** Show the time axis (bottom facet only). */
    timeAxis?: boolean;
    sync?: string;
    label: string;
    unit: string;
    big?: boolean;
  }

  let {
    xs,
    ys,
    start,
    end,
    now = null,
    digits = 1,
    baseline = null,
    threshold = null,
    flagged = [],
    timeAxis = true,
    sync,
    label,
    unit,
    big = false,
  }: Props = $props();

  let host: HTMLDivElement;
  let plot: uPlot | null = null;
  let pal: ChartPalette | null = null;
  let size = $state({ w: 0, h: 0 });

  function build(): void {
    plot?.destroy();
    plot = null;
    if (size.w <= 0 || size.h <= 0) return;
    const p = (pal = chartPalette(host));
    const style = big ? { font: 18, ySize: 92, gap: 6 } : { font: 10, ySize: 52 };
    plot = new uPlot(
      {
        width: size.w,
        height: size.h,
        padding: [6, 10, 0, 0],
        legend: { show: false },
        cursor: { sync: sync ? { key: sync } : undefined, drag: { x: false, y: false }, points: { show: false }, y: false },
        scales: {
          x: { time: false },
          y: {
            range: (_u, lo, hi) => {
              let a = lo;
              let b = hi;
              if (threshold) b = Math.max(b, threshold.y);
              if (baseline !== null) a = Math.min(a, baseline);
              return padRange(a, b, 0.1, Math.pow(10, -digits) * 4);
            },
          },
        },
        axes: [xAxis(p, style, timeAxis), yAxis(p, style, digits, 3)],
        series: [{}, { stroke: 'transparent', width: 0, points: { show: false }, paths: () => null }],
        plugins: [
          periods({
            ranges: () => flagged,
            events: () => [],
            now: () => now,
            hatch: () => withAlpha(p.warning, 0.22),
            line: () => p.warning,
            text: () => p.text,
            reference: () => p.reference,
            font: () => `10px ${p.mono}`,
          }),
          hlines({
            lines: () => [
              ...(threshold ? [{ y: threshold.y, color: p.warning, label: threshold.label }] : []),
              ...(baseline !== null ? [{ y: baseline, color: p.reference, label: big ? undefined : 'baseline' }] : []),
            ],
            text: () => p.text,
            font: () => `${big ? 16 : 10}px ${p.mono}`,
          }),
          roleMarkers({ shape: 'circle', color: () => p.fgMuted, size: big ? 6 : 4, latest: () => p.highlight }),
        ],
      },
      [Float64Array.from(xs), Float64Array.from(ys)],
      host,
    );
    plot.setScale('x', { min: start - 240, max: end + 240 });
  }

  $effect(() => {
    void env.theme;
    void big;
    void timeAxis;
    untrack(build);
  });

  $effect(() => {
    const { w, h } = size;
    untrack(() => {
      if (!plot) return build();
      plot.setSize({ width: w, height: h });
    });
  });

  $effect(() => {
    void xs;
    void ys;
    void start;
    void end;
    void baseline;
    void threshold;
    void flagged;
    void now;
    untrack(() => {
      if (!plot) return;
      plot.setData([Float64Array.from(xs), Float64Array.from(ys)], false);
      plot.setScale('x', { min: start - 240, max: end + 240 });
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
  void pal;
</script>

<div class="trend" class:big role="img" aria-label="{label} over the run, {unit}">
  <div class="plot" bind:this={host}></div>
  <span class="label" aria-hidden="true">{label} <span class="unit">{unit}</span></span>
</div>

<style>
  .trend {
    position: relative;
    height: 100%;
    min-height: 0;
    background: var(--chart-surface);
  }
  .plot {
    position: absolute;
    inset: 0;
  }
  .label {
    position: absolute;
    top: 5px;
    left: 60px;
    padding: 0 var(--space-1);
    background: var(--chart-surface);
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
    pointer-events: none;
  }
  .unit {
    color: var(--text-muted);
    text-transform: none;
    letter-spacing: 0;
  }
  .big .label {
    left: 104px;
    font-size: var(--lab-watch-tick);
  }
  .trend :global(.u-cursor-x) {
    border-right: 1px solid var(--chart-highlight);
  }
  .trend :global(.u-cursor-y) {
    display: none;
  }
</style>

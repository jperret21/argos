<!--
  Histogram of the displayed frame (uPlot, log count axis) with the display
  levels as handles on its own x axis: black and white in brass (the values
  being adjusted), the midtones point dashed. Dragging a handle along the
  axis sets that level (snapped to whole ADU; the balance to 0.001), so a
  handle is always exactly over the part of the histogram it acts on.
  Keyboard input goes through the numeric fields beside the plot.

  - Binning ports the Qt preview (viewer/histogram.ts): range [min, p99.8],
    bins snapped to the ADU quantization grid. Empty bins are gaps (log axis):
    no value is invented. A level outside that range is drawn dashed at the
    edge; type it in its field.
  - Colours are read from the design tokens at draw time and re-read on a
    theme change, so Night Red holds on the canvas too.
  - The plot is built once per theme; a new frame only replaces the data and
    a resize only resizes it, so the hover readout survives live view.
-->
<script lang="ts">
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import { onMount, untrack } from 'svelte';
  import type { Theme } from '../app/theme';
  import { Ink } from '../charts/ink';
  import { drawText } from '../charts/text';
  import { compactCount, fixed, int } from '../format/number';
  import { binHistogram, type BinnedHistogram } from '../viewer/histogram';
  import { dragLevel, handleLevels, type LevelHandle, pickHandle } from '../viewer/levels';
  import type { Histogram16, StretchParams } from '../viewer/stretch';

  interface Props {
    histogram: Histogram16 | null;
    levels: StretchParams | null;
    theme: Theme;
    /** Shown above the plot when the pointer is not over it. */
    caption?: string | null;
    /** Plot height, CSS px. */
    height?: number;
    /** A handle was dragged: the level change to apply. */
    onlevel?: (patch: Partial<Omit<StretchParams, 'mode'>>) => void;
  }

  let { histogram, levels, theme, caption = null, height = 104, onlevel }: Props = $props();

  let host: HTMLDivElement;
  let plot: uPlot | null = null;
  let width = $state(0);
  let hover: { lo: number; hi: number; count: number } | null = $state(null);
  let grabbing: LevelHandle | null = $state(null);

  const binned: BinnedHistogram | null = $derived(histogram ? binHistogram(histogram) : null);
  /** The canvas inside the 1 px frame of the plot box. */
  const plotH = $derived(Math.max(40, Math.round(height) - 2));

  /** Room above the plot area for the B / M / W tags (no gridline runs there). */
  const TAG_ROOM = 14;

  interface Palette {
    line: string;
    fill: string;
    grid: string;
    axis: string;
    text: string;
    level: string;
    mid: string;
    font: string;
  }

  function readPalette(): Palette {
    const css = getComputedStyle(host);
    const v = (name: string) => css.getPropertyValue(name).trim();
    // Canvas needs resolved colours (charts/ink.ts: hex, rgb(), color(srgb …), color-mix()).
    const ink = (name: string) => new Ink(v(name) || '#000');
    const line = ink('--fg-muted');
    return {
      line: line.a(),
      fill: line.a(0.16), // a light wash of the line colour under the curve
      grid: ink('--chart-grid').a(),
      axis: ink('--chart-axis').a(),
      text: ink('--chart-text').a(),
      level: ink('--accent').a(),
      mid: line.a(),
      font: v('--font-mono') || 'monospace',
    };
  }

  /** x = bin edges, y = counts with the last one repeated (stepped path), 0 -> gap. */
  function toData(b: BinnedHistogram): uPlot.AlignedData {
    const xs = Array.from(b.edges);
    const ys: (number | null)[] = Array.from(b.counts, (c) => (c > 0 ? c : null));
    ys.push(ys[ys.length - 1] ?? null);
    return [xs, ys];
  }

  /** Log-axis counts: 1, 10, 100, 1k, 10k, 1.5M (format/number.ts). */
  const compact = compactCount;

  /** Handle positions in CSS px within the plot overlay. */
  function handlePositions(u: uPlot, p: StretchParams): Record<LevelHandle, number> {
    const at = handleLevels(p);
    return {
      black: u.valToPos(at.black, 'x'),
      mid: u.valToPos(at.mid, 'x'),
      white: u.valToPos(at.white, 'x'),
    };
  }

  function drawLevels(u: uPlot, pal: Palette): void {
    const p = levels;
    if (!p || !binned) return;
    const { ctx } = u;
    const dpr = uPlot.pxRatio;
    const top = u.bbox.top;
    const bottom = u.bbox.top + u.bbox.height;
    const left = u.bbox.left;
    const right = u.bbox.left + u.bbox.width;
    const at = handleLevels(p);
    const marks: { key: LevelHandle; v: number; color: string; dash: number[]; tag: string }[] = [
      { key: 'black', v: at.black, color: pal.level, dash: [], tag: 'B' },
      { key: 'mid', v: at.mid, color: pal.mid, dash: [3 * dpr, 3 * dpr], tag: 'M' },
      { key: 'white', v: at.white, color: pal.level, dash: [], tag: 'W' },
    ];
    ctx.save();
    const tagStyle = { font: `600 ${10 * dpr}px ${pal.font}`, fill: pal.text, align: 'center', baseline: 'bottom' } as const;
    for (const m of marks) {
      let x = u.valToPos(m.v, 'x', true);
      const outside = x < left || x > right;
      x = Math.round(Math.min(right, Math.max(left, x))) + 0.5;
      const active = grabbing === m.key;
      ctx.strokeStyle = m.color;
      ctx.lineWidth = (active ? 2 : 1.5) * dpr;
      ctx.setLineDash(outside ? [1.5 * dpr, 2.5 * dpr] : m.dash);
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, bottom);
      ctx.stroke();
      // Grip on the axis: the part to take hold of.
      ctx.setLineDash([]);
      ctx.fillStyle = m.color;
      const g = 5 * dpr;
      ctx.beginPath();
      ctx.moveTo(x, bottom - g * 1.6);
      ctx.lineTo(x - g, bottom);
      ctx.lineTo(x + g, bottom);
      ctx.closePath();
      ctx.fill();
      // Tag in the room above the plot, clear of the gridlines.
      const tx = Math.min(right - 4 * dpr, Math.max(left + 4 * dpr, x));
      drawText(ctx, m.tag, tx, top - 2 * dpr, tagStyle);
    }
    ctx.restore();
  }

  function build(): void {
    plot?.destroy();
    plot = null;
    if (!host || width <= 0) return;
    const pal = readPalette();
    const axisFont = `400 10px ${pal.font}`;
    const opts: uPlot.Options = {
      width,
      height: plotH,
      padding: [TAG_ROOM, 10, null, null],
      legend: { show: false },
      cursor: {
        y: false,
        points: { show: false },
        drag: { x: false, y: false, setScale: false },
      },
      select: { show: false, left: 0, top: 0, width: 0, height: 0 },
      scales: {
        x: {
          time: false,
          range: (_u, min, max) => {
            const b = binned; // current frame, not the one at build time
            return b ? [b.edges[0], b.edges[b.edges.length - 1]] : [min, max];
          },
        },
        y: {
          distr: 3,
          log: 10,
          range: (_u, _min, max) => [1, Math.max(10, (max ?? 10) * 1.6)],
        },
      },
      axes: [
        {
          stroke: pal.text,
          font: axisFont,
          size: 22,
          gap: 3,
          ticks: { stroke: pal.axis, width: 1, size: 3 },
          grid: { show: false },
          border: { show: true, stroke: pal.axis, width: 1 },
          values: (_u, splits) => splits.map((v) => int(v)), // "20 000" (U+202F)
          space: 64,
        },
        {
          stroke: pal.text,
          font: axisFont,
          size: 34,
          gap: 4,
          ticks: { show: false },
          grid: { stroke: pal.grid, width: 1 },
          // A hairline per power of ten, nothing in between.
          splits: (u) => {
            const max = u.scales.y.max ?? 10;
            const out: number[] = [];
            for (let v = 1; v <= max; v *= 10) out.push(v);
            return out;
          },
          // Keep every decade (uPlot's log filter would thin them to null).
          filter: (_u, splits) => splits,
          // Below 150 px a label per decade would be ~13 px apart: every other one.
          values: (u, splits) =>
            splits.map((v, i) =>
              v == null || (u.height < 150 && i % 2 === 1) ? '' : compact(v),
            ),
        },
      ],
      series: [
        {},
        {
          stroke: pal.line,
          width: 1.5,
          fill: pal.fill,
          fillTo: (u) => u.scales.y.min ?? 1,
          paths: uPlot.paths.stepped!({ align: 1 }),
          spanGaps: false,
          points: { show: false },
        },
      ],
      hooks: {
        draw: [(u) => drawLevels(u, pal)],
        setCursor: [
          (u) => {
            const i = u.cursor.idx;
            const bb = binned;
            if (grabbing || i === null || i === undefined || !bb || i >= bb.counts.length) {
              hover = null;
              return;
            }
            hover = { lo: bb.edges[i], hi: bb.edges[i + 1], count: bb.counts[i] };
          },
        ],
      },
    };
    const b = binned;
    plot = new uPlot(opts, b ? toData(b) : [[0, 1], [null, null]], host);
    attachHandles(plot);
  }

  /** Pointer handling of the level handles, on uPlot's overlay. */
  function attachHandles(u: uPlot): void {
    const over = u.over;
    const localX = (e: PointerEvent) => e.clientX - over.getBoundingClientRect().left;
    const near = (e: PointerEvent) => (levels ? pickHandle(localX(e), handlePositions(u, levels)) : null);

    over.addEventListener('pointerdown', (e) => {
      if (e.button !== 0 || !levels || !onlevel) return;
      const which = near(e);
      if (!which) return;
      e.preventDefault(); // no text selection, no uPlot mouse handling
      over.setPointerCapture(e.pointerId);
      grabbing = which;
      hover = null;
      u.redraw(false, false);
    });
    over.addEventListener('pointermove', (e) => {
      if (grabbing && levels && onlevel) {
        const [lo, hi] = [u.scales.x.min ?? 0, u.scales.x.max ?? 65535];
        const x = Math.min(over.clientWidth, Math.max(0, localX(e)));
        const adu = Math.min(hi, Math.max(lo, u.posToVal(x, 'x')));
        onlevel(dragLevel(grabbing, adu, levels));
        return;
      }
      over.style.cursor = onlevel && near(e) ? 'ew-resize' : '';
    });
    const end = (e: PointerEvent) => {
      if (!grabbing) return;
      grabbing = null;
      if (over.hasPointerCapture(e.pointerId)) over.releasePointerCapture(e.pointerId);
      u.redraw(false, false);
    };
    over.addEventListener('pointerup', end);
    over.addEventListener('pointercancel', end);
  }

  onMount(() => {
    const ro = new ResizeObserver((entries) => {
      const w = Math.floor(entries[entries.length - 1]?.contentRect.width ?? 0);
      if (w !== width) width = w;
    });
    ro.observe(host);
    return () => {
      ro.disconnect();
      plot?.destroy();
      plot = null;
    };
  });

  // Rebuild when the theme changes (axis colours live in the options) or once
  // the first width is known. Only those: build() also reads the frame.
  $effect(() => {
    void theme;
    const ready = width > 0;
    untrack(() => {
      if (ready) build();
    });
  });

  // Resize in place.
  $effect(() => {
    const w = width;
    const h = plotH;
    untrack(() => {
      if (plot && w > 0 && (plot.width !== w || plot.height !== h)) plot.setSize({ width: w, height: h });
    });
  });

  // New frame: new bins and a new x range. Levels: redraw only.
  $effect(() => {
    const b = binned;
    untrack(() => {
      if (plot && b) plot.setData(toData(b), true);
    });
  });

  $effect(() => {
    if (levels) void [levels.black, levels.white, levels.midtones, levels.mode];
    untrack(() => plot?.redraw(false, false));
  });

  const fmt = (v: number) => (Number.isInteger(v) ? int(v) : fixed(v, 1, { group: true }));
</script>

<div class="histogram">
  <p class="readout num" aria-live="off">
    {#if hover}
      <span class="val">{fmt(hover.lo)}–{fmt(hover.hi)}</span> ADU ·
      <span class="val">{int(hover.count)}</span> px
    {:else if binned}
      {caption ?? `Range ${int(binned.lo)}–${int(binned.hi)} ADU`}{binned.step > 1
        ? ` · ${int(binned.step)} ADU steps`
        : ''}
    {:else}
      No frame
    {/if}
  </p>
  <div
    class="plot"
    class:grabbing={!!grabbing}
    bind:this={host}
    style:height="{height}px"
    role="img"
    aria-label="Histogram of the displayed frame, with the black, midtones and white levels"
  ></div>
</div>

<style>
  .histogram {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .readout {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .val {
    color: var(--fg);
  }

  .plot {
    position: relative;
    width: 100%;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--chart-surface);
    overflow: hidden;
  }
  .plot.grabbing :global(.u-over) {
    cursor: ew-resize !important;
  }

  /* uPlot's stylesheet hard-codes a grey dashed cursor: tokens instead. */
  .plot :global(.u-cursor-x) {
    border-right: 1px solid var(--chart-highlight) !important;
  }
  .plot :global(.uplot) {
    font-family: var(--font-mono);
  }
</style>

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

  Wave 3 (web/lab/PROPOSAL.md 3.2 and 6; promoted from
  src/lab/charts/charts/HistogramStretch.svelte), each opt-in so the levels strip
  keeps its shape:
  - `handles`: B, M and W are also focusable sliders on a track under the plot
    (app/attachments/handle.ts): arrows move one ADU quantization step (the
    balance 0.005), Shift ten, Home / End the plot range. The pointer still grabs
    the lines on the plot.
  - `clipped`: what the stretch throws away is said: the region below black is
    hatched, the one above white washed, each labelled with its exact pixel
    fraction; pixels at the ADC's top code are counted even when the plot range
    (min .. p99.8) leaves them out.
  - `transfer`: the transfer curve over the histogram (dashed, normalised: a
    mapping, not data).
  - `ramp`: the exact display ramp under the plot (owner decision D11): for each
    ADU of the x axis, the byte the viewer draws (stretchValue, then x
    --viewer-tint, quantised as the GPU does): red only in Night Red.
-->
<script lang="ts">
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import { onMount, untrack } from 'svelte';
  import type { Theme } from '../app/theme';
  import { Ink } from '../charts/ink';
  import { drawText } from '../charts/text';
  import { compactCount, fixed, int } from '../format/number';
  import { valueHandle } from '../app/attachments/handle';
  import { adcStep } from '../viewer/framestats';
  import { binHistogram, type BinnedHistogram } from '../viewer/histogram';
  import { dragLevel, handleLevels, type LevelHandle, pickHandle } from '../viewer/levels';
  import { stretchValue, type Histogram16, type StretchParams } from '../viewer/stretch';

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
    /** Focusable B / M / W sliders on a track under the plot. */
    handles?: boolean;
    /** Shade and label the clipped regions; count the pixels at the top code. */
    clipped?: boolean;
    /** Draw the transfer curve over the histogram. */
    transfer?: boolean;
    /** The exact display ramp under the plot (D11). */
    ramp?: boolean;
    /** Full-scale colour of the viewer (--viewer-tint, 0..1 RGB) for the ramp. */
    tint?: readonly [number, number, number];
    /** Write the level values on the handles (off where fields beside the plot show them). */
    handleValues?: boolean;
  }

  let {
    histogram,
    levels,
    theme,
    caption = null,
    height = 104,
    onlevel,
    handles = false,
    clipped = false,
    transfer = false,
    ramp = false,
    tint = [1, 1, 1],
    handleValues = true,
  }: Props = $props();

  let host: HTMLDivElement;
  let plot: uPlot | null = null;
  let width = $state(0);
  let hover: { lo: number; hi: number; count: number } | null = $state(null);
  let grabbing: LevelHandle | null = $state(null);
  /** Where the plot area sits in the host (CSS px): the ramp and the handle track follow it. */
  // The plot box and its x scale: the handles are re-placed when either changes (a page
  // opened on a still frame placed them on the scale of the first draw, review W3).
  let geom = $state({ left: 0, width: 0, x0: 0, x1: 0 });
  let rampCanvas: HTMLCanvasElement | undefined = $state();
  const RAMP_H = 8;

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
    reference: string;
    hatch: string;
    wash: string;
    surface: string;
    danger: string;
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
      reference: ink('--chart-reference').a(0.9),
      hatch: line.a(0.22),
      wash: line.a(0.1),
      surface: ink('--chart-surface').a(0.88),
      danger: ink('--danger').a(),
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

  /** What the levels clip, exactly, from the 65 536-bin histogram (display only). */
  const clip = $derived.by(() => {
    const h = histogram;
    const p = levels;
    if (!clipped || !h || !p || h.n === 0) return null;
    const at = handleLevels(p);
    let below = 0;
    let above = 0;
    for (let v = h.min; v <= h.max; v++) {
      const c = h.counts[v];
      if (!c) continue;
      if (v <= at.black) below += c;
      else if (v >= at.white) above += c;
    }
    const step = adcStep(h);
    const top = 65536 - step;
    let atTop = 0;
    for (let v = top; v <= 65535; v++) atTop += h.counts[v];
    return { below: below / h.n, above: above / h.n, atTop, top };
  });

  const pct = (f: number) => (f >= 0.001 ? `${fixed(f * 100, f < 0.1 ? 2 : 1)} %` : f > 0 ? '< 0.1 %' : '0 %');

  /** Clipped regions, transfer curve and their labels (under the level lines). */
  function drawClipAndTransfer(u: uPlot, pal: Palette): void {
    const p = levels;
    if (!p || !binned || (!clipped && !transfer)) return;
    const dpr = uPlot.pxRatio;
    const { ctx } = u;
    const { left, top, width, height } = u.bbox;
    const right = left + width;
    const at = handleLevels(p);
    ctx.save();
    ctx.beginPath();
    ctx.rect(left, top, width, height);
    ctx.clip();
    const xb = Math.max(left, Math.min(right, u.valToPos(at.black, 'x', true)));
    const xw = Math.max(left, Math.min(right, u.valToPos(at.white, 'x', true)));
    if (clipped) {
      // Below black: hatched (BRAND 2 exception, owner D11). Above white: a wash.
      if (xb > left) {
        ctx.strokeStyle = pal.hatch;
        ctx.lineWidth = dpr;
        ctx.beginPath();
        for (let x = left - height; x < xb; x += 6 * dpr) {
          ctx.moveTo(Math.max(left, x), top + height - Math.max(0, left - x));
          ctx.lineTo(Math.min(xb, x + height), top + height - Math.min(height, xb - x));
        }
        ctx.stroke();
      }
      if (xw < right) {
        ctx.fillStyle = pal.wash;
        ctx.fillRect(xw, top, right - xw, height);
      }
    }
    if (transfer) {
      ctx.strokeStyle = pal.reference;
      ctx.lineWidth = 1.25 * dpr;
      ctx.setLineDash([4 * dpr, 3 * dpr]);
      ctx.beginPath();
      const steps = Math.max(2, Math.round(width / (2 * dpr)));
      for (let k = 0; k <= steps; k++) {
        const x = left + (width * k) / steps;
        const v = u.posToVal((x - left) / dpr, 'x');
        const y = top + height - stretchValue(v, p) * height;
        if (k === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.setLineDash([]);
    }
    const c = clip;
    if (c) {
      const font = `500 ${10 * dpr}px ${pal.font}`;
      const tag = (text: string, x: number, align: 'left' | 'right', y = top + 6 * dpr) => {
        ctx.font = font;
        const w = ctx.measureText(text).width;
        const bx = align === 'left' ? x : x - w;
        ctx.fillStyle = pal.surface;
        ctx.fillRect(bx - 3 * dpr, y - 1 * dpr, w + 6 * dpr, 14 * dpr);
        drawText(ctx, text, x, y + 6 * dpr, { font, fill: pal.text, align, baseline: 'middle' });
      };
      if (xb - left > 70 * dpr) tag(`${pct(c.below)} → black`, xb - 6 * dpr, 'right');
      if (right - xw > 70 * dpr) tag(`${pct(c.above)} → white`, xw + 6 * dpr, 'left');
      if (c.atTop > 0) {
        const xs = u.valToPos(c.top, 'x', true);
        // Beyond the plotted range: said in the readout row, never written over the data.
        if (xs <= right + 1) {
          ctx.strokeStyle = pal.danger;
          ctx.lineWidth = 2 * dpr;
          ctx.beginPath();
          ctx.moveTo(Math.min(xs, right - dpr), top + height);
          ctx.lineTo(Math.min(xs, right - dpr), top + height - 18 * dpr);
          ctx.stroke();
        }
      }
    }
    ctx.restore();
  }

  /** The exact display ramp under the plot: what each ADU of the x axis becomes on screen. */
  function drawRamp(u: uPlot): void {
    const p = levels;
    if (!ramp || !rampCanvas) return;
    const cssW = Math.max(1, Math.round(u.bbox.width / uPlot.pxRatio));
    const dpr = typeof devicePixelRatio === 'number' ? devicePixelRatio : 1;
    const W = Math.round(cssW * dpr);
    const H = Math.round(RAMP_H * dpr);
    if (rampCanvas.width !== W || rampCanvas.height !== H) {
      rampCanvas.width = W;
      rampCanvas.height = H;
    }
    const ctx = rampCanvas.getContext('2d');
    if (!ctx) return;
    const img = ctx.createImageData(W, H);
    const [r, g, b] = tint;
    for (let x = 0; x < W; x++) {
      const v = u.posToVal(x / dpr, 'x');
      const n = p ? stretchValue(v, p) : 0;
      // The shader writes n x tint into an 8-bit target: round(n x tint x 255).
      const R = Math.round(n * r * 255);
      const G = Math.round(n * g * 255);
      const B = Math.round(n * b * 255);
      for (let y = 0; y < H; y++) {
        const o = (y * W + x) * 4;
        img.data[o] = R;
        img.data[o + 1] = G;
        img.data[o + 2] = B;
        img.data[o + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
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
        draw: [
          (u) => {
            drawClipAndTransfer(u, pal);
            drawLevels(u, pal);
            drawRamp(u);
            const left = u.over.offsetLeft;
            const w = u.bbox.width / uPlot.pxRatio;
            const x0 = u.scales.x.min ?? 0;
            const x1 = u.scales.x.max ?? 0;
            if (geom.left !== left || geom.width !== w || geom.x0 !== x0 || geom.x1 !== x1) geom = { left, width: w, x0, x1 };
          },
        ],
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
    void [tint[0], tint[1], tint[2], clipped, transfer, ramp, clip];
    untrack(() => plot?.redraw(false, false));
  });

  // -- Keyboard handles (wave 3) --------------------------------------------------
  const handlePos = $derived.by(() => {
    void geom;
    void binned;
    const p = levels;
    if (!handles || !p || !plot || geom.width <= 0) return null;
    const at = handleLevels(p);
    const x = (v: number) => Math.min(geom.width, Math.max(0, plot!.valToPos(v, 'x')));
    return { black: x(at.black), mid: x(at.mid), white: x(at.white), at };
  });

  /** clientX -> ADU on the plot's x scale. */
  function aduAt(clientX: number): number | null {
    if (!plot) return null;
    const r = plot.over.getBoundingClientRect();
    return plot.posToVal(Math.min(r.width, Math.max(0, clientX - r.left)), 'x');
  }
  const rangeLo = () => binned?.edges[0] ?? 0;
  const rangeHi = () => binned?.edges[binned.edges.length - 1] ?? 65535;
  const aduStep = () => binned?.step ?? 1;

  function levelHandle(which: LevelHandle) {
    if (which === 'mid') {
      return valueHandle({
        axis: 'x',
        toValue: (cx) => {
          const v = aduAt(cx);
          return v === null || !levels ? null : (dragLevel('mid', v, levels).midtones ?? null);
        },
        get: () => levels?.midtones ?? 0.5,
        set: (m) => onlevel?.({ midtones: Math.round(Math.min(0.999, Math.max(0.001, m)) * 1000) / 1000 }),
        step: 0.005,
        min: () => 0.001,
        max: () => 0.999,
        ondrag: (a) => (grabbing = a ? 'mid' : null),
      });
    }
    return valueHandle({
      axis: 'x',
      toValue: (cx) => aduAt(cx),
      get: () => (levels ? handleLevels(levels)[which] : 0),
      set: (v) => {
        if (levels) onlevel?.(dragLevel(which, v, levels));
      },
      step: aduStep,
      min: rangeLo,
      max: rangeHi,
      ondrag: (a) => (grabbing = a ? which : null),
    });
  }

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
        : ''}{#if clip && clip.atTop > 0 && clip.top > binned.hi}<span class="beyond">{' · '}{int(clip.atTop)} px at {int(clip.top)}, beyond the range</span>{/if}
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
  {#if ramp}
    <canvas
      class="ramp"
      bind:this={rampCanvas}
      style:margin-left="{geom.left + 1}px"
      style:width="{geom.width}px"
      style:height="{RAMP_H}px"
      aria-hidden="true"
    ></canvas>
  {/if}
  {#if handles}
    <div class="track" style:margin-left="{geom.left + 1}px" style:width="{geom.width}px">
      {#if handlePos && levels}
        {@const near = Math.abs(handlePos.white - handlePos.black) < 92}
        {@const edge = (x: number) => (x < 40 ? 'edge-l' : x > geom.width - 40 ? 'edge-r' : '')}
        <div
          class="handle black {edge(handlePos.black)}"
          class:near
          class:grabbing={grabbing === 'black'}
          style:left="{handlePos.black}px"
          role="slider"
          tabindex="0"
          aria-label="Black level"
          aria-orientation="horizontal"
          aria-valuemin={rangeLo()}
          aria-valuemax={rangeHi()}
          aria-valuenow={handlePos.at.black}
          aria-valuetext="{int(handlePos.at.black)} ADU"
          {@attach levelHandle('black')}
        >
          <span class="num">B{#if handleValues}&nbsp;{int(handlePos.at.black)}{/if}</span>
        </div>
        <div
          class="handle mid {edge(handlePos.mid)}"
          class:grabbing={grabbing === 'mid'}
          style:left="{handlePos.mid}px"
          role="slider"
          tabindex="0"
          aria-label="Midtones balance"
          aria-orientation="horizontal"
          aria-valuemin={0.001}
          aria-valuemax={0.999}
          aria-valuenow={levels.midtones}
          aria-valuetext="balance {fixed(levels.midtones, 3)}, at {int(handlePos.at.mid)} ADU"
          {@attach levelHandle('mid')}
        >
          <span class="num">M{#if handleValues}&nbsp;{fixed(levels.midtones, 3)}{/if}</span>
        </div>
        <div
          class="handle white {edge(handlePos.white)}"
          class:near
          class:grabbing={grabbing === 'white'}
          style:left="{handlePos.white}px"
          role="slider"
          tabindex="0"
          aria-label="White level"
          aria-orientation="horizontal"
          aria-valuemin={rangeLo()}
          aria-valuemax={rangeHi()}
          aria-valuenow={handlePos.at.white}
          aria-valuetext="{int(handlePos.at.white)} ADU"
          {@attach levelHandle('white')}
        >
          <span class="num">W{#if handleValues}&nbsp;{int(handlePos.at.white)}{/if}</span>
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .histogram {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .ramp {
    display: block;
    flex: none;
    margin-top: 1px;
    border-radius: 1px;
  }
  /* B and W on the first row, M on a second one: it never hides them. */
  .track {
    position: relative;
    flex: none;
    height: 22px;
  }
  .handle {
    position: absolute;
    top: 2px;
    display: flex;
    align-items: center;
    height: 18px;
    padding: 0 5px;
    transform: translateX(-50%);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-2xs);
    white-space: nowrap;
    cursor: ew-resize;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
  }
  /* A notch on the axis; brass for B and W, the levels being adjusted (as their lines). */
  .handle::before {
    content: '';
    position: absolute;
    left: 50%;
    bottom: 100%;
    margin-left: -3px;
    border: 3px solid transparent;
    border-bottom-color: var(--accent);
    border-top: 0;
  }
  .handle.mid {
    top: 2px;
    border-style: dashed;
  }
  .handle.mid::before {
    border-bottom-color: var(--fg-muted);
  }
  .handle.black.near {
    transform: translateX(-100%);
  }
  .handle.white.near {
    transform: none;
  }
  .handle.black.near::before {
    left: auto;
    right: 3px;
    margin-left: 0;
  }
  .handle.white.near::before {
    left: 3px;
    margin-left: 0;
  }
  /* At the ends of the track a tab leans inwards, so its value is never cut. */
  .handle.edge-l {
    transform: translateX(-4px);
  }
  .handle.edge-r {
    transform: translateX(calc(-100% + 4px));
  }
  .handle.edge-l::before {
    left: 4px;
    margin-left: -3px;
  }
  .handle.edge-r::before {
    left: auto;
    right: 1px;
    margin-left: 0;
  }
  .handle:hover,
  .handle.grabbing {
    background: var(--surface);
  }
  .handle:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
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
  .beyond {
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

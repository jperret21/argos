<!--
  Histogram with stretch handles: an improvement of lib/imaging/Histogram
  (same binning, same levels maths: lib/viewer/histogram.ts, levels.ts,
  stretch.ts, imported read-only).

  What changes, and why:
  - B / M / W are HTML handles on a track under the plot: focusable sliders
    (arrows = one quantization step, Shift = 10, Home / End), value in mono
    on the handle. The Qt and spike versions were pointer-only grips.
  - What the stretch throws away is stated: the regions clipped to black and
    to white are shaded and labelled with their exact pixel fractions.
  - The display ramp under the plot is the actual mapping (v x --viewer-tint,
    red-only in Night Red): it links the ADU axis to what the picture shows.
    The transfer curve can be drawn over the histogram (normalised, no axis).
  - Sensor saturation is counted at 65 535 and marked even when the plot
    range (min .. 99.8th percentile) leaves it out; "Full" shows it.
  - Counts log or linear; hover gives the bin, its count and the percentile.
  Data never animates: a new frame redraws the bars; the handles move only
  when Auto recomputes the levels (a value change, so an instant jump).
-->
<script lang="ts">
  import uPlot from 'uplot';
  import { untrack } from 'svelte';
  import Icon from '../../../lib/components/Icon.svelte';
  import { tooltip } from '../../../lib/components/tooltip';
  import { binHistogram, type BinnedHistogram } from '../../../lib/viewer/histogram';
  import { dragLevel, handleLevels, type LevelHandle } from '../../../lib/viewer/levels';
  import { autoStf, median, medianAbsDeviation, MAD_TO_SIGMA, stretchValue, type Histogram16, type StretchMode, type StretchParams } from '../../../lib/viewer/stretch';
  import { env } from '../env.svelte';
  import { clock } from '../sim/stream.svelte';
  import { FLAG_SATURATED } from '../sim/night';
  import { synthHistogram, FRAME_H, FRAME_W } from '../sim/frame';
  import { readInks, type ChartInks } from '../core/palette';
  import { PlotHost } from '../core/uplot/host';
  import { compactCount, fixed, grouped } from '../core/format';

  interface Props {
    compact?: boolean;
  }
  let { compact = false }: Props = $props();

  const q = new URLSearchParams(location.search);
  let range = $state<'auto' | 'full'>(q.get('range') === 'full' ? 'full' : 'auto');
  let countScale = $state<'log' | 'linear'>('log');
  let showTransfer = $state(true);
  let auto = $state(true);
  let levels = $state<StretchParams>({ black: 1100, white: 2600, midtones: 0.25, mode: 'linear' });
  let hist = $state.raw<Histogram16 | null>(null);
  let frameNo = $state(0);
  let hover = $state<{ lo: number; hi: number; count: number; pct: number; x: number } | null>(null);
  let grabbing = $state<LevelHandle | null>(null);
  let geom = $state({ left: 0, width: 0 });

  let root: HTMLDivElement;
  let ramp: HTMLCanvasElement;
  let host: PlotHost | null = null;
  let inks: ChartInks | null = null;

  const binned = $derived.by((): BinnedHistogram | null => {
    if (!hist) return null;
    return range === 'full' ? binHistogram(hist, 256, { lo: 0, hi: 65535 }) : binHistogram(hist);
  });

  const stats = $derived.by(() => {
    const h = hist;
    if (!h) return null;
    const med = median(h);
    const mad = medianAbsDeviation(h, med);
    let sum = 0;
    let below = 0;
    let above = 0;
    const at = handleLevels(levels);
    for (let v = h.min; v <= h.max; v++) {
      const c = h.counts[v];
      if (!c) continue;
      sum += c * v;
      if (v <= at.black) below += c;
      else if (v >= at.white) above += c;
    }
    return { min: h.min, max: h.max, med, sigma: mad * MAD_TO_SIGMA, mean: sum / h.n, saturated: h.counts[65535], below: below / h.n, above: above / h.n, n: h.n };
  });

  /** New frame from the night's latest frame (sky, stars, HFD, saturation). */
  function frameFrom(i: number): Histogram16 {
    const c = clock.night.cols;
    const hfd = c.hfd[i];
    return synthHistogram({
      seed: 1000 + i,
      sky: c.sky[i],
      sigma: 17 + 0.004 * c.sky[i],
      stars: c.stars[i],
      hfd,
      saturatedPx: Math.round(560 * Math.pow(2.25 / hfd, 2) + (c.flags[i] & FLAG_SATURATED ? 90 : 0)),
    });
  }

  function update(): void {
    const n = clock.night.n;
    if (!n) return;
    hist = frameFrom(n - 1);
    frameNo = n;
    if (auto) levels = { ...autoStf(hist), mode: levels.mode };
  }

  function toData(b: BinnedHistogram): uPlot.AlignedData {
    const xs = Array.from(b.edges);
    const ys: (number | null)[] = Array.from(b.counts, (c) => (c > 0 ? c : countScale === 'log' ? null : 0));
    ys.push(ys[ys.length - 1] ?? null);
    return [xs, ys];
  }

  function drawOverlays(u: uPlot): void {
    const ink = inks!;
    const b = binned;
    const s = stats;
    if (!b || !s) return;
    const dpr = uPlot.pxRatio;
    const { ctx } = u;
    const { left, top, width, height } = u.bbox;
    const right = left + width;
    const at = handleLevels(levels);
    const X = (v: number) => u.valToPos(v, 'x', true);
    ctx.save();
    ctx.beginPath();
    ctx.rect(left, top, width, height);
    ctx.clip();
    // Clipped regions: hatched below black, washed above white.
    const xb = Math.max(left, Math.min(right, X(at.black)));
    const xw = Math.max(left, Math.min(right, X(at.white)));
    if (xb > left) {
      ctx.strokeStyle = ink.fgMuted.a(0.22);
      ctx.lineWidth = dpr;
      ctx.beginPath();
      for (let x = left - height; x < xb; x += 6 * dpr) {
        ctx.moveTo(Math.max(left, x), top + height - Math.max(0, left - x));
        ctx.lineTo(Math.min(xb, x + height), top + height - Math.min(height, xb - x));
      }
      ctx.stroke();
    }
    if (xw < right) {
      ctx.fillStyle = ink.fgMuted.a(0.1);
      ctx.fillRect(xw, top, right - xw, height);
    }
    // Transfer curve, normalised to the plot height (a mapping, not data).
    if (showTransfer) {
      ctx.strokeStyle = ink.reference.a(0.9);
      ctx.lineWidth = 1.25 * dpr;
      ctx.setLineDash([4 * dpr, 3 * dpr]);
      ctx.beginPath();
      const steps = Math.max(2, Math.round(width / (2 * dpr)));
      for (let k = 0; k <= steps; k++) {
        const x = left + (width * k) / steps;
        const v = u.posToVal(x / dpr - u.bbox.left / dpr, 'x');
        const y = top + height - stretchValue(v, levels) * height;
        if (k === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.setLineDash([]);
    }
    // Level lines.
    const line = (v: number, color: string, w: number, dash: number[]) => {
      let x = X(v);
      const outside = x < left || x > right;
      x = Math.round(Math.min(right, Math.max(left, x))) + 0.5;
      ctx.strokeStyle = color;
      ctx.lineWidth = w * dpr;
      ctx.setLineDash(outside ? [1.5 * dpr, 2.5 * dpr] : dash.map((d) => d * dpr));
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, top + height);
      ctx.stroke();
      ctx.setLineDash([]);
    };
    line(at.black, ink.accent.a(), grabbing === 'black' ? 2 : 1.5, []);
    line(at.mid, ink.fgMuted.a(), grabbing === 'mid' ? 2 : 1.25, [3, 3]);
    line(at.white, ink.accent.a(), grabbing === 'white' ? 2 : 1.5, []);
    // Clip labels (words, not colour).
    ctx.font = `500 ${10 * dpr}px ${ink.mono}`;
    ctx.textBaseline = 'top';
    const tag = (text: string, x: number, align: CanvasTextAlign) => {
      ctx.textAlign = align;
      const w = ctx.measureText(text).width;
      const bx = align === 'left' ? x : x - w;
      ctx.fillStyle = ink.surface.a(0.85);
      ctx.fillRect(bx - 3 * dpr, top + 6 * dpr, w + 6 * dpr, 14 * dpr);
      ctx.fillStyle = ink.text.a();
      ctx.fillText(text, x, top + 8 * dpr);
    };
    if (xb - left > 60 * dpr) tag(`${pct(s.below)} → black`, xb - 6 * dpr, 'right');
    if (right - xw > 60 * dpr) tag(`${pct(s.above)} → white`, xw + 6 * dpr, 'left');
    // Sensor saturation: a rug at the right edge (or a note when out of range).
    if (s.saturated > 0) {
      const xs = X(65535);
      if (xs > right + 1) {
        const text = `${grouped(s.saturated)} px at 65 535 · beyond the range`;
        ctx.textAlign = 'right';
        const w = ctx.measureText(text).width;
        ctx.fillStyle = ink.surface.a(0.85);
        ctx.fillRect(right - w - 9 * dpr, top + 24 * dpr, w + 6 * dpr, 14 * dpr);
        ctx.fillStyle = ink.text.a();
        ctx.fillText(text, right - 6 * dpr, top + 26 * dpr);
      } else {
        ctx.strokeStyle = ink.danger.a();
        ctx.lineWidth = 2 * dpr;
        ctx.beginPath();
        ctx.moveTo(Math.min(xs, right - dpr), top + height);
        ctx.lineTo(Math.min(xs, right - dpr), top + height - 18 * dpr);
        ctx.stroke();
      }
    }
    ctx.restore();
    if (geom.left !== u.over.offsetLeft || geom.width !== u.bbox.width / dpr) geom = { left: u.over.offsetLeft, width: u.bbox.width / dpr };
    drawRamp(u);
  }

  const pct = (f: number) => (f >= 0.001 ? `${(f * 100).toFixed(f < 0.1 ? 2 : 1)} %` : f > 0 ? '< 0.1 %' : '0 %');

  /** The display ramp: what each ADU of the x axis becomes on screen. */
  function drawRamp(u: uPlot): void {
    if (!ramp || !inks) return;
    const dpr = window.devicePixelRatio || 1;
    const w = Math.round(u.bbox.width / uPlot.pxRatio);
    const h = 10;
    ramp.style.width = `${w}px`;
    ramp.style.marginLeft = `${u.over.offsetLeft}px`;
    ramp.width = Math.round(w * dpr);
    ramp.height = Math.round(h * dpr);
    const ctx = ramp.getContext('2d');
    if (!ctx) return;
    const [r, g, b] = inks.viewerTint.rgb01;
    const img = ctx.createImageData(ramp.width, ramp.height);
    for (let x = 0; x < ramp.width; x++) {
      const v = u.posToVal(x / dpr, 'x');
      const s = stretchValue(v, levels);
      const k = Math.floor(Math.min(1, Math.max(0, s)) * 255 + 0.5);
      for (let y = 0; y < ramp.height; y++) {
        const o = (y * ramp.width + x) * 4;
        img.data[o] = Math.round(k * r);
        img.data[o + 1] = Math.round(k * g);
        img.data[o + 2] = Math.round(k * b);
        img.data[o + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  function options(): uPlot.Options {
    const ink = inks!;
    const font = `400 10px ${ink.mono}`;
    return {
      width: 100,
      height: 100,
      padding: [10, 18, 0, 0],
      legend: { show: false },
      cursor: { y: false, points: { show: false }, drag: { x: false, y: false, setScale: false } },
      select: { show: false, left: 0, top: 0, width: 0, height: 0 },
      scales: {
        x: {
          time: false,
          range: (_u, min, max) => {
            const b = binned;
            return b ? [b.edges[0], b.edges[b.edges.length - 1]] : [min, max];
          },
        },
        y:
          countScale === 'log'
            ? { distr: 3, log: 10, range: (_u, _min, max) => [1, Math.max(10, (max ?? 10) * 1.8)] }
            : { range: (_u, _min, max) => [0, Math.max(10, (max ?? 10) * 1.08)] },
      },
      axes: [
        {
          stroke: ink.text.a(),
          font,
          size: 24,
          gap: 3,
          space: 70,
          ticks: { stroke: ink.axis.a(), width: 1, size: 3 },
          grid: { show: false },
          border: { show: true, stroke: ink.axis.a(), width: 1 },
          values: (_u, splits) => splits.map((v) => grouped(v)),
        },
        {
          stroke: ink.text.a(),
          font,
          size: 46,
          gap: 4,
          ticks: { show: false },
          grid: { stroke: ink.grid.a(), width: 1 },
          ...(countScale === 'log'
            ? {
                splits: (u: uPlot) => {
                  const out: number[] = [];
                  for (let v = 1; v <= (u.scales.y.max ?? 10); v *= 10) out.push(v);
                  return out;
                },
                filter: (_u: uPlot, splits: number[]) => splits,
              }
            : {}),
          values: (_u, splits) => splits.map((v) => (v == null ? '' : compactCount(v))),
        },
      ],
      series: [
        {},
        {
          stroke: ink.fgMuted.a(),
          width: 1.5,
          fill: ink.fgMuted.a(0.16),
          fillTo: (u) => u.scales.y.min ?? 1,
          paths: uPlot.paths.stepped!({ align: 1 }),
          spanGaps: false,
          points: { show: false },
        },
      ],
      hooks: {
        draw: [drawOverlays],
        setCursor: [
          (u) => {
            const i = u.cursor.idx;
            const b = binned;
            const h = hist;
            if (grabbing || i == null || !b || !h || i >= b.counts.length || (u.cursor.left ?? -1) < 0) {
              hover = null;
              return;
            }
            let below = 0;
            for (let v = h.min; v < b.edges[i + 1] && v <= 65535; v++) below += h.counts[v];
            hover = { lo: b.edges[i], hi: b.edges[i + 1], count: b.counts[i], pct: (100 * below) / h.n, x: (u.cursor.left ?? 0) + u.over.offsetLeft };
          },
        ],
      },
    };
  }

  function attach(el: HTMLElement) {
    host = new PlotHost(
      el,
      () => ({ opts: options(), data: binned ? toData(binned) : [[0, 1], [null, null]] }),
      undefined,
      (u) => drawRamp(u),
    );
    return () => {
      host?.destroy();
      host = null;
    };
  }

  $effect(() => {
    void env.theme;
    void countScale;
    untrack(() => {
      inks = readInks(root);
      host?.build();
    });
  });

  $effect(() => {
    const b = binned;
    untrack(() => {
      if (b) host?.u?.setData(toData(b), true);
    });
  });

  $effect(() => {
    void levels.black;
    void levels.white;
    void levels.midtones;
    void levels.mode;
    void showTransfer;
    void grabbing;
    untrack(() => host?.u?.redraw(false, false));
  });

  $effect(() =>
    untrack(() => {
      update();
      return clock.night.onAppend(update);
    }),
  );

  // -- Handles -------------------------------------------------------------------------
  const pos = $derived.by(() => {
    const u = host?.u;
    void geom;
    void binned;
    if (!u) return null;
    const at = handleLevels(levels);
    const clampX = (v: number) => Math.min(geom.width, Math.max(0, u.valToPos(v, 'x')));
    return { black: clampX(at.black), mid: clampX(at.mid), white: clampX(at.white), at };
  });

  function setFrom(which: LevelHandle, adu: number): void {
    auto = false;
    levels = { ...levels, ...dragLevel(which, adu, levels) };
  }

  function handle(which: LevelHandle) {
    return (el: HTMLElement) => {
      const toAdu = (clientX: number) => {
        const u = host?.u;
        if (!u) return null;
        const r = u.over.getBoundingClientRect();
        const x = Math.min(r.width, Math.max(0, clientX - r.left));
        return u.posToVal(x, 'x');
      };
      const down = (e: PointerEvent) => {
        if (e.button !== 0) return;
        e.preventDefault();
        el.setPointerCapture(e.pointerId);
        grabbing = which;
      };
      const move = (e: PointerEvent) => {
        if (grabbing !== which) return;
        const v = toAdu(e.clientX);
        if (v !== null) setFrom(which, v);
      };
      const up = (e: PointerEvent) => {
        if (grabbing === which) grabbing = null;
        if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
      };
      const key = (e: KeyboardEvent) => {
        const step = (binned?.step ?? 1) * (e.shiftKey ? 10 : 1);
        const at = handleLevels(levels);
        if (which === 'mid') {
          const d = e.shiftKey ? 0.05 : 0.005;
          let m = levels.midtones;
          if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') m = Math.max(0.001, m - d);
          else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') m = Math.min(0.999, m + d);
          else return;
          e.preventDefault();
          auto = false;
          levels = { ...levels, midtones: +m.toFixed(3) };
          return;
        }
        const cur = which === 'black' ? at.black : at.white;
        let v: number | null = null;
        if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') v = cur - step;
        else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') v = cur + step;
        else if (e.key === 'Home') v = binned?.edges[0] ?? 0;
        else if (e.key === 'End') v = binned?.edges[binned.edges.length - 1] ?? 65535;
        if (v === null) return;
        e.preventDefault();
        setFrom(which, v);
      };
      el.addEventListener('pointerdown', down);
      el.addEventListener('pointermove', move);
      el.addEventListener('pointerup', up);
      el.addEventListener('pointercancel', up);
      el.addEventListener('keydown', key);
      return () => {
        el.removeEventListener('pointerdown', down);
        el.removeEventListener('pointermove', move);
        el.removeEventListener('pointerup', up);
        el.removeEventListener('pointercancel', up);
        el.removeEventListener('keydown', key);
      };
    };
  }

  const MODES: { id: StretchMode; label: string }[] = [
    { id: 'linear', label: 'Linear' },
    { id: 'log', label: 'Log' },
    { id: 'asinh', label: 'Asinh' },
  ];
  const fmtAdu = (v: number) => grouped(v);
</script>

<div class="hs" class:compact bind:this={root}>
  <section class="plotcol">
    <header class="head">
      <Icon name="histogram" size={16} />
      <h3>Histogram</h3>
      <span class="sub num">frame #{frameNo} · {FRAME_W} × {FRAME_H} · {grouped(stats?.n ?? 0)} px · {binned?.step ?? 1} ADU steps</span>
      <span class="grow"></span>
      {#if hover}
        <span class="readout num"><b>{fmtAdu(hover.lo)}–{fmtAdu(hover.hi)}</b> ADU · <b>{grouped(hover.count)}</b> px · p<b>{hover.pct.toFixed(1)}</b></span>
      {:else if binned}
        <span class="readout num">{range === 'auto' ? `range ${fmtAdu(binned.lo)}–${fmtAdu(binned.hi)} ADU (min … 99.8th percentile)` : 'full range 0–65 535 ADU'}</span>
      {/if}
    </header>
    <div class="plotwrap">
      <div class="lab-plot-host plot" {@attach attach} role="img" aria-label="Histogram of the displayed frame with the black, midtones and white levels"></div>
      <canvas class="ramp" bind:this={ramp} aria-hidden="true"></canvas>
      <div class="track" style:margin-left="{geom.left}px" style:width="{geom.width}px">
        {#if pos}
          {#each [{ k: 'black', x: pos.black, v: `B ${fmtAdu(pos.at.black)}`, text: `${fmtAdu(pos.at.black)} ADU` }, { k: 'mid', x: pos.mid, v: `M ${levels.midtones.toFixed(3)}`, text: `balance ${levels.midtones.toFixed(3)}, at ${fmtAdu(pos.at.mid)} ADU` }, { k: 'white', x: pos.white, v: `W ${fmtAdu(pos.at.white)}`, text: `${fmtAdu(pos.at.white)} ADU` }] as h (h.k)}
            <div
              class="handle {h.k}"
              class:grabbing={grabbing === h.k}
              class:near={h.k !== 'mid' && Math.abs(pos.white - pos.black) < 84}
              style:left="{h.x}px"
              role="slider"
              tabindex="0"
              data-shot="handle-{h.k}"
              aria-label={h.k === 'black' ? 'Black level' : h.k === 'white' ? 'White level' : 'Midtones balance'}
              aria-orientation="horizontal"
              aria-valuenow={h.k === 'mid' ? levels.midtones : h.k === 'black' ? pos.at.black : pos.at.white}
              aria-valuetext={h.text}
              {@attach handle(h.k as LevelHandle)}
            >
              <span class="num">{h.v}</span>
            </div>
          {/each}
        {/if}
      </div>
    </div>
  </section>

  {#if !compact}
    <aside class="panel">
      <div class="row">
        <span class="lab-eyebrow">Levels</span>
        <button class="lab-tool" aria-pressed={auto} aria-label="Auto stretch" aria-keyshortcuts="A" use:tooltip={{ text: 'Auto stretch on every frame', shortcut: 'A' }} onclick={() => { auto = !auto; if (auto) update(); }}>
          <Icon name="stretch-auto" size={16} />
        </button>
      </div>
      <dl class="levels">
        <dt>Black</dt>
        <dd class="num big">{fmtAdu(handleLevels(levels).black)}<small>ADU</small></dd>
        <dt>Midtones</dt>
        <dd class="num big">{levels.midtones.toFixed(3)}<small>at {fmtAdu(handleLevels(levels).mid)}</small></dd>
        <dt>White</dt>
        <dd class="num big">{fmtAdu(handleLevels(levels).white)}<small>ADU</small></dd>
      </dl>
      <div class="lab-seg" role="radiogroup" aria-label="Transfer">
        {#each MODES as m (m.id)}
          <button role="radio" aria-checked={levels.mode === m.id} onclick={() => (levels = { ...levels, mode: m.id })}>{m.label}</button>
        {/each}
      </div>
      <div class="opts">
        <span class="lab-eyebrow">Plot</span>
        <div class="lab-seg" role="radiogroup" aria-label="Range">
          <button role="radio" aria-checked={range === 'auto'} onclick={() => (range = 'auto')}>Min … p99.8</button>
          <button role="radio" aria-checked={range === 'full'} onclick={() => (range = 'full')}>Full</button>
        </div>
        <div class="lab-seg" role="radiogroup" aria-label="Counts">
          <button role="radio" aria-checked={countScale === 'log'} onclick={() => (countScale = 'log')}>Log</button>
          <button role="radio" aria-checked={countScale === 'linear'} onclick={() => (countScale = 'linear')}>Linear</button>
        </div>
        <button class="lab-btn" aria-pressed={showTransfer} onclick={() => (showTransfer = !showTransfer)}>Transfer curve</button>
      </div>
      {#if stats}
        <p class="lab-eyebrow">Frame statistics</p>
        <dl class="stats num">
          <dt>min</dt><dd>{fmtAdu(stats.min)}</dd>
          <dt>median</dt><dd>{fmtAdu(stats.med)}</dd>
          <dt>σ (MAD)</dt><dd>{fixed(stats.sigma, 1)}</dd>
          <dt>mean</dt><dd>{fixed(stats.mean, 1)}</dd>
          <dt>max</dt><dd>{fmtAdu(stats.max)}</dd>
          <dt>→ black</dt><dd>{pct(stats.below)}</dd>
          <dt>→ white</dt><dd>{pct(stats.above)}</dd>
          <dt>at 65 535</dt><dd class:sat={stats.saturated > 0}>{grouped(stats.saturated)} px</dd>
        </dl>
      {/if}
      <p class="note">Keyboard: focus a handle, arrows move one {binned?.step ?? 1}-ADU step, Shift ten. Dragging or typing turns Auto off. The ramp is the display mapping in this theme’s viewer tint.</p>
    </aside>
  {/if}
</div>

<style>
  .hs {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 320px;
    height: 100%;
    min-height: 0;
    background: var(--chart-surface);
  }
  .hs.compact {
    grid-template-columns: minmax(0, 1fr);
  }
  .plotcol {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: var(--lab-chart-toolbar-h);
    padding: 0 var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
    background: var(--bg);
    color: var(--fg-muted);
    flex: none;
  }
  h3 {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-semibold);
  }
  .sub,
  .readout {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .readout b {
    color: var(--fg);
    font-weight: var(--weight-regular);
  }
  .grow {
    flex: 1;
  }
  .plotwrap {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: var(--space-4) var(--space-4) var(--space-3) var(--space-3);
  }
  .plot {
    flex: 1;
  }
  .ramp {
    display: block;
    height: 10px;
    margin-top: 6px;
    border: var(--border-w) solid var(--border-soft);
    box-sizing: content-box;
  }
  .track {
    position: relative;
    height: 50px;
    margin-top: 2px;
  }
  .handle {
    position: absolute;
    top: 4px;
    display: flex;
    align-items: center;
    height: 20px;
    padding: 0 6px;
    transform: translateX(-50%);
    border: 1px solid var(--accent);
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
  .handle::before {
    content: '';
    position: absolute;
    left: 50%;
    bottom: 100%;
    margin-left: -4px;
    border: 4px solid transparent;
    border-bottom-color: var(--accent);
    border-top: 0;
  }
  /* Midtones on a second row: it never hides B or W when they come close. */
  .handle.mid {
    top: 26px;
    border-color: var(--border);
  }
  .handle.mid::before {
    border-bottom-color: var(--fg-muted);
    border-width: 0 1px 22px;
    margin-left: -1px;
    border-style: solid;
    border-color: transparent transparent var(--fg-muted);
  }
  /* B and W close together: each tab leans away from the other, so both stay readable. */
  .handle.black.near {
    transform: translateX(-100%);
  }
  .handle.white.near {
    transform: none;
  }
  .handle.black.near::before {
    left: auto;
    right: 4px;
    margin-left: 0;
  }
  .handle.white.near::before {
    left: 4px;
    margin-left: 0;
  }
  .handle:hover,
  .handle.grabbing {
    background: var(--surface);
  }
  .panel {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-4);
    border-left: var(--border-w) solid var(--border);
    background: var(--bg);
    overflow: auto;
  }
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .levels,
  .stats {
    display: grid;
    grid-template-columns: auto 1fr;
    align-items: baseline;
    gap: 6px var(--space-4);
    margin: 0;
  }
  dt {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  dd {
    margin: 0;
    text-align: right;
    font-size: var(--text-xs);
  }
  dd.big {
    font-size: var(--text-xl);
    font-weight: var(--weight-medium);
  }
  dd small {
    margin-left: 6px;
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-regular);
  }
  .stats dt {
    font-family: var(--font-ui);
    font-size: var(--text-xs);
  }
  dd.sat {
    color: var(--fg);
  }
  .opts {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    padding-top: var(--space-2);
    border-top: var(--border-w) solid var(--border-soft);
  }
  .opts .lab-eyebrow {
    width: 100%;
  }
  .note {
    margin: auto 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-relaxed);
  }
</style>

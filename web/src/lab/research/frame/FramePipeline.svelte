<!--
  Demo 2: a live 2 Mpx frame at 1 fps, end to end.

  worker (synthesis + statistics), transferred to main (texSubImage2D R16UI +
  one draw), transferred back to the worker. The main thread only uploads and
  draws; everything O(n) runs in the worker. Measured per frame and shown.

  Also: LUT false colour (disabled in Night Red, spec D30), gestures as an
  attachment (wheel / pinch / drag / double-click / long-press / right-click),
  device-pixel-exact canvas sizing, Canvas 2D sparklines for the conditions.
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';
  import { env } from '../env.svelte';
  import { cssVar, rgb01 } from '../tokens';
  import type { FrameReply, FrameRequest } from './frame.worker';
  import { gestures } from './gestures';
  import { LabRenderer, midtonesFor, type Palette, type View } from './gl';
  import Sparkline from './Sparkline.svelte';

  interface Props {
    /** Frames per second (1 = the Seestar live cadence). */
    fps?: number;
  }
  let { fps = 1 }: Props = $props();

  const W = 1920;
  const H = 1080;
  const KEEP = 120;

  let host: HTMLDivElement;
  let canvas: HTMLCanvasElement;
  let renderer: LabRenderer | null = null;
  let worker: Worker | null = null;

  let failure = $state<string | null>(null);
  let live = $state(true);
  let palette = $state<Palette>('neutral');
  let seq = $state(0);
  let stats = $state.raw<FrameReply['stats'] | null>(null);
  let timing = $state({ synth: 0, stats: 0, upload: 0, draw: 0, synced: 0, roundtrip: 0 });
  let series = $state.raw({ sky: [] as number[], stars: [] as number[], hfd: [] as number[], main: [] as number[] });
  let zoomPct = $state(0);
  let menu = $state<{ x: number; y: number } | null>(null);
  let readout = $state<{ x: number; y: number; v: number } | null>(null);
  let dpcb = $state(false);
  let inFlight = false;
  let sentAt = 0;

  // Not reactive on purpose: drawing is imperative and coalesced per frame.
  let view: View = { scale: 1, cx: W / 2, cy: H / 2 };
  let fitted = $state(true);
  let current: FrameReply | null = null;
  let spare: ArrayBuffer | null = null;
  let raf = 0;

  const nightRed = $derived(env.theme === 'night-red');
  const effective = $derived<Palette>(nightRed ? 'neutral' : palette);

  function levels(): { black: number; white: number; mid: number } {
    const s = stats;
    if (!s) return { black: 0, white: 65535, mid: 0.5 };
    const madn = 1.4826 * s.mad;
    const black = Math.max(0, s.median - 2.8 * madn);
    const white = 65535;
    return { black, white, mid: midtonesFor((s.median - black) / (white - black), 0.1) };
  }

  function drawNow(): number {
    if (!renderer || !current) return 0;
    const tint: [number, number, number] = effective === 'neutral' ? rgb01(cssVar(host, '--viewer-tint')) : [1, 1, 1];
    return renderer.draw({ view, tint, ...levels() });
  }

  function schedule(): void {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      drawNow();
    });
  }

  function fit(): void {
    if (!canvas.width) return;
    const s = Math.min(canvas.width / W, canvas.height / H);
    view = { scale: s, cx: W / 2, cy: H / 2 };
    fitted = true;
    zoomPct = Math.round((s / (window.devicePixelRatio || 1)) * 100);
    schedule();
  }

  function zoomAt(factor: number, x: number, y: number): void {
    const dpr = window.devicePixelRatio || 1;
    const fitS = Math.min(canvas.width / W, canvas.height / H);
    const next = Math.min(16 * dpr, Math.max(fitS * 0.5, view.scale * factor));
    const sx = x * dpr - canvas.width / 2;
    const sy = y * dpr - canvas.height / 2;
    const px = view.cx + sx / view.scale;
    const py = view.cy + sy / view.scale;
    view = { scale: next, cx: px - sx / next, cy: py - sy / next };
    fitted = false;
    zoomPct = Math.round((next / dpr) * 100);
    schedule();
  }

  function pan(dx: number, dy: number): void {
    const dpr = window.devicePixelRatio || 1;
    view = { ...view, cx: view.cx - (dx * dpr) / view.scale, cy: view.cy - (dy * dpr) / view.scale };
    fitted = false;
    schedule();
  }

  function hover(x: number, y: number): void {
    if (!current || Number.isNaN(x)) {
      readout = null;
      return;
    }
    const dpr = window.devicePixelRatio || 1;
    const ix = Math.floor(view.cx + (x * dpr - canvas.width / 2) / view.scale);
    const iy = Math.floor(view.cy + (y * dpr - canvas.height / 2) / view.scale);
    if (ix < 0 || iy < 0 || ix >= W || iy >= H) {
      readout = null;
      return;
    }
    readout = { x: ix, y: iy, v: new Uint16Array(current.buffer)[iy * W + ix] };
  }

  function request(): void {
    if (!worker || inFlight) return;
    inFlight = true;
    sentAt = performance.now();
    const req: FrameRequest = { type: 'frame', width: W, height: H, recycle: spare };
    worker.postMessage(req, spare ? [spare] : []);
    spare = null;
  }

  function onFrame(r: FrameReply): void {
    inFlight = false;
    const t0 = performance.now();
    if (!renderer) return;
    const upload = renderer.upload(new Uint16Array(r.buffer), r.width, r.height);
    if (current) spare = current.buffer; // the frame on screen goes back next time
    current = r;
    stats = r.stats;
    const draw = drawNow();
    // The calls above return before the GPU has copied anything: force the
    // pipeline once (1-px readPixels) to measure upload + draw for real.
    const synced = renderer.sync() + upload + draw;
    seq = r.seq;
    const push = (a: number[], v: number) => (a.length >= KEEP ? [...a.slice(1), v] : [...a, v]);
    const main = performance.now() - t0;
    series = {
      sky: push(series.sky, r.stats.median),
      stars: push(series.stars, r.stats.stars),
      hfd: push(series.hfd, r.stats.hfd),
      main: push(series.main, main),
    };
    timing = { synth: r.timings.synth, stats: r.timings.stats, upload, draw, synced, roundtrip: performance.now() - sentAt };
  }

  $effect(() => {
    try {
      renderer = new LabRenderer(canvas);
    } catch (e) {
      failure = e instanceof Error ? e.message : String(e);
      return;
    }
    worker = new Worker(new URL('./frame.worker.ts', import.meta.url), { type: 'module' });
    worker.onmessage = (e: MessageEvent<FrameReply>) => onFrame(e.data);
    worker.onerror = (e) => (failure = `worker: ${e.message}`);

    const ro = new ResizeObserver((entries) => {
      const e = entries[entries.length - 1];
      const box = e.devicePixelContentBoxSize?.[0];
      dpcb = !!box;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = box ? box.inlineSize : Math.round(e.contentRect.width * dpr);
      canvas.height = box ? box.blockSize : Math.round(e.contentRect.height * dpr);
      if (fitted) fit();
      else schedule();
    });
    try {
      ro.observe(canvas, { box: 'device-pixel-content-box' });
    } catch {
      ro.observe(canvas);
    }
    request();
    return () => {
      ro.disconnect();
      worker?.terminate();
      worker = null;
      renderer?.dispose();
      renderer = null;
      cancelAnimationFrame(raf);
    };
  });

  // Cadence: one request per period while live (never queue: a slow frame is skipped, not stacked).
  $effect(() => {
    if (!live) return;
    const id = setInterval(request, 1000 / fps);
    return () => clearInterval(id);
  });

  // Palette, theme: redraw (the LUT texture changes, the frame does not).
  $effect(() => {
    void env.theme;
    const p = effective;
    renderer?.setPalette(p);
    schedule();
  });

  function key(e: KeyboardEvent): void {
    const r = canvas.getBoundingClientRect();
    const cx = r.width / 2;
    const cy = r.height / 2;
    if (e.key === '+' || e.key === '=') zoomAt(1.25, cx, cy);
    else if (e.key === '-') zoomAt(0.8, cx, cy);
    else if (e.key === 'f' || e.key === 'F') fit();
    else if (e.key === '1') zoomAt(((window.devicePixelRatio || 1) * 1) / view.scale, cx, cy);
    else if (e.key === 'ArrowLeft') pan(40, 0);
    else if (e.key === 'ArrowRight') pan(-40, 0);
    else if (e.key === 'ArrowUp') pan(0, 40);
    else if (e.key === 'ArrowDown') pan(0, -40);
    else if (e.key === 'Escape') menu = null;
    else return;
    e.preventDefault();
  }

  const fmt = (v: number, d = 1) => (Number.isFinite(v) ? v.toFixed(d) : '—');
  const histMarks = $derived.by(() => {
    const s = stats;
    if (!s) return [];
    const l = levels();
    return [(l.black - s.histLo) / (s.histHi - s.histLo)];
  });
  const PALETTES: { id: Palette; label: string }[] = [
    { id: 'neutral', label: 'Neutral' },
    { id: 'negative', label: 'Negative' },
    { id: 'fire', label: 'Fire' },
    { id: 'ice', label: 'Ice' },
  ];
</script>

<div class="pipeline">
  <div class="viewer" bind:this={host}>
    <canvas
      bind:this={canvas}
      tabindex="0"
      aria-label="Synthetic live frame. Wheel or pinch to zoom, drag to pan, double-click to fit, F fit, 1 actual pixels."
      onkeydown={key}
      {@attach gestures({ zoom: zoomAt, pan, fit, hover, menu: (x, y) => (menu = { x, y }) })}
    ></canvas>
    {#if failure}
      <p class="failure">{failure}</p>
    {/if}
    <div class="hud top">
      <span class="lab-chip"><span class="lab-dot {live ? 'accent' : ''}"></span><b>{live ? 'LIVE' : 'PAUSED'}</b></span>
      <span class="lab-chip">#<b>{seq}</b></span>
      <span class="lab-chip"><b>10.0</b> s</span>
      <span class="lab-chip"><b>1920×1080</b> u16 · synthetic</span>
    </div>
    <div class="hud bottom">
      <span class="lab-chip">{fitted ? 'Fit' : 'Zoom'} <b>{zoomPct} %</b></span>
      {#if readout}
        <span class="lab-chip">X <b>{readout.x}</b> Y <b>{readout.y}</b> <b>{readout.v}</b> ADU</span>
      {/if}
      <span class="lab-chip hint">wheel / pinch zoom · drag pan · double-click fit · right-click / long-press menu</span>
    </div>
    {#if menu}
      <div class="menu" role="menu" style:left="{menu.x}px" style:top="{menu.y}px">
        <button role="menuitem" onclick={() => { zoomAt((window.devicePixelRatio || 1) / view.scale, menu!.x, menu!.y); menu = null; }}>
          <Icon name="zoom-1to1" size={16} /> Actual pixels here
        </button>
        <button role="menuitem" onclick={() => { fit(); menu = null; }}><Icon name="zoom-fit" size={16} /> Fit</button>
        <button role="menuitem" onclick={() => (menu = null)}><Icon name="target-star" size={16} /> Set as target</button>
      </div>
    {/if}
  </div>

  <aside class="side">
    <section class="card">
      <header>
        <p class="lab-eyebrow">Per frame · this engine</p>
        <button class="lab-btn ghost" aria-pressed={live} aria-label={live ? 'Pause live frames' : 'Resume live frames'} onclick={() => (live = !live)}>
          <Icon name={live ? 'pause' : 'live'} size={16} />
        </button>
      </header>
      <table class="times num">
        <tbody>
          <tr><th>Worker · synthesis</th><td>{fmt(timing.synth)} ms</td></tr>
          <tr><th>Worker · statistics</th><td>{fmt(timing.stats)} ms</td></tr>
          <tr><th>Main · texSubImage2D</th><td>{fmt(timing.upload, 2)} ms</td></tr>
          <tr><th>Main · draw call</th><td>{fmt(timing.draw, 2)} ms</td></tr>
          <tr><th>GPU · upload + draw, synced</th><td>{fmt(timing.synced, 2)} ms</td></tr>
          <tr><th>Request → on screen</th><td>{fmt(timing.roundtrip)} ms</td></tr>
        </tbody>
      </table>
      <div class="spark-row">
        <span class="lab-eyebrow">Main thread</span>
        <Sparkline values={series.main} label="Main-thread time per frame, last 120 frames" />
        <span class="num val">{fmt(series.main.at(-1) ?? NaN, 2)} ms</span>
      </div>
      <ul class="lab-facts">
        <li class="yes">transfer: zero-copy ping-pong</li>
        <li class={dpcb ? 'yes' : 'no'}>device-pixel box: {dpcb ? 'exact' : 'rounded (fallback)'}</li>
      </ul>
    </section>

    <section class="card">
      <header><p class="lab-eyebrow">Frame statistics</p></header>
      {#if stats}
        <dl class="kv num">
          <div><dt>Min</dt><dd>{stats.min}</dd></div>
          <div><dt>Median</dt><dd>{fmt(stats.median)}</dd></div>
          <div><dt>MAD</dt><dd>{fmt(stats.mad)}</dd></div>
          <div><dt>Max</dt><dd>{stats.max}</dd></div>
          <div><dt>Stars</dt><dd>{stats.stars}</dd></div>
          <div><dt>HFD</dt><dd>{fmt(stats.hfd, 2)} px</dd></div>
        </dl>
        <Sparkline kind="bars" values={stats.hist} marks={histMarks} height={34} label="Histogram of the frame, log counts, black level marked" />
      {:else}
        <p class="muted">Waiting for the first frame…</p>
      {/if}
    </section>

    <section class="card">
      <header><p class="lab-eyebrow">Conditions · last {KEEP} frames</p></header>
      <div class="spark-row">
        <span class="name">Sky</span>
        <Sparkline values={series.sky} label="Sky background median" />
        <span class="num val">{fmt(series.sky.at(-1) ?? NaN)} ADU</span>
      </div>
      <div class="spark-row">
        <span class="name">Stars</span>
        <Sparkline values={series.stars} label="Detected stars" />
        <span class="num val">{series.stars.at(-1) ?? '—'}</span>
      </div>
      <div class="spark-row">
        <span class="name">HFD</span>
        <Sparkline values={series.hfd} label="Half-flux diameter" />
        <span class="num val">{fmt(series.hfd.at(-1) ?? NaN, 2)} px</span>
      </div>
    </section>

    <section class="card">
      <header><p class="lab-eyebrow">Palette (LUT texture)</p></header>
      <div class="lab-seg" role="radiogroup" aria-label="Palette">
        {#each PALETTES as p (p.id)}
          <button
            role="radio"
            data-shot="palette-{p.id}"
            aria-checked={effective === p.id}
            aria-disabled={nightRed && p.id !== 'neutral'}
            aria-describedby={nightRed && p.id !== 'neutral' ? 'lab-palette-reason' : undefined}
            onclick={() => {
              if (!(nightRed && p.id !== 'neutral')) palette = p.id;
            }}>{p.label}</button
          >
        {/each}
      </div>
      {#if !nightRed && (effective === 'fire' || effective === 'ice')}
        <p class="muted">OKLCH ramp: lightness equals the stretched value, hue only adds separation.</p>
      {/if}
      {#if nightRed}
        <p class="muted" id="lab-palette-reason">False colour is off in Night Red: neutral × <span class="num">--viewer-tint</span> only.</p>
      {/if}
    </section>
  </aside>
</div>

<style>
  .pipeline {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 340px;
    height: 100%;
    min-height: 0;
    border-top: var(--border-w) solid var(--border);
  }

  .viewer {
    position: relative;
    min-width: 0;
    min-height: 0;
    background: var(--viewer-bg);
  }
  canvas {
    display: block;
    width: 100%;
    height: 100%;
    touch-action: none;
    cursor: grab;
  }
  canvas:active {
    cursor: grabbing;
  }
  canvas:focus-visible {
    outline-offset: -2px;
  }

  .hud {
    position: absolute;
    left: var(--space-3);
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    pointer-events: none;
  }
  .hud.top {
    top: var(--space-3);
  }
  .hud.bottom {
    bottom: var(--space-3);
    right: var(--space-3);
  }
  .hud .hint {
    margin-left: auto;
  }

  .failure {
    position: absolute;
    inset: 40% 20% auto;
    color: var(--fg);
    text-align: center;
  }

  .menu {
    position: absolute;
    z-index: var(--z-popover);
    display: flex;
    flex-direction: column;
    min-width: 200px;
    padding: var(--space-1) 0;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg);
    box-shadow: var(--shadow-2);
  }
  .menu button {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: 28px;
    padding: 0 var(--space-4);
    border: 0;
    background: none;
    color: var(--fg);
    text-align: left;
    cursor: pointer;
  }
  .menu button:hover {
    background: var(--hover-bg);
  }
  .menu :global(.icon) {
    color: var(--fg-muted);
  }

  .side {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-height: 0;
    padding: var(--space-3);
    overflow: auto;
    border-left: var(--border-w) solid var(--border);
    background: var(--bg);
  }
  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-4);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
  }
  .card header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 20px;
    margin: -4px 0;
  }

  .times {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-s);
  }
  .times th {
    padding: 2px 0;
    color: var(--text-muted);
    font-family: var(--font-ui);
    font-weight: var(--weight-regular);
    text-align: left;
  }
  .times td {
    padding: 2px 0;
    text-align: right;
    color: var(--fg);
  }

  .kv {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--space-2) var(--space-4);
    margin: 0;
  }
  .kv div {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .kv dt {
    color: var(--text-muted);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .kv dd {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
  }

  .spark-row {
    display: grid;
    grid-template-columns: 76px minmax(0, 1fr) 76px;
    align-items: center;
    gap: var(--space-3);
  }
  .spark-row .name {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .spark-row .val {
    color: var(--fg);
    font-size: var(--text-s);
    text-align: right;
  }

  .muted {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }

  .lab-seg {
    align-self: start;
  }
  .lab-seg button[aria-disabled='true'] {
    color: var(--fg-disabled);
    cursor: not-allowed;
  }
</style>

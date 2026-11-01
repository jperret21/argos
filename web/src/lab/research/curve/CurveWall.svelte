<!--
  Demo 1: live light curve, three facets (target, check, conditions) on one
  linked time axis (spec R1 plot wall, D25, D26).

  - uPlot with a scale direction of -1 for magnitudes (brighter up), shape-
    coded markers and error bars from a plugin (curve/plugins.ts).
  - cursor.sync: one crosshair across facets; linkX: a drag-zoom on any
    facet zooms all; double-click or F fits all.
  - Live append: the columns are typed arrays outside Svelte's reactive graph
    (no deep proxy on thousands of numbers); setData(data, resetScales =
    !manualZoom) so new data never resets a manual zoom (spec 3.13).
  - Every draw is timed (setData -> last facet's draw hook) and shown.
  - Check facet: a native uPlot band (bands: [{ series: [hi, lo] }]) of the
    trailing 15-point mean ± 1 sigma, i.e. the photometric scatter now; it
    widens in a cloud passage. Trailing, so the band already drawn never
    changes when a point arrives.
  - Conditions facet: a quality threshold drawn by a plugin (dashed line,
    rings and an x-axis rug on every frame at or above it) and moved by an
    HTML handle (pointer capture + keyboard slider, curve/handle.ts).
-->
<script lang="ts">
  import uPlot from 'uplot';
  import { untrack } from 'svelte';
  import Icon from '../../../lib/components/Icon.svelte';
  import { env } from '../env.svelte';
  import { appendPoint, curvePoint, emptyColumns, prng, unixToJd, type CurveColumns } from '../synth';
  import { chartPalette, withAlpha, type ChartPalette } from '../tokens';
  import { valueHandle } from './handle';
  import { emptyBand, extendBand, type BandColumns } from './band';
  import { linkX, markers, shapeSvgPath, thresholdMarks, type Shape } from './plugins';

  type Axis = 'utc' | 'jd';
  type FacetId = 'target' | 'check' | 'hfd';
  interface Facet {
    id: FacetId;
    title: string;
    sub: string;
    shape: Shape | null;
    share: number;
    token: string;
  }

  const FACETS: Facet[] = [
    { id: 'target', title: 'Target', sub: 'SW And (synthetic RRab) · V mag', shape: 'circle', share: 0.48, token: '--chart-1' },
    { id: 'check', title: 'Check', sub: '000-BCX-329 · V mag', shape: 'triangle', share: 0.3, token: '--chart-3' },
    { id: 'hfd', title: 'Conditions', sub: 'HFD · px', shape: null, share: 0.22, token: '--fg-muted' },
  ];
  const JD0 = 2461346;
  const HEADER_H = 26;
  const TITLE_H = 24; // the axis title line under the wall
  const BAND_W = 15; // trailing window of the check-star band, points

  let wall: HTMLDivElement;
  const hosts: Record<FacetId, HTMLDivElement | undefined> = { target: undefined, check: undefined, hfd: undefined };
  const plots = new Map<FacetId, uPlot>();
  const group = new Set<uPlot>();

  // Big data: plain typed arrays, not $state (see the header comment).
  let cols: CurveColumns = emptyColumns(1024);
  let jdCache: { n: number; xs: Float64Array } = { n: -1, xs: new Float64Array(0) };
  let rand = prng(5);
  let next = 0;
  let pal: ChartPalette | null = null;
  let pendingAt = 0;
  let suspended = false;
  let band: BandColumns = emptyBand(1024);
  let cadence = 60; // s between frames of the loaded night; live points continue it

  let count = $state(0);
  let live = $state(true);
  let errors = $state(true);
  let axis = $state<Axis>('utc');
  let manualZoom = $state(false);
  let drawMs = $state(0);
  let hoverIdx = $state<number | null>(null);
  let size = $state({ w: 0, h: 0 });
  // HFD quality threshold (px), its line position and the frames at or above it.
  let threshold = $state(2.6);
  let handle = $state<{ y: number; x: number } | null>(null);
  let flagged = $state(0);
  let handleDragging = $state(false);

  function xs(): Float64Array {
    const n = cols.length;
    if (axis === 'utc') return cols.t.subarray(0, n);
    if (jdCache.n !== n) {
      const out = new Float64Array(n);
      for (let i = 0; i < n; i++) out[i] = unixToJd(cols.t[i]) - JD0;
      jdCache = { n, xs: out };
    }
    return jdCache.xs;
  }

  function dataFor(id: FacetId): uPlot.AlignedData {
    const n = cols.length;
    if (id === 'check') {
      band = extendBand(band, cols.check, n, BAND_W);
      return [xs(), cols.check.subarray(0, n), band.hi.subarray(0, n), band.lo.subarray(0, n), band.mean.subarray(0, n)];
    }
    const y = id === 'target' ? cols.target : cols.hfd;
    return [xs(), y.subarray(0, n)];
  }

  /** Cursor ring on the measured series only, not on the band edges or the mean. */
  function cursorPoint(_u: uPlot, si: number): HTMLElement | undefined {
    if (si !== 1) return undefined;
    const el = document.createElement('div');
    el.style.cssText = 'width:11px;height:11px;margin:-5.5px 0 0 -5.5px;border-width:1.5px';
    return el;
  }

  function errFor(id: FacetId): ArrayLike<number> | null {
    if (id === 'target') return cols.targetErr;
    if (id === 'check') return cols.checkErr;
    return null;
  }

  function colorFor(f: Facet): string {
    const p = pal!;
    return f.id === 'target' ? p.target : f.id === 'check' ? p.check : p.fgMuted;
  }

  function heightFor(f: Facet): number {
    const avail = Math.max(240, size.h - FACETS.length * HEADER_H - TITLE_H);
    return Math.max(90, Math.floor(avail * f.share));
  }

  function options(f: Facet, last: boolean): uPlot.Options {
    const p = pal!;
    const font = `400 10px ${p.mono}`;
    const magnitude = f.id !== 'hfd';
    const timeAxis: uPlot.Axis = {
      stroke: p.text,
      font,
      size: last ? 26 : 4,
      gap: 3,
      space: 72,
      ticks: { stroke: p.axis, width: 1, size: last ? 3 : 0 },
      grid: { stroke: p.grid, width: 1 },
      border: { show: true, stroke: p.axis, width: 1 },
      values: last
        ? axis === 'utc'
          ? '{HH}:{mm}'
          : (_u, splits) => splits.map((v) => v.toFixed(3))
        : (_u, splits) => splits.map(() => ''),
    };
    return {
      width: Math.max(200, size.w),
      height: heightFor(f),
      padding: [10, 14, last ? 0 : 4, 0],
      legend: { show: false },
      tzDate: (ts) => uPlot.tzDate(new Date(ts * 1e3), 'Etc/UTC'),
      cursor: {
        sync: { key: 'lab-lightcurve', setSeries: false },
        points: {
          show: cursorPoint as unknown as boolean,
          size: 11,
          width: 1.5,
          stroke: () => pal!.highlight,
          fill: () => 'rgba(0, 0, 0, 0)',
        },
        drag: { x: true, y: false, setScale: true },
        bind: {
          dblclick: () => () => {
            fitAll();
            return null;
          },
        },
      },
      scales: {
        x: { time: axis === 'utc' },
        y: {
          dir: magnitude ? -1 : 1,
          range: (_u, min, max) => {
            // The HFD threshold is a reference the observer set: always in view.
            if (!magnitude) {
              min = Math.min(min, threshold);
              max = Math.max(max, threshold);
            }
            const span = Math.max(magnitude ? 0.06 : 0.4, max - min);
            const pad = span * 0.08;
            return [min - pad, max + pad];
          },
        },
      },
      axes: [
        timeAxis,
        {
          stroke: p.text,
          font,
          size: 46,
          gap: 4,
          space: 28,
          ticks: { show: false },
          grid: { stroke: p.grid, width: 1 },
          values: (_u, splits) => splits.map((v) => (magnitude ? v.toFixed(2) : v.toFixed(1))),
        },
      ],
      series: [
        {},
        f.shape
          ? { stroke: colorFor(f), paths: () => null, points: { show: false } }
          : { stroke: colorFor(f), width: 1.25, points: { show: false } },
        ...(f.id === 'check'
          ? [
              { stroke: withAlpha(p.check, 0.35), width: 1, points: { show: false } },
              { stroke: withAlpha(p.check, 0.35), width: 1, points: { show: false } },
              { stroke: p.reference, width: 1, dash: [3, 3], points: { show: false } },
            ]
          : []),
      ],
      bands: f.id === 'check' ? [{ series: [2, 3], fill: () => withAlpha(pal!.check, 0.14) }] : [],
      plugins: [
        ...(f.id === 'hfd'
          ? [
              thresholdMarks({
                value: () => threshold,
                line: () => pal!.reference,
                mark: () => pal!.warning,
                onDraw: (u, y, count) => {
                  const dpr = uPlot.pxRatio;
                  const inside = y >= u.bbox.top / dpr - 1 && y <= (u.bbox.top + u.bbox.height) / dpr + 1;
                  handle = inside ? { y, x: (u.bbox.left + u.bbox.width) / dpr } : null;
                  if (count !== flagged) flagged = count;
                },
              }),
            ]
          : []),
        ...(f.shape
          ? [
              markers({
                shape: f.shape,
                color: () => colorFor(f),
                errorAlpha: () => pal!.errorAlpha,
                errors: () => errFor(f.id),
                showErrors: () => errors,
                latest: () => pal!.highlight,
              }),
            ]
          : []),
        linkX(group, (z) => {
          if (!suspended) manualZoom = z;
        }),
      ],
      hooks: {
        setCursor: [(u) => (hoverIdx = u.cursor.idx ?? null)],
        draw: [
          () => {
            if (pendingAt) drawMs = performance.now() - pendingAt;
          },
        ],
      },
    };
  }

  function build(): void {
    for (const u of plots.values()) u.destroy();
    plots.clear();
    group.clear();
    if (size.w <= 0) return;
    pal = chartPalette(wall);
    FACETS.forEach((f, i) => {
      const host = hosts[f.id];
      if (!host) return;
      const u = new uPlot(options(f, i === FACETS.length - 1), dataFor(f.id), host);
      plots.set(f.id, u);
      group.add(u);
    });
  }

  function push(reset: boolean): void {
    pendingAt = performance.now();
    suspended = true;
    for (const [id, u] of plots) u.setData(dataFor(id), reset);
    suspended = false;
    count = cols.length;
  }

  function fitAll(): void {
    manualZoom = false;
    push(true);
  }

  function load(n: number, step: number): void {
    cadence = step;
    rand = prng(5);
    cols = emptyColumns(Math.max(1024, n));
    for (let i = 0; i < n; i++) cols = appendPoint(cols, curvePoint(i, rand, step));
    next = n;
    manualZoom = false;
    push(true);
  }

  function tick(): void {
    cols = appendPoint(cols, curvePoint(next++, rand, cadence));
    push(!manualZoom);
  }

  // First data: the first 3 h of the night at the 1-min cadence.
  load(180, 60);

  $effect(() => {
    const ro = new ResizeObserver((e) => {
      const r = e[e.length - 1].contentRect;
      size = { w: Math.floor(r.width), h: Math.floor(r.height) };
    });
    ro.observe(wall);
    return () => {
      ro.disconnect();
      for (const u of plots.values()) u.destroy();
      plots.clear();
    };
  });

  // Rebuild on theme and axis (colours and scale type live in the options),
  // and once the first size is known. Never on a resize: that is setSize.
  const ready = $derived(size.w > 0);
  $effect(() => {
    void env.theme;
    void axis;
    if (ready) untrack(build);
  });

  // Resize in place.
  $effect(() => {
    const { w } = size;
    void size.h;
    for (const f of FACETS) plots.get(f.id)?.setSize({ width: Math.max(200, w), height: heightFor(f) });
  });

  // Error bars on / off: a redraw, not a rebuild.
  $effect(() => {
    void errors;
    for (const u of plots.values()) u.redraw(false, false);
  });

  // Threshold moved: redraw the conditions facet only (no rescale).
  $effect(() => {
    void threshold;
    plots.get('hfd')?.redraw(false, false);
  });

  function hfdToValue(clientY: number): number | null {
    const u = plots.get('hfd');
    if (!u) return null;
    return u.posToVal(clientY - u.over.getBoundingClientRect().top, 'y');
  }
  const hfdMin = () => plots.get('hfd')?.scales.y.min ?? 1;
  const hfdMax = () => plots.get('hfd')?.scales.y.max ?? 5;

  // Screenshot / test hooks (lab only).
  $effect(() => {
    const w = window as unknown as { __lab?: Record<string, unknown> };
    w.__lab = {
      ...w.__lab,
      zoomCurve: () => {
        const u = plots.get('target');
        const x = xs();
        if (!u || x.length < 140) return;
        manualZoom = true;
        u.setScale('x', { min: x[60], max: x[130] });
      },
      setThreshold: (v: number) => (threshold = v),
    };
    return () => {
      if (w.__lab) {
        delete w.__lab.zoomCurve;
        delete w.__lab.setThreshold;
      }
    };
  });

  $effect(() => {
    if (!live) return;
    const id = setInterval(tick, 500);
    return () => clearInterval(id);
  });

  function onKey(e: KeyboardEvent): void {
    if ((e.target as HTMLElement).closest('input, textarea')) return;
    if (e.key === 'f' || e.key === 'F') fitAll();
    else if (e.key === 'u' || e.key === 'U') errors = !errors;
    else return;
    e.preventDefault();
  }

  const MINUS = '−';
  function utc(t: number): string {
    const d = new Date(t * 1000);
    return `${d.toISOString().slice(11, 19)} UTC`;
  }
  const readout = $derived.by(() => {
    void count;
    const i = hoverIdx ?? count - 1;
    if (i < 0 || i >= cols.length) return null;
    return {
      hovered: hoverIdx !== null,
      t: utc(cols.t[i]),
      jd: unixToJd(cols.t[i]).toFixed(5),
      target: `${cols.target[i].toFixed(3)} ± ${cols.targetErr[i].toFixed(3)}`,
      check: `${cols.check[i].toFixed(3)} ± ${cols.checkErr[i].toFixed(3)}`,
      sigma: i < band.n && i >= 2 ? (band.hi[i] - band.mean[i]).toFixed(4) : '—',
      hfd: `${cols.hfd[i].toFixed(2)} px`,
    };
  });
  const fmtInt = new Intl.NumberFormat('en-GB');
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div class="curve" role="region" aria-label="Live light curve" onkeydown={onKey}>
  <div class="toolbar">
    <button class="lab-btn ghost" aria-pressed={live} aria-label={live ? 'Pause live points' : 'Resume live points'} onclick={() => (live = !live)}>
      <Icon name={live ? 'pause' : 'live'} size={16} />
    </button>
    <button class="lab-btn ghost" aria-pressed={errors} aria-label="Error bars (U)" aria-keyshortcuts="U" onclick={() => (errors = !errors)}>
      <Icon name="error-bars" size={16} />
    </button>
    <button class="lab-btn ghost" aria-label="Fit all plots (F)" aria-keyshortcuts="F" onclick={fitAll}>
      <Icon name="zoom-fit" size={16} />
    </button>
    <span class="sep"></span>
    <div class="lab-seg" role="radiogroup" aria-label="Time axis">
      <button role="radio" aria-checked={axis === 'utc'} onclick={() => (axis = 'utc')}>UTC</button>
      <button role="radio" aria-checked={axis === 'jd'} onclick={() => (axis = 'jd')}>JD</button>
    </div>
    <span class="sep"></span>
    <button class="lab-btn" data-shot="load-night" onclick={() => load(3600, 10)}>Night · 3 600 pts</button>
    <button class="lab-btn" data-shot="load-season" onclick={() => load(50000, 10)}>Season · 50 000 pts</button>
    <span class="grow"></span>
    {#if manualZoom}
      <span class="lab-chip"><span class="lab-dot accent"></span>Manual zoom kept · <b>F</b> fits</span>
    {/if}
    <span class="lab-chip"><b>{fmtInt.format(count)}</b> pts × 3 facets</span>
    <span class="lab-chip">last update <b>{drawMs.toFixed(1)}</b> ms</span>
  </div>

  <div class="wall" bind:this={wall}>
    {#each FACETS as f (f.id)}
      <section class="facet" aria-label="{f.title}: {f.sub}">
        <header style:height="{HEADER_H}px">
          {#if f.shape}
            <svg class="glyph" viewBox="0 0 20 20" aria-hidden="true" style:fill="var({f.token})">
              <path d={shapeSvgPath(f.shape)} />
            </svg>
          {:else}
            <svg class="glyph" viewBox="0 0 20 20" aria-hidden="true">
              <path d="M3 13l4-5 4 3 6-6" fill="none" stroke="var(--fg-muted)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          {/if}
          <h3>{f.title}</h3>
          <span class="sub">{f.sub}</span>
          <span class="grow"></span>
          {#if readout}
            <span class="readout num" class:hovered={readout.hovered}>
              {#if f.id === 'target'}{readout.t} · JD {readout.jd} · <b>{readout.target}</b>
              {:else if f.id === 'check'}σ<sub>{BAND_W}</sub> {readout.sigma} · <b>{readout.check}</b>
              {:else}<b>{readout.hfd}</b>{/if}
            </span>
          {/if}
          {#if f.id === 'check'}
            <span class="key" aria-hidden="true"><i class="swatch band"></i>mean ± 1σ, last {BAND_W} pts</span>
          {/if}
          {#if f.id === 'hfd'}
            <span class="lab-chip flag" class:on={flagged > 0}>
              <span class="lab-dot {flagged > 0 ? 'busy' : 'ok'}"></span><b>{fmtInt.format(flagged)}</b> frames ≥ {threshold.toFixed(2)} px
            </span>
          {/if}
        </header>
        <div class="plot-wrap">
          <div class="plot" bind:this={hosts[f.id]}></div>
          {#if f.id === 'hfd' && handle}
            <div
              class="thr"
              class:dragging={handleDragging}
              style:top="{handle.y}px"
              style:left="{handle.x}px"
              role="slider"
              tabindex="0"
              aria-label="HFD quality threshold"
              aria-orientation="vertical"
              aria-valuemin={Number(hfdMin().toFixed(2))}
              aria-valuemax={Number(hfdMax().toFixed(2))}
              aria-valuenow={Number(threshold.toFixed(2))}
              aria-valuetext="{threshold.toFixed(2)} px"
              {@attach valueHandle({
                toValue: hfdToValue,
                get: () => threshold,
                set: (v) => (threshold = Math.round(v * 100) / 100),
                step: 0.05,
                min: hfdMin,
                max: hfdMax,
                ondrag: (a) => (handleDragging = a),
              })}
            >
              <span class="num">{threshold.toFixed(2)}</span>
            </div>
          {/if}
        </div>
      </section>
    {/each}
    <p class="axis-title num">
      {axis === 'utc' ? 'UTC · night of 2026-11-01' : `JD ${MINUS} ${JD0}`} · BJD<sub>TDB</sub> is computed by the server (barycentric correction)
    </p>
  </div>
</div>

<style>
  .curve {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    border-top: var(--border-w) solid var(--border);
  }

  .toolbar {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    height: 40px;
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border);
    flex: none;
  }
  .toolbar .sep {
    width: 1px;
    height: 18px;
    margin: 0 var(--space-2);
    background: var(--border-soft);
  }
  .grow {
    flex: 1;
  }
  .toolbar .lab-chip + .lab-chip {
    margin-left: var(--space-1);
  }

  .wall {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: var(--space-2) var(--space-4) 0;
    background: var(--chart-surface);
    overflow: hidden;
  }

  .facet header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding-left: 46px;
  }
  .glyph {
    width: 14px;
    height: 14px;
    flex: none;
  }
  h3 {
    margin: 0;
    font-size: var(--text-s);
    font-weight: var(--weight-semibold);
    color: var(--fg);
  }
  .sub {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
  .readout {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .readout b {
    color: var(--fg);
    font-weight: var(--weight-regular);
  }
  .readout.hovered b {
    color: var(--chart-highlight);
  }

  .key {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    margin-left: var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .swatch.band {
    display: inline-block;
    width: 14px;
    height: 8px;
    background: color-mix(in srgb, var(--chart-3) 22%, transparent);
    border-top: 1px solid color-mix(in srgb, var(--chart-3) 45%, transparent);
    border-bottom: 1px solid color-mix(in srgb, var(--chart-3) 45%, transparent);
  }
  .flag {
    margin-left: var(--space-3);
  }
  sub {
    font-size: 0.75em;
  }

  .plot-wrap {
    position: relative;
  }
  /* The threshold handle: a brass tab on the right end of the line (a
     deliberate control), 14 px tall hit area, value in mono. */
  .thr {
    position: absolute;
    z-index: 2;
    display: flex;
    align-items: center;
    height: 16px;
    padding: 0 5px 0 4px;
    transform: translate(-100%, -50%);
    border: 1px solid var(--accent);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-2xs);
    cursor: ns-resize;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
  }
  .thr::before {
    content: '';
    position: absolute;
    right: 100%;
    top: 50%;
    width: 0;
    height: 0;
    margin-top: -4px;
    border: 4px solid transparent;
    border-right-color: var(--accent);
    border-left: 0;
  }
  .thr.dragging,
  .thr:hover {
    background: var(--surface);
  }

  .plot :global(.u-cursor-x) {
    border-right: 1px solid var(--chart-highlight) !important;
  }
  .plot :global(.u-cursor-y) {
    display: none;
  }
  .plot :global(.u-select) {
    background: color-mix(in srgb, var(--accent) 14%, transparent);
    border-left: 1px solid var(--accent);
    border-right: 1px solid var(--accent);
  }
  .plot :global(.uplot) {
    font-family: var(--font-mono);
  }

  .axis-title {
    margin: 2px 0 var(--space-2) 46px;
    color: var(--text-muted);
    font-size: var(--text-2xs);
    letter-spacing: 0.02em;
  }
</style>

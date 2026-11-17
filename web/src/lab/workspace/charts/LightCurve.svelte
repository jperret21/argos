<!--
  Live light curve: target and check as TWO FACETS on one time axis (they
  differ by magnitudes: one y axis would flatten both; BRAND 10, D25 refined
  by functional-spaces 4.6).

  - Target facet: magnitude, inverted (brighter up), error bars, the newest
    point ringed (static: data is marked, never animated).
  - Check facet: difference from its own median, with its trailing 15-point
    mean ± 1 sigma as a quiet envelope (research T3): the photometry's
    stability at a glance; it widens when the data degrades.
  - The x axis is the PLANNED run window (start to the end estimated from the
    observed cadence): the curve grows into the time still to come, and a
    dashed line marks now.
  - A rule that fired (HFD rise) hatches its period on both facets and labels
    its start, so the noisier stretch is explained where it is seen.
  - Drag on either facet zooms both (linked x); a manual zoom survives new
    points (spec 3.13); double-click or F fits the run window again.
  - Hover: one crosshair on both facets, the readout in the header in mono
    (UTC, JD, value ± error, frame number). Legend in the header, never over
    the data.
-->
<script lang="ts">
  import uPlot from 'uplot';
  import { onMount, untrack } from 'svelte';
  import { emptyBand, extendBand, type BandColumns } from '../../research/curve/band';
  import { linkX } from '../../research/curve/plugins';
  import { withAlpha } from '../../research/tokens';
  import { env } from '../model/env.svelte';
  import { fixed, jd, mag, signed, utc } from '../model/format';
  import { median, type FrameRecord } from '../model/night';
  import { chartPalette, xAxis, yAxis, padRange, type ChartPalette } from './axes';
  import { envelope, periods, roleMarkers, shapePath } from './plugins';

  interface Props {
    records: readonly FrameRecord[];
    start: number;
    end: number;
    now?: number | null;
    /** Rule start lines, e.g. { x: t, label: 'HFD rule · 22:16' }. */
    events?: readonly { x: number; label: string }[];
    /** Hatched periods (a rule still true). */
    flagged?: readonly [number, number][];
    variant?: 'band' | 'drawer' | 'watch';
    targetName?: string;
    checkName?: string | null;
    errors?: boolean;
    header?: boolean;
  }

  let {
    records,
    start,
    end,
    now = null,
    events = [],
    flagged = [],
    variant = 'band',
    targetName = 'Target',
    checkName = 'Check',
    errors = true,
    header = true,
  }: Props = $props();

  const watch = $derived(variant === 'watch');
  const SYNC = `lc-${Math.random().toString(36).slice(2, 8)}`;

  let tHost: HTMLDivElement;
  let cHost: HTMLDivElement | undefined = $state();
  let tPlot: uPlot | null = null;
  let cPlot: uPlot | null = null;
  const group = new Set<uPlot>();
  let pal: ChartPalette | null = null;

  // Columns: plain typed arrays, outside the reactive graph (research T1).
  let xs = new Float64Array(0);
  let tgt = new Float64Array(0);
  let tErr = new Float64Array(0);
  let chk = new Float64Array(0);
  let cErr = new Float64Array(0);
  let band: BandColumns = $state.raw(emptyBand(256));
  let checkMedian = $state(0);

  let zoomed = $state(false);
  let hover = $state<number | null>(null);
  let sizes = $state({ tw: 0, th: 0, cw: 0, ch: 0 });

  const n = $derived(records.length);
  const last = $derived(n ? records[n - 1] : null);
  const hasCheck = $derived(checkName !== null);
  const style = $derived(watch ? { font: 20, ySize: 104, gap: 6 } : { font: 10, ySize: 52, gap: 4 });

  function columns(): void {
    const m = records.length;
    xs = new Float64Array(m);
    tgt = new Float64Array(m);
    tErr = new Float64Array(m);
    chk = new Float64Array(m);
    cErr = new Float64Array(m);
    for (let i = 0; i < m; i++) {
      const r = records[i];
      xs[i] = r.t;
      tgt[i] = r.target;
      tErr[i] = r.targetErr;
      cErr[i] = r.checkErr;
    }
    checkMedian = median(records.map((r) => r.check));
    for (let i = 0; i < m; i++) chk[i] = records[i].check - checkMedian;
    band = extendBand(emptyBand(Math.max(256, m)), chk, m, 15);
  }

  function fitX(): void {
    for (const p of group) p.setScale('x', { min: start - 240, max: end + 240 });
    zoomed = false;
  }

  export function fit(): void {
    fitX();
  }

  function font(): string {
    return `${watch ? 18 : 10}px ${pal?.mono ?? 'monospace'}`;
  }

  function opts(kind: 'target' | 'check', w: number, h: number): uPlot.Options {
    const p = pal!;
    const isT = kind === 'target';
    const bottom = !isT || !hasCheck;
    return {
      width: w,
      height: h,
      padding: [isT ? (watch ? 10 : 6) : watch ? 16 : 12, watch ? 64 : 34, bottom ? 0 : 10, 0],
      legend: { show: false },
      cursor: {
        sync: { key: SYNC },
        drag: { x: true, y: false, setScale: true },
        // Hovered point: a 10 px ring (--chart-marker-hover) in --chart-highlight.
        points: {
          show: true,
          size: watch ? 16 : 12,
          width: 1.5,
          stroke: () => p.highlight,
          fill: () => 'transparent',
        },
        y: false,
      },
      scales: {
        x: { time: false },
        y: {
          dir: -1,
          range: (_u, lo, hi) => {
            if (isT) return padRange(lo, hi, 0.12, 0.05);
            const a = Math.max(Math.abs(lo), Math.abs(hi), 0.02);
            return [-a * 1.25, a * 1.25];
          },
        },
      },
      axes: [xAxis(p, style, bottom), yAxis(p, style, isT ? 2 : 2, watch ? 3 : 3)],
      series: [{}, { stroke: 'transparent', width: 0, points: { show: false }, paths: () => null }],
      plugins: [
        linkX(group, (z) => (zoomed = z)),
        periods({
          ranges: () => flagged,
          events: () => events,
          now: () => now,
          hatch: () => withAlpha(p.warning, 0.22),
          line: () => p.warning,
          text: () => p.text,
          reference: () => p.reference,
          font,
          labels: isT,
        }),
        ...(isT
          ? []
          : [
              envelope({
                hi: () => band.hi.subarray(0, band.n),
                lo: () => band.lo.subarray(0, band.n),
                mean: () => band.mean.subarray(0, band.n),
                fill: () => withAlpha(p.check, 0.16),
                meanStroke: () => withAlpha(p.check, 0.7),
              }),
            ]),
        roleMarkers({
          shape: isT ? 'circle' : 'triangle',
          color: () => (isT ? p.target : p.check),
          errors: () => (errors ? (isT ? tErr : cErr) : null),
          errorAlpha: () => p.errorAlpha,
          size: watch ? 9 : undefined,
          latest: () => p.highlight,
        }),
      ],
      hooks: {
        setCursor: [
          (u) => {
            const i = u.cursor.idx;
            hover = i == null ? null : i;
          },
        ],
      },
    };
  }

  function data(kind: 'target' | 'check'): uPlot.AlignedData {
    return [xs, kind === 'target' ? tgt : chk];
  }

  function destroy(): void {
    tPlot?.destroy();
    cPlot?.destroy();
    tPlot = cPlot = null;
    group.clear();
  }

  function build(): void {
    destroy();
    if (!tHost || sizes.tw <= 0 || sizes.th <= 0) return;
    pal = chartPalette(tHost);
    tPlot = new uPlot(opts('target', sizes.tw, sizes.th), data('target'), tHost);
    group.add(tPlot);
    if (hasCheck && cHost && sizes.cw > 0 && sizes.ch > 0) {
      cPlot = new uPlot(opts('check', sizes.cw, sizes.ch), data('check'), cHost);
      group.add(cPlot);
    }
    if (!zoomed) fitX();
  }

  // Rebuild on theme, variant or check change; resize otherwise.
  $effect(() => {
    void env.theme;
    void variant;
    void hasCheck;
    untrack(() => {
      columns();
      build();
    });
  });

  $effect(() => {
    const { tw, th, cw, ch } = sizes;
    untrack(() => {
      if (!tPlot) return build();
      tPlot.setSize({ width: tw, height: th });
      cPlot?.setSize({ width: cw, height: ch });
    });
  });

  // New points: replace the data, keep a manual zoom (spec 3.13).
  $effect(() => {
    void records;
    void start;
    void end;
    void errors;
    untrack(() => {
      columns();
      if (!tPlot) return;
      const keep = zoomed;
      tPlot.setData(data('target'), false);
      cPlot?.setData(data('check'), false);
      if (!keep) fitX();
      else for (const p of group) p.redraw(false);
    });
  });

  // Overlays (now line, events, flagged ranges) change without new data.
  $effect(() => {
    void now;
    void events;
    void flagged;
    untrack(() => {
      for (const p of group) p.redraw(false);
    });
  });

  onMount(() => {
    const ro = new ResizeObserver(() => {
      const t = tHost.getBoundingClientRect();
      const c = cHost?.getBoundingClientRect();
      sizes = {
        tw: Math.floor(t.width),
        th: Math.floor(t.height),
        cw: Math.floor(c?.width ?? 0),
        ch: Math.floor(c?.height ?? 0),
      };
    });
    ro.observe(tHost);
    if (cHost) ro.observe(cHost);
    return () => {
      ro.disconnect();
      destroy();
    };
  });

  const h = $derived(hover !== null && hover < n ? records[hover] : null);
</script>

<div class="lc variant-{variant}" ondblclick={fitX} role="group" aria-label="Light curve of {targetName}{hasCheck ? ` and check star ${checkName}` : ''}">
  {#if header}
    <div class="head">
      <span class="who">
        <svg viewBox="0 0 20 20" class="glyph target" aria-hidden="true"><path d={shapePath('circle')} /></svg>
        <span class="name">{targetName}</span>
        <span class="unit">TG mag</span>
        {#if hasCheck}
          <svg viewBox="0 0 20 20" class="glyph check" aria-hidden="true"><path d={shapePath('triangle')} /></svg>
          <span class="name">Check</span>
          <span class="unit">Δ from median</span>
        {/if}
      </span>
      <span class="readout num" aria-live="off">
        {#if h}
          <span class="k">#{h.n}</span>
          <span>{utc(h.t)} UTC</span>
          <span class="k">JD {jd(h.t)}</span>
          <span>{mag(h.target, h.targetErr)}</span>
          {#if hasCheck}<span class="k">chk {signed(h.check - checkMedian, 3)}</span>{/if}
        {:else if zoomed}
          <span class="chip">Manual zoom kept · double-click or F fits</span>
        {:else if last}
          <span class="k">latest #{last.n}</span>
          <span>{mag(last.target, last.targetErr)}</span>
          {#if hasCheck}<span class="k">check rms {fixed(band.n ? (band.hi[band.n - 1] - band.lo[band.n - 1]) / 2 : NaN, 3)}</span>{/if}
        {/if}
      </span>
    </div>
  {/if}
  <div class="facets">
    <div class="facet target" class:solo={!hasCheck}>
      <div class="plot" bind:this={tHost}></div>
      <span class="label" aria-hidden="true">
        <svg viewBox="0 0 20 20" class="glyph target"><path d={shapePath('circle')} /></svg>
        {targetName} · brighter up
      </span>
    </div>
    {#if hasCheck}
      <div class="facet check">
        <div class="plot" bind:this={cHost}></div>
        <span class="label" aria-hidden="true">
          <svg viewBox="0 0 20 20" class="glyph check"><path d={shapePath('triangle')} /></svg>
          {checkName} · Δ mag, ±1σ trailing
        </span>
      </div>
    {/if}
  </div>
</div>

<style>
  .lc {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: var(--chart-surface);
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    height: 24px;
    padding: 0 var(--space-3);
    flex: none;
    font-size: var(--text-xs);
  }
  .who {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    color: var(--fg);
    white-space: nowrap;
  }
  .who .name {
    font-weight: var(--weight-medium);
  }
  .who .unit {
    color: var(--text-muted);
    margin-right: var(--space-3);
  }
  .readout {
    display: inline-flex;
    gap: var(--space-3);
    color: var(--fg);
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
  }
  .readout .k {
    color: var(--text-muted);
  }
  .chip {
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-family: var(--font-ui);
  }

  .glyph {
    width: 12px;
    height: 12px;
    flex: none;
  }
  .glyph.target path {
    fill: var(--chart-1);
  }
  .glyph.check path {
    fill: var(--chart-3);
  }

  .facets {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  .facet {
    position: relative;
    min-height: 0;
  }
  .facet.target {
    flex: 58;
  }
  .facet.target.solo {
    flex: 1;
  }
  .facet.check {
    flex: 42;
  }
  .plot {
    position: absolute;
    inset: 0;
  }

  /* Direct labels, top-left inside each facet, on an opaque token chip so
     they never sit on points unreadably. */
  .label {
    position: absolute;
    top: 6px;
    left: 60px;
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    padding: 0 var(--space-1);
    background: var(--chart-surface);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    font-family: var(--font-mono);
    letter-spacing: 0.02em;
    pointer-events: none;
  }

  .variant-watch .label {
    top: 10px;
    left: 116px;
    font-size: var(--lab-watch-tick);
    gap: var(--space-2);
  }
  .variant-watch .label .glyph {
    width: 22px;
    height: 22px;
  }

  /* uPlot's own cursor and selection: tokens, never its default grey. */
  .lc :global(.u-cursor-x) {
    border-right: 1px solid var(--chart-highlight);
  }
  .lc :global(.u-cursor-y) {
    display: none;
  }
  .lc :global(.u-select) {
    background: color-mix(in srgb, var(--fg) 8%, transparent);
    border-left: 1px solid var(--chart-reference);
    border-right: 1px solid var(--chart-reference);
  }
  .lc :global(.u-over) {
    cursor: crosshair;
  }
</style>

<!--
  Conditions timeline (decision D6): up to three small multiples on one UTC axis
  (HFD and FWHM, stars, sky, peak, airmass, sensor, focuser), one implementation
  merged from src/lab/charts/charts/ConditionsTimeline.svelte and
  src/lab/workspace/charts/Trend.svelte (web/lab/PROPOSAL.md 3.2 and 6, W3). Data:
  the server's conditions rows (A37) in typed-array columns (conditions.svelte.ts);
  uPlot reads subarray views, never a $state proxy.

  - An interval with no frame longer than max(2 x cadence, cadence + 60 s) breaks every
    series (no line invents a trend that was not measured) and is drawn as a neutral
    hatched period named by its cause ("autofocus 13:36–13:38", else "no frame").
  - The x range runs to NOW, not to the last frame: the gap after the newest point IS
    the age of the last frame. While frames are expected (live view) and none came
    for max(2 x cadence, cadence + 60 s), the gap is hatched and named ("no frame for
    3 min 12 s"): a frozen run never looks healthy. When nothing is expected the gap
    is plain.
  - One unit per axis, two series at most per plot (HFD solid, FWHM dashed, both px);
    airmass has 1.0 at the top (up = better, like altitude). Neutral inks.
  - Drag across a plot to zoom (the zoom is kept while frames arrive, "Zoom kept · F
    fits"); F or double-click fits the session to now. Hover reads every column of
    the frame under the cursor, in mono, with its UTC time.
  - Updates are batched per animation frame: one setData per plot per frame.
-->
<script lang="ts">
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import './plot-host.css';
  import { onMount, untrack } from 'svelte';
  import { fixed, int } from '../format/number';
  import { clockUtc, duration } from '../format/time';
  import { gapLabel, gapsOf, liveness, timeRange, type Column, type TimelinePeriod } from './conditions';
  import type { ConditionsStore } from './conditions.svelte';
  import { METRICS, type ConditionsView, type MetricId } from './conditionsView.svelte';
  import { readInks, type ChartInks } from './ink';
  import Sparkline from './mini/Sparkline.svelte';
  import { utcAxis, valueAxis, padRange } from './uplot/axes';
  import { PlotHost } from './uplot/host';
  import { annotations, type Annotation } from './uplot/overlays';

  interface Props {
    store: ConditionsStore;
    view: ConditionsView;
    theme?: unknown;
    /** Frames are expected now (live view running): only then is a gap overdue. */
    expecting?: boolean;
    /** Seconds of history shown (null: the whole session). */
    window?: number | null;
    /** A fixed list of metrics (the Focus band's HFD trend): no chips. */
    metrics?: MetricId[] | null;
    /** The column of current values with their sparklines (the drawer tab). */
    rows?: boolean;
    /** Vertical marks (an autofocus that ended), unix seconds. */
    marks?: readonly { t: number; label: string }[];
    /** Periods that explain a frameless interval (the autofocus runs of the session). */
    periods?: readonly TimelinePeriod[];
    /** Wall clock, unix seconds (tests and the gallery pass a fixed one). */
    clock?: () => number;
    label?: string;
    /** What the x range covers, said on the first plot ("last 30 min", "session"). */
    scope?: string | null;
  }

  let {
    store,
    view,
    theme,
    expecting = false,
    window = null,
    metrics = null,
    rows = false,
    marks = [],
    periods = [],
    clock = () => Date.now() / 1000,
    label = 'Conditions timeline',
    scope = null,
  }: Props = $props();

  const shown: MetricId[] = $derived(metrics ?? view.metrics);
  let root: HTMLDivElement;
  let wall: HTMLDivElement | undefined = $state();
  const hosts = new Map<MetricId, PlotHost>();
  let inks: ChartInks | null = null;
  const syncKey = `cond-${Math.random().toString(36).slice(2, 8)}`;
  let now = $state(untrack(() => clock()));
  let hover = $state<{ idx: number; left: number; top: number } | null>(null);
  let activeFacet: MetricId | null = null;

  const cols = untrack(() => store.cols);
  const empty = $derived.by(() => {
    void store.version;
    return cols.n === 0;
  });
  const live = $derived.by(() => {
    void store.version;
    return liveness(cols, now, expecting);
  });

  /** The x range: a kept zoom, else the window (or the session) running to now. */
  function range(): [number, number] {
    return view.zoom ?? timeRange(cols, now, window);
  }

  /** A column as uPlot data: the typed-array view itself unless it holds NaN (uPlot gaps are null). */
  function series(c: Column): ArrayLike<number | null> {
    const v = cols.view(c);
    for (let i = 0; i < v.length; i++) {
      if (Number.isNaN(v[i])) return Array.from(v, (x) => (Number.isNaN(x) ? null : x));
    }
    return v;
  }

  // Frameless intervals, recomputed once per store change.
  let gapMemo: { version: number; n: number; gaps: number[] } = { version: -1, n: -1, gaps: [] };
  function gaps(): number[] {
    const v = untrack(() => store.version);
    if (gapMemo.version !== v || gapMemo.n !== cols.n) gapMemo = { version: v, n: cols.n, gaps: gapsOf(cols.cols.t, cols.n) };
    return gapMemo.gaps;
  }
  /** Data index -> row of the columns (-1 for the null point that breaks a gap). */
  let rowOf: Int32Array | null = null;

  function dataFor(id: MetricId): uPlot.AlignedData {
    const g = gaps();
    if (!g.length) {
      rowOf = null;
      return [cols.view('t'), ...METRICS[id].cols.map(series)] as unknown as uPlot.AlignedData;
    }
    // One null point inside every gap: uPlot breaks the line there (spanGaps false).
    const n = cols.n;
    const m = n + g.length;
    const t = cols.cols.t;
    const x = new Float64Array(m);
    const map = new Int32Array(m);
    const ys = METRICS[id].cols.map(() => new Array<number | null>(m));
    let k = 0;
    let j = 0;
    for (let i = 0; i < n; i++) {
      x[k] = t[i];
      map[k] = i;
      METRICS[id].cols.forEach((c, s) => {
        const v = cols.cols[c][i];
        ys[s][k] = Number.isNaN(v) ? null : v;
      });
      k++;
      if (j < g.length && g[j] === i) {
        x[k] = (t[i] + t[i + 1]) / 2;
        map[k] = -1;
        for (const y of ys) y[k] = null;
        k++;
        j++;
      }
    }
    rowOf = map;
    return [x, ...ys] as unknown as uPlot.AlignedData;
  }

  function annFor(first: boolean): Annotation[] {
    const ink = inks;
    if (!ink) return [];
    const out: Annotation[] = [];
    for (const m of marks) out.push({ kind: 'vline', x: m.t, color: ink.reference.a(0.5), dash: [2, 3], label: first ? { text: m.label } : undefined });
    const t = cols.cols.t;
    // A gap is named only when it is wide enough for its words and clear of the previous
    // named one (labels never overlap); every gap is hatched.
    const [x0, x1] = range();
    const room = (x1 - x0) * 0.14;
    let lastNamed = -Infinity;
    for (const i of gaps()) {
      const a = t[i];
      const b = t[i + 1];
      const named = first && Math.min(b, x1) - Math.max(a, x0) >= room && a - lastNamed >= room;
      if (named) lastNamed = a;
      out.push({ kind: 'vspan', from: a, to: b, hatch: ink.fgMuted.a(0.22), edge: ink.fgMuted.a(0.35), edgeDash: [2, 3], label: named ? { text: gapLabel(a, b, periods), at: 'bottom' } : undefined });
    }
    const n = cols.n;
    const lastT = n ? cols.cols.t[n - 1] : null;
    if (lastT !== null && live.overdue) {
      out.push({ kind: 'vspan', from: lastT, to: now, hatch: ink.warning.a(0.45), edge: ink.warning.a(0.8), layer: 'over' });
    }
    const nowText = `now ${clockUtc(now)}${live.overdue && live.age !== null ? ` · no frame for ${duration(live.age)}` : ''}`;
    out.push({ kind: 'vline', x: now, color: ink.highlight.a(0.85), label: first ? { text: nowText, at: 'top', color: live.overdue ? ink.fg.a() : undefined } : undefined });
    return out;
  }

  function options(id: MetricId, first: boolean, last: boolean): uPlot.Options {
    const ink = inks!;
    const m = METRICS[id];
    const s: uPlot.Series[] = [{}];
    m.cols.forEach((_c, k) => {
      s.push({
        stroke: k === 0 ? ink.fg.a(0.92) : ink.fgMuted.a(0.9),
        width: k === 0 ? 1.5 : 1.25,
        dash: k === 0 ? undefined : [4, 3],
        spanGaps: false,
        points: {
          show: (u: uPlot) => {
            const [a, b] = u.series[0].idxs ?? [0, 999];
            return b - a < 240;
          },
          size: 4,
          fill: k === 0 ? ink.fg.a() : ink.fgMuted.a(),
          stroke: 'rgba(0,0,0,0)',
        } as uPlot.Series.Points,
      });
    });
    const fmt = (v: number) => (m.digits === 0 ? int(v) : fixed(v, Math.min(m.digits, 2)));
    return {
      width: 100,
      height: 100,
      padding: [first ? 6 : 4, 24, last ? 0 : 2, 0],
      legend: { show: false },
      cursor: {
        sync: { key: syncKey, setSeries: false },
        points: { size: 8, width: 1.5, stroke: () => ink.highlight.a(), fill: () => 'rgba(0,0,0,0)' },
        drag: { x: true, y: false, setScale: false, dist: 6 },
        focus: { prox: -1 },
      },
      select: { show: true, left: 0, top: 0, width: 0, height: 0 },
      scales: {
        x: { time: false, range: () => range() },
        y: { dir: m.invert ? -1 : 1, range: (_u, min, max) => padRange(min, max, m.minSpan, 0.12) },
      },
      axes: [utcAxis(ink, { labels: last }), valueAxis(ink, { format: fmt, size: 46, space: 22 })],
      series: s,
      plugins: [annotations(() => annFor(first), () => inks)],
      hooks: {
        init: [
          (u) => {
            u.over.addEventListener('pointerenter', () => (activeFacet = id));
            u.over.addEventListener('pointerleave', () => {
              if (activeFacet === id) activeFacet = null;
              hover = null;
            });
            u.over.addEventListener('dblclick', () => view.fit());
          },
        ],
        setSelect: [
          (u) => {
            if (u.select.width < 6) return;
            const a = u.posToVal(u.select.left, 'x');
            const b = u.posToVal(u.select.left + u.select.width, 'x');
            u.setSelect({ left: 0, top: 0, width: 0, height: 0 }, false);
            view.setZoom(a, b);
          },
        ],
        setCursor: [
          (u) => {
            if (activeFacet !== id || !wall) return;
            const i = u.cursor.idx;
            const left = u.cursor.left ?? -1;
            if (i == null || left < 0) {
              hover = null;
              return;
            }
            const wr = wall.getBoundingClientRect();
            const or = u.over.getBoundingClientRect();
            hover = { idx: i, left: or.left - wr.left + left, top: or.top - wr.top + (u.cursor.top ?? 0) };
          },
        ],
      },
    };
  }

  function facet(id: MetricId, first: boolean, last: boolean) {
    return (el: HTMLElement) => {
      inks ??= readInks(el);
      const h = new PlotHost(el, () => ({ opts: options(id, first, last), data: dataFor(id) }));
      hosts.set(id, h);
      return () => {
        h.destroy();
        hosts.delete(id);
      };
    };
  }

  // -- Updates: one batch per animation frame -----------------------------------------
  let raf = 0;
  function push(): void {
    raf = 0;
    const r = range();
    for (const [id, h] of hosts) {
      const u = h.u;
      if (!u) continue;
      u.batch(() => {
        u.setData(dataFor(id), false);
        u.setScale('x', { min: r[0], max: r[1] });
      });
    }
  }
  function schedule(): void {
    if (!raf && typeof requestAnimationFrame !== 'undefined') raf = requestAnimationFrame(push);
  }

  $effect(() => {
    void store.version;
    void view.zoom;
    void live.overdue;
    untrack(schedule);
  });

  // The now-line and the age tick once a second.
  onMount(() => {
    const t = setInterval(() => {
      now = clock();
      schedule();
    }, 1000);
    return () => {
      clearInterval(t);
      if (raf) cancelAnimationFrame(raf);
    };
  });

  $effect(() => {
    void theme;
    void shown.length;
    untrack(() => {
      if (!root) return;
      inks = readInks(root);
      for (const h of hosts.values()) h.build();
    });
  });

  function onKey(e: KeyboardEvent): void {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === 'f' || e.key === 'F') {
      view.fit();
      e.preventDefault();
      e.stopPropagation();
    }
  }

  // -- The column of current values -------------------------------------------------
  const ROWS: { id: MetricId; col: Column; name: string }[] = [
    { id: 'focus', col: 'hfd', name: 'HFD' },
    { id: 'focus', col: 'fwhm', name: 'FWHM' },
    { id: 'stars', col: 'stars', name: 'Stars' },
    { id: 'sky', col: 'sky', name: 'Sky' },
    { id: 'peak', col: 'peak', name: 'Peak' },
    { id: 'airmass', col: 'airmassMount', name: 'Airmass' },
    { id: 'sensor', col: 'sensorC', name: 'Sensor' },
    { id: 'focuser', col: 'focuser', name: 'Focuser' },
  ];
  const SPARK_WINDOW = 3600;
  const fmtCol = (id: MetricId, v: number) => (Number.isFinite(v) ? (METRICS[id].digits === 0 ? int(v) : fixed(v, METRICS[id].digits)) : '—');
  const rowState = $derived.by(() => {
    void store.version;
    const n = cols.n;
    const tEnd = n ? cols.cols.t[n - 1] : 0;
    return ROWS.map((r) => ({ ...r, value: cols.last(r.col), range: cols.extent(r.col, tEnd - SPARK_WINDOW) }));
  });

  const hoverRead = $derived.by(() => {
    void store.version;
    if (!hover) return null;
    const i = rowOf ? (rowOf[hover.idx] ?? -1) : hover.idx;
    if (i < 0 || i >= cols.n) return null;
    return {
      t: clockUtc(cols.cols.t[i]),
      frame: cols.cols.frameSeq[i],
      exposure: cols.cols.exposure[i],
      rows: ROWS.map((r) => ({ name: r.name, unit: METRICS[r.id].unit, v: fmtCol(r.id, cols.cols[r.col][i]) })),
    };
  });
  const tipStyle = $derived.by(() => {
    if (!hover || !wall) return '';
    const w = wall.clientWidth;
    const left = hover.left + 16 + 190 > w ? hover.left - 16 - 190 : hover.left + 16;
    const top = Math.max(2, Math.min(wall.clientHeight - 200, hover.top - 40));
    return `left:${left}px;top:${top}px`;
  });
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
<div class="cond" class:with-rows={rows} bind:this={root} role="region" aria-label={label} tabindex="0" onkeydown={onKey}>
  {#if rows}
    <ul class="rows" aria-label="Latest values">
      {#each rowState as r (r.col)}
        <li>
          <span class="name">{r.name}</span>
          <span class="val num"><b>{fmtCol(r.id, r.value)}</b>{#if METRICS[r.id].unit}<small>{METRICS[r.id].unit}</small>{/if}</span>
          <Sparkline
            width={72}
            height={16}
            {theme}
            version={store.version}
            label="{r.name}, the last hour{Number.isFinite(r.range[0]) ? `, from ${fmtCol(r.id, r.range[0])} to ${fmtCol(r.id, r.range[1])}` : ''}"
            spec={(ink) => {
              const n = cols.n;
              const tEnd = n ? cols.cols.t[n - 1] : 0;
              // The last hour, or the session when it is shorter.
              const x0 = n ? Math.max(cols.cols.t[0], tEnd - SPARK_WINDOW) : 0;
              return { xs: cols.cols.t, ys: cols.cols[r.col], n, x0, x1: tEnd, invert: METRICS[r.id].invert, color: ink.fgMuted.a(), lastDot: true };
            }}
          />
        </li>
      {/each}
    </ul>
  {/if}

  <div class="wall" bind:this={wall}>
    {#if empty}
      <p class="empty">
        No frame measured yet in this session. HFD, stars, sky and the other conditions appear here, one point per frame
        (live view and single exposures).
      </p>
    {/if}
    {#each empty ? [] : shown as id, k (id)}
      {@const m = METRICS[id]}
      <div class="facet" class:last={k === shown.length - 1}>
        <span class="tag num">{m.names.join(' · ')}{m.unit ? ` · ${m.unit}` : ''}{m.invert ? ' · 1.0 at top' : ''}{k === 0 && scope ? ` · ${view.zoom ? 'zoomed' : scope}` : ''}</span>
        <div class="plot-host" {@attach facet(id, k === 0, k === shown.length - 1)}></div>
      </div>
    {/each}
    {#if hoverRead}
      <div class="tip num" style={tipStyle} aria-hidden="true">
        <div class="t">{hoverRead.t} UTC · frame #{int(hoverRead.frame)} · {fixed(hoverRead.exposure, 1)} s</div>
        {#each hoverRead.rows as r (r.name)}
          <div><span>{r.name}</span><b>{r.v}</b>{r.unit ? ` ${r.unit}` : ''}</div>
        {/each}
      </div>
    {/if}
  </div>
</div>

<style>
  .cond {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    height: 100%;
    min-height: 0;
    min-width: 0;
    outline: none;
  }
  .cond.with-rows {
    grid-template-columns: 236px minmax(0, 1fr);
  }
  .cond:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -2px;
  }
  .rows {
    list-style: none;
    margin: 0;
    padding: var(--space-1) var(--space-3);
    border-right: var(--border-w) solid var(--border-soft);
    overflow: auto;
  }
  .rows li {
    display: grid;
    grid-template-columns: 56px 1fr 72px;
    align-items: center;
    gap: var(--space-2);
    height: 19px;
  }
  .name {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .val {
    color: var(--fg);
    font-size: var(--text-xs);
    text-align: right;
    white-space: nowrap;
  }
  .val b {
    font-weight: var(--weight-regular);
  }
  .val small {
    margin-left: 3px;
    color: var(--text-muted);
    font-size: var(--text-2xs);
  }
  .wall {
    position: relative;
    display: flex;
    flex-direction: column;
    min-height: 0;
    min-width: 0;
    padding: var(--space-1) var(--space-2) var(--space-1) 0;
  }
  .facet {
    position: relative;
    flex: 1 1 0;
    min-height: 0;
    display: flex;
  }
  .facet.last {
    flex-grow: 1.35; /* room for the time labels */
  }
  .facet .plot-host {
    flex: 1;
  }
  .tag {
    position: absolute;
    top: 1px;
    left: 52px;
    z-index: 1;
    padding: 0 3px;
    background: var(--chart-surface);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    pointer-events: none;
  }
  .empty {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    margin: 0;
    padding: 0 var(--space-6);
    color: var(--text-muted);
    font-size: var(--text-s);
    text-align: center;
    z-index: 2;
    pointer-events: none;
  }
  .tip {
    position: absolute;
    z-index: 3;
    width: 190px;
    padding: var(--space-1) var(--space-2);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    pointer-events: none;
    box-shadow: var(--elev-hud);
  }
  .tip .t {
    margin-bottom: 2px;
    color: var(--fg);
  }
  .tip div:not(.t) {
    display: flex;
    gap: var(--space-2);
  }
  .tip span {
    width: 52px;
  }
  .tip b {
    margin-left: auto;
    color: var(--fg);
    font-weight: var(--weight-regular);
  }
</style>

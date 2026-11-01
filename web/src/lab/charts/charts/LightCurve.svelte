<!--
  Live differential light curve (spec D25, D26, 3.13; BRAND 10).

  Three facets on one linked time axis, one y axis each, never more than
  three series per plot:
  - Target (circles): calibrated V, magnitude axis inverted, error bars,
    optional trailing median (causal: drawn points never move).
  - Check (triangles): check star minus its catalogue V, with the trailing
    15-point mean +/- 1 sigma as a band: the photometry is trustworthy while
    the band stays thin.
  - Comparison ensemble (squares): instrumental minus catalogue, the zero
    point. Clouds and extinction dim every star and show here; they cancel in
    the target facet, which is the point of differential photometry. The band
    is the spread of the comparisons around their mean on each frame.
  Flags by shape: suspect = hollow, saturated = x. The newest point is ringed.

  Interaction: hover crosshair synced across facets with one readout for
  all series; drag = box zoom; wheel / pinch = zoom time about the pointer;
  horizontal swipe or Shift+wheel = pan; double-click or F = fit; + / − zoom;
  ← → pan; End = follow the newest frame; click = select a time (Esc clears);
  legend items toggle their series; U = error bars. New frames never move a
  manual zoom; a zoom touching the newest frame follows it.

  Data: typed-array views of the stream (no Svelte proxy), one batched
  setData + setScale per facet and per animation frame; the cost of each
  update is measured and reported.
-->
<script lang="ts" module>
  export type FacetId = 'target' | 'check' | 'ensemble';
</script>

<script lang="ts">
  import uPlot from 'uplot';
  import { untrack } from 'svelte';
  import Icon from '../../../lib/components/Icon.svelte';
  import { tooltip } from '../../../lib/components/tooltip';
  import { env, reducedMotion, toast } from '../env.svelte';
  import { clock, type FrameStream } from '../sim/stream.svelte';
  import { AUTOFOCUS, COMPS, FLAG_SATURATED, FLAG_SUSPECT, NIGHT_LABEL, TARGET } from '../sim/night';
  import { jdFromUnix } from '../sim/astro';
  import { readInks, type ChartInks } from '../core/palette';
  import { PlotHost } from '../core/uplot/host';
  import { TimeZoom, type ZoomMode } from '../core/uplot/zoom';
  import { markers, type Shape } from '../core/uplot/markers';
  import { annotations, type Annotation } from '../core/uplot/overlays';
  import { paddedRange, timeAxis, utcTz, valueAxis, type TimeAxisMode } from '../core/uplot/axes';
  import { trailingBand, trailingMedian, rms, type Band } from '../core/stats';
  import { PerfRecorder, type PerfSummary } from '../core/perf';
  import { browserExport, composeCanvas, toTsv } from '../core/export';
  import { clockUtc, duration, fixed, grouped, isoUtc, julian, mag, MINUS, signed } from '../core/format';
  import RoleGlyph from './RoleGlyph.svelte';

  interface Props {
    stream?: FrameStream;
    facets?: FacetId[];
    /** Observe band: one toolbar row, no export, smaller headers. */
    compact?: boolean;
    /** Initial time axis. */
    axis?: TimeAxisMode;
    onperf?: (s: PerfSummary, points: number) => void;
    /** Exposed for the lab's screenshot script. */
    hooks?: (api: { zoomTo: (a: number, b: number) => void; hoverAt: (fx: number, facet: FacetId) => void; select: (i: number) => void }) => void;
  }

  let { stream = clock.night, facets = ['target', 'check', 'ensemble'], compact = false, axis = 'utc', onperf, hooks }: Props = $props();

  interface FacetDef {
    title: string;
    sub: string;
    shape: Shape;
    token: string;
    share: number;
    digits: number;
    minSpan: number;
    unit: string;
  }
  const DEF: Record<FacetId, FacetDef> = {
    target: { title: TARGET.label, sub: 'target · V (TG) · differential', shape: 'circle', token: '--chart-1', share: 0.5, digits: 2, minSpan: 0.08, unit: 'mag' },
    check: { title: 'Check', sub: 'K minus catalogue V', shape: 'triangle', token: '--chart-3', share: 0.25, digits: 3, minSpan: 0.04, unit: 'mag' },
    ensemble: { title: 'Comparison ensemble', sub: `instrumental − catalogue · ${COMPS.length} stars`, shape: 'square', token: '--chart-2', share: 0.25, digits: 2, minSpan: 0.1, unit: 'mag' },
  };
  const JD0 = Math.floor(jdFromUnix(Date.UTC(2026, 10, 1, 18) / 1000));
  const CHECK_W = 15;
  const TREND_W = 9;

  // -- State ------------------------------------------------------------------
  let root: HTMLDivElement;
  let wall: HTMLDivElement;
  const hosts = new Map<FacetId, PlotHost>();
  let inks: ChartInks | null = null;
  const syncKey = `lc-${Math.random().toString(36).slice(2, 8)}`;

  let count = $state(0);
  let axisMode = $state<TimeAxisMode>(untrack(() => axis));
  let showErrors = $state(true);
  let show = $state({ target: true, trend: false, check: true, checkBand: true, ensemble: true, ensBand: true });
  let mode = $state<ZoomMode>('fit');
  let viewSpan = $state(0);
  let selected = $state<number | null>(null);
  let hover = $state<{ idx: number; facet: FacetId; left: number; top: number } | null>(null);
  let perf = $state<PerfSummary | null>(null);
  let activeFacet: FacetId | null = null;
  const recorder = new PerfRecorder();

  // Causal derived columns over the whole stream (revealed prefix shown).
  interface Derived {
    trend: Float64Array;
    checkBand: Band;
    ensHi: Float64Array;
    ensLo: Float64Array;
  }
  let derivedFor: FrameStream | null = null;
  let cache: Derived | null = null;
  function getDerived(): Derived {
    if (cache && derivedFor === stream) return cache;
    const c = stream.cols;
    const n = c.n;
    const ensHi = new Float64Array(n);
    const ensLo = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      ensHi[i] = c.ensOffset[i] + c.ensSpread[i];
      ensLo[i] = c.ensOffset[i] - c.ensSpread[i];
    }
    cache = {
      trend: trailingMedian(c.target, n, TREND_W, (i) => c.flags[i] !== 0),
      checkBand: trailingBand(c.checkDelta, n, CHECK_W),
      ensHi,
      ensLo,
    };
    derivedFor = stream;
    return cache;
  }

  const zoom = new TimeZoom({
    extent: () => {
      const n = stream.n;
      return n ? [stream.cols.t[0], stream.cols.t[n - 1]] : null;
    },
    minSpan: 300,
    padRight: 0.015,
    reducedMotion,
    onChange: (m, v) => {
      mode = m;
      viewSpan = v ? v[1] - v[0] : 0;
    },
  });

  // -- Data and options ---------------------------------------------------------
  function dataFor(id: FacetId): uPlot.AlignedData {
    const c = stream.cols;
    const n = stream.n;
    const d = getDerived();
    const t = c.t.subarray(0, n);
    if (id === 'target') return [t, c.target.subarray(0, n), d.trend.subarray(0, n)];
    if (id === 'check') return [t, c.checkDelta.subarray(0, n), d.checkBand.hi.subarray(0, n), d.checkBand.lo.subarray(0, n), d.checkBand.mean.subarray(0, n)];
    return [t, c.ensOffset.subarray(0, n), d.ensHi.subarray(0, n), d.ensLo.subarray(0, n)];
  }

  const colorOf = (id: FacetId) => (id === 'target' ? inks!.target : id === 'check' ? inks!.check : inks!.comparison);

  function cursorPoint(_u: uPlot, si: number): HTMLElement | undefined {
    if (si !== 1) return undefined;
    const el = document.createElement('div');
    el.style.cssText = 'width:10px;height:10px;margin:-5px 0 0 -5px';
    return el;
  }

  function annFor(id: FacetId): Annotation[] {
    const ink = inks!;
    const out: Annotation[] = [];
    for (const t of AUTOFOCUS) {
      out.push({ kind: 'vline', x: t + 100, color: ink.reference.a(0.55), dash: [2, 3], label: id === facets[0] ? { text: 'AF', at: 'top' } : undefined });
    }
    if (selected !== null && selected < stream.n) {
      out.push({ kind: 'vline', x: stream.cols.t[selected], color: ink.highlight.a(0.9), dash: [4, 3] });
    }
    return out;
  }

  function options(id: FacetId, last: boolean): uPlot.Options {
    const ink = inks!;
    const def = DEF[id];
    const role = colorOf(id);
    const series: uPlot.Series[] = [{}, { stroke: role.a(), paths: () => null, points: { show: false }, show: id === 'target' ? show.target : id === 'check' ? show.check : show.ensemble }];
    const bands: uPlot.Band[] = [];
    if (id === 'target') {
      series.push({ stroke: ink.reference.a(0.9), width: 1.5, points: { show: false }, show: show.trend });
    } else if (id === 'check') {
      series.push(
        { stroke: role.a(0.35), width: 1, points: { show: false }, show: show.checkBand },
        { stroke: role.a(0.35), width: 1, points: { show: false }, show: show.checkBand },
        { stroke: ink.reference.a(0.9), width: 1, dash: [3, 3], points: { show: false }, show: show.checkBand },
      );
      bands.push({ series: [2, 3], fill: role.a(ink.lab.bandAlpha) });
    } else {
      series.push({ stroke: role.a(0.3), width: 1, points: { show: false }, show: show.ensBand }, { stroke: role.a(0.3), width: 1, points: { show: false }, show: show.ensBand });
      bands.push({ series: [2, 3], fill: role.a(ink.lab.bandAlpha) });
    }
    return {
      width: 100,
      height: 100,
      padding: [6, 22, last ? 0 : 2, 0],
      legend: { show: false },
      tzDate: utcTz,
      cursor: {
        sync: { key: syncKey, setSeries: false },
        points: { show: cursorPoint as unknown as boolean, size: 10, width: 1.5, stroke: () => ink.highlight.a(), fill: () => 'rgba(0,0,0,0)' },
        drag: { x: true, y: false, setScale: true, dist: 5 },
        bind: TimeZoom.cursorBind(),
        focus: { prox: -1 },
      },
      scales: {
        x: { time: axisMode === 'utc' },
        y: { dir: -1, range: paddedRange(def.minSpan, 0.1) },
      },
      axes: [
        timeAxis(ink, { mode: axisMode, jd0: JD0, labels: last, bjdOffsetS: bjdOffsetAt }),
        valueAxis(ink, { format: (v) => fixed(v, def.digits), size: 50, space: compact ? 22 : 26 }),
      ],
      series,
      bands,
      plugins: [
        zoom.plugin(),
        annotations(() => annFor(id), () => inks!),
        markers({
          seriesIdx: 1,
          shape: def.shape,
          color: () => colorOf(id).a(),
          errors: () => (id === 'target' ? stream.cols.targetErr : id === 'check' ? stream.cols.checkErr : null),
          showErrors: () => showErrors,
          errorAlpha: () => ink.errorAlpha,
          flags: () => (id === 'target' ? stream.cols.flags : null),
          latest: () => (id === 'ensemble' ? null : ink.highlight.a()),
          selected: () => (selected !== null && selected < stream.n ? { idx: selected, color: ink.highlight.a() } : null),
        }),
      ],
      hooks: {
        init: [
          (u) => {
            u.over.addEventListener('mouseenter', () => (activeFacet = id));
            u.over.addEventListener('mouseleave', () => {
              if (activeFacet === id) activeFacet = null;
              hover = null;
            });
            u.over.addEventListener('click', () => {
              const i = u.cursor.idx;
              if (i != null) selected = i;
            });
          },
        ],
        setCursor: [
          (u) => {
            if (activeFacet !== id) return;
            const i = u.cursor.idx;
            const left = u.cursor.left ?? -1;
            if (i == null || left < 0) {
              hover = null;
              return;
            }
            const wr = wall.getBoundingClientRect();
            const or = u.over.getBoundingClientRect();
            hover = { idx: i, facet: id, left: or.left - wr.left + left, top: or.top - wr.top + (u.cursor.top ?? 0) };
          },
        ],
      },
    };
  }

  function bjdOffsetAt(t: number): number {
    const c = stream.cols;
    const n = c.n;
    if (!n) return 69.184;
    const i = Math.max(0, Math.min(n - 1, stream.indexAt(t)));
    return c.bjdOffsetS[i];
  }

  // -- Facet hosts (attachments) ------------------------------------------------
  function facetHost(id: FacetId, last: boolean) {
    return (el: HTMLElement) => {
      const h = new PlotHost(el, () => ({ opts: options(id, last), data: dataFor(id) }));
      hosts.set(id, h);
      return () => {
        h.destroy();
        hosts.delete(id);
      };
    };
  }

  function rebuild(): void {
    if (!root) return;
    inks = readInks(root);
    zoom.update();
    for (const h of hosts.values()) h.build();
  }

  // -- Live updates: one batched draw per facet per animation frame ----------------
  let raf = 0;
  function schedule(): void {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      push();
    });
  }

  function push(): void {
    if (!inks) return;
    const t0 = performance.now();
    zoom.update();
    let drawn = 0;
    for (const [id, h] of hosts) {
      const u = h.u;
      if (!u) continue;
      zoom.batch(u, () => u.setData(dataFor(id), false));
      drawn++;
    }
    const ms = performance.now() - t0;
    zoom.notify();
    count = stream.n;
    if (selected !== null && selected >= stream.n) selected = null;
    if (!drawn) return;
    recorder.record(ms);
    perf = recorder.summary();
    onperf?.(perf, stream.n);
  }

  $effect(() => {
    const s = stream;
    return untrack(() => {
      cache = null;
      count = s.n;
      selected = null;
      zoom.fit();
      recorder.reset();
      schedule();
      return s.onAppend(() => schedule());
    });
  });

  // Theme and time axis live in the options: rebuild (the zoom view is kept).
  $effect(() => {
    void env.theme;
    void axisMode;
    untrack(rebuild);
  });

  // Series visibility and error bars: no rebuild.
  $effect(() => {
    const s = { ...show };
    const e = showErrors;
    void e;
    untrack(() => {
      const set = (id: FacetId, idx: number, on: boolean) => {
        const u = hosts.get(id)?.u;
        if (u && u.series[idx] && u.series[idx].show !== on) u.setSeries(idx, { show: on });
      };
      set('target', 1, s.target);
      set('target', 2, s.trend);
      set('check', 1, s.check);
      for (const i of [2, 3, 4]) set('check', i, s.checkBand);
      set('ensemble', 1, s.ensemble);
      for (const i of [2, 3]) set('ensemble', i, s.ensBand);
      for (const h of hosts.values()) h.u?.redraw(false, false);
    });
  });

  $effect(() => {
    void selected;
    untrack(() => {
      for (const h of hosts.values()) h.u?.redraw(false, false);
    });
  });

  $effect(() => {
    hooks?.({
      zoomTo: (a, b) => zoom.setUser(a, b),
      hoverAt: (fx, facet) => {
        const u = hosts.get(facet)?.u;
        if (!u) return;
        activeFacet = facet;
        u.setCursor({ left: u.over.clientWidth * fx, top: u.over.clientHeight * 0.4 });
      },
      select: (i) => (selected = i),
    });
  });

  // -- Keyboard ---------------------------------------------------------------------
  function onKey(e: KeyboardEvent): void {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key;
    if (k === 'f' || k === 'F') zoom.fit(true);
    else if (k === '+' || k === '=') zoom.zoomBy(1 / 1.6, undefined, true);
    else if (k === '-' || k === '_') zoom.zoomBy(1.6, undefined, true);
    else if (k === 'ArrowLeft') zoom.panBy(-0.25, true);
    else if (k === 'ArrowRight') zoom.panBy(0.25, true);
    else if (k === 'End') zoom.follow(true);
    else if (k === 'u' || k === 'U') showErrors = !showErrors;
    else if (k === 'Escape' && selected !== null) selected = null;
    else return;
    e.preventDefault();
  }

  // -- Export hooks -----------------------------------------------------------------
  async function exportTsv(): Promise<void> {
    const c = stream.cols;
    const n = stream.n;
    const rows: (string | number)[][] = [];
    for (let i = 0; i < n; i++) {
      const t = c.t[i];
      const f = c.flags[i];
      rows.push([
        isoUtc(t).replace(' UTC', 'Z').replace(' ', 'T'),
        (t / 86400 + 2440587.5).toFixed(6),
        (t / 86400 + 2440587.5 + c.bjdOffsetS[i] / 86400).toFixed(6),
        c.target[i].toFixed(4),
        c.targetErr[i].toFixed(4),
        c.checkDelta[i].toFixed(4),
        c.checkErr[i].toFixed(4),
        c.ensOffset[i].toFixed(4),
        c.nUsed[i],
        c.airmass[i].toFixed(3),
        [f & FLAG_SUSPECT ? 'suspect' : '', f & FLAG_SATURATED ? 'saturated' : ''].filter(Boolean).join(',') || '-',
      ]);
    }
    const text = toTsv(['utc', 'jd_utc', 'bjd_tdb_approx', 'v_mag', 'v_err', 'check_minus_cat', 'check_err', 'ens_offset', 'comps_used', 'airmass', 'flags'], rows);
    toast(await browserExport.tsv(`sw-and-${NIGHT_LABEL}.tsv`, text, n));
  }

  async function exportPng(): Promise<void> {
    const ink = inks!;
    const texts = [...root.querySelectorAll('[data-export-text]')].map((el) => ({
      el,
      color: el.getAttribute('data-export-text') === 'muted' ? ink.textMuted.a() : ink.fg.a(),
      font: `500 11px ${ink.ui}`,
    }));
    const canvas = composeCanvas(wall, ink.surface.a(), texts);
    toast(await browserExport.png(`sw-and-${NIGHT_LABEL}-lightcurve.png`, canvas));
  }

  // -- Readouts -----------------------------------------------------------------------
  const readIdx = $derived(hover?.idx ?? selected ?? (count > 0 ? count - 1 : null));
  const readKind = $derived(hover ? 'hover' : selected !== null ? 'selected' : 'latest');

  function pointText(i: number) {
    const c = stream.cols;
    const t = c.t[i];
    const jd = t / 86400 + 2440587.5;
    const f = c.flags[i];
    return {
      utc: clockUtc(t),
      jd: julian(jd),
      bjd: julian(jd + c.bjdOffsetS[i] / 86400),
      target: mag(c.target[i], c.targetErr[i]),
      check: `${signed(c.checkDelta[i], 3)} ± ${fixed(c.checkErr[i], 3)}`,
      ens: fixed(c.ensOffset[i], 3),
      spread: fixed(c.ensSpread[i], 3),
      used: `${c.nUsed[i]}/${COMPS.length}`,
      airmass: fixed(c.airmass[i], 3),
      alt: `${fixed(c.alt[i], 1)}°`,
      frame: i + 1,
      flags: [f & FLAG_SUSPECT ? 'suspect' : '', f & FLAG_SATURATED ? `saturated (peak ${grouped(c.peakAdu[i])} ADU)` : ''].filter(Boolean),
    };
  }

  const read = $derived.by(() => {
    void count;
    return readIdx !== null && readIdx < stream.n ? pointText(readIdx) : null;
  });

  const flagCounts = $derived.by(() => {
    void count;
    let s = 0;
    let x = 0;
    for (let i = 0; i < stream.n; i++) {
      const f = stream.cols.flags[i];
      if (f & FLAG_SATURATED) x++;
      else if (f & FLAG_SUSPECT) s++;
    }
    return { suspect: s, saturated: x };
  });

  const checkRms = $derived.by(() => {
    void count;
    return rms(stream.cols.checkDelta, Math.max(0, stream.n - 60), stream.n);
  });

  const modeText = $derived(
    mode === 'fit' ? 'Whole run' : mode === 'follow' ? `Following newest · ${duration(viewSpan)}` : 'Zoom kept',
  );

  const axisTitle = $derived(
    axisMode === 'utc'
      ? `UTC · night of ${NIGHT_LABEL} · ${TARGET.label} from Paris`
      : axisMode === 'jd'
        ? `JD ${MINUS} ${JD0} (UTC)`
        : `BJD_TDB ${MINUS} ${JD0} · lab approximation, ± 4 s (the server computes the exact value)`,
  );

  // Tooltip placement: right of the cursor, flipped near the right edge.
  const tipStyle = $derived.by(() => {
    if (!hover || !wall) return '';
    const w = wall.clientWidth;
    const left = hover.left + 16 + 230 > w ? hover.left - 16 - 230 : hover.left + 16;
    const top = Math.max(4, Math.min(wall.clientHeight - 196, hover.top - 60));
    return `left:${left}px;top:${top}px`;
  });

  // flex-grow values must sum to 1 or part of the free space stays empty.
  const shareSum = $derived(facets.reduce((a, id) => a + DEF[id].share, 0));

  const AXES: { id: TimeAxisMode; label: string }[] = [
    { id: 'utc', label: 'UTC' },
    { id: 'jd', label: 'JD' },
    { id: 'bjd', label: 'BJD' },
  ];
</script>

<!-- A focusable chart region: its keys (F, + / −, arrows, End, U, Esc) are
     listed in the header comment and in each tool's tooltip. -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
<div
  class="lc"
  class:compact
  bind:this={root}
  role="region"
  aria-label="Live light curve of {TARGET.label}"
  tabindex="0"
  onkeydown={onKey}
>
  <div class="bar">
    {#if compact}
      <span class="title"><RoleGlyph shape="circle" color="var(--chart-1)" /> {TARGET.label}</span>
      <span class="lab-eyebrow">Light curve</span>
    {/if}
    <div class="lab-seg mono" role="radiogroup" aria-label="Time axis">
      {#each AXES as a (a.id)}
        <button role="radio" aria-checked={axisMode === a.id} onclick={() => (axisMode = a.id)}>{a.label}</button>
      {/each}
    </div>
    <span class="lab-sep"></span>
    <button class="lab-tool" aria-label="Zoom out time" aria-keyshortcuts="-" use:tooltip={{ text: 'Zoom out time', shortcut: '-' }} onclick={() => zoom.zoomBy(1.6, undefined, true)}>
      <Icon name="zoom-out" size={16} />
    </button>
    <button class="lab-tool" aria-label="Zoom in time" aria-keyshortcuts="+" use:tooltip={{ text: 'Zoom in time', shortcut: '+' }} onclick={() => zoom.zoomBy(1 / 1.6, undefined, true)}>
      <Icon name="zoom-in" size={16} />
    </button>
    <button class="lab-tool" aria-label="Fit the whole run" aria-keyshortcuts="F" use:tooltip={{ text: 'Fit the whole run', shortcut: 'F' }} onclick={() => zoom.fit(true)}>
      <Icon name="zoom-fit" size={16} />
    </button>
    <button
      class="lab-tool"
      aria-label="Follow the newest frame"
      aria-keyshortcuts="End"
      aria-pressed={mode === 'follow'}
      use:tooltip={{ text: 'Follow the newest frame', shortcut: 'End' }}
      onclick={() => zoom.follow(true)}
    >
      <Icon name="live" size={16} />
    </button>
    <span class="lab-chip mode" class:manual={mode === 'manual'} data-shot="zoom-mode">
      {#if mode === 'manual'}<span class="lab-dot accent"></span>{/if}{modeText}{#if mode !== 'fit'}<span class="hint">· <kbd class="lab-key">F</kbd> fits</span>{/if}
    </span>
    <span class="lab-sep"></span>
    <button class="lab-tool" aria-label="Error bars" aria-keyshortcuts="U" aria-pressed={showErrors} use:tooltip={{ text: 'Error bars', shortcut: 'U' }} onclick={() => (showErrors = !showErrors)}>
      <Icon name="error-bars" size={16} />
    </button>
    {#if !compact}
      <button class="lab-tool" aria-label="Copy data (TSV)" use:tooltip={{ text: 'Copy data (TSV)' }} onclick={exportTsv} data-shot="export-tsv">
        <Icon name="copy" size={16} />
      </button>
      <button class="lab-tool" aria-label="Save view as PNG" use:tooltip={{ text: 'Save view as PNG' }} onclick={exportPng} data-shot="export-png">
        <Icon name="export" size={16} />
      </button>
    {/if}
    <span class="grow"></span>
    {#if read}
      <span class="readout num" class:hovered={readKind !== 'latest'}>
        <span class="kind">{readKind === 'hover' ? 'Cursor' : readKind === 'selected' ? 'Selected' : 'Latest'}</span>
        <span>{read.utc} UTC</span>
        <b>V {read.target}</b>
        {#if !compact}<span>K {read.check}</span>{/if}
      </span>
    {/if}
    {#if perf && !compact}
      <span class="lab-chip perf" use:tooltip={{ text: 'setData + draw of every facet for one update (median / p95 of the last 240)' }}>
        <b>{grouped(count)}</b> pts · <b>{perf.last.toFixed(1)}</b> ms · p95 {perf.p95.toFixed(1)}
      </span>
    {/if}
  </div>

  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="wall" bind:this={wall} onpointerleave={() => (hover = null)}>
    {#each facets as id, i (id)}
      {@const def = DEF[id]}
      {@const last = i === facets.length - 1}
      <section class="facet" style:flex-grow={def.share / shareSum} style:flex-basis={last ? '24px' : '0px'} aria-label="{def.title}: {def.sub}">
        <header>
          <RoleGlyph shape={def.shape} color="var({def.token})" />
          <h3 data-export-text="fg">{def.title}</h3>
          <span class="sub" data-export-text="muted">{def.sub}</span>
          <span class="legend" role="group" aria-label="Series of {def.title}">
            {#if id === 'target'}
              <button class="key" aria-pressed={show.target} onclick={() => (show.target = !show.target)}>
                <RoleGlyph shape="circle" color="var(--chart-1)" size={10} />measured
              </button>
              <button class="key" aria-pressed={show.trend} onclick={() => (show.trend = !show.trend)}>
                <RoleGlyph shape="circle" color="var(--chart-reference)" variant="line" size={10} />median of {TREND_W}
              </button>
              {#if !compact}
                <span class="key static" use:tooltip={{ text: 'Flagged by the pipeline: excluded from exports by default' }}>
                  <RoleGlyph shape="circle" color="var(--chart-1)" variant="hollow" size={10} />suspect <b class="num">{flagCounts.suspect}</b>
                  <RoleGlyph shape="circle" color="var(--chart-1)" variant="cross" size={10} />saturated <b class="num">{flagCounts.saturated}</b>
                </span>
              {/if}
            {:else if id === 'check'}
              <button class="key" aria-pressed={show.check} onclick={() => (show.check = !show.check)}>
                <RoleGlyph shape="triangle" color="var(--chart-3)" size={10} />measured
              </button>
              <button class="key" aria-pressed={show.checkBand} onclick={() => (show.checkBand = !show.checkBand)}>
                <RoleGlyph shape="triangle" color="var(--chart-3)" variant="band" size={10} />mean ± 1σ, last {CHECK_W}
              </button>
              <span class="key static num">rms (60) <b>{fixed(checkRms, 3)}</b></span>
            {:else}
              <button class="key" aria-pressed={show.ensemble} onclick={() => (show.ensemble = !show.ensemble)}>
                <RoleGlyph shape="square" color="var(--chart-2)" size={10} />mean
              </button>
              <button class="key" aria-pressed={show.ensBand} onclick={() => (show.ensBand = !show.ensBand)}>
                <RoleGlyph shape="square" color="var(--chart-2)" variant="band" size={10} />spread ± 1σ
              </button>
              {#if read}<span class="key static num">used <b>{read.used}</b></span>{/if}
            {/if}
          </span>
        </header>
        <div class="lab-plot-host plot" {@attach facetHost(id, last)}></div>
      </section>
    {/each}

    {#if hover && read}
      <div class="lab-readout" style={tipStyle} aria-hidden="true">
        <div class="t">{read.utc} UTC · frame {read.frame}</div>
        <div>JD {read.jd}</div>
        <div>BJD {read.bjd} <span class="k">approx.</span></div>
        <hr />
        {#if facets.includes('target')}
          <div class="row"><RoleGlyph shape="circle" color="var(--chart-1)" size={11} /><span class="v">{read.target}</span><span class="k">V</span></div>
        {/if}
        {#if facets.includes('check')}
          <div class="row"><RoleGlyph shape="triangle" color="var(--chart-3)" size={11} /><span class="v">{read.check}</span><span class="k">K − cat</span></div>
        {/if}
        {#if facets.includes('ensemble')}
          <div class="row"><RoleGlyph shape="square" color="var(--chart-2)" size={11} /><span class="v">{read.ens} ± {read.spread}</span><span class="k">{read.used} used</span></div>
        {/if}
        <hr />
        <div>airmass <span class="v">{read.airmass}</span> · alt <span class="v">{read.alt}</span></div>
        {#each read.flags as f (f)}<div class="flag">flag: {f}</div>{/each}
      </div>
    {/if}
  </div>
  {#if !compact}<p class="axis-title num" data-export-text="muted">{axisTitle}</p>{/if}
</div>

<style>
  .lc {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: var(--chart-surface);
    outline-offset: -2px;
  }

  .bar {
    display: flex;
    align-items: center;
    gap: 2px;
    height: var(--lab-chart-toolbar-h);
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    background: var(--bg);
    flex: none;
    min-width: 0;
  }
  .compact .bar {
    height: 32px;
    gap: 1px;
  }
  .bar .lab-seg {
    margin-right: var(--space-1);
  }
  .title {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    margin-right: var(--space-2);
    font-size: var(--text-s);
    font-weight: var(--weight-semibold);
  }
  .compact .title + .lab-eyebrow {
    margin-right: var(--space-3);
  }
  .grow {
    flex: 1;
    min-width: var(--space-2);
  }
  .mode {
    margin-left: var(--space-1);
  }
  .mode .hint {
    display: inline-flex;
    align-items: center;
    gap: 3px;
  }
  .readout {
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-3);
    margin-right: var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
  }
  .readout .kind {
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: var(--tracking-caps);
  }
  .readout b {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .perf {
    margin-left: var(--space-1);
  }

  .wall {
    position: relative;
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 2px var(--space-3) 0 var(--space-2);
  }
  .facet {
    display: flex;
    flex-direction: column;
    flex-basis: 0;
    min-height: 70px;
  }
  .facet + .facet {
    border-top: var(--border-w) solid var(--border-soft);
  }
  header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: var(--lab-chart-header-h);
    padding-left: 50px;
    flex: none;
    min-width: 0;
  }
  .compact header {
    height: 18px;
    gap: var(--space-1);
  }
  .compact h3 {
    font-size: var(--text-xs);
  }
  .compact .key {
    height: 16px;
    font-size: var(--text-2xs);
  }
  h3 {
    margin: 0;
    font-size: var(--text-s);
    font-weight: var(--weight-semibold);
    color: var(--fg);
    white-space: nowrap;
  }
  .sub {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .compact .sub {
    display: none;
  }
  .legend {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    margin-left: var(--space-3);
    min-width: 0;
    overflow: hidden;
  }
  .key {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    height: 20px;
    padding: 0 6px;
    border: 0;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    cursor: pointer;
  }
  .key:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .key[aria-pressed='false'] {
    color: var(--fg-disabled);
  }
  .key[aria-pressed='false'] :global(.glyph) {
    opacity: 0.35;
  }
  .key.static {
    cursor: default;
    gap: 4px;
  }
  .key.static:hover {
    background: transparent;
    color: var(--text-muted);
  }
  .key b {
    color: var(--fg);
    font-weight: var(--weight-regular);
    margin-right: 6px;
  }
  .plot {
    flex: 1;
    min-height: 40px;
  }

  .axis-title {
    margin: 0;
    padding: 2px var(--space-3) 6px 58px;
    color: var(--text-muted);
    font-size: var(--text-2xs);
    letter-spacing: 0.02em;
    flex: none;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>

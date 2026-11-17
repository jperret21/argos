<!--
  Review plot wall (spec 07 WF-B, D4, D26; functional-spaces P12).

  - One star per cell (target, check, each comparison) plus HFD, all on one
    linked time axis: one crosshair across the wall (cursor sync), one zoom
    (drag, Ctrl / Cmd + wheel, F, double-click), so a dip can be compared
    between stars at a glance. Plain wheel scrolls the wall (it scrolls in
    the app); a hint says how to zoom.
  - A 56 px health strip on top: frames and gaps, HFD episodes above
    1.5 x baseline, frames with fewer comparisons than planned. The
    morning-after triage the owner's nights needed.
  - Click selects a time on every cell (dashed line + ring) and fills the
    Selected point card; Esc clears. Cell menu: copy TSV, save PNG, expand.
  - Comparison cells plot the leave-one-out residual; the scatter and the
    status word (Stable / Noisy / Unstable) sit in the header.
-->
<script lang="ts">
  import uPlot from 'uplot';
  import { untrack } from 'svelte';
  import Icon from '../../../lib/components/Icon.svelte';
  import { tooltip } from '../../../lib/components/tooltip';
  import { env, reducedMotion, toast } from '../env.svelte';
  import { clock } from '../sim/stream.svelte';
  import { CHECK, COMPS, FLAG_SATURATED, FLAG_SUSPECT, hfdEpisodes, NIGHT_LABEL, TARGET } from '../sim/night';
  import { jdFromUnix } from '../sim/astro';
  import { readInks, type ChartInks, type Ink } from '../core/palette';
  import { PlotHost } from '../core/uplot/host';
  import { TimeZoom, type ZoomMode } from '../core/uplot/zoom';
  import { markers, type Shape } from '../core/uplot/markers';
  import { annotations, type Annotation } from '../core/uplot/overlays';
  import { paddedRange, timeAxis, utcTz, valueAxis, type TimeAxisMode } from '../core/uplot/axes';
  import { robustSigma } from '../core/stats';
  import { browserExport, composeCanvas, toTsv } from '../core/export';
  import { fixed, grouped, isoUtc, julian, MINUS, signed } from '../core/format';
  import RoleGlyph from './RoleGlyph.svelte';

  type CellId = 'T' | 'K' | 'C1' | 'C2' | 'C3' | 'C4' | 'C5' | 'HFD';
  interface Cell {
    id: CellId;
    title: string;
    sub: string;
    shape: Shape;
    token: string;
    digits: number;
    minSpan: number;
    invert: boolean;
  }
  const CELLS: Cell[] = [
    { id: 'T', title: TARGET.label, sub: 'target · V', shape: 'circle', token: '--chart-1', digits: 2, minSpan: 0.1, invert: true },
    { id: 'K', title: 'Check', sub: `${CHECK.label} · minus catalogue`, shape: 'triangle', token: '--chart-3', digits: 3, minSpan: 0.04, invert: true },
    ...COMPS.map((c) => ({ id: c.key as CellId, title: c.key, sub: `${c.label.split(' · ')[1]} · leave-one-out residual`, shape: 'square' as Shape, token: '--chart-2', digits: 3, minSpan: 0.04, invert: true })),
    { id: 'HFD', title: 'HFD', sub: 'px · per frame', shape: 'dot', token: '--fg', digits: 1, minSpan: 1, invert: false },
  ];
  const JD0 = Math.floor(jdFromUnix(Date.UTC(2026, 10, 1, 18) / 1000));

  const stream = clock.night;
  const cols = stream.cols;
  // Nullable copies of the comparison residuals (NaN = not measured on that frame).
  const compNull = COMPS.map((_c, j) => Array.from(cols.comps[j], (v) => (Number.isFinite(v) ? v : null)));

  let root: HTMLDivElement;
  const hosts = new Map<string, PlotHost>();
  let inks: ChartInks | null = null;
  const syncKey = `wall-${Math.random().toString(36).slice(2, 8)}`;

  let axisMode = $state<TimeAxisMode>('utc');
  let showErrors = $state(true);
  let columns = $state<2 | 3>(3);
  let expanded = $state<CellId | null>(null);
  let selected = $state<number | null>(null);
  let count = $state(stream.n);
  let mode = $state<ZoomMode>('fit');
  let menuFor = $state<CellId | null>(null);
  let lastHint = 0;

  const zoom = new TimeZoom({
    extent: () => (stream.n ? [cols.t[0], cols.t[stream.n - 1]] : null),
    minSpan: 600,
    wheel: 'modifier',
    reducedMotion,
    onChange: (m) => (mode = m),
    onWheelHint: () => {
      const now = performance.now();
      if (now - lastHint > 4000) {
        lastHint = now;
        toast('Ctrl / ⌘ + wheel zooms time; the wheel alone scrolls the wall');
      }
    },
  });

  function yFor(id: CellId, n: number): ArrayLike<number | null> {
    if (id === 'T') return cols.target.subarray(0, n);
    if (id === 'K') return cols.checkDelta.subarray(0, n);
    if (id === 'HFD') return cols.hfd.subarray(0, n);
    return compNull[Number(id.slice(1)) - 1].slice(0, n);
  }
  function errFor(id: CellId): ArrayLike<number> | null {
    if (id === 'T') return cols.targetErr;
    if (id === 'K') return cols.checkErr;
    if (id === 'HFD') return null;
    return cols.compErr[Number(id.slice(1)) - 1];
  }
  const inkFor = (c: Cell): Ink => (c.id === 'T' ? inks!.target : c.id === 'K' ? inks!.check : c.id === 'HFD' ? inks!.fg : inks!.comparison);

  function dataFor(id: CellId): uPlot.AlignedData {
    const n = stream.n;
    return [cols.t.subarray(0, n), yFor(id, n) as number[]];
  }

  function annFor(id: CellId): Annotation[] {
    const ink = inks!;
    const out: Annotation[] = [];
    if (id === 'HFD') {
      for (const e of hfdEpisodes(cols, stream.n, 1.5)) {
        out.push({ kind: 'vspan', from: cols.t[e.fired], to: e.end !== null ? cols.t[e.end] : cols.t[stream.n - 1], fill: ink.warning.a(0.1), edge: ink.warning.a(0.6) });
      }
    }
    if (selected !== null && selected < stream.n) out.push({ kind: 'vline', x: cols.t[selected], color: ink.highlight.a(0.9), dash: [4, 3] });
    return out;
  }

  function cursorPoint(_u: uPlot, si: number): HTMLElement | undefined {
    if (si !== 1) return undefined;
    const el = document.createElement('div');
    el.style.cssText = 'width:10px;height:10px;margin:-5px 0 0 -5px';
    return el;
  }

  function options(c: Cell): uPlot.Options {
    const ink = inks!;
    return {
      width: 100,
      height: 100,
      padding: [6, 18, 0, 0],
      legend: { show: false },
      tzDate: utcTz,
      cursor: {
        sync: { key: syncKey, setSeries: false },
        points: { show: cursorPoint as unknown as boolean, size: 10, width: 1.5, stroke: () => ink.highlight.a(), fill: () => 'rgba(0,0,0,0)' },
        drag: { x: true, y: false, setScale: true, dist: 5 },
        bind: TimeZoom.cursorBind(),
        focus: { prox: -1 },
      },
      scales: { x: { time: axisMode === 'utc' }, y: { dir: c.invert ? -1 : 1, range: paddedRange(c.minSpan, 0.12) } },
      axes: [
        timeAxis(ink, { mode: axisMode, jd0: JD0, labels: true, size: 20, bjdOffsetS: (t) => cols.bjdOffsetS[Math.max(0, stream.indexAt(t))] ?? 69.184 }),
        valueAxis(ink, { format: (v) => (c.id === 'T' || c.id === 'HFD' ? fixed(v, c.digits) : signed(v, c.digits)), size: 48, space: 22 }),
      ],
      series: [{}, { stroke: inkFor(c).a(), paths: () => null, points: { show: false } }],
      plugins: [
        zoom.plugin(),
        annotations(() => annFor(c.id), () => inks!),
        markers({
          seriesIdx: 1,
          shape: c.shape,
          color: () => inkFor(c).a(c.id === 'HFD' ? 0.85 : 1),
          errors: () => errFor(c.id),
          showErrors: () => showErrors,
          errorAlpha: () => ink.errorAlpha,
          flags: () => (c.id === 'T' ? cols.flags : null),
          size: (v) => (v < 60 ? 7 : v < 400 ? 5 : 4),
          selected: () => (selected !== null && selected < stream.n ? { idx: selected, color: ink.highlight.a() } : null),
        }),
      ],
      hooks: {
        init: [
          (u) => {
            u.over.addEventListener('click', () => {
              if (u.cursor.idx != null) selected = u.cursor.idx;
            });
          },
        ],
      },
    };
  }

  /** The health strip: lanes on the same x scale as the cells. */
  function healthOptions(): uPlot.Options {
    const ink = inks!;
    const lanes = ['frames', 'HFD', 'comps'];
    return {
      width: 100,
      height: 100,
      padding: [4, 18, 0, 0],
      legend: { show: false },
      tzDate: utcTz,
      cursor: { sync: { key: syncKey, setSeries: false }, points: { show: false }, drag: { x: true, y: false, setScale: true, dist: 5 }, bind: TimeZoom.cursorBind(), focus: { prox: -1 } },
      scales: { x: { time: axisMode === 'utc' }, y: { range: [0, 3] } },
      axes: [
        { show: false },
        { stroke: ink.text.a(), size: 48, ticks: { show: false }, grid: { show: false }, splits: () => [], values: () => [] },
      ],
      series: [{}, { show: false }],
      plugins: [
        zoom.plugin(),
        {
          hooks: {
            draw: [
              (u) => {
                const dpr = uPlot.pxRatio;
                const { ctx } = u;
                const { left, top, width, height } = u.bbox;
                const n = stream.n;
                const laneH = height / 3;
                const X = (t: number) => u.valToPos(t, 'x', true);
                ctx.save();
                ctx.font = `500 ${9 * dpr}px ${ink.mono}`;
                ctx.textAlign = 'right';
                ctx.textBaseline = 'middle';
                ctx.fillStyle = ink.textMuted.a();
                lanes.forEach((l, k) => ctx.fillText(l, left - 6 * dpr, top + laneH * (k + 0.5)));
                ctx.beginPath();
                ctx.rect(left, top, width, height);
                ctx.clip();
                ctx.strokeStyle = ink.borderSoft.a();
                ctx.lineWidth = dpr;
                ctx.beginPath();
                for (let k = 1; k < 3; k++) {
                  ctx.moveTo(left, Math.round(top + laneH * k) + 0.5);
                  ctx.lineTo(left + width, Math.round(top + laneH * k) + 0.5);
                }
                ctx.stroke();
                const pad = 3 * dpr;
                // Lane 0: coverage, gaps left empty.
                ctx.fillStyle = ink.fgMuted.a(0.55);
                let i0 = 0;
                for (let i = 1; i <= n; i++) {
                  if (i === n || cols.t[i] - cols.t[i - 1] > 150) {
                    if (n) ctx.fillRect(X(cols.t[i0]), top + pad, Math.max(dpr, X(cols.t[i - 1]) - X(cols.t[i0])), laneH - 2 * pad);
                    i0 = i;
                  }
                }
                // Lane 1: HFD episodes.
                ctx.fillStyle = ink.warning.a(0.75);
                for (const e of hfdEpisodes(cols, n, 1.5)) {
                  const a = X(cols.t[e.start]);
                  const b = X(e.end !== null ? cols.t[e.end] : cols.t[n - 1]);
                  ctx.fillRect(a, top + laneH + pad, Math.max(dpr, b - a), laneH - 2 * pad);
                }
                // Lane 2: frames with comparisons missing.
                ctx.fillStyle = ink.fg.a(0.7);
                for (let i = 0; i < n; i++) {
                  if (cols.nUsed[i] >= COMPS.length) continue;
                  const a = X(cols.t[i]);
                  ctx.fillRect(a - dpr, top + 2 * laneH + pad, 2 * dpr, laneH - 2 * pad);
                }
                if (selected !== null && selected < n) {
                  const x = Math.round(X(cols.t[selected])) + 0.5;
                  ctx.strokeStyle = ink.highlight.a(0.9);
                  ctx.setLineDash([4 * dpr, 3 * dpr]);
                  ctx.beginPath();
                  ctx.moveTo(x, top);
                  ctx.lineTo(x, top + height);
                  ctx.stroke();
                }
                ctx.restore();
              },
            ],
          },
        },
      ],
      hooks: {
        init: [
          (u) => {
            u.over.addEventListener('click', () => {
              if (u.cursor.idx != null) selected = u.cursor.idx;
            });
          },
        ],
      },
    };
  }

  function cellHost(c: Cell) {
    return (el: HTMLElement) => {
      const h = new PlotHost(el, () => ({ opts: options(c), data: dataFor(c.id) }));
      hosts.set(c.id, h);
      return () => {
        h.destroy();
        hosts.delete(c.id);
      };
    };
  }
  function healthHost(el: HTMLElement) {
    const h = new PlotHost(el, () => ({ opts: healthOptions(), data: [cols.t.subarray(0, stream.n), cols.hfd.subarray(0, stream.n)] }));
    hosts.set('health', h);
    return () => {
      h.destroy();
      hosts.delete('health');
    };
  }

  function rebuild(): void {
    inks = readInks(root);
    zoom.update();
    for (const h of hosts.values()) h.build();
  }

  function push(): void {
    if (!inks) return;
    zoom.update();
    for (const [id, h] of hosts) {
      const u = h.u;
      if (!u) continue;
      zoom.batch(u, () => u.setData(id === 'health' ? [cols.t.subarray(0, stream.n), cols.hfd.subarray(0, stream.n)] : dataFor(id as CellId), false));
    }
    zoom.notify();
    count = stream.n;
  }
  let raf = 0;
  const schedule = () => {
    if (!raf)
      raf = requestAnimationFrame(() => {
        raf = 0;
        push();
      });
  };
  $effect(() => untrack(() => stream.onAppend(schedule)));
  $effect(() => {
    void env.theme;
    void axisMode;
    untrack(rebuild);
  });
  $effect(() => {
    void selected;
    void showErrors;
    untrack(() => {
      for (const h of hosts.values()) h.u?.redraw(false, false);
    });
  });
  $effect(() => {
    void expanded;
    void columns;
    // Layout changed: the hosts resize themselves (ResizeObserver); cursor rects need a refresh.
    requestAnimationFrame(() => {
      for (const h of hosts.values()) h.u?.syncRect();
    });
  });

  $effect(() => {
    (window as unknown as { __wall?: unknown }).__wall = {
      select: (i: number) => (selected = i),
      expand: (id: CellId | null) => (expanded = id),
    };
  });

  function onKey(e: KeyboardEvent): void {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key;
    if (k === 'f' || k === 'F') zoom.fit(true);
    else if (k === '+' || k === '=') zoom.zoomBy(1 / 1.6, undefined, true);
    else if (k === '-' || k === '_') zoom.zoomBy(1.6, undefined, true);
    else if (k === 'ArrowLeft' && selected !== null) selected = Math.max(0, selected - 1);
    else if (k === 'ArrowRight' && selected !== null) selected = Math.min(stream.n - 1, selected + 1);
    else if (k === 'ArrowLeft') zoom.panBy(-0.25, true);
    else if (k === 'ArrowRight') zoom.panBy(0.25, true);
    else if (k === 'u' || k === 'U') showErrors = !showErrors;
    else if (k === 'Escape') {
      if (menuFor) menuFor = null;
      else if (expanded) expanded = null;
      else selected = null;
    } else return;
    e.preventDefault();
  }

  // -- Cell statistics ------------------------------------------------------------------
  const cellStats = $derived.by(() => {
    void count;
    const n = stream.n;
    const out = new Map<CellId, { n: number; sigma: number; status: string | null; lo: number; hi: number }>();
    for (const c of CELLS) {
      const ys = c.id === 'T' ? cols.target : c.id === 'K' ? cols.checkDelta : c.id === 'HFD' ? cols.hfd : cols.comps[Number(c.id.slice(1)) - 1];
      let k = 0;
      let lo = Infinity;
      let hi = -Infinity;
      for (let i = 0; i < n; i++) {
        if (!Number.isFinite(ys[i])) continue;
        k++;
        if (c.id === 'T' && cols.flags[i]) continue;
        lo = Math.min(lo, ys[i]);
        hi = Math.max(hi, ys[i]);
      }
      const sigma = robustSigma(ys, 0, n);
      const status = c.id.startsWith('C') || c.id === 'K' ? (sigma < 0.012 ? 'Stable' : sigma < 0.02 ? 'Noisy' : 'Unstable') : null;
      out.set(c.id, { n: k, sigma, status, lo, hi });
    }
    return out;
  });

  async function copyCell(c: Cell): Promise<void> {
    menuFor = null;
    const n = stream.n;
    const ys = yFor(c.id, n);
    const es = errFor(c.id);
    const rows: (string | number)[][] = [];
    for (let i = 0; i < n; i++) {
      const v = ys[i];
      if (v == null) continue;
      rows.push([isoUtc(cols.t[i]).replace(' UTC', 'Z').replace(' ', 'T'), (jdFromUnix(cols.t[i]) + cols.bjdOffsetS[i] / 86400).toFixed(6), v.toFixed(4), es ? es[i].toFixed(4) : '']);
    }
    toast(await browserExport.tsv(`${c.title}-${NIGHT_LABEL}.tsv`, toTsv(['utc', 'bjd_tdb_approx', c.id === 'HFD' ? 'hfd_px' : 'mag', 'err'], rows), rows.length));
  }
  async function pngCell(c: Cell): Promise<void> {
    menuFor = null;
    const el = root.querySelector(`[data-cell="${c.id}"]`) as HTMLElement | null;
    if (!el || !inks) return;
    const canvas = composeCanvas(el, inks.surface.a(), [...el.querySelectorAll('[data-export-text]')].map((t) => ({ el: t, color: inks!.fg.a(), font: `500 11px ${inks!.ui}` })));
    toast(await browserExport.png(`${c.title}-${NIGHT_LABEL}.png`, canvas));
  }

  const sel = $derived.by(() => {
    void count;
    if (selected === null || selected >= stream.n) return null;
    const i = selected;
    const t = cols.t[i];
    const jd = jdFromUnix(t);
    return {
      i,
      utc: isoUtc(t),
      jd: julian(jd),
      bjd: julian(jd + cols.bjdOffsetS[i] / 86400),
      target: `${fixed(cols.target[i], 3)} ± ${fixed(cols.targetErr[i], 3)}`,
      check: `${signed(cols.checkDelta[i], 3)} ± ${fixed(cols.checkErr[i], 3)}`,
      comps: COMPS.map((c, j) => ({ key: c.key, v: Number.isFinite(cols.comps[j][i]) ? signed(cols.comps[j][i], 3) : 'not measured' })),
      used: `${cols.nUsed[i]} / ${COMPS.length}`,
      airmass: fixed(cols.airmass[i], 3),
      hfd: fixed(cols.hfd[i], 2),
      fwhm: fixed(cols.fwhm[i], 2),
      sky: grouped(cols.sky[i]),
      flags: [cols.flags[i] & FLAG_SUSPECT ? 'suspect' : '', cols.flags[i] & FLAG_SATURATED ? 'saturated' : ''].filter(Boolean).join(', ') || '–',
      file: `SW_And_20261101_e010000ms_g080_${String(i + 1).padStart(5, '0')}.fit`,
    };
  });

  const visibleCells = $derived(expanded ? CELLS.filter((c) => c.id === expanded) : CELLS);
  const AXES: { id: TimeAxisMode; label: string }[] = [
    { id: 'utc', label: 'UTC' },
    { id: 'jd', label: 'JD' },
    { id: 'bjd', label: 'BJD' },
  ];
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
<div class="pw" bind:this={root} role="region" aria-label="Review plot wall" tabindex="0" onkeydown={onKey}>
  <div class="bar">
    <Icon name="open-session" size={16} />
    <span class="ident"><b>{TARGET.label}</b> · {NIGHT_LABEL} 18:40 → 02:05 UTC · {grouped(count)} lights · V (TG) · 10 s · gain 80</span>
    <span class="lab-sep"></span>
    <div class="lab-seg mono" role="radiogroup" aria-label="Time axis">
      {#each AXES as a (a.id)}
        <button role="radio" aria-checked={axisMode === a.id} onclick={() => (axisMode = a.id)}>{a.label}</button>
      {/each}
    </div>
    <button class="lab-tool" aria-label="Error bars" aria-keyshortcuts="U" aria-pressed={showErrors} use:tooltip={{ text: 'Error bars', shortcut: 'U' }} onclick={() => (showErrors = !showErrors)}>
      <Icon name="error-bars" size={16} />
    </button>
    <button class="lab-tool" aria-label="Fit every cell" aria-keyshortcuts="F" use:tooltip={{ text: 'Fit every cell', shortcut: 'F' }} onclick={() => zoom.fit(true)}>
      <Icon name="zoom-fit" size={16} />
    </button>
    <span class="lab-chip mode">{mode === 'fit' ? 'Whole session' : 'Zoom kept · F fits'}</span>
    <span class="grow"></span>
    <button class="lab-tool layout" aria-label="Columns" aria-pressed={columns === 3} use:tooltip={{ text: columns === 3 ? 'Two columns' : 'Three columns' }} onclick={() => (columns = columns === 3 ? 2 : 3)}>
      <Icon name="layout-tile" size={16} />
    </button>
  </div>

  <div class="body">
    <div class="wallcol">
      <div class="health">
        <div class="lab-plot-host hplot" {@attach healthHost}></div>
      </div>
      <div class="wall" style:--cols={expanded ? 1 : columns}>
        {#each visibleCells as c (c.id)}
          {@const st = cellStats.get(c.id)}
          <section class="cell" class:expanded={expanded === c.id} data-cell={c.id} aria-label="{c.title}: {c.sub}">
            <header>
              {#if c.id === 'HFD'}
                <Icon name="focus-metrics" size={14} />
              {:else}
                <RoleGlyph shape={c.shape} color="var({c.token})" />
              {/if}
              <h4 data-export-text>{c.title}</h4>
              <span class="sub">{c.sub}</span>
              <span class="grow"></span>
              {#if st}
                <span class="stat num">n {st.n} · {c.id === 'T' ? `${fixed(st.lo, 2)}–${fixed(st.hi, 2)}` : `σ ${fixed(st.sigma, c.id === 'HFD' ? 2 : 3)}`}</span>
                {#if st.status}<span class="status" class:warn={st.status !== 'Stable'}>{st.status}</span>{/if}
              {/if}
              <span class="tools">
                <button class="lab-tool s" aria-label={expanded === c.id ? 'Restore the wall' : `Expand ${c.title}`} aria-pressed={expanded === c.id} use:tooltip={{ text: expanded === c.id ? 'Restore the wall (Esc)' : 'Expand this cell' }} onclick={() => (expanded = expanded === c.id ? null : c.id)}>
                  <Icon name={expanded === c.id ? 'zoom-out' : 'zoom-fill'} size={14} />
                </button>
                <button class="lab-tool s" aria-label="Cell menu" aria-haspopup="menu" aria-expanded={menuFor === c.id} onclick={() => (menuFor = menuFor === c.id ? null : c.id)}>
                  <Icon name="disclosure" size={14} />
                </button>
              </span>
              {#if menuFor === c.id}
                <div class="menu" role="menu">
                  <button role="menuitem" onclick={() => copyCell(c)}><Icon name="copy" size={14} />Copy data (TSV)</button>
                  <button role="menuitem" onclick={() => pngCell(c)}><Icon name="export" size={14} />Save as PNG</button>
                  <button role="menuitem" onclick={() => { menuFor = null; expanded = expanded === c.id ? null : c.id; }}><Icon name="zoom-fill" size={14} />{expanded === c.id ? 'Restore the wall' : 'Expand'}</button>
                </div>
              {/if}
            </header>
            <div class="lab-plot-host plot" {@attach cellHost(c)}></div>
          </section>
        {/each}
      </div>
      <p class="axis-title num">{axisMode === 'utc' ? `UTC · night of ${NIGHT_LABEL}` : `${axisMode === 'jd' ? 'JD' : 'BJD_TDB (approx.)'} ${MINUS} ${JD0}`} · click a point to select a time · Ctrl / ⌘ + wheel zooms</p>
    </div>

    <aside class="rail">
      <section class="card">
        <header><Icon name="crosshair" size={16} /><h3>Selected point</h3></header>
        {#if sel}
          <dl class="kv num">
            <dt>UTC</dt><dd>{sel.utc.replace(' UTC', '')}</dd>
            <dt>JD</dt><dd>{sel.jd}</dd>
            <dt>BJD</dt><dd>{sel.bjd} <span class="muted">approx.</span></dd>
          </dl>
          <div class="stars">
            <div class="srow"><RoleGlyph shape="circle" color="var(--chart-1)" size={11} /><span>{TARGET.label}</span><b class="num">{sel.target}</b></div>
            <div class="srow"><RoleGlyph shape="triangle" color="var(--chart-3)" size={11} /><span>Check</span><b class="num">{sel.check}</b></div>
            {#each sel.comps as cp (cp.key)}
              <div class="srow"><RoleGlyph shape="square" color="var(--chart-2)" size={11} /><span>{cp.key}</span><b class="num">{cp.v}</b></div>
            {/each}
          </div>
          <dl class="kv num">
            <dt>comps</dt><dd>{sel.used}</dd>
            <dt>airmass</dt><dd>{sel.airmass}</dd>
            <dt>HFD · FWHM</dt><dd>{sel.hfd} · {sel.fwhm} px</dd>
            <dt>sky</dt><dd>{sel.sky} ADU</dd>
            <dt>flags</dt><dd>{sel.flags}</dd>
          </dl>
          <p class="file num">{sel.file}</p>
          <button class="lab-btn" onclick={() => toast('Frame inspector (R2) would open this frame')}><Icon name="open-image" size={14} />Open frame</button>
        {:else}
          <p class="empty">Click a point on any cell to read every star at that time. ← → step frame by frame, Esc clears.</p>
        {/if}
      </section>
      <section class="card">
        <header><Icon name="comparison-quality" size={16} /><h3>Comparison quality</h3></header>
        <table class="cq num">
          <thead><tr><th>star</th><th>n</th><th>σ</th><th>status</th></tr></thead>
          <tbody>
            {#each COMPS as cp (cp.key)}
              {@const st = cellStats.get(cp.key as CellId)}
              <tr class:on={expanded === cp.key}>
                <td><button class="rowbtn" aria-pressed={expanded === cp.key} onclick={() => (expanded = expanded === cp.key ? null : (cp.key as CellId))}>{cp.label}</button></td><td>{st?.n}</td><td>{fixed(st?.sigma ?? NaN, 3)}</td><td class:warn={st?.status !== 'Stable'}>{st?.status}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    </aside>
  </div>
</div>

<style>
  .pw {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: var(--bg);
    outline-offset: -2px;
  }
  .bar {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: var(--lab-chart-toolbar-h);
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--fg-muted);
    flex: none;
  }
  .ident {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .ident b {
    color: var(--fg);
    font-weight: var(--weight-semibold);
  }
  .grow {
    flex: 1;
  }
  .body {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) 320px;
  }
  .wallcol {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    background: var(--chart-surface);
  }
  .health {
    position: relative;
    height: 62px;
    flex: none;
    padding: 4px var(--space-2) 2px 0;
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .hplot {
    height: 100%;
  }
  .wall {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: repeat(var(--cols), minmax(0, 1fr));
    grid-auto-rows: minmax(200px, 1fr);
    overflow: auto;
  }
  .cell {
    position: relative;
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: var(--chart-surface);
    border-right: var(--border-w) solid var(--border-soft);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .cell header {
    position: relative;
    display: flex;
    align-items: center;
    gap: 6px;
    height: 26px;
    padding: 0 4px 0 10px;
    color: var(--fg-muted);
    flex: none;
  }
  h4 {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-semibold);
    white-space: nowrap;
  }
  .sub {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }
  .stat {
    color: var(--text-muted);
    font-size: var(--text-2xs);
    white-space: nowrap;
  }
  .status {
    padding: 0 5px;
    border: 1px solid var(--border-soft);
    border-radius: var(--radius-s);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    white-space: nowrap;
  }
  .status.warn {
    border-color: var(--warning);
    color: var(--fg);
  }
  .tools {
    display: inline-flex;
  }
  .menu {
    position: absolute;
    top: 26px;
    right: 4px;
    z-index: var(--z-popover);
    display: grid;
    min-width: 180px;
    padding: 4px;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg-2);
    box-shadow: var(--shadow-2);
  }
  .menu button {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: 28px;
    padding: 0 var(--space-2);
    border: 0;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-s);
    text-align: left;
    cursor: pointer;
  }
  .menu button:hover {
    background: var(--hover-bg);
  }
  .plot {
    flex: 1;
    min-height: 60px;
    margin: 0 var(--space-2) var(--space-1) 0;
  }
  .axis-title {
    margin: 0;
    padding: 4px var(--space-3) 6px 58px;
    color: var(--text-muted);
    font-size: var(--text-2xs);
    flex: none;
    border-top: var(--border-w) solid var(--border-soft);
  }
  .rail {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-3);
    border-left: var(--border-w) solid var(--border);
    overflow: auto;
  }
  .card {
    display: grid;
    gap: var(--space-2);
    padding: 12px 14px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
  }
  .card header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--fg-muted);
  }
  .card h3 {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  .kv {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 3px var(--space-3);
    margin: 0;
    font-size: var(--text-xs);
  }
  .kv dt {
    color: var(--text-muted);
  }
  .kv dd {
    margin: 0;
    text-align: right;
  }
  .muted {
    color: var(--text-muted);
  }
  .stars {
    display: grid;
    gap: 2px;
    padding: 6px 0;
    border-top: 1px solid var(--border-soft);
    border-bottom: 1px solid var(--border-soft);
  }
  .srow {
    display: grid;
    grid-template-columns: 14px 1fr auto;
    align-items: center;
    gap: 6px;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .srow b {
    color: var(--fg);
    font-weight: var(--weight-regular);
  }
  .file {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-2xs);
    word-break: break-all;
  }
  .empty {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
    line-height: var(--leading-relaxed);
  }
  .cq {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-xs);
  }
  .cq th {
    color: var(--text-muted);
    font-weight: var(--weight-regular);
    text-align: right;
    padding: 2px 4px;
  }
  .cq th:first-child,
  .cq td:first-child {
    text-align: left;
    font-family: var(--font-ui);
  }
  .cq td {
    padding: 3px 4px;
    text-align: right;
    border-top: 1px solid var(--border-soft);
    cursor: pointer;
  }
  .cq tr:hover td {
    background: var(--hover-bg);
  }
  .cq tr.on td {
    background: var(--toggled-bg);
  }
  .rowbtn {
    padding: 0;
    border: 0;
    background: none;
    color: var(--fg);
    font-size: var(--text-xs);
    cursor: pointer;
  }
  .cq td.warn {
    color: var(--fg);
  }
</style>

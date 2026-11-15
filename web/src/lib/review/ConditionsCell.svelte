<!--
  The wall's Conditions cell (decision D6; spec 07 E9 "Frame quality", 08 "Quality trend"):
  one frame metric of the session (HFD, FWHM, stars, sky, airmass, eccentricity, sensor
  temperature) at each light frame's mid-exposure, on the wall's time axis (CurveLink: one
  zoom, one crosshair, one selected time with the light curves), so a seeing or sky spike
  lines up with the curve feature it explains (fixes 07 P17). Neutral ink (BRAND 10:
  geometry and conditions never wear a role colour); airmass is drawn with 1.0 at the top.
  The median is the dashed reference line; for HFD the 1.5 × median threshold of the health
  strip is the warning line.
  Same plot frame as a LightCurvePlot facet (50 px value axis, 18 px right pad, 24 px title
  row in the top margin), so the time axes of a column line up.
-->
<script lang="ts">
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import '../charts/plot-host.css';
  import { untrack, type Snippet } from 'svelte';
  import { DASH, fixed, int } from '../format/number';
  import { clockUtc, julian, utcDate } from '../format/time';
  import { readInks, type ChartInks } from '../charts/ink';
  import { padRange, stepDigits, timeAxis, JD_UNIX_EPOCH } from '../charts/uplot/axes';
  import { PlotHost } from '../charts/uplot/host';
  import { markers } from '../charts/uplot/markers';
  import { annotations, type Annotation } from '../charts/uplot/overlays';
  import { niceSplits, padPixels } from '../charts/lightcurve/facets';
  import { medianOf } from '../charts/lightcurve/trailing';
  import type { CurveLink } from '../charts/lightcurve/link.svelte';
  import type { CurveDisplayLike } from '../charts/lightcurve/view.svelte';
  import type { StarCurve } from '../charts/lightcurve/store';
  import Icon from '../components/Icon.svelte';
  import { METRICS, metricSeries, type MetricId, type MetricSeries, type WallFrame } from './wall';

  interface Props {
    frames: readonly WallFrame[];
    metric: MetricId;
    /** The target curve (airmass when the frames carry none; BJD ticks). */
    target: StarCurve | null;
    link: CurveLink;
    display: CurveDisplayLike;
    /** Re-read the data when this changes (the source's version). */
    version: number;
    theme?: unknown;
    /** The cell's tools, at the end of the title row. */
    headerEnd?: Snippet;
    /** The metric picker: the cell's name ("HFD (px) ⌄"), after its icon. */
    picker?: Snippet;
    /** The title (the picker names the metric; this is its accessible name). */
    label?: string;
  }

  let { frames, metric, target, link, display, version, theme, headerEnd, picker, label = 'Conditions' }: Props = $props();

  const def = $derived(METRICS[metric]);
  const series: MetricSeries = $derived.by(() => {
    void version;
    return metricSeries(frames, metric, target);
  });
  const median = $derived(series.any ? medianOf(series.y, series.n) : NaN);

  let root: HTMLDivElement;
  let wall = $state<HTMLDivElement | undefined>();
  let host: PlotHost | null = null;
  let inks: ChartInks | null = null;
  let hover = $state<{ i: number; left: number; top: number } | null>(null);
  let downAt: { x: number; y: number } | null = null;
  let active = false;

  const TITLE_PX = 24;
  const MARGIN_PX = 8;

  const timeInfo = $derived.by(() => {
    void version;
    const c = target?.cols;
    const t0 = series.n ? series.x[0] : c && c.n ? c.t[0] : NaN;
    let bjdOk = !!c && c.n > 0;
    for (let i = 0; c && i < c.n && bjdOk; i++) bjdOk = Number.isFinite(c.bjd[i]);
    const jd0 = Number.isFinite(t0) ? Math.floor(t0 / 86400 + JD_UNIX_EPOCH) : 0;
    return { jd0, bjd0: bjdOk && c ? Math.floor(c.bjd[0]) : jd0, date: Number.isFinite(t0) ? utcDate(t0) : '' };
  });

  function bjdOffsetS(t: number): number {
    const c = target?.cols;
    if (!c || !c.n) return 0;
    const i = c.nearest(t);
    const off = (c.bjd[i] - c.jd[i]) * 86400;
    return Number.isFinite(off) ? off : 0;
  }

  function selectedIdx(): number | null {
    const t = link.selection.t;
    if (t === null || !series.n) return null;
    let best = -1;
    for (let i = 0; i < series.n; i++) if (best < 0 || Math.abs(series.x[i] - t) < Math.abs(series.x[best] - t)) best = i;
    // Within half a cadence (the light curves' tolerance), else no frame is "that frame".
    const cad = series.n > 1 ? (series.x[series.n - 1] - series.x[0]) / (series.n - 1) : 30;
    return best >= 0 && Math.abs(series.x[best] - t) <= Math.max(1, cad / 2) ? best : null;
  }

  function annFor(): Annotation[] {
    const ink = inks;
    if (!ink) return [];
    const out: Annotation[] = [];
    // Each reference line says what it is at its right end (design review).
    if (Number.isFinite(median)) out.push({ kind: 'hline', y: median, color: ink.reference.a(0.55), dash: [2, 3], layer: 'under', label: { text: `median ${fixed(median, median >= 100 ? 0 : 1)}`, at: 'right', color: ink.text.a(), halo: true } });
    if (metric === 'hfd' && Number.isFinite(median)) out.push({ kind: 'hline', y: median * 1.5, color: ink.warning.a(0.75), dash: [4, 3], layer: 'under', label: { text: '1.5×', at: 'right', color: ink.warning.a(), halo: true } });
    if (link.selection.t !== null) out.push({ kind: 'vline', x: link.selection.t, color: ink.highlight.a(0.9), dash: [4, 3] });
    return out;
  }

  /** The y range over the frames in view (uPlot's own min / max takes a leading NaN). */
  function yRange(u: uPlot): [number, number] {
    const px = u.bbox.height / uPlot.pxRatio;
    const a = u.scales.x.min ?? -Infinity;
    const b = u.scales.x.max ?? Infinity;
    let lo = Infinity;
    let hi = -Infinity;
    for (let i = 0; i < series.n; i++) {
      const x = series.x[i];
      const v = series.y[i];
      if (x < a || x > b || !Number.isFinite(v)) continue;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    const extra = metric === 'hfd' && Number.isFinite(median) ? [median * 1.5] : [];
    const [l, h] = padRange(Number.isFinite(lo) ? lo : null, Number.isFinite(hi) ? hi : null, def.minSpan, 0, extra);
    return padPixels(l, h, px, MARGIN_PX);
  }

  function options(): uPlot.Options {
    const ink = inks!;
    const font = `400 10px ${ink.mono}`;
    return {
      width: 100,
      height: 100,
      padding: [TITLE_PX, 18, 0, 0],
      legend: { show: false },
      cursor: {
        sync: { key: link.syncKey, setSeries: false },
        points: { show: false },
        drag: { x: true, y: false, setScale: true, dist: 5 },
        bind: { dblclick: () => () => null },
        focus: { prox: -1 },
      },
      scales: { x: { time: false }, y: { dir: def.invert ? -1 : 1, range: (u) => yRange(u) } },
      axes: [
        timeAxis(ink, { mode: display.axis, labels: true, suffix: true, jd0: display.axis === 'bjd' ? timeInfo.bjd0 : timeInfo.jd0, bjdOffsetS }),
        {
          stroke: ink.text.a(),
          font,
          size: 50,
          gap: 5,
          ticks: { show: false },
          grid: { stroke: ink.grid.a(), width: 1 },
          splits: (u) => {
            const { min, max } = u.scales.y;
            if (min == null || max == null) return [];
            const px = u.bbox.height / uPlot.pxRatio;
            const m = ((max - min) * MARGIN_PX) / Math.max(1, px);
            return niceSplits(min + m, max - m, Math.max(0, px - 2 * MARGIN_PX), 13, 3).splits;
          },
          values: (_u, splits) => {
            const step = splits.length > 1 ? Math.abs(splits[1] - splits[0]) : 1;
            const digits = Math.min(3, stepDigits(step));
            return splits.map((v) => (v == null ? '' : fixed(v, digits)));
          },
        },
      ],
      series: [{}, { stroke: ink.fg.a(), paths: () => null, points: { show: false } }],
      plugins: [
        link.zoom.plugin(),
        annotations(annFor, () => inks),
        markers({
          seriesIdx: 1,
          // A hollow diamond: not a star (BRAND principle 6 keeps the filled circle for the target).
          shape: 'diamond',
          outline: true,
          color: () => ink.fg.a(0.85),
          selected: () => {
            const i = selectedIdx();
            return i !== null && inks ? { idx: i, color: inks.highlight.a() } : null;
          },
        }),
      ],
      hooks: {
        init: [
          (u) => {
            u.over.addEventListener('pointerenter', () => (active = true));
            u.over.addEventListener('pointerleave', () => {
              active = false;
              hover = null;
            });
            u.over.addEventListener('pointerdown', (e) => (downAt = { x: e.clientX, y: e.clientY }));
            u.over.addEventListener('click', (e) => {
              if (downAt && Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) > 4) return;
              const i = u.cursor.idx;
              if (i == null || i >= series.n) return link.select(null);
              const px = u.valToPos(series.x[i], 'x');
              const rect = u.over.getBoundingClientRect();
              link.select(Math.abs(px - (e.clientX - rect.left)) <= 12 ? series.x[i] : null);
            });
          },
        ],
        setCursor: [
          (u) => {
            if (!active || !wall) return;
            const i = u.cursor.idx;
            const left = u.cursor.left ?? -1;
            if (i == null || left < 0 || i >= series.n) {
              hover = null;
              return;
            }
            const wr = wall.getBoundingClientRect();
            const or = u.over.getBoundingClientRect();
            hover = { i, left: or.left - wr.left + left, top: or.top - wr.top + (u.cursor.top ?? 0) };
          },
        ],
      },
    };
  }

  function data(): uPlot.AlignedData {
    return [series.x.subarray(0, series.n), series.y.subarray(0, series.n)] as unknown as uPlot.AlignedData;
  }

  function attach(el: HTMLElement) {
    inks ??= readInks(el);
    host = new PlotHost(el, () => ({ opts: options(), data: data() }), (u) => link.zoom.batch(u, () => {}));
    return () => {
      host?.destroy();
      host = null;
    };
  }

  // Theme, axis, metric or data: rebuild (the group's zoom view is kept).
  $effect(() => {
    void theme;
    void display.axis;
    void series;
    void timeInfo.jd0;
    untrack(() => {
      if (!root) return;
      inks = readInks(root);
      link.zoom.update();
      host?.build();
    });
  });
  // Selection: a redraw.
  $effect(() => {
    void link.selection.t;
    untrack(() => host?.u?.redraw(false, false));
  });

  const hoverText = $derived.by(() => {
    if (!hover || hover.i >= series.n) return null;
    const t = series.x[hover.i];
    const v = series.y[hover.i];
    return { utc: clockUtc(t), jd: julian(t / 86400 + JD_UNIX_EPOCH), value: Number.isFinite(v) ? (def.digits === 0 ? int(v) : fixed(v, def.digits)) : DASH };
  });
  const selText = $derived.by(() => {
    void link.selection.t;
    const i = selectedIdx();
    if (i === null) return null;
    const v = series.y[i];
    return Number.isFinite(v) ? (def.digits === 0 ? int(v) : fixed(v, def.digits)) : DASH;
  });
  const tipStyle = $derived.by(() => {
    if (!hover || !wall) return '';
    const w = wall.clientWidth;
    const left = hover.left + 16 + 200 <= w ? hover.left + 16 : hover.left - 16 - 200;
    return `left:${Math.max(0, left)}px;top:${Math.max(4, Math.min(wall.clientHeight - 90, hover.top - 30))}px`;
  });
</script>

<div class="cc" bind:this={root} role="group" aria-label="{label}: {def.label}{def.unit ? ` (${def.unit})` : ''}, {series.source}">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="wall" bind:this={wall} onpointerleave={() => (hover = null)}>
    <header>
      <Icon name="session-metrics" size={14} />
      {#if picker}<span class="pick">{@render picker()}</span>{:else}<span class="name">{def.label}{def.unit ? ` (${def.unit})` : ''}</span>{/if}
      <span class="sub">{series.source}</span>
      {#if selText !== null}<span class="rd num"><span class="v">{selText}</span><span class="ring" aria-hidden="true"></span></span>{/if}
      {#if headerEnd}<span class="end">{@render headerEnd()}</span>{/if}
    </header>
    {#if series.any}
      <div class="plot-host plot" {@attach attach}></div>
    {:else}
      <p class="missing">
        {metric === 'airmass' ? 'No airmass: the frames carry no AIRMASS and no curve has one' : `No ${def.label} in this session's frames`}
      </p>
    {/if}
    {#if hover && hoverText}
      <div class="tip num" style={tipStyle} aria-hidden="true">
        <div class="t">{hoverText.utc} UTC · {timeInfo.date}</div>
        <div>JD {hoverText.jd} · mid-exposure</div>
        <div>{def.label} <span class="v">{hoverText.value}</span> {def.unit}</div>
      </div>
    {/if}
  </div>
</div>

<style>
  .cc {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    min-width: 0;
    background: var(--chart-surface);
  }
  .wall {
    position: relative;
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 2px var(--space-2) 0 var(--space-1);
  }
  header {
    position: absolute;
    z-index: 1;
    top: 2px;
    left: calc(50px + var(--space-1));
    right: calc(18px + var(--space-2));
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: 24px;
    color: var(--fg-muted);
    min-width: 0;
    overflow: hidden;
    pointer-events: none;
  }
  .pick {
    display: inline-flex;
    flex: none;
    pointer-events: auto;
  }
  .name {
    flex: none;
    color: var(--fg);
    font-size: var(--text-s);
    white-space: nowrap;
  }
  .sub {
    flex: 0 1 auto;
    min-width: 0;
    overflow: hidden;
    color: var(--text-muted);
    font-size: var(--text-xs);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .rd {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    margin-left: auto;
    color: var(--fg);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .ring {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--chart-highlight);
  }
  .end {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: 2px;
    margin-left: auto;
    pointer-events: auto;
  }
  .rd + .end {
    margin-left: var(--space-1);
  }
  .plot {
    flex: 1;
    min-height: 0;
  }
  .missing {
    margin: 32px 0 0 56px;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .tip {
    position: absolute;
    z-index: 2;
    width: 200px;
    padding: var(--space-2) var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg);
    box-shadow: var(--shadow-2);
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: 1.55;
    pointer-events: none;
  }
  .tip .t,
  .tip .v {
    color: var(--fg);
  }
</style>

<!--
  Live differential light curve: ONE component for the Observe Run band, the
  drawer's Light curve tab and (wave 7) Review (web/lab/PROPOSAL.md 3.2 and 6,
  W5). Merged from src/lab/charts/charts/LightCurve.svelte, core/uplot/*,
  src/lab/research/curve/* and src/lab/workspace/charts/LightCurve.svelte.

  Facets on one linked time axis, one y axis each, never more than three
  series per plot (BRAND 10):
  - Target (circles): the differential magnitude, axis inverted (brighter
    up), error bars = the server's mag_err (with the run-level floor, S19).
  - Check (triangles): check − its catalogue magnitude (D10), with the
    trailing 15-point mean ± 1 sigma as a band and a zero line: the
    photometry is trustworthy while the band stays thin and near zero.
  - Ensemble (squares, drawer and Review): per frame, the target's ensemble
    zero point (mean of catalogue − instrumental over the comparisons used)
    ± its rms: the night's extinction and transparency, up = more light.
  Y axes: at least three labelled values on a 1 / 2 / 5 step; the check on a
  symmetric ±rung scale that holds its band and 90 % of the points (the
  others are carets on the edge), so its height shows its scatter. The y
  range is padded in pixels: a marker and the newest ring are never cut.
  Facet titles sit in the plot's top margin; a facet that would get less
  than its floor (target 48 px, check 32 px) is left out and the target's
  title says the check's σ and check − V instead.
  Relative flux view (M): median-normalised flux (S16 baseline), not
  inverted; ratio-only points (S18) appear there.
  Flags by shape: suspect = hollow, saturated = x. The newest point wears a
  static ring in --chart-highlight; a selected time a wider one.

  Liveness: while frames are expected the x range ends at NOW; past
  max(2 x cadence, cadence + 60 s) the gap after the newest point is
  hatched and the now-line says "no frame for …" (BRAND 10).

  Zoom states named by a chip (Whole run, Following, Zoom kept): drag = box
  zoom, wheel / pinch = zoom time about the pointer, Shift+wheel or a
  horizontal swipe = pan, double-click or F = fit, + / − zoom, End follows,
  Shift+← / → pan, ← / → step the selected point, U error bars, M magnitude
  / relative flux. New frames never move a kept zoom. Escape is left to the
  app (abort a slew).

  Time stays unix seconds on the x scale; UTC / JD / BJD only change the
  ticks (D26). One readout for every series at the hovered, selected or
  newest frame (UTC, JD, BJD to 5 decimals). Copy data (TSV): every frame
  with full precision.

  Data never enters the reactive graph: typed-array columns in the store,
  subarray views for uPlot, one batched setData + setScale per facet per
  animation frame (store.onChange -> rAF).
-->
<script lang="ts" module>
  export type { FacetId, YMode } from './facets';

  /** Driven by the gallery's screenshot script and the stress check. */
  export interface LightCurveApi {
    zoomTo: (a: number, b: number) => void;
    fit: () => void;
    follow: () => void;
    hoverAt: (fx: number, facet: import('./facets').FacetId) => void;
    select: (t: number | null) => void;
    /** Push the store to the plots now; returns the milliseconds it took. */
    pushNow: () => number;
    /** The zoom state and each facet's x scale (checks and screenshots). */
    state: () => { mode: string; view: [number, number] | null; scales: Record<string, [number, number] | null> };
  }
</script>

<script lang="ts">
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import '../plot-host.css';
  import { onMount, untrack } from 'svelte';
  import Icon from '../../components/Icon.svelte';
  import { reducedMotion } from '../../components/motion.svelte';
  import IconButton from '../../components/IconButton.svelte';
  import Segmented from '../../components/Segmented.svelte';
  import { tooltip } from '../../components/tooltip';
  import { fixed, int } from '../../format/number';
  import { clockUtc, duration, utcDate } from '../../format/time';
  import { observedCadence, overdueAfter } from '../conditions';
  import { readInks, type ChartInks } from '../ink';
  import { padRange, stepDigits, timeAxis, type TimeAxisMode } from '../uplot/axes';
  import { PlotHost } from '../uplot/host';
  import { CAPS_BELOW, markers } from '../uplot/markers';
  import { annotations, type Annotation } from '../uplot/overlays';
  import { TimeZoom, type ZoomMode } from '../uplot/zoom';
  import NumText from '../../components/NumText.svelte';
  import CurveKey from './CurveKey.svelte';
  import { CHECK_RUNGS, FACET_MIN_SPAN, FACET_SHAPE, alignedOf, checkRung, checkSigma, facetData, flagCounts, niceSplits, padPixels, visibleRange, type FacetData, type FacetId, type YMode } from './facets';
  import { curveTsv, readoutAt, type PointReadout } from './readout';
  import type { LiveCurveStore } from './store';

  interface Props {
    store: LiveCurveStore;
    /** Facets top to bottom. Observe band: target + check (D25); drawer and Review add the ensemble. */
    facets?: FacetId[];
    /** 'band': one compact toolbar row (Observe Run band); 'drawer': the full toolbar. */
    variant?: 'band' | 'drawer';
    /** Time axis (bindable: the host persists it). */
    axis?: TimeAxisMode;
    /** Error bars shown (bindable). */
    errors?: boolean;
    /** Relative-flux view instead of magnitudes (bindable). */
    flux?: boolean;
    /** Frames are expected now (live photometry running): x to now, overdue hatching. */
    expecting?: boolean;
    /** Wall clock, unix seconds (the gallery passes a fixed one). */
    clock?: () => number;
    /** Rebuild the plots when this changes (the tokens moved). */
    theme?: unknown;
    /** Which target / check star (default: the first of the role). */
    targetKey?: string | null;
    checkKey?: string | null;
    /** Feedback of Copy data (TSV): the host shows it as a toast. */
    notify?: (title: string, message?: string) => void;
    /** Shown when no facet has a point. */
    emptyText?: string | null;
    label?: string;
    hooks?: (api: LightCurveApi) => void;
    /** Cost of each update (dev: the gallery's stress check). */
    onperf?: (ms: number, points: number) => void;
    /** 'modifier' inside a scrolling wall (Review): plain wheel scrolls, Ctrl / Cmd + wheel zooms. */
    wheel?: 'zoom' | 'modifier';
  }

  let {
    store,
    facets = ['target', 'check'],
    variant = 'drawer',
    axis = $bindable('utc'),
    errors = $bindable(true),
    flux = $bindable(false),
    expecting = false,
    clock = () => Date.now() / 1000,
    theme,
    targetKey = null,
    checkKey = null,
    notify,
    emptyText = null,
    label = 'Light curve',
    hooks,
    onperf,
    wheel = 'zoom',
  }: Props = $props();

  const compact = $derived(variant === 'band');
  const ymode: YMode = $derived(flux ? 'flux' : 'mag');

  // -- Plot state (outside the reactive graph) -------------------------------------
  let root: HTMLDivElement;
  let wall: HTMLDivElement | undefined = $state();
  const hosts = new Map<FacetId, PlotHost>();
  let inks: ChartInks | null = null;
  const syncKey = `lc-${Math.random().toString(36).slice(2, 8)}`;
  let activeFacet: FacetId | null = null;
  let downAt: { x: number; y: number } | null = null;

  // Facet data, recomputed once per store version and view.
  let cache = new Map<FacetId, FacetData | null>();
  let cacheKey = '';
  function dataOf(id: FacetId): FacetData | null {
    const key = `${store.version}|${ymode}|${targetKey}|${checkKey}`;
    if (key !== cacheKey) {
      cache = new Map();
      cacheKey = key;
    }
    if (!cache.has(id)) cache.set(id, facetData(store, id, ymode, { target: targetKey, check: checkKey }));
    return cache.get(id) ?? null;
  }

  // -- Reactive state (small values only) --------------------------------------------
  let version = $state(0);
  let now = $state(untrack(() => clock()));
  let mode = $state<ZoomMode>('fit');
  let viewSpan = $state(0);
  /** The shown time range, unix s ("a,b"): `data-lc-view` for scripted checks (a kept zoom never moves). */
  let viewRange = $state('');
  let hover = $state.raw<{ t: number; left: number; top: number } | null>(null);
  let selectedT = $state<number | null>(null);
  let hidden = $state({ target: false, check: false, checkBand: false, ensemble: false, ensBand: false });
  /** The wall's height (px): which facets keep their floor. */
  let wallH = $state(0);
  /** The check facet's ±rung (mag), as its y range last chose it. */
  let rung = $state<number | null>(null);

  // -- Time ----------------------------------------------------------------------------
  /** The series that times the run: the target, else the check, else the ensemble. */
  function timeSeries(): { t: Float64Array; n: number } | null {
    for (const id of ['target', 'check', 'ensemble'] as const) {
      const d = dataOf(id);
      if (d && d.n) return { t: d.x, n: d.n };
    }
    return null;
  }

  function firstLast(): [number, number] | null {
    let a = Infinity;
    let b = -Infinity;
    for (const id of facets) {
      const d = dataOf(id);
      if (!d || !d.n) continue;
      a = Math.min(a, d.x[0]);
      b = Math.max(b, d.x[d.n - 1]);
    }
    return Number.isFinite(a) ? [a, b] : null;
  }

  const zoom = new TimeZoom({
    extent: () => {
      const e = firstLast();
      if (!e) return null;
      return expecting ? [e[0], Math.max(e[1], now)] : e;
    },
    minSpan: 300,
    padLeft: 0.012,
    padRight: 0.012,
    anchor: () => (expecting ? 'right' : 'center'),
    wheel: untrack(() => wheel),
    reducedMotion,
    onChange: (m, v) => {
      mode = m;
      viewSpan = v ? v[1] - v[0] : 0;
      viewRange = v ? `${v[0]},${v[1]}` : '';
    },
  });

  const live = $derived.by(() => {
    void version;
    const ts = timeSeries();
    const n = ts?.n ?? 0;
    const cadence = ts ? observedCadence(ts.t, n) : null;
    const limit = overdueAfter(cadence);
    const lastT = n ? ts!.t[n - 1] : null;
    const age = lastT !== null ? Math.max(0, now - lastT) : null;
    return { cadence, limit, lastT, age, overdue: expecting && age !== null && age > limit };
  });

  // JD / BJD axes: an integer day from the run's first point, BJD only when every point has one.
  function anchorCols() {
    return store.primary('target', targetKey)?.cols ?? store.primary('check', checkKey)?.cols ?? null;
  }
  const timeInfo = $derived.by(() => {
    void version;
    const c = anchorCols();
    if (!c || !c.n) return { jd0: 0, bjd0: 0, bjdOk: false, date: '' };
    let bjdOk = true;
    for (let i = 0; i < c.n && bjdOk; i++) bjdOk = Number.isFinite(c.bjd[i]);
    return { jd0: Math.floor(c.jd[0]), bjd0: bjdOk ? Math.floor(c.bjd[0]) : 0, bjdOk, date: utcDate(c.t[0]) };
  });
  $effect(() => {
    if (axis === 'bjd' && !timeInfo.bjdOk && version > 0) untrack(() => (axis = 'jd'));
  });

  function bjdOffsetS(t: number): number {
    const c = anchorCols();
    if (!c || !c.n) return 0;
    const i = c.nearest(t);
    const off = (c.bjd[i] - c.jd[i]) * 86400;
    return Number.isFinite(off) ? off : 0;
  }

  // -- Colours and texts per facet -------------------------------------------------------
  const TOKEN: Record<FacetId, string> = { target: '--chart-1', check: '--chart-3', ensemble: '--chart-2' };
  const colorOf = (id: FacetId) => (id === 'target' ? inks!.target : id === 'check' ? inks!.check : inks!.comparison);

  function seriesShown(id: FacetId): boolean {
    return id === 'target' ? !hidden.target : id === 'check' ? !hidden.check : !hidden.ensemble;
  }
  function bandShown(id: FacetId): boolean {
    return id === 'check' ? !hidden.checkBand : id === 'ensemble' ? !hidden.ensBand : false;
  }

  // -- Plugins ---------------------------------------------------------------------------
  /**
   * The trailing band (check) or the spread (ensemble), drawn under the
   * markers: one polygon per run of finite rows, broken where no frame came
   * for max(2 x cadence, cadence + 60 s), so the band never bridges a gap.
   */
  function bandPlugin(id: FacetId): uPlot.Plugin {
    return {
      hooks: {
        drawAxes: [
          (u) => {
            const ink = inks;
            const d = dataOf(id);
            if (!ink || !d || !d.band || !bandShown(id) || !d.n) return;
            const xs = d.x;
            const { hi, lo, mean } = d.band;
            const [a0, a1] = u.series[1].idxs ?? [0, d.n - 1];
            const i0 = Math.max(0, a0 - 1);
            const i1 = Math.min(d.n - 1, a1 + 1);
            const gap = live.limit;
            const { ctx } = u;
            const { left, top, width, height } = u.bbox;
            const dpr = uPlot.pxRatio;
            ctx.save();
            ctx.beginPath();
            ctx.rect(left, top, width, height);
            ctx.clip();
            ctx.fillStyle = colorOf(id).a(ink.bandAlpha);
            const X = (k: number) => u.valToPos(xs[k], 'x', true);
            const Y = (v: number) => u.valToPos(v, 'y', true);
            // Dense view: one column per device pixel, the band's extent in it (the
            // same picture at a fraction of the vertices; 50 000 points).
            const dense = i1 - i0 > width;
            const fill = (s: number, e: number) => {
              if (e <= s) return;
              ctx.beginPath();
              if (!dense) {
                ctx.moveTo(X(s), Y(hi[s]));
                for (let k = s + 1; k <= e; k++) ctx.lineTo(X(k), Y(hi[k]));
                for (let k = e; k >= s; k--) ctx.lineTo(X(k), Y(lo[k]));
              } else {
                const cols: { x: number; a: number; b: number }[] = [];
                for (let k = s; k <= e; k++) {
                  const x = Math.round(X(k));
                  const ya = Y(hi[k]);
                  const yb = Y(lo[k]);
                  const a = Math.min(ya, yb);
                  const b = Math.max(ya, yb);
                  const c = cols[cols.length - 1];
                  if (c && c.x === x) {
                    if (a < c.a) c.a = a;
                    if (b > c.b) c.b = b;
                  } else cols.push({ x, a, b });
                }
                ctx.moveTo(cols[0].x, cols[0].a);
                for (const c of cols) ctx.lineTo(c.x, c.a);
                for (let k = cols.length - 1; k >= 0; k--) ctx.lineTo(cols[k].x, cols[k].b);
              }
              ctx.fill();
            };
            let start = -1;
            for (let i = i0; i <= i1; i++) {
              const ok = Number.isFinite(hi[i]) && Number.isFinite(lo[i]);
              const broken = start >= 0 && i > start && xs[i] - xs[i - 1] > gap;
              if (start >= 0 && (!ok || broken)) {
                fill(start, i - 1);
                start = -1;
              }
              if (ok && start < 0) start = i;
            }
            if (start >= 0) fill(start, i1);
            if (id === 'check') {
              // The trailing mean, dashed in the reference ink (min / max per pixel column when dense).
              ctx.setLineDash([3 * dpr, 3 * dpr]);
              ctx.strokeStyle = ink.reference.a(0.9);
              ctx.lineWidth = dpr;
              ctx.beginPath();
              let pen = false;
              let col = NaN;
              let cMin = 0;
              let cMax = 0;
              for (let i = i0; i <= i1; i++) {
                const v = mean[i];
                if (!Number.isFinite(v) || (i > i0 && xs[i] - xs[i - 1] > gap)) {
                  pen = false;
                  col = NaN;
                  if (!Number.isFinite(v)) continue;
                }
                const y = Y(v);
                if (dense) {
                  const x = Math.round(X(i));
                  if (x === col) {
                    if (y < cMin || y > cMax) {
                      cMin = Math.min(cMin, y);
                      cMax = Math.max(cMax, y);
                      ctx.lineTo(x, y);
                    }
                    continue;
                  }
                  col = x;
                  cMin = cMax = y;
                  if (pen) ctx.lineTo(x, y);
                  else ctx.moveTo(x, y);
                } else if (pen) ctx.lineTo(X(i), y);
                else ctx.moveTo(X(i), y);
                pen = true;
              }
              ctx.stroke();
              ctx.setLineDash([]);
            }
            ctx.restore();
          },
        ],
      },
    };
  }

  /**
   * Dense views: the band's edges as 1 px lines over the markers, which cover
   * its fill once a run has a few hundred frames (the fill stays under).
   */
  function bandEdges(id: FacetId): uPlot.Plugin {
    return {
      hooks: {
        draw: [
          (u) => {
            const ink = inks;
            const d = dataOf(id);
            if (!ink || !d || !d.band || !bandShown(id) || !d.n) return;
            const [i0, i1] = u.series[1].idxs ?? [0, d.n - 1];
            if (i1 - i0 + 1 < CAPS_BELOW) return;
            const { ctx } = u;
            const { left, top, width, height } = u.bbox;
            const gap = live.limit;
            ctx.save();
            ctx.beginPath();
            ctx.rect(left, top, width, height);
            ctx.clip();
            ctx.strokeStyle = ink.textMuted.a(0.9);
            ctx.lineWidth = uPlot.pxRatio;
            for (const edge of [d.band.hi, d.band.lo]) {
              ctx.beginPath();
              let pen = false;
              for (let i = i0; i <= i1; i++) {
                const v = edge[i];
                if (!Number.isFinite(v) || (i > i0 && d.x[i] - d.x[i - 1] > gap)) {
                  pen = false;
                  if (!Number.isFinite(v)) continue;
                }
                const x = u.valToPos(d.x[i], 'x', true);
                const y = u.valToPos(v, 'y', true);
                if (pen) ctx.lineTo(x, y);
                else ctx.moveTo(x, y);
                pen = true;
              }
              ctx.stroke();
            }
            ctx.restore();
          },
        ],
      },
    };
  }

  function annFor(id: FacetId, first: boolean): Annotation[] {
    const ink = inks;
    if (!ink) return [];
    const out: Annotation[] = [];
    if (id === 'ensemble' ? ymode === 'flux' : id === 'check' && (ymode === 'flux' || deltaView(id))) {
      const zero = ymode === 'mag' ? 0 : 1;
      out.push({ kind: 'hline', y: zero, color: ink.reference.a(0.55), dash: [2, 3], layer: 'under' });
    }
    if (expecting && live.lastT !== null) {
      if (live.overdue) out.push({ kind: 'vspan', from: live.lastT, to: now, hatch: ink.warning.a(0.45), edge: ink.warning.a(0.8), layer: 'over' });
      const text = `now ${clockUtc(now)}${live.overdue && live.age !== null ? ` · no frame for ${duration(live.age)}` : ''}`;
      out.push({ kind: 'vline', x: now, color: ink.highlight.a(0.85), label: first ? { text, at: 'top', color: live.overdue ? ink.fg.a() : undefined } : undefined });
    }
    if (selectedT !== null) out.push({ kind: 'vline', x: selectedT, color: ink.highlight.a(0.9), dash: [4, 3] });
    return out;
  }

  function selectedIdx(id: FacetId): number | null {
    if (selectedT === null) return null;
    const d = dataOf(id);
    if (!d || !d.n) return null;
    let lo = 0;
    let hi = d.n;
    while (lo < hi) {
      const m = (lo + hi) >> 1;
      if (d.x[m] < selectedT) lo = m + 1;
      else hi = m;
    }
    let best = -1;
    for (const k of [lo - 1, lo]) if (k >= 0 && k < d.n && (best < 0 || Math.abs(d.x[k] - selectedT) < Math.abs(d.x[best] - selectedT))) best = k;
    return best >= 0 && Math.abs(d.x[best] - selectedT) <= tolerance() ? best : null;
  }

  /** How far (s) a series' frame may be from a time and still be "that frame". */
  function tolerance(): number {
    const c = live.cadence;
    return c ? Math.max(1, c / 2) : 30;
  }

  /** The facet draws check − catalogue V, a signed difference about 0 (D10). */
  function deltaView(id: FacetId): boolean {
    return id === 'check' && (store.primary('check', checkKey)?.catalogue ?? null) !== null;
  }

  /** Pixels kept free inside the plot edges: a marker's radius (its ring may spill past the edge). */
  const MARGIN_PX = 5;

  function rungView(id: FacetId): boolean {
    return id === 'check' && ymode === 'mag' && deltaView(id);
  }

  function yRange(u: uPlot, id: FacetId, min: number | null, max: number | null): [number, number] {
    const px = u.bbox.height / uPlot.pxRatio;
    if (rungView(id)) {
      const d = dataOf(id);
      const r = d ? checkRung(d, u.scales.x.min ?? -Infinity, u.scales.x.max ?? Infinity) : CHECK_RUNGS[0];
      if (r !== rung) rung = r;
      return padPixels(-r, r, px, MARGIN_PX);
    }
    const [lo, hi] = padRange(min, max, FACET_MIN_SPAN[id][ymode], 0);
    return padPixels(lo, hi, px, MARGIN_PX);
  }

  /** Y ticks: three or more round values; the check's ±rung, 0 and the half rungs when they fit. */
  function ySplits(id: FacetId) {
    return (u: uPlot): number[] => {
      const { min, max } = u.scales.y;
      if (min == null || max == null) return [];
      const px = u.bbox.height / uPlot.pxRatio;
      // The ticks label the data part, not the pixel margins; labels stay 13 px apart.
      const dataPx = Math.max(0, px - 2 * MARGIN_PX);
      if (rungView(id) && rung !== null) return dataPx >= 52 ? [-rung, -rung / 2, 0, rung / 2, rung] : dataPx >= 26 ? [-rung, 0, rung] : [-rung, rung];
      const m = ((max - min) * MARGIN_PX) / Math.max(1, px);
      return niceSplits(min + m, max - m, dataPx).splits;
    };
  }

  // -- Options ----------------------------------------------------------------------------
  function cursorPoint(_u: uPlot, si: number): HTMLElement | undefined {
    if (si !== 1) return undefined;
    const el = document.createElement('div');
    el.style.cssText = 'width:10px;height:10px;margin:-5px 0 0 -5px';
    return el;
  }

  function yValues(id: FacetId) {
    return (_u: uPlot, splits: number[]) => {
      const step = splits.length > 1 ? Math.abs(splits[1] - splits[0]) : 0.01;
      // Magnitudes keep two decimals at least: "12.00", never "12".
      const digits = Math.min(4, Math.max(2, stepDigits(step)));
      const signedView = ymode === 'mag' && deltaView(id);
      return splits.map((v) => {
        if (v == null) return '';
        const zero = Math.abs(v) < step / 2;
        const s = fixed(zero ? 0 : v, digits);
        return signedView && !zero && v > 0 ? `+${s}` : s;
      });
    };
  }

  function options(id: FacetId, first: boolean, last: boolean): uPlot.Options {
    const ink = inks!;
    const role = colorOf(id);
    const font = `400 10px ${ink.mono}`;
    const d = dataOf(id);
    const hasBand = !!d?.band;
    const series: uPlot.Series[] = [{}, { stroke: role.a(), paths: () => null, points: { show: false }, show: seriesShown(id) }];
    // The band edges ride as invisible series so the y range includes them.
    if (hasBand) series.push({ stroke: 'rgba(0,0,0,0)', paths: () => null, points: { show: false } }, { stroke: 'rgba(0,0,0,0)', paths: () => null, points: { show: false } });
    return {
      width: 100,
      height: 100,
      // The top margin holds the facet's title (an in-plot label, as Conditions).
      padding: [TITLE_PX, 18, last ? 0 : 3, 0],
      legend: { show: false },
      cursor: {
        sync: { key: syncKey, setSeries: false },
        // The hovered point: a 10 px ring (--chart-marker-hover) on the drawn series only.
        points: {
          show: cursorPoint,
          size: 10,
          width: 1.5,
          stroke: () => ink.highlight.a(),
          fill: () => 'rgba(0,0,0,0)',
        } as unknown as uPlot.Cursor.Points,
        drag: { x: true, y: false, setScale: true, dist: 5 },
        bind: TimeZoom.cursorBind(),
        focus: { prox: -1 },
      },
      scales: {
        x: { time: false },
        // Magnitudes (and magnitude differences) inverted: brighter up. The zero point is not
        // inverted: more light (a larger zero point) is up too.
        y: { dir: ymode === 'mag' && id !== 'ensemble' ? -1 : 1, range: (u, min, max) => yRange(u, id, min, max) },
      },
      axes: [
        timeAxis(ink, { mode: axis, labels: last, suffix: true, jd0: axis === 'bjd' ? timeInfo.bjd0 : timeInfo.jd0, bjdOffsetS }),
        {
          stroke: ink.text.a(),
          font,
          size: 50,
          gap: 5,
          ticks: { show: false },
          grid: { stroke: ink.grid.a(), width: 1 },
          splits: ySplits(id),
          values: yValues(id),
        },
      ],
      series,
      plugins: [
        zoom.plugin(),
        annotations(() => annFor(id, first), () => inks),
        bandPlugin(id),
        markers({
          seriesIdx: 1,
          shape: FACET_SHAPE[id],
          // Points beyond the check's rung: a caret on the edge, never silently cut.
          carets: () => rungView(id),
          color: () => colorOf(id).a(),
          errors: () => dataOf(id)?.err ?? null,
          showErrors: () => errors,
          errorAlpha: () => inks?.errorAlpha ?? 0.55,
          flags: () => dataOf(id)?.flags ?? null,
          latest: () => (id === 'ensemble' ? null : (inks?.highlight.a() ?? null)),
          selected: () => {
            const i = selectedIdx(id);
            return i !== null && inks ? { idx: i, color: inks.highlight.a() } : null;
          },
        }),
        bandEdges(id),
      ],
      hooks: {
        init: [
          (u) => {
            u.over.addEventListener('pointerenter', () => (activeFacet = id));
            u.over.addEventListener('pointerleave', () => {
              if (activeFacet === id) activeFacet = null;
              hover = null;
            });
            u.over.addEventListener('pointerdown', (e) => (downAt = { x: e.clientX, y: e.clientY }));
            u.over.addEventListener('click', (e) => onPlotClick(u, id, e));
          },
        ],
        setCursor: [
          (u) => {
            if (activeFacet !== id || !wall) return;
            const i = u.cursor.idx;
            const left = u.cursor.left ?? -1;
            const dd = dataOf(id);
            if (i == null || left < 0 || !dd || i >= dd.n) {
              hover = null;
              return;
            }
            const wr = wall.getBoundingClientRect();
            const or = u.over.getBoundingClientRect();
            hover = { t: dd.x[i], left: or.left - wr.left + left, top: or.top - wr.top + (u.cursor.top ?? 0) };
          },
        ],
      },
    };
  }

  function dataFor(id: FacetId): uPlot.AlignedData {
    const d = dataOf(id);
    const [x, y] = alignedOf(d);
    if (d?.band) return [x, y, d.band.hi, d.band.lo] as unknown as uPlot.AlignedData;
    return [x, y] as unknown as uPlot.AlignedData;
  }

  // A click without a drag selects the frame under the pointer; on empty plot it clears.
  function onPlotClick(u: uPlot, id: FacetId, e: MouseEvent): void {
    if (downAt && Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) > 4) return;
    const d = dataOf(id);
    const i = u.cursor.idx;
    if (!d || i == null || i >= d.n) {
      selectedT = null;
      return;
    }
    const px = u.valToPos(d.x[i], 'x');
    const rect = u.over.getBoundingClientRect();
    selectedT = Math.abs(px - (e.clientX - rect.left)) <= 12 ? d.x[i] : null;
  }

  // -- Hosts and updates ---------------------------------------------------------------------
  // Facet heights: the target gets the most; the check keeps a readable height.
  // Target 3 : check 2 (: ensemble 2) in both variants. At 2 : 1 the drawer's default 216-260 px left
  // the check 35-45 px of plot: its ±1σ band (D10, the stability check) was unreadable (wave 5).
  const share = (id: FacetId) => (id === 'target' ? 3 : 2);
  /** The time axis rows the last facet carries (timeAxis size 22): its basis, so the plots share the rest. */
  const TIME_AXIS_PX = 22;
  /** The facet title's line, in the plot's top margin. */
  const TITLE_PX = 16;
  /** Least plot height (px) a facet is drawn with; below, it is left out (the check: in the target's title). */
  const FLOOR: Record<FacetId, number> = { target: 48, check: 32, ensemble: 32 };

  // Which facets have a series (the others show why they have none).
  const withData = $derived.by(() => {
    void version;
    void ymode;
    return facets.filter((id) => untrack(() => dataOf(id)) !== null);
  });
  // Which of them get a plot: the last ones go while one would fall under its floor.
  const plotted = $derived.by(() => {
    let ids = withData;
    if (!wallH) return ids;
    while (ids.length > 1) {
      const sum = ids.reduce((a, id) => a + share(id), 0);
      const room = wallH - TIME_AXIS_PX - 4 - ids.length * TITLE_PX - (ids.length - 1) * 3;
      if (ids.every((id) => (room * share(id)) / sum >= FLOOR[id])) break;
      ids = ids.slice(0, -1);
    }
    return ids;
  });

  function facetHost(id: FacetId) {
    return (el: HTMLElement) => {
      inks ??= readInks(el);
      const h = new PlotHost(
        el,
        () => {
          const ids = facets.filter((f) => plotted.includes(f));
          const k = ids.indexOf(id);
          return { opts: options(id, k === 0, k === ids.length - 1), data: dataFor(id) };
        },
        // uPlot ranges x on the data while it builds: put the group's view back at once.
        (u) => zoom.batch(u, () => {}),
      );
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

  let raf = 0;
  function schedule(): void {
    if (raf || typeof requestAnimationFrame === 'undefined') return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      push();
    });
  }

  let shape = '';
  function push(): number {
    const t0 = performance.now();
    if (!inks) return 0;
    // The band series exist only while a facet has a band: a new shape rebuilds the plot.
    const s = plotted.map((id) => `${id}:${dataOf(id)?.band ? 1 : 0}`).join(',');
    if (!firstLast()) zoom.reset();
    zoom.update();
    if (s !== shape) {
      shape = s;
      for (const h of hosts.values()) h.build();
    } else {
      for (const [id, h] of hosts) {
        const u = h.u;
        if (!u) continue;
        zoom.batch(u, () => u.setData(dataFor(id), false));
      }
    }
    zoom.notify();
    const ms = performance.now() - t0;
    onperf?.(ms, store.points);
    return ms;
  }

  // The store changed: one update per animation frame.
  $effect(() => {
    const s = store;
    return untrack(() => {
      cacheKey = '';
      zoom.reset();
      selectedT = null;
      version = s.version;
      schedule();
      return s.onChange(() => {
        version = s.version;
        schedule();
      });
    });
  });

  // Theme, time axis and view live in the options: rebuild (the zoom view is kept).
  $effect(() => {
    void theme;
    void axis;
    void ymode;
    void timeInfo.jd0;
    untrack(() => {
      cacheKey = '';
      shape = '';
      rebuild();
    });
  });

  // Visibility, error bars, selection, liveness: a redraw, no rebuild.
  $effect(() => {
    void hidden.target;
    void hidden.check;
    void hidden.ensemble;
    void hidden.checkBand;
    void hidden.ensBand;
    void errors;
    void selectedT;
    void live.overdue;
    untrack(() => {
      for (const [id, h] of hosts) {
        const u = h.u;
        if (!u) continue;
        if (u.series[1] && u.series[1].show !== seriesShown(id)) u.setSeries(1, { show: seriesShown(id) });
        u.redraw(false, false);
      }
    });
  });

  // The now-line and the age move once a second while frames are expected.
  onMount(() => {
    const tick = setInterval(() => {
      if (!expecting) return;
      now = clock();
      schedule();
    }, 1000);
    return () => {
      clearInterval(tick);
      if (raf) cancelAnimationFrame(raf);
    };
  });

  $effect(() => {
    hooks?.({
      zoomTo: (a, b) => zoom.setUser(a, b),
      fit: () => zoom.fit(),
      follow: () => zoom.follow(),
      hoverAt: (fx, facet) => {
        const u = hosts.get(facet)?.u;
        if (!u) return;
        activeFacet = facet;
        u.setCursor({ left: u.over.clientWidth * fx, top: u.over.clientHeight * 0.4 });
      },
      select: (t) => (selectedT = t),
      pushNow: () => push(),
      state: () => ({
        mode: zoom.mode,
        view: zoom.view,
        scales: Object.fromEntries([...hosts].map(([id, h]) => [id, h.u ? [h.u.scales.x.min ?? NaN, h.u.scales.x.max ?? NaN] : null])),
      }),
    });
  });

  // -- Keyboard (the focused plot region; unhandled keys go on to the app) -------------------
  /** ← / →: select the previous / next frame of the target (the newest first); the view pans to keep it. */
  function step(dir: -1 | 1): void {
    const id: FacetId = dataOf('target') ? 'target' : 'check';
    const d = dataOf(id);
    if (!d || !d.n) return;
    const cur = selectedIdx(id);
    const i = cur === null ? d.n - 1 : Math.max(0, Math.min(d.n - 1, cur + dir));
    const t = d.x[i];
    selectedT = t;
    const v = zoom.view;
    if (v && (t < v[0] || t > v[1])) zoom.panBy((t - (v[0] + v[1]) / 2) / (v[1] - v[0]), true);
  }

  function onKey(e: KeyboardEvent): void {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key;
    if (k === 'f' || k === 'F') zoom.fit(true);
    else if (k === '+' || k === '=') zoom.zoomBy(1 / 1.6, undefined, true);
    else if (k === '-' || k === '_') zoom.zoomBy(1.6, undefined, true);
    else if (k === 'ArrowLeft' && e.shiftKey) zoom.panBy(-0.25, true);
    else if (k === 'ArrowRight' && e.shiftKey) zoom.panBy(0.25, true);
    else if (k === 'ArrowLeft') step(-1);
    else if (k === 'ArrowRight') step(1);
    else if (k === 'End') zoom.follow(true);
    else if (k === 'u' || k === 'U') errors = !errors;
    else if (k === 'm' || k === 'M') flux = !flux;
    else return;
    e.preventDefault();
  }

  // -- Copy data (TSV) ------------------------------------------------------------------------
  async function copyTsv(): Promise<void> {
    const { text, rows } = curveTsv(store, { target: targetKey, check: checkKey });
    const name = `lightcurve-${(store.object ?? 'run').replace(/[^\w.-]+/g, '_')}.tsv`;
    try {
      await navigator.clipboard.writeText(text);
      notify?.(`Copied ${int(rows)} frames as TSV`, 'UTC, JD, BJD_TDB, magnitudes, errors and flags, full precision');
    } catch {
      const url = URL.createObjectURL(new Blob([text], { type: 'text/tab-separated-values' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      notify?.(`Saved ${name}`, `${int(rows)} frames (the clipboard was not available)`);
    }
  }

  // -- Words ------------------------------------------------------------------------------------
  const keys = $derived({ target: targetKey, check: checkKey });
  const hoverRead: PointReadout | null = $derived.by(() => {
    void version;
    return hover ? readoutAt(store, hover.t, ymode, keys, tolerance()) : null;
  });
  const fixedRead: PointReadout | null = $derived.by(() => {
    void version;
    if (selectedT !== null) return readoutAt(store, selectedT, ymode, keys, tolerance());
    return live.lastT !== null ? readoutAt(store, live.lastT, ymode, keys, tolerance()) : null;
  });

  const counts = $derived.by(() => {
    void version;
    void ymode;
    const out = {} as Record<FacetId, { suspect: number; saturated: number }>;
    for (const id of facets) {
      const d = untrack(() => dataOf(id));
      out[id] = flagCounts(d?.flags ?? null, d?.y ?? null);
    }
    return out;
  });
  const sigma = $derived.by(() => {
    void version;
    return checkSigma(store, checkKey);
  });
  const stars = $derived.by(() => {
    void version;
    const t = store.primary('target', targetKey);
    const c = store.primary('check', checkKey);
    const comps = store.comparisons().length;
    // The comparisons behind the newest zero point (the target's comps_used).
    const tc = t?.cols;
    const last = tc && tc.n ? tc.comps[tc.n - 1] : NaN;
    return {
      target: t?.name ?? 'Target',
      check: c?.name ?? null,
      checkCat: c?.catalogue ?? null,
      comps,
      used: Number.isFinite(last) ? `${last}${comps ? ` of ${comps}` : ''}` : null,
    };
  });
  const anyData = $derived(plotted.length > 0);
  const band = $derived(store.band ?? 'mag');

  const modeText = $derived(mode === 'fit' ? 'Whole run' : mode === 'follow' ? `Following · ${duration(viewSpan)}` : 'Zoom kept');
  /** Frames newer than a kept zoom's right edge (they never move it). */
  const newer = $derived.by(() => {
    void version;
    void viewRange;
    const v = zoom.view;
    const ts = mode === 'manual' && v ? timeSeries() : null;
    if (!ts || !v) return 0;
    return ts.n - 1 - visibleRange(ts.t, ts.n, -Infinity, v[1])[1];
  });
  /** The x axis named in a few words, in the last facet's title row (mid-exposure times). */
  const axisShort = $derived(axis === 'utc' ? `mid-exposure · ${timeInfo.date || '—'}` : axis === 'jd' ? `JD − ${timeInfo.jd0} · UTC` : `BJD_TDB − ${timeInfo.bjd0}`);
  const axisTip = $derived(axis === 'bjd' ? 'Exposure midpoints, BJD_TDB from the server (per star)' : 'Exposure midpoints (UTC)');
  /** The check left out for room: its σ and newest check − V in the target's title. */
  const checkLine = $derived.by(() => {
    if (!withData.includes('check') || plotted.includes('check') || ymode !== 'mag') return null;
    const parts: string[] = [];
    if (sigma && Number.isFinite(sigma.sigma)) parts.push(`check σ${sigma.count} ${fixed(sigma.sigma, 3)}`);
    if (fixedRead?.check) parts.push(`check − V ${fixedRead.check.value}`);
    return parts.length ? parts.join(' · ') : null;
  });
  const AXES = $derived([
    { value: 'utc' as const, label: 'UTC' },
    { value: 'jd' as const, label: 'JD' },
    { value: 'bjd' as const, label: 'BJD', disabledReason: timeInfo.bjdOk ? null : 'BJD_TDB needs the observing site (Settings › Site) on every point' },
  ]);

  function sub(id: FacetId): string {
    if (id === 'target') return ymode === 'mag' ? `${band} · differential mag` : 'relative flux · median-normalised';
    if (id === 'check') {
      if (ymode === 'flux') return 'relative flux · median-normalised';
      return stars.checkCat !== null ? `check − V ${fixed(stars.checkCat, 3)}${rung !== null ? ` · ±${rung} mag` : ''}` : 'no catalogue magnitude: drawn as measured';
    }
    if (ymode === 'flux') return 'transmission · run median = 1';
    return `zero point ± rms${stars.used ? ` · ${stars.used} comparisons` : ''}`;
  }
  function title(id: FacetId): string {
    return id === 'target' ? stars.target : id === 'check' ? (stars.check ?? 'Check star') : 'Ensemble';
  }
  function missing(id: FacetId): string {
    if (id === 'check') return stars.check ? 'No point measured for the check star yet' : 'No check star: give one the Check role to see how stable the photometry is';
    if (id === 'ensemble') return stars.comps ? 'No ensemble zero point yet' : 'No comparison star';
    return ymode === 'flux' ? 'No relative flux for the target' : 'No magnitude for the target yet';
  }

  const shareSum = $derived(plotted.reduce((a, id) => a + share(id), 0) || 1);
  /** The hover tooltip's width (px). */
  const TIP_W = 264;

  const tipStyle = $derived.by(() => {
    if (!hover || !wall) return '';
    const w = wall.clientWidth;
    // Live views: the tooltip opens away from the newest points (on the left of the pointer).
    const leftFirst = expecting || mode === 'follow';
    const fitsLeft = hover.left - 16 - TIP_W >= 0;
    const fitsRight = hover.left + 16 + TIP_W <= w;
    const left = (leftFirst ? fitsLeft || !fitsRight : !fitsRight && fitsLeft) ? hover.left - 16 - TIP_W : hover.left + 16;
    const top = Math.max(4, Math.min(wall.clientHeight - 170, hover.top - 50));
    return `left:${left}px;top:${top}px`;
  });
</script>

<!-- A focusable chart region: its keys are listed in the header comment and on each tool's tooltip. -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
<div class="lc" class:compact bind:this={root} role="region" aria-label="{label}: {stars.target}" tabindex="0" onkeydown={onKey} data-lc-mode={mode} data-lc-view={viewRange}>
  <div class="bar">
    <Segmented label="Time axis" size="s" options={AXES} bind:value={axis} />
    <span class="sep"></span>
    <span class="steps">
      <IconButton icon="zoom-out" label="Zoom out time" shortcut="-" size="s" variant="ghost" tooltip="top" onclick={() => zoom.zoomBy(1.6, undefined, true)} disabled={!anyData} />
      <IconButton icon="zoom-in" label="Zoom in time" shortcut="+" size="s" variant="ghost" tooltip="top" onclick={() => zoom.zoomBy(1 / 1.6, undefined, true)} disabled={!anyData} />
    </span>
    <IconButton icon="zoom-fit" label="Fit the whole run" shortcut="F" size="s" variant="ghost" tooltip="top" onclick={() => zoom.fit(true)} disabled={!anyData} />
    <IconButton icon="live" label="Follow the newest frame" shortcut="End" size="s" variant="ghost" tooltip="top" pressed={mode === 'follow'} layoutToggle onclick={() => zoom.follow(true)} disabled={!anyData} />
    <span class="chip" class:kept={mode === 'manual'} data-zoom-state={mode} aria-live="polite" use:tooltip={{ text: mode === 'fit' ? 'The whole run is in view; new frames widen it' : mode === 'follow' ? 'The right edge follows the newest frame' : 'New frames never move this view', shortcut: ['F', 'End'] }}>
      {modeText}{#if mode !== 'fit'}<span class="hint">· <kbd>F</kbd></span>{/if}
    </span>
    {#if newer > 0}
      <button type="button" class="newer num" onclick={() => zoom.follow(true)} use:tooltip={{ text: 'Frames after this view: follow the newest', shortcut: ['End'] }}>{newer} newer ›</button>
    {/if}
    <span class="sep"></span>
    <IconButton icon="error-bars" label="Error bars" shortcut="U" size="s" variant="ghost" tooltip="top" pressed={errors} layoutToggle onclick={() => (errors = !errors)} />
    <IconButton icon="relative-flux" label="Relative flux (median-normalised)" shortcut="M" size="s" variant="ghost" tooltip="top" pressed={flux} layoutToggle onclick={() => (flux = !flux)} />
    {#if !compact}
      <IconButton icon="copy" label="Copy data (TSV)" size="s" variant="ghost" tooltip="top" onclick={copyTsv} disabledReason={anyData ? null : 'No point to copy yet'} />
    {/if}
    <span class="grow"></span>
    {#if fixedRead}
      <!-- Items in priority order: what does not fit wraps out of sight whole, never cut inside a number. -->
      <span class="readout num" class:sel={selectedT !== null}>
        <span class="kind" use:tooltip={{ text: selectedT !== null ? 'The selected frame (← / → step, a click elsewhere clears)' : 'The newest frame' }}>
          <span class="ring" aria-hidden="true"></span><span class="word">{selectedT !== null ? 'Selected' : 'Latest'}</span>
        </span>
        {#if fixedRead.target}<span class="v"><CurveKey shape="circle" color="var(--chart-1)" />{fixedRead.target.value}</span>{/if}
        {#if sigma && ymode === 'mag'}<span class="v sig" use:tooltip={{ text: `Scatter of the check star over its last ${sigma.count} points (the trailing band)` }}>σ<sub>{sigma.count}</sub>&nbsp;{Number.isFinite(sigma.sigma) ? fixed(sigma.sigma, 3) : '—'}</span>{/if}
        {#if fixedRead.check}<span class="v chk"><CurveKey shape="triangle" color="var(--chart-3)" />{fixedRead.check.value}</span>{/if}
        <span class="v utc">{fixedRead.utc}</span>
      </span>
    {/if}
  </div>

  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="wall" bind:this={wall} bind:clientHeight={wallH} onpointerleave={() => (hover = null)}>
    {#if !anyData}
      <div class="empty">
        <Icon name="light-curve" size={24} />
        <p>{emptyText ?? (expecting ? 'Waiting for the first measured frame' : 'No light curve: no point measured yet')}</p>
      </div>
    {:else}
      {#each facets as id (id)}
        {@const has = plotted.includes(id)}
        {#if has || !withData.includes(id)}
          <section class="facet" class:slim={!has} style:flex-grow={has ? share(id) / shareSum : 0} style:flex-basis={has && id === plotted[plotted.length - 1] ? `${TIME_AXIS_PX}px` : null} aria-label="{title(id)}: {sub(id)}">
            <!-- The title sits in the plot's top margin (an in-plot label), never above it. -->
            <header class:over={has}>
              <CurveKey shape={FACET_SHAPE[id]} color="var({TOKEN[id]})" size={11} />
              <h3>{title(id)}</h3>
              {#if has}<span class="sub"><NumText text={sub(id)} /></span>{/if}
              {#if has && id === 'target' && checkLine}<span class="sub chkline"><CurveKey shape="triangle" color="var(--chart-3)" size={10} /><NumText text={checkLine} /></span>{/if}
              {#if has}
                <span class="legend" role="group" aria-label="Series of {title(id)}">
                  {#if id === 'check'}
                    <button type="button" class="key" aria-pressed={!hidden.checkBand} onclick={() => (hidden.checkBand = !hidden.checkBand)}><CurveKey shape="triangle" color="var(--chart-3)" variant="band" /><span><span class="num">±1σ</span>, last <span class="num">15</span></span></button>
                  {:else if id === 'ensemble'}
                    <button type="button" class="key" aria-pressed={!hidden.ensBand} onclick={() => (hidden.ensBand = !hidden.ensBand)}><CurveKey shape="square" color="var(--chart-2)" variant="band" />± rms</button>
                  {/if}
                  {#if counts[id]?.suspect}
                    <span class="key static" use:tooltip={{ text: 'Aperture peak without PSF support (hot pixel or cosmic ray?): kept, the observer decides' }}><CurveKey shape={FACET_SHAPE[id]} color="var({TOKEN[id]})" variant="hollow" />suspect <b class="num">{counts[id].suspect}</b></span>
                  {/if}
                  {#if counts[id]?.saturated}
                    <span class="key static" use:tooltip={{ text: 'Saturated: the aperture holds clipped pixels, the value is wrong' }}><CurveKey shape={FACET_SHAPE[id]} color="var({TOKEN[id]})" variant="cross" />saturated <b class="num">{counts[id].saturated}</b></span>
                  {/if}
                </span>
              {/if}
              {#if has && id === plotted[plotted.length - 1]}<span class="axis-name num" use:tooltip={{ text: axisTip }}>{axisShort}</span>{/if}
            </header>
            {#if has}
              <div class="plot-host plot" {@attach facetHost(id)}></div>
            {:else}
              <p class="missing">{missing(id)}</p>
            {/if}
          </section>
        {/if}
      {/each}
    {/if}

    {#if hover && hoverRead}
      <div class="tip num" style={tipStyle} aria-hidden="true">
        <div class="t">{hoverRead.utc} UTC · {timeInfo.date}{hoverRead.point !== null ? ` · point ${hoverRead.point}` : ''}</div>
        <div>JD {hoverRead.jd}</div>
        <div>BJD {hoverRead.bjd ?? '— (no site)'}{hoverRead.checkBjd ? ' target' : ''}</div>
        {#if hoverRead.checkBjd}<div>BJD {hoverRead.checkBjd} check</div>{/if}
        <hr />
        {#if hoverRead.target}
          <div class="row"><CurveKey shape="circle" color="var(--chart-1)" size={11} /><span class="v">{hoverRead.target.value}</span><span class="k">{hoverRead.target.what}</span></div>
        {/if}
        {#if hoverRead.check}
          <div class="row"><CurveKey shape="triangle" color="var(--chart-3)" size={11} /><span class="v">{hoverRead.check.value}</span><span class="k">{hoverRead.check.what}</span></div>
        {/if}
        {#if hoverRead.ensemble && facets.includes('ensemble')}
          <div class="row"><CurveKey shape="square" color="var(--chart-2)" size={11} /><span class="v">{hoverRead.ensemble.value}</span><span class="k">{hoverRead.ensemble.what}</span></div>
        {/if}
        {#if hoverRead.airmass}<div>airmass <span class="v">{hoverRead.airmass}</span></div>{/if}
        {#each [...(hoverRead.target?.flags ?? []).map((f) => `target ${f}`), ...(hoverRead.check?.flags ?? []).map((f) => `check ${f}`)] as f (f)}
          <div class="flag">{f}</div>
        {/each}
      </div>
    {/if}
  </div>
</div>

<style>
  .lc {
    container-type: inline-size;
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    min-width: 0;
    background: var(--chart-surface);
    outline-offset: -2px;
  }
  /* Key focus (F, + and − are the image's keys too): a line under the plot's tools, not a
     ring round the whole wall (the brass budget, BRAND 8). */
  .lc:focus-visible {
    outline: none;
  }
  .lc:focus-visible .bar {
    box-shadow: inset 0 calc(-1 * var(--focus-ring-w)) 0 var(--focus-ring);
  }

  .bar {
    display: flex;
    align-items: center;
    gap: 2px;
    height: var(--chart-toolbar-h);
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    background: var(--bg);
    flex: none;
    min-width: 0;
    overflow: hidden;
  }
  /* 32 px in both variants: the drawer's default height is mostly plot (wave 5 design review). */
  .bar {
    height: 32px;
  }
  .compact .bar {
    padding: 0 var(--space-2);
  }
  .sep {
    width: 1px;
    height: 16px;
    margin: 0 var(--space-1);
    background: var(--border-soft);
    flex: none;
  }
  .grow {
    flex: 1;
    min-width: var(--space-2);
  }
  /* A label (the zoom state's name), not a button. */
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    height: 20px;
    margin-left: var(--space-1);
    padding: 0 var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    flex: none;
  }
  .chip.kept {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .newer {
    height: 20px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-xs);
    white-space: nowrap;
    flex: none;
    cursor: pointer;
  }
  .newer:hover {
    background: var(--hover-bg);
  }
  .newer:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -1px;
  }
  .chip .hint {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    color: var(--text-muted);
  }
  kbd {
    padding: 0 3px;
    border: var(--border-w) solid var(--border);
    border-radius: 3px;
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    line-height: 13px;
  }
  /* Wraps instead of cutting: an item that does not fit goes whole to a hidden second line,
     the last (least needed) first. */
  .readout {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    align-content: flex-start;
    justify-content: flex-end;
    column-gap: var(--space-3);
    height: 20px;
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
    min-width: 0;
    flex: 0 1 auto;
  }
  .readout > span {
    flex: none;
    height: 20px;
    display: inline-flex;
    align-items: center;
  }
  .steps {
    display: contents;
  }
  .readout sub {
    font-size: 0.8em;
    vertical-align: -0.15em;
  }
  .axis-name {
    margin-left: auto;
    padding-right: var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    white-space: nowrap;
  }
  .readout .kind {
    gap: 4px;
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: var(--tracking-caps);
  }
  /* The newest point's ring; filled for a selected frame. Never hidden. */
  .readout .ring {
    width: 9px;
    height: 9px;
    border: 1.5px solid var(--chart-highlight);
    border-radius: 50%;
    box-sizing: border-box;
  }
  .readout.sel .ring {
    background: var(--chart-highlight);
  }
  .readout .v {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--fg);
  }
  .readout.sel .kind {
    color: var(--fg);
  }

  .wall {
    position: relative;
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 2px var(--space-2) 0 var(--space-1);
  }
  .facet {
    position: relative;
    display: flex;
    flex-direction: column;
    flex-basis: 0;
    min-height: 0;
  }
  .facet.slim {
    min-height: 0;
    flex: none;
  }
  .facet + .facet {
    border-top: var(--border-w) solid var(--border-soft);
  }
  header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: var(--chart-header-h);
    padding-left: 50px;
    flex: none;
    min-width: 0;
    overflow: hidden;
  }
  /* In the plot's top margin (TITLE_PX), over the plot's left edge. */
  header.over {
    position: absolute;
    z-index: 1;
    top: 0;
    left: 50px;
    right: 18px;
    height: 16px;
    padding-left: 0;
    gap: var(--space-2);
    pointer-events: none;
  }
  header.over .key,
  header.over .axis-name {
    pointer-events: auto;
  }
  .compact header {
    gap: var(--space-1);
  }
  h3 {
    margin: 0;
    font-size: var(--text-xs);
    font-weight: var(--weight-semibold);
    color: var(--fg);
    white-space: nowrap;
  }
  .sub {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .chkline {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .legend {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    margin-left: var(--space-2);
    min-width: 0;
    overflow: hidden;
  }
  .key {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    height: 16px;
    padding: 0 6px;
    border: 0;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    cursor: pointer;
  }
  .compact .key {
    font-size: var(--text-2xs);
  }
  .key:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .key:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -1px;
  }
  .key[aria-pressed='false'] {
    color: var(--fg-disabled);
  }
  .key[aria-pressed='false'] :global(.key-glyph) {
    opacity: 0.35;
  }
  .key.static {
    cursor: default;
  }
  .key.static:hover {
    background: transparent;
    color: var(--text-muted);
  }
  .key b {
    color: var(--fg);
    font-weight: var(--weight-regular);
  }
  .plot {
    flex: 1;
    min-height: 0;
  }
  .missing {
    margin: 0 0 var(--space-2);
    padding-left: 50px;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .empty {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .empty p {
    margin: 0;
  }

  .tip {
    position: absolute;
    z-index: 2;
    width: 264px;
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
  .tip .t {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .tip hr {
    margin: 4px 0;
    border: 0;
    border-top: var(--border-w) solid var(--border-soft);
  }
  .tip .row {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .tip .v {
    color: var(--fg);
    white-space: nowrap;
  }
  .tip .k {
    margin-left: auto;
    font-size: var(--text-2xs);
  }
  .tip .flag {
    color: var(--fg);
  }

  /* Narrow plots drop words first, then the less used tools (BRAND 7: symbols stay); the
     readout drops whole items by itself (it wraps). */
  @container (max-width: 1000px) {
    .readout .word,
    .chip .hint {
      display: none;
    }
  }
  @container (max-width: 820px) {
    .steps {
      display: none;
    }
  }
</style>

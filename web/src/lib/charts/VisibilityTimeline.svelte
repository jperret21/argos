<!--
  Visibility timeline for one night (spec 06 sections 1.7, 2.3.1, 2.4; Q-P6, Q-P10, S26;
  M74), promoted from src/lab/charts/charts/VisibilityTimeline.svelte (web/lab/PROPOSAL.md
  section 6, W6). The geometry is the server's (A65, api/sequence.ts checkVisibility); the
  model is charts/visibility.ts.

  - Twilight as luminance washes of --fg-muted, no hue (Night Red keeps them apart): the
    four steps when the server sends the Sun's altitude, else everything outside the
    astronomical night (Q-P6) as one wash.
  - Altitude in a NEUTRAL ink (BRAND 10: geometry is not a photometric role, and brass
    stays scarce); the part below the minimum altitude is dashed, so "too low" never
    rests on colour. The minimum altitude (a site setting) is a --chart-reference line
    with its value written on it.
  - The planned run: an outlined band (edges) with a strip at the bottom where the subs
    already taken are a NEUTRAL coverage fill; a transit: the transit itself hatched,
    its baseline (coverage start and end) dotted edges. Outline, hatch and wash differ by
    pattern, not hue (spec 2.4 Night Red).
  - Now: --chart-highlight line. Peak: a dotted reference and a direct label.
  - Two time rows on one x scale: UTC under the plot (named), the computer's local time
    above (named by its offset). One y axis. No pan, zoom or export (spec 2.2, 1.7 #1-3).
  - Empty states say why (no site: never a 0 / 0 curve, P4; no source; the server's words).
-->
<script lang="ts">
  import type uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import './plot-host.css';
  import { untrack } from 'svelte';
  import type { TransitSpans, Visibility } from '../api/sequence';
  import Button from '../components/Button.svelte';
  import Spinner from '../components/Spinner.svelte';
  import { clockUtc } from '../format/time';
  import { readInks, type ChartInks } from './ink';
  import { coverageSegments } from './mini/progress';
  import { drawText } from './text';
  import { PlotHost } from './uplot/host';
  import { annotations, haloText, type Annotation } from './uplot/overlays';
  import { utcAxis, valueAxis } from './uplot/axes';
  import { aboveSpans, browserOffsetMin, factsLine, hoverRead, peakWords, runCheck, splitAtLimit, twilightSpans, zoneLabel, type Span } from './visibility';

  export type VisibilityEmpty = { kind: 'site' | 'source' | 'loading' | 'error'; message?: string };

  interface Props {
    vis: Visibility | null;
    /** Why there is no curve (ignored when `vis` is set). */
    empty?: VisibilityEmpty | null;
    /** The source's name ("T CrB"). */
    target?: string | null;
    /** The planned run (start: now or the scheduled start; end: start + the plan's estimate). */
    run?: Span | null;
    transit?: TransitSpans | null;
    /** Saved subs of the run in progress (unix s, prefix of length nFrames). */
    frames?: ArrayLike<number> | null;
    nFrames?: number;
    /** Unix s; null hides the now-line (a night that is not tonight). */
    now?: number | null;
    /** Minutes east of UTC for the local row (default: the browser's zone). */
    offsetMin?: number | null;
    /** Rebuild the plot when this changes (the tokens moved). */
    theme?: unknown;
    /** Link of the "no site" state (Settings > Site). */
    onsite?: () => void;
  }

  let { vis, empty = null, target = null, run = null, transit = null, frames = null, nFrames = 0, now = null, offsetMin = null, theme, onsite }: Props = $props();

  let root: HTMLDivElement | undefined = $state();
  let host: PlotHost | null = null;
  let inks: ChartInks | null = null;
  let hoverIdx = $state<number | null>(null);
  let hoverLeft = $state(0);
  let plotW = $state(0);

  const label = $derived(target || 'Source');
  const limit = $derived(vis?.minAlt ?? 30);
  const offset = $derived(offsetMin ?? (vis ? browserOffsetMin((vis.t[0] + vis.t[vis.t.length - 1]) / 2) : 0));
  const windows = $derived.by<Span[]>(() => {
    if (!vis) return [];
    // The server's spans for its own limit; recomputed from the samples otherwise.
    if (vis.windows.length && vis.minAlt === limit) return vis.windows;
    return aboveSpans(vis.t, vis.alt, limit, vis.dark);
  });
  /** Above the limit whatever the Sun (the run check's "below" parts). */
  const above = $derived(vis ? aboveSpans(vis.t, vis.alt, limit) : []);
  const check = $derived(vis ? runCheck(run, above, windows, limit, vis.dark, label) : null);
  const facts = $derived(vis ? factsLine(vis, windows, limit) : '');
  const hover = $derived(vis && hoverIdx !== null ? hoverRead(vis, hoverIdx, offset) : null);
  const inRun = $derived(vis && hoverIdx !== null && run ? vis.t[hoverIdx] >= run.start && vis.t[hoverIdx] <= run.end : false);
  const inTransit = $derived(vis && hoverIdx !== null && transit ? vis.t[hoverIdx] >= transit.ingress && vis.t[hoverIdx] <= transit.egress : false);

  function data(): uPlot.AlignedData {
    if (!vis) return [[], [], []];
    const s = splitAtLimit(vis.alt, limit);
    return [Array.from(vis.t), s.above, s.below];
  }

  function annFor(): Annotation[] {
    const ink = inks;
    if (!ink || !vis) return [];
    const out: Annotation[] = [];
    for (const s of twilightSpans(vis)) out.push({ kind: 'vspan', from: s.start, to: s.end, fill: ink.fgMuted.a(ink.twilight[s.level]) });
    if (transit) {
      out.push({ kind: 'vspan', from: transit.coverageStart, to: transit.coverageEnd, edge: ink.fgMuted.a(0.8), edgeDash: [1, 3] });
      out.push({
        kind: 'vspan',
        from: transit.ingress,
        to: transit.egress,
        hatch: ink.fgMuted.a(ink.flagAlpha * 1.6),
        label: { text: `transit ${clockUtc(transit.ingress, false)} → ${clockUtc(transit.egress, false)}`, at: 'bottom', dy: -14, halo: true },
      });
    }
    if (run && run.end > run.start) {
      out.push({ kind: 'vspan', from: run.start, to: run.end, edge: ink.fg.a(0.6), label: { text: `planned run ${clockUtc(run.start, false)} → ${clockUtc(run.end, false)}`, at: 'top', halo: true }, layer: 'over' });
    }
    out.push({ kind: 'hline', y: limit, color: ink.reference.a(), dash: [5, 3], label: { text: `min. altitude ${limit}°`, at: 'left' } });
    if (vis.peak) out.push({ kind: 'vline', x: vis.peak.t, color: ink.reference.a(0.7), dash: [1, 3] });
    if (now !== null) out.push({ kind: 'vline', x: now, color: ink.highlight.a(0.9), label: { text: `now ${clockUtc(now, false)}`, at: 'top', dy: run ? 18 : 0, halo: true } });
    return out;
  }

  /** The run's bottom strip (outlined) with the coverage of the subs taken, the peak label, the row names. */
  function extras(): uPlot.Plugin {
    return {
      hooks: {
        draw: [
          (u) => {
            const ink = inks;
            if (!ink || !vis) return;
            const dpr = devicePixelRatio || 1;
            const { ctx } = u;
            const { left, top, width, height } = u.bbox;
            ctx.save();
            if (run && run.end > run.start) {
              const xa = Math.max(left, u.valToPos(run.start, 'x', true));
              const xb = Math.min(left + width, u.valToPos(run.end, 'x', true));
              const h = 6 * dpr;
              const y = top + height - h - 2 * dpr;
              if (xb > xa) {
                ctx.strokeStyle = ink.fg.a(0.6);
                ctx.lineWidth = dpr;
                ctx.strokeRect(Math.round(xa) + 0.5, Math.round(y) + 0.5, Math.round(xb - xa) - 1, Math.round(h));
                if (frames && nFrames > 0) {
                  ctx.fillStyle = ink.fgMuted.a(0.85);
                  for (const [a, b] of coverageSegments(frames, nFrames)) {
                    const x0 = Math.max(xa, u.valToPos(a, 'x', true));
                    const x1 = Math.min(xb, u.valToPos(b, 'x', true));
                    if (x1 >= x0) ctx.fillRect(Math.round(x0), Math.round(y) + dpr, Math.max(dpr, Math.round(x1 - x0)), Math.round(h) - dpr);
                  }
                }
              }
            }
            const font = `500 ${Math.round(10 * dpr)}px ${ink.mono}`;
            if (vis.peak) {
              const px = u.valToPos(vis.peak.t, 'x', true);
              const py = u.valToPos(vis.peak.alt, 'y', true);
              const text = (peakWords(vis) ?? '').replace(/ at (\d\d:\d\d)/, ' · $1');
              // Above the peak, unless the labels of the top row (the planned run, then "now" under
              // it) are there: then below it.
              ctx.font = font;
              const half = ctx.measureText(text).width / 2;
              const boxes: [number, number][] = [];
              if (run && run.end > run.start) {
                const xa = Math.max(left, u.valToPos(run.start, 'x', true));
                boxes.push([xa, xa + ctx.measureText(`planned run ${clockUtc(run.start, false)} → ${clockUtc(run.end, false)}`).width + 8 * dpr]);
              }
              if (now !== null) {
                const xn = u.valToPos(now, 'x', true);
                boxes.push([xn - 4 * dpr, xn + ctx.measureText(`now ${clockUtc(now, false)}`).width + 12 * dpr]);
              }
              const rowBottom = top + (run ? 34 : 16) * dpr;
              const below = py - 20 * dpr < rowBottom && boxes.some(([a, b]) => px + half > a && px - half < b);
              if (px > left + 40 * dpr && px < left + width - 40 * dpr && py > top + 30 * dpr) {
                // A halo, not a box: the curve under the label stays visible (BRAND 10).
                const ty = below ? py + 8 * dpr : py - 6 * dpr;
                haloText(ctx, ink, text, px, ty, font, 'center', below ? 'top' : 'bottom');
              }
            }
            const small = `500 ${Math.round(9 * dpr)}px ${ink.mono}`;
            drawText(ctx, zoneLabel(offset), left + width + 6 * dpr, top - 10 * dpr, { font: small, fill: ink.textMuted.a(), align: 'left', baseline: 'middle' });
            drawText(ctx, 'UTC', left + width + 6 * dpr, top + height + 12 * dpr, { font: small, fill: ink.textMuted.a(), align: 'left', baseline: 'middle' });
            ctx.restore();
          },
        ],
      },
    };
  }

  function nearRightEdge(u: uPlot, v: number): boolean {
    const x = u.valToPos(v, 'x');
    const right = u.bbox.width / (devicePixelRatio || 1);
    return Number.isFinite(x) && right - x < 28;
  }

  function options(): uPlot.Options {
    const ink = inks as ChartInks;
    const font = `400 10px ${ink.mono}`;
    const t0 = vis ? vis.t[0] : 0;
    const t1 = vis ? vis.t[vis.t.length - 1] : 1;
    const local = (v: number) => clockUtc(v + offset * 60, false);
    const utc = utcAxis(ink, { labels: true, suffix: false });
    const utcValues = utc.values as (u: uPlot, splits: number[], ...rest: unknown[]) => string[];
    // The row names ("UTC", the zone) sit right of the plot: a tick label within 28 px of the
    // right edge would run into them, so it is left out (the grid line stays).
    const bottom: uPlot.Axis = { ...utc, values: (u, splits, ...rest) => utcValues(u, splits, ...rest).map((t, i) => (nearRightEdge(u, splits[i]) ? '' : t)) };
    return {
      width: 100,
      height: 100,
      padding: [6, 40, 0, 6],
      legend: { show: false },
      cursor: {
        points: { show: false },
        drag: { x: false, y: false, setScale: false },
        focus: { prox: -1 },
      },
      scales: { x: { time: false, range: [t0, t1] }, y: { range: [0, 90] } },
      axes: [
        bottom,
        {
          scale: 'x',
          side: 0,
          stroke: ink.text.a(0.75),
          font,
          size: 18,
          gap: 2,
          ticks: { show: false },
          grid: { show: false },
          splits: bottom.splits,
          values: (u, splits) => splits.map((v) => (nearRightEdge(u, v) ? '' : local(v))),
        },
        valueAxis(ink, { format: (v) => `${v}°`, size: 36, space: 18, splits: () => [0, 15, 30, 45, 60, 75, 90].filter((v) => Math.abs(v - limit) > 5) }),
      ],
      series: [
        {},
        { stroke: ink.fg.a(0.9), width: 2, spanGaps: false, points: { show: false } },
        { stroke: ink.fgMuted.a(0.9), width: 1.5, dash: [5, 4], spanGaps: false, points: { show: false } },
      ],
      plugins: [annotations(annFor, () => inks), extras()],
      hooks: {
        setCursor: [
          (u) => {
            const i = u.cursor.idx;
            hoverIdx = i == null || (u.cursor.left ?? -1) < 0 ? null : i;
            hoverLeft = (u.cursor.left ?? 0) + u.over.offsetLeft;
          },
        ],
      },
    };
  }

  function attach(el: HTMLElement) {
    inks = readInks(el);
    host = new PlotHost(el, () => ({ opts: options(), data: data() }));
    return () => {
      host?.destroy();
      host = null;
    };
  }

  // Tokens or the night changed: rebuild (the x range and the axes live in the options).
  $effect(() => {
    void theme;
    void vis;
    void offset;
    untrack(() => {
      if (!root) return;
      inks = readInks(root);
      host?.build();
    });
  });

  // The overlays (run, transit, frames, now) only redraw.
  $effect(() => {
    void run;
    void transit;
    void nFrames;
    void now;
    void limit;
    untrack(() => host?.u?.setData(data(), false));
  });

  const where = $derived(vis ? `${vis.siteName ? ` · ${vis.siteName}` : ''}${vis.night ? ` · night of ${vis.night}` : ''}` : '');
  const aria = $derived(
    vis
      ? `Altitude of ${label} over the night of ${vis.night ?? 'the chosen date'}: ${facts}${check ? `. ${check.text}` : ''}`
      : `Visibility of ${label}: no curve`,
  );
</script>

<div class="vis" bind:this={root}>
  {#if vis}
    <div class="head">
      <span class="what"><b>{label}</b>{where}</span>
      <span class="facts">{facts}</span>
      <!-- The run check on its own row: the planning answer is never cut (design review W6a). -->
      {#if check}
        <span class="check" class:note={!check.ok}>
          <span class="mark" aria-hidden="true"></span><span class="visually-hidden">{check.ok ? 'OK:' : 'Note:'}</span>{check.text}
        </span>
      {/if}
    </div>
    <div class="plot-host plot" bind:clientWidth={plotW} {@attach attach} role="img" aria-label={aria}>
      {#if hover}
        <div class="readout num" style:left="{hoverLeft + 210 > plotW ? hoverLeft - 204 : hoverLeft + 14}px" aria-hidden="true">
          <div class="t">{hover.utc} UTC · {hover.local} {zoneLabel(offset) === 'UTC' ? 'local' : zoneLabel(offset)}</div>
          <div>{label} <b>{hover.alt}</b> · airmass <b>{hover.airmass}</b></div>
          <div>{hover.phase}{inRun ? ' · planned run' : ''}{inTransit ? ' · transit' : ''}</div>
        </div>
      {/if}
    </div>
  {:else}
    <div class="empty" role="status">
      {#if empty?.kind === 'loading'}
        <Spinner size={16} /><span>Computing the altitudes for the night…</span>
      {:else if empty?.kind === 'site'}
        <span>{empty.message ?? 'Set the observing site in Settings to compute altitudes.'}</span>
        {#if onsite}<Button label="Open Settings › Site" size="s" onclick={onsite} />{/if}
      {:else if empty?.kind === 'error'}
        <span class="err"><span class="mark" aria-hidden="true"></span>{empty.message ?? 'The altitudes could not be computed.'}</span>
      {:else}
        <span>{empty?.message ?? 'Find a source to see its altitude tonight.'}</span>
      {/if}
    </div>
  {/if}
</div>

<style>
  .vis {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    min-width: 0;
    background: var(--chart-surface);
  }
  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    column-gap: var(--space-3);
    row-gap: 2px;
    min-height: 26px;
    padding: 3px var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    font-size: var(--text-xs);
    color: var(--text-muted);
    white-space: nowrap;
    min-width: 0;
  }
  .what b {
    color: var(--fg);
    font-weight: var(--weight-semibold);
  }
  .facts {
    font-variant-numeric: var(--numeric);
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--fg);
    flex: 1 0 100%;
    white-space: normal;
  }
  /* OK: a filled dot; a note: the attention mark (a bar over a dot), never colour alone. */
  .check .mark {
    flex: none;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--status-ok);
  }
  .check.note .mark {
    width: 3px;
    height: 11px;
    border-radius: 0;
    background: linear-gradient(var(--warning) 0 6px, transparent 6px 8px, var(--warning) 8px 11px);
  }
  .plot {
    flex: 1;
    margin: var(--space-1) var(--space-2) var(--space-1) 0;
  }
  .readout {
    position: absolute;
    top: 28px;
    z-index: 3;
    width: 196px;
    padding: var(--space-1) var(--space-2);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--surface);
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: 1.5;
    pointer-events: none;
  }
  .readout .t {
    color: var(--fg);
  }
  .readout b {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .empty {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-3);
    padding: var(--space-4);
    color: var(--text-muted);
    font-size: var(--text-s);
    text-align: center;
  }
  .err {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--fg);
  }
  .err .mark {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--danger);
    flex: none;
  }
</style>

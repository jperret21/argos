<!--
  Autofocus V-curve (spec 05 1.5, P9), promoted from src/lab/charts/charts/VCurve.svelte
  and core/fit.ts (web/lab/PROPOSAL.md 3.2 and 6, W3), on the server's `autofocus` record
  (A36; the model is charts/vcurve.ts).

  - Samples: filled = in the fit (the samples the worker fits: the fine sweep and the
    coarse minimum; every coarse sample while the coarse sweep runs), hollow = the rest of
    the coarse sweep, left out as the worker leaves it out; the verification frame is ringed; a failed frame is a tick on the
    axis (no HFD is invented). Error bars on the fitted samples are their +/- 1 sigma
    scatter about the fit: the server sends no per-sample error, and the legend says so.
  - Display fit: a hyperbola over the fitted samples (solid), extrapolated dashed, with its
    +/- 1 sigma envelope and its asymptotes (the "V"). While the sweep runs its vertex is
    PROVISIONAL (dashed reference line, no brass).
  - The worker's own parabola is drawn dotted over its window: it is what moved the
    focuser. The DECISION (`best.position` once the sweep ends `done`) is the one brass
    line (BRAND 3: a decision).
  - The focuser's polled position is the highlight line; it jumps from step to step (the
    hardware moves in steps; no tween). The start position is a dotted reference.
  - Data never animates; the plot is rebuilt on a theme change only, a new sample only
    replaces the data.
-->
<script lang="ts">
  import type uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import './plot-host.css';
  import { untrack } from 'svelte';
  import { fixed, int } from '../format/number';
  import { readInks, type ChartInks } from './ink';
  import { PlotHost } from './uplot/host';
  import { annotations, type Annotation } from './uplot/overlays';
  import { valueAxis } from './uplot/axes';
  import { addErrorBar, addShape } from './uplot/markers';
  import { hyperbola } from './fit';
  import { curveColumns, vcurveModel, type AutofocusRecord, type VCurveModel } from './vcurve';

  interface Props {
    af: AutofocusRecord | null;
    /** Rebuild the plot when this changes (the tokens moved). */
    theme?: unknown;
    /** Show the legend row above the plot. */
    legend?: boolean;
    label?: string;
  }

  let { af, theme, legend = true, label = 'Autofocus V-curve' }: Props = $props();

  let root: HTMLDivElement;
  let host: PlotHost | null = null;
  let inks: ChartInks | null = null;
  let hoverI = $state<number | null>(null);
  let hoverXY = $state({ x: 0, y: 0 });

  const model: VCurveModel = $derived(vcurveModel(af));
  // Read inside uPlot hooks without tracking.
  let current: VCurveModel = untrack(() => model);

  function data(): uPlot.AlignedData {
    const c = curveColumns(current);
    return [c.xs, c.inside, c.outside, c.hi, c.lo, c.parabola];
  }

  function annFor(): Annotation[] {
    const ink = inks!;
    const m = current;
    const out: Annotation[] = [];
    if (m.provisional) {
      const { position, sigma } = m.provisional;
      out.push({ kind: 'vspan', from: position - sigma, to: position + sigma, fill: ink.reference.a(0.1) });
      out.push({
        kind: 'vline',
        x: position,
        color: ink.reference.a(),
        dash: [5, 3],
        label: { text: `vertex ${int(position)} ± ${int(Math.max(1, sigma))} · provisional`, at: 'top', color: ink.fg.a() },
      });
    }
    if (m.decided) {
      out.push({
        kind: 'vline',
        x: m.decided.position,
        color: ink.accent.a(),
        width: 1.5,
        label: { text: `best ${int(m.decided.position)}${m.decided.method === 'raw' ? ' · lowest sample' : ''}`, at: 'top', color: ink.fg.a() },
      });
    }
    if (m.start !== null) {
      out.push({ kind: 'vline', x: m.start, color: ink.reference.a(0.6), dash: [1, 3], label: { text: `start ${int(m.start)}`, at: 'bottom' } });
    }
    if (m.focuser !== null && af && (af.state === 'running' || af.state === 'stopping')) {
      out.push({ kind: 'vline', x: m.focuser, color: ink.highlight.a(0.85), dash: [4, 3], label: { text: `focuser ${int(m.focuser)}`, at: 'top', dy: 18 } });
    }
    return out;
  }

  function samplesPlugin(): uPlot.Plugin {
    return {
      hooks: {
        draw: [
          (u) => {
            const ink = inks;
            if (!ink) return;
            const m = current;
            const dpr = devicePixelRatio || 1;
            const { ctx } = u;
            const { left, top, width, height } = u.bbox;
            ctx.save();
            ctx.beginPath();
            ctx.rect(left, top, width, height);
            ctx.clip();
            // Asymptotes: the V itself (slopes +/- a / b through (c, 0)).
            const f = m.fit;
            if (f && f.b > 0 && f.b < 1e6) {
              const k = f.a / f.b;
              ctx.strokeStyle = ink.reference.a(0.5);
              ctx.lineWidth = dpr;
              ctx.setLineDash([2 * dpr, 4 * dpr]);
              ctx.beginPath();
              for (const xe of m.xRange) {
                ctx.moveTo(u.valToPos(f.c, 'x', true), u.valToPos(0, 'y', true));
                ctx.lineTo(u.valToPos(xe, 'x', true), u.valToPos(k * Math.abs(xe - f.c), 'y', true));
              }
              ctx.stroke();
              ctx.setLineDash([]);
            }
            const r = 4 * dpr;
            const bars = new Path2D();
            const solid = new Path2D();
            const open = new Path2D();
            const failed = new Path2D();
            for (const s of m.samples) {
              const x = u.valToPos(s.x, 'x', true);
              if (s.kind === 'failed') {
                const yb = top + height;
                failed.moveTo(Math.round(x) + 0.5, yb);
                failed.lineTo(Math.round(x) + 0.5, yb - 8 * dpr);
                continue;
              }
              const y = u.valToPos(s.y, 'y', true);
              if (s.kind === 'fitted' && m.scatter && m.scatter > 0) {
                const ya = u.valToPos(s.y - m.scatter, 'y', true);
                const yb = u.valToPos(s.y + m.scatter, 'y', true);
                if (Math.abs(yb - ya) > 2 * r) addErrorBar(bars, x, ya, yb, 3 * dpr);
              }
              addShape(s.kind === 'outside' ? open : solid, 'dot', x, y, r);
            }
            ctx.strokeStyle = ink.fg.a();
            ctx.globalAlpha = ink.errorAlpha;
            ctx.lineWidth = dpr;
            ctx.stroke(bars);
            ctx.globalAlpha = 1;
            ctx.fillStyle = ink.fg.a();
            ctx.fill(solid);
            ctx.lineWidth = 1.5 * dpr;
            ctx.stroke(open);
            ctx.strokeStyle = ink.warning.a();
            ctx.stroke(failed);
            const verify = m.samples.find((s) => s.kind === 'verify');
            const last = m.samples[m.samples.length - 1];
            const ring = verify ?? (af?.state === 'running' ? last : null);
            if (ring && Number.isFinite(ring.y)) {
              ctx.strokeStyle = ring.kind === 'verify' && m.decided ? ink.accent.a() : ink.highlight.a();
              ctx.lineWidth = 1.5 * dpr;
              ctx.beginPath();
              ctx.arc(u.valToPos(ring.x, 'x', true), u.valToPos(ring.y, 'y', true), r + 4 * dpr, 0, Math.PI * 2);
              ctx.stroke();
            }
            const hov = hoverI !== null ? m.samples[hoverI] : null;
            if (hov && Number.isFinite(hov.y)) {
              ctx.strokeStyle = ink.highlight.a();
              ctx.lineWidth = 1.5 * dpr;
              ctx.beginPath();
              ctx.arc(u.valToPos(hov.x, 'x', true), u.valToPos(hov.y, 'y', true), r + 2.5 * dpr, 0, Math.PI * 2);
              ctx.stroke();
            }
            ctx.restore();
          },
        ],
      },
    };
  }

  function options(): uPlot.Options {
    const ink = inks!;
    const font = `400 10px ${ink.mono}`;
    return {
      width: 100,
      height: 100,
      padding: [12, 16, 0, 4],
      legend: { show: false },
      cursor: { show: true, x: false, y: false, points: { show: false }, drag: { x: false, y: false, setScale: false } },
      select: { show: false, left: 0, top: 0, width: 0, height: 0 },
      scales: {
        x: { time: false, range: () => current.xRange },
        y: { range: () => [current.yMin, current.yMax] },
      },
      axes: [
        {
          stroke: ink.text.a(),
          font,
          size: 34,
          gap: 3,
          space: 70,
          ticks: { stroke: ink.axis.a(), width: 1, size: 3 },
          grid: { stroke: ink.grid.a(), width: 1 },
          border: { show: true, stroke: ink.axis.a(), width: 1 },
          values: (_u, splits) => splits.map((v) => int(v)),
          label: 'focuser position · steps',
          labelSize: 14,
          labelFont: font,
        },
        valueAxis(ink, { format: (v) => fixed(v, Number.isInteger(v) ? 0 : 1), size: 40, space: 30, label: 'HFD · px' }),
      ],
      series: [
        {},
        { stroke: ink.reference.a(), width: 1.75, points: { show: false } },
        { stroke: ink.reference.a(0.7), width: 1.25, dash: [5, 4], points: { show: false } },
        { stroke: 'rgba(0,0,0,0)', width: 0, points: { show: false } },
        { stroke: 'rgba(0,0,0,0)', width: 0, points: { show: false } },
        { stroke: ink.fgMuted.a(0.9), width: 1.25, dash: [1.5, 3], points: { show: false } },
      ],
      bands: [{ series: [3, 4], fill: ink.reference.a(ink.bandAlpha) }],
      plugins: [annotations(annFor, () => inks), samplesPlugin()],
      hooks: {
        init: [
          (u) => {
            u.over.addEventListener('pointermove', (e) => {
              const rect = u.over.getBoundingClientRect();
              const mx = e.clientX - rect.left;
              const my = e.clientY - rect.top;
              let best: number | null = null;
              let bd = 16;
              current.samples.forEach((s, i) => {
                if (!Number.isFinite(s.y)) return;
                const d = Math.hypot(u.valToPos(s.x, 'x') - mx, u.valToPos(s.y, 'y') - my);
                if (d < bd) {
                  bd = d;
                  best = i;
                }
              });
              if (best !== hoverI) {
                hoverI = best;
                u.redraw(false, false);
              }
              hoverXY = { x: mx + u.over.offsetLeft, y: my + u.over.offsetTop };
            });
            u.over.addEventListener('pointerleave', () => {
              hoverI = null;
              u.redraw(false, false);
            });
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

  $effect(() => {
    void theme;
    untrack(() => {
      if (!root) return;
      inks = readInks(root);
      host?.build();
    });
  });

  // New sample, new state: new data (instant), new ranges.
  $effect(() => {
    const m = model;
    untrack(() => {
      current = m;
      host?.u?.setData(data(), true);
    });
  });

  const hovered = $derived(hoverI !== null ? (model.samples[hoverI] ?? null) : null);
  const stageWord: Record<string, string> = { coarse: 'coarse', fine: 'fine', verify: 'verification' };
</script>

<div class="vcurve" bind:this={root}>
  {#if legend}
    <div class="keys" aria-hidden="true">
      <!-- Only the series drawn now, each glyph as plotted (review of wave 3). -->
      {#if model.samples.some((s) => s.kind === 'fitted')}<span class="key"><i class="dot"></i>fitted</span>{/if}
      {#if model.samples.some((s) => s.kind === 'outside')}<span class="key"><i class="dot open"></i>not fitted</span>{/if}
      {#if model.fit}
        <span class="key"><i class="line"></i>hyperbola ± 1σ{model.fitScope === 'all' ? ' · all samples' : ''}</span>
      {:else if model.noFit}
        <span class="key">{model.noFit}</span>
      {/if}
      {#if model.parabola}<span class="key"><i class="line dot-line"></i>worker parabola</span>{/if}
      {#if model.decided}<span class="key"><i class="line brass"></i>best</span>{/if}
      {#if model.scatter}<span class="key note num">bars ± {fixed(model.scatter, 2)} px scatter</span>{/if}
    </div>
  {/if}
  <div
    class="plot-host"
    {@attach attach}
    role="img"
    aria-label="{label}: {model.samples.length} samples{model.decided ? `, best focus ${model.decided.position} steps` : model.provisional ? `, provisional vertex ${Math.round(model.provisional.position)} steps` : ''}"
  >
    {#if hovered}
      <div class="readout num" style:left="{hoverXY.x + 14}px" style:top="{Math.max(4, hoverXY.y - 64)}px" aria-hidden="true">
        <div class="t">frame {hovered.n} · {stageWord[hovered.stage] ?? hovered.stage}{hovered.kind === 'outside' ? ' · not fitted' : ''}</div>
        <div>position <b>{int(hovered.x)}</b> steps</div>
        <div>HFD <b>{fixed(hovered.y, 2)}</b> px</div>
        {#if model.fit}<div>fit here <b>{fixed(hyperbola(hovered.x, model.fit.a, model.fit.b, model.fit.c), 2)}</b> px</div>{/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .vcurve {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    min-width: 0;
  }
  .keys {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 2px var(--space-3);
    padding: 0 var(--space-2) var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    flex: none;
  }
  .key {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
  }
  .key .dot {
    width: 7px;
    height: 7px;
    border-radius: var(--radius-round);
    background: var(--fg);
  }
  .key .dot.open {
    background: transparent;
    border: 1.5px solid var(--fg);
  }
  .key .line {
    width: 14px;
    border-top: 1.75px solid var(--chart-reference);
  }
  .key .line.dot-line {
    border-top: 1.5px dotted var(--fg-muted);
  }
  .key .line.brass {
    border-top-color: var(--accent);
  }
  .key.note {
    margin-left: auto;
  }
  .plot-host {
    flex: 1;
  }
  .readout {
    position: absolute;
    z-index: 2;
    padding: var(--space-1) var(--space-2);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    pointer-events: none;
    box-shadow: var(--elev-hud);
  }
  .readout .t {
    color: var(--fg);
  }
  .readout b {
    color: var(--fg);
    font-weight: var(--weight-regular);
  }
</style>

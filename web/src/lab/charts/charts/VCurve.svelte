<!--
  Autofocus V-curve, building point by point (spec 05 1.5 / 2.3 D, P9).

  - Coarse sweep (hollow dots: not in the fit), fine sweep around the coarse
    minimum (filled dots with their HFD error bars), then one verification
    frame at the chosen position (ringed).
  - The fit is the worker's: a weighted hyperbola on the fine samples only,
    refitted after each fine sample (it updates instantly: every drawn curve
    is the fit of the samples on screen). Drawn solid over the fitted window
    and dashed where it is extrapolated, with its +/- 1 sigma envelope; the
    asymptotes are the "V".
  - The chosen position is brass (a decision, BRAND 3) with its +/- 1 sigma
    band; the focuser's own position is the highlight line, and it jumps
    from step to step (the hardware moves in steps; no tween).
  - The verdict is in words, with the exact reason when rejected.
-->
<script lang="ts">
  import uPlot from 'uplot';
  import { untrack } from 'svelte';
  import Icon from '../../../lib/components/Icon.svelte';
  import { tooltip } from '../../../lib/components/tooltip';
  import { env } from '../env.svelte';
  import { gauss, prng } from '../sim/night';
  import { readInks, type ChartInks } from '../core/palette';
  import { PlotHost } from '../core/uplot/host';
  import { annotations, type Annotation } from '../core/uplot/overlays';
  import { valueAxis } from '../core/uplot/axes';
  import { addShape } from '../core/uplot/markers';
  import { curveSigma, fitHyperbola, hyperbola, judge, type HyperbolaFit, type Sample, type Verdict } from '../core/fit';
  import { fixed, grouped } from '../core/format';

  type Scenario = 'good' | 'seeing' | 'flat';
  type Stage = 'idle' | 'coarse' | 'fine' | 'verify' | 'done';
  interface AfSample extends Sample {
    stage: 'coarse' | 'fine' | 'verify';
    n: number;
  }

  interface Props {
    compact?: boolean;
  }
  let { compact = false }: Props = $props();

  const START = 1305;
  const COARSE = [600, 833, 1067, 1300, 1533, 1767, 2000];
  const FINE_STEP = 70;
  const MODELS: Record<Scenario, { a: number; b: number; c: number; noise: (y: number) => number; label: string }> = {
    good: { a: 2.55, b: 88, c: 1287, noise: (y) => 0.035 * y + 0.05, label: 'Good seeing' },
    seeing: { a: 3.2, b: 120, c: 1262, noise: (y) => 0.11 * y + 0.18, label: 'Poor seeing' },
    flat: { a: 3.1, b: 2600, c: 1290, noise: (y) => 0.025 * y + 0.04, label: 'Flat (no V)' },
  };

  const q = new URLSearchParams(location.search);
  let scenario = $state<Scenario>((['good', 'seeing', 'flat'] as const).find((s) => s === q.get('scenario')) ?? 'good');
  let samples = $state.raw<AfSample[]>([]);
  let stage = $state<Stage>('idle');
  let focuser = $state(START);
  let fit = $state.raw<HyperbolaFit | null>(null);
  let verdict = $state.raw<Verdict | null>(null);
  let hoverI = $state<number | null>(null);
  let hoverXY = $state({ x: 0, y: 0 });
  let plan: { x: number; stage: 'coarse' | 'fine' | 'verify' }[] = [];
  let timer = 0;
  let seed = 7;

  let root: HTMLDivElement;
  let host: PlotHost | null = null;
  let inks: ChartInks | null = null;

  const X0 = 520;
  const X1 = 2080;
  const GRID = 240;

  function measure(x: number, k: number): AfSample['y'] {
    const m = MODELS[scenario];
    const r = prng(seed * 101 + k * 7919 + Math.round(x));
    const y = hyperbola(x, m.a, m.b, m.c);
    return Math.max(1.2, y + m.noise(y) * gauss(r));
  }

  function fineSamples(list = samples): Sample[] {
    return list.filter((s) => s.stage === 'fine');
  }

  function refit(list: AfSample[]): void {
    const fine = fineSamples(list);
    fit = fine.length >= 4 ? fitHyperbola(fine) : null;
  }

  /** The next frame of the sweep: plan the fine sweep when the coarse one is done. */
  function step(): boolean {
    if (!plan.length) {
      if (stage === 'idle' || stage === 'done') {
        plan = COARSE.map((x) => ({ x, stage: 'coarse' }));
      } else if (stage === 'coarse') {
        const best = samples.reduce((a, b) => (b.y < a.y ? b : a));
        const c0 = Math.round(best.x / 10) * 10;
        plan = Array.from({ length: 9 }, (_, i) => ({ x: c0 - 4 * FINE_STEP + i * FINE_STEP, stage: 'fine' }));
      } else if (stage === 'fine') {
        const fine = fineSamples();
        verdict = judge(fit, fine, FINE_STEP);
        if (!verdict.accepted || !fit) {
          focuser = START;
          stage = 'done';
          return false;
        }
        plan = [{ x: Math.round(fit.c), stage: 'verify' }];
      } else {
        stage = 'done';
        return false;
      }
    }
    const next = plan.shift()!;
    stage = next.stage;
    focuser = next.x;
    const y = measure(next.x, samples.length);
    const s: AfSample = { x: next.x, y, s: MODELS[scenario].noise(y), stage: next.stage, n: samples.length + 1 };
    const list = [...samples, s];
    samples = list;
    if (next.stage === 'fine') refit(list);
    if (next.stage === 'verify') {
      stage = 'done';
      focuser = next.x;
      return false;
    }
    return true;
  }

  function run(): void {
    clearInterval(timer);
    seed++;
    samples = [];
    fit = null;
    verdict = null;
    plan = [];
    stage = 'idle';
    focuser = START;
    step();
    timer = window.setInterval(() => {
      if (!step()) clearInterval(timer);
    }, 520);
  }

  /** Jump to the end (or to step k) at once: the screenshot states. */
  function runTo(k: number): void {
    clearInterval(timer);
    samples = [];
    fit = null;
    verdict = null;
    plan = [];
    stage = 'idle';
    focuser = START;
    let i = 0;
    while (i++ < k && step());
  }

  // -- Plot ------------------------------------------------------------------------
  function data(): uPlot.AlignedData {
    const xs = new Float64Array(GRID);
    const inFit = new Array<number | null>(GRID);
    const outFit = new Array<number | null>(GRID);
    const hi = new Array<number | null>(GRID);
    const lo = new Array<number | null>(GRID);
    const fine = fineSamples();
    const fx0 = fine.length ? Math.min(...fine.map((s) => s.x)) : 0;
    const fx1 = fine.length ? Math.max(...fine.map((s) => s.x)) : 0;
    for (let i = 0; i < GRID; i++) {
      const x = X0 + ((X1 - X0) * i) / (GRID - 1);
      xs[i] = x;
      if (!fit) {
        inFit[i] = outFit[i] = hi[i] = lo[i] = null;
        continue;
      }
      const y = hyperbola(x, fit.a, fit.b, fit.c);
      const inside = x >= fx0 - 1 && x <= fx1 + 1;
      const step = (X1 - X0) / (GRID - 1);
      inFit[i] = inside || (x >= fx0 - step && x <= fx1 + step) ? y : null;
      outFit[i] = !inside || x < fx0 + step || x > fx1 - step ? y : null;
      const sg = curveSigma(fit, x);
      hi[i] = inside ? y + sg : null;
      lo[i] = inside ? y - sg : null;
    }
    return [xs, inFit, outFit, hi, lo];
  }

  function annFor(): Annotation[] {
    const ink = inks!;
    const out: Annotation[] = [];
    const accepted = verdict?.accepted ?? false;
    if (fit && verdict === null) {
      // Still sweeping: the vertex of the current fit, not yet a decision (no brass).
      out.push({ kind: 'vspan', from: fit.c - fit.sigmaC, to: fit.c + fit.sigmaC, fill: ink.reference.a(0.1) });
      out.push({ kind: 'vline', x: fit.c, color: ink.reference.a(), dash: [5, 3], label: { text: `vertex ${grouped(fit.c)} ± ${Math.max(1, Math.round(fit.sigmaC))} · provisional`, at: 'top', color: ink.fg.a() } });
    } else if (fit && accepted) {
      // The decision: brass (BRAND 3), with its 1 sigma band.
      out.push({ kind: 'vspan', from: fit.c - fit.sigmaC, to: fit.c + fit.sigmaC, fill: ink.accent.a(0.13) });
      out.push({ kind: 'vline', x: fit.c, color: ink.accent.a(), width: 1.5, label: { text: `best ${grouped(fit.c)} ± ${Math.max(1, Math.round(fit.sigmaC))}`, at: 'top', color: ink.fg.a() } });
    }
    out.push({ kind: 'vline', x: START, color: ink.reference.a(0.6), dash: [1, 3], label: { text: `start ${grouped(START)}`, at: 'bottom' } });
    if (stage !== 'idle') {
      out.push({ kind: 'vline', x: focuser, color: ink.highlight.a(0.85), dash: [4, 3], label: { text: `focuser ${grouped(focuser)}`, at: 'top', dy: 18 } });
    }
    return out;
  }

  function samplesPlugin(): uPlot.Plugin {
    return {
      hooks: {
        draw: [
          (u) => {
            const ink = inks!;
            const dpr = uPlot.pxRatio;
            const { ctx } = u;
            const { left, top, width, height } = u.bbox;
            ctx.save();
            ctx.beginPath();
            ctx.rect(left, top, width, height);
            ctx.clip();
            ctx.setLineDash([]);
            // Asymptotes: the V itself.
            if (fit && fit.b < 1000) {
              const k = fit.a / fit.b;
              ctx.strokeStyle = ink.reference.a(0.5);
              ctx.lineWidth = dpr;
              ctx.setLineDash([2 * dpr, 4 * dpr]);
              ctx.beginPath();
              for (const xe of [X0, X1]) {
                ctx.moveTo(u.valToPos(fit.c, 'x', true), u.valToPos(0, 'y', true));
                ctx.lineTo(u.valToPos(xe, 'x', true), u.valToPos(k * Math.abs(xe - fit.c), 'y', true));
              }
              ctx.stroke();
              ctx.setLineDash([]);
            }
            const r = 4 * dpr;
            const bars = new Path2D();
            const solid = new Path2D();
            const open = new Path2D();
            for (const s of samples) {
              const x = u.valToPos(s.x, 'x', true);
              const y = u.valToPos(s.y, 'y', true);
              const ya = u.valToPos(s.y - s.s, 'y', true);
              const yb = u.valToPos(s.y + s.s, 'y', true);
              if (s.stage !== 'coarse' && Math.abs(yb - ya) > 2 * r) {
                const xr = Math.round(x) + 0.5;
                bars.moveTo(xr, ya);
                bars.lineTo(xr, yb);
                bars.moveTo(xr - 3 * dpr, Math.round(ya) + 0.5);
                bars.lineTo(xr + 3 * dpr, Math.round(ya) + 0.5);
                bars.moveTo(xr - 3 * dpr, Math.round(yb) + 0.5);
                bars.lineTo(xr + 3 * dpr, Math.round(yb) + 0.5);
              }
              addShape(s.stage === 'coarse' ? open : solid, 'dot', x, y, r);
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
            const last = samples[samples.length - 1];
            if (last) {
              ctx.strokeStyle = last.stage === 'verify' ? ink.accent.a() : ink.highlight.a();
              ctx.lineWidth = 1.5 * dpr;
              ctx.beginPath();
              ctx.arc(u.valToPos(last.x, 'x', true), u.valToPos(last.y, 'y', true), r + 4 * dpr, 0, Math.PI * 2);
              ctx.stroke();
            }
            if (hoverI !== null && samples[hoverI]) {
              const s = samples[hoverI];
              ctx.strokeStyle = ink.highlight.a();
              ctx.lineWidth = 1.5 * dpr;
              ctx.beginPath();
              ctx.arc(u.valToPos(s.x, 'x', true), u.valToPos(s.y, 'y', true), r + 2.5 * dpr, 0, Math.PI * 2);
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
    return {
      width: 100,
      height: 100,
      padding: [12, 24, 0, 4],
      legend: { show: false },
      cursor: { show: true, x: false, y: false, points: { show: false }, drag: { x: false, y: false, setScale: false } },
      scales: {
        x: { time: false, range: [X0, X1] },
        y: {
          range: () => {
            let max = 6;
            for (const s of samples) max = Math.max(max, s.y + s.s);
            return [0, Math.ceil(max * 1.08)];
          },
        },
      },
      axes: [
        {
          stroke: ink.text.a(),
          font: `400 10px ${ink.mono}`,
          size: 34,
          gap: 3,
          space: 70,
          ticks: { stroke: ink.axis.a(), width: 1, size: 3 },
          grid: { stroke: ink.grid.a(), width: 1 },
          border: { show: true, stroke: ink.axis.a(), width: 1 },
          values: (_u, splits) => splits.map((v) => grouped(v)),
          label: 'focuser position · steps',
          labelSize: 14,
          labelFont: `400 10px ${ink.mono}`,
        },
        { ...valueAxis(ink, { format: (v) => fixed(v, Number.isInteger(v) ? 0 : 1), size: 44, space: 34 }), label: 'HFD · px', labelSize: 14, labelFont: `400 10px ${ink.mono}` },
      ],
      series: [
        {},
        { stroke: ink.reference.a(), width: 1.75, points: { show: false } },
        { stroke: 'rgba(0,0,0,0)', width: 0, points: { show: false }, show: false },
        { stroke: 'rgba(0,0,0,0)', width: 0, points: { show: false } },
        { stroke: 'rgba(0,0,0,0)', width: 0, points: { show: false } },
      ],
      bands: [{ series: [3, 4], fill: ink.reference.a(ink.lab.bandAlpha) }],
      plugins: [annotations(annFor, () => inks!), samplesPlugin()],
      hooks: {
        init: [
          (u) => {
            u.over.addEventListener('mousemove', (e) => {
              const rect = u.over.getBoundingClientRect();
              const mx = e.clientX - rect.left;
              const my = e.clientY - rect.top;
              let best: number | null = null;
              let bd = 16;
              samples.forEach((s, i) => {
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
            u.over.addEventListener('mouseleave', () => {
              hoverI = null;
              u.redraw(false, false);
            });
          },
        ],
      },
    };
  }

  function attach(el: HTMLElement) {
    host = new PlotHost(el, () => ({ opts: options(), data: data() }));
    return () => {
      host?.destroy();
      host = null;
    };
  }

  $effect(() => {
    void env.theme;
    untrack(() => {
      inks = readInks(root);
      host?.build();
    });
  });

  // New sample, new fit, new stage: new data (instant).
  $effect(() => {
    void samples;
    void fit;
    void stage;
    void focuser;
    untrack(() => host?.u?.setData(data(), true));
  });

  // Start: the URL may ask for a fixed state (screenshots), otherwise run live.
  {
    const af = q.get('af');
    if (af === 'done') runTo(99);
    else if (af?.startsWith('step-')) runTo(Number(af.slice(5)) || 5);
    else queueMicrotask(run);
  }
  $effect(() => () => clearInterval(timer));

  const total = COARSE.length + 9 + 1;
  const stageText: Record<Stage, string> = { idle: 'Idle', coarse: 'Coarse sweep', fine: 'Fine sweep', verify: 'Verification', done: 'Done' };
  const finalState = $derived(stage === 'done' && verdict ? (verdict.accepted ? 'Focused' : 'Rejected') : null);
  const hovered = $derived(hoverI !== null ? samples[hoverI] : null);
  const fineCount = $derived(samples.filter((s) => s.stage === 'fine').length);
  const SCENARIOS: Scenario[] = ['good', 'seeing', 'flat'];
</script>

<div class="vc" class:compact bind:this={root}>
  <section class="plotcol">
    <header class="head">
      <Icon name="autofocus" size={16} />
      <h3>V-curve</h3>
      <span class="sub">HFD against focuser position · this autofocus</span>
      <span class="grow"></span>
      <span class="key"><i class="dot"></i>fine (fitted)</span>
      <span class="key"><i class="dot open"></i>coarse (not fitted)</span>
      <span class="key"><i class="line"></i>hyperbola fit ± 1σ</span>
      <span class="key"><i class="line dash"></i>asymptotes (the V)</span>
      <span class="key"><i class="line brass"></i>chosen position</span>
    </header>
    <div class="lab-plot-host plot" {@attach attach} role="img" aria-label="Autofocus V-curve: {samples.length} samples{fit ? `, best focus ${Math.round(fit.c)} steps at ${fit.a.toFixed(2)} px` : ''}">
      {#if hovered}
        <div class="lab-readout" style:left="{hoverXY.x + 14}px" style:top="{Math.max(4, hoverXY.y - 70)}px" aria-hidden="true">
          <div class="t">frame {hovered.n} of {total} · {hovered.stage}</div>
          <hr />
          <div>position <span class="v">{grouped(hovered.x)}</span> steps</div>
          <div>HFD <span class="v">{fixed(hovered.y, 2)} ± {fixed(hovered.s, 2)}</span> px</div>
          {#if fit}<div>fit here <span class="v">{fixed(hyperbola(hovered.x, fit.a, fit.b, fit.c), 2)}</span> px</div>{/if}
        </div>
      {/if}
    </div>
  </section>

  <aside class="panel">
    <div class="state">
      <span class="lab-eyebrow">Autofocus</span>
      <span class="lab-chip" class:attention={finalState === 'Rejected'}>
        <span class="lab-dot {finalState === 'Focused' ? 'ok' : finalState === 'Rejected' ? 'error' : stage === 'idle' ? '' : 'busy'}"></span>{finalState ?? stageText[stage]}
      </span>
    </div>
    <div class="progress" aria-label="Step {samples.length} of {total}">
      <div class="ticks">
        {#each Array.from({ length: total }, (_, i) => i) as i (i)}
          <i class:done={i < samples.length} class:fine={i >= COARSE.length && i < total - 1} class:verify={i === total - 1}></i>
        {/each}
      </div>
      <span class="num">step <b>{samples.length}</b> / {total} · {stageText[stage].toLowerCase()}</span>
    </div>

    <dl class="readouts">
      <dt>Focuser</dt>
      <dd class="num big">{grouped(focuser)}<small>steps</small></dd>
      <dt>{verdict ? 'Best focus' : 'Vertex (so far)'}</dt>
      <dd class="num big">{#if fit && (verdict?.accepted ?? true)}{grouped(fit.c)}<small>± {Math.max(1, Math.round(fit.sigmaC))} steps</small>{:else}—{/if}</dd>
      <dt>HFD at best</dt>
      <dd class="num big">{#if fit && (verdict?.accepted ?? true)}{fixed(fit.a, 2)}<small>± {fixed(fit.sigmaA, 2)} px</small>{:else}—{/if}</dd>
      <dt>Fit</dt>
      <dd class="num">{#if fit}{fineCount} fine · R² {fixed(fit.r2, 3)} · χ²<sub>red</sub> {fixed(fit.chi2red, 2)}{:else}{fineCount < 4 && stage === 'fine' ? `waiting for 4 fine samples (${fineCount})` : 'pending'}{/if}</dd>
    </dl>

    {#if verdict}
      <p class="verdict" class:rejected={!verdict.accepted}>
        {#if verdict.accepted}
          <b>Measured.</b> Focuser moved to {grouped(focuser)}{samples.at(-1)?.stage === 'verify' ? `; verification frame ${fixed(samples.at(-1)!.y, 2)} px` : ''}.
        {:else}
          <b>Rejected:</b> {verdict.reason}. Focus unchanged, returned to {grouped(START)}.
        {/if}
      </p>
    {/if}

    <div class="actions">
      <button class="lab-btn primary" onclick={run} use:tooltip={{ text: 'Run the autofocus sweep (moves the focuser)' }}>
        <Icon name="autofocus" size={16} />Autofocus
      </button>
      <div class="lab-seg" role="radiogroup" aria-label="Scenario">
        {#each SCENARIOS as s (s)}
          <button
            role="radio"
            aria-checked={scenario === s}
            onclick={() => {
              scenario = s;
              run();
            }}>{MODELS[s].label}</button
          >
        {/each}
      </div>
    </div>
    <p class="note">AF frames 2.0 s, gain 80. Fit: weighted Levenberg–Marquardt on HFD = a·√(1 + ((x − c)/b)²), fine samples only; uncertainties from the covariance scaled by χ²<sub>red</sub>. Accepted when the span exceeds 15 %, the vertex lies inside the sweep and σ<sub>c</sub> ≤ ¼ step.</p>
  </aside>
</div>

<style>
  .vc {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 340px;
    height: 100%;
    min-height: 0;
    background: var(--chart-surface);
  }
  .plotcol {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: var(--lab-chart-toolbar-h);
    padding: 0 var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
    background: var(--bg);
    color: var(--fg-muted);
    flex: none;
  }
  h3 {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-semibold);
  }
  .sub {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .grow {
    flex: 1;
  }
  .key {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .key .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--fg);
  }
  .key .dot.open {
    background: transparent;
    border: 1.5px solid var(--fg);
  }
  .key .line {
    width: 16px;
    border-top: 1.75px solid var(--chart-reference);
  }
  .key .line.dash {
    border-top-style: dashed;
  }
  .key .line.brass {
    border-top-color: var(--accent);
  }
  .plot {
    flex: 1;
    margin: var(--space-3) var(--space-3) var(--space-2) var(--space-2);
  }
  .panel {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-4);
    border-left: var(--border-w) solid var(--border);
    background: var(--bg);
    overflow: auto;
  }
  .state {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .progress {
    display: grid;
    gap: 6px;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .progress b {
    color: var(--fg);
    font-weight: var(--weight-regular);
  }
  .ticks {
    display: grid;
    grid-template-columns: repeat(17, 1fr);
    gap: 2px;
  }
  .ticks i {
    height: 6px;
    border-radius: 1px;
    background: var(--border-soft);
  }
  .ticks i.done {
    background: var(--fg-muted);
  }
  .ticks i.fine.done {
    background: var(--fg);
  }
  .ticks i.verify {
    outline: 1px solid var(--border);
  }
  .ticks i.verify.done {
    background: var(--accent);
  }
  .readouts {
    display: grid;
    grid-template-columns: auto 1fr;
    align-items: baseline;
    gap: var(--space-2) var(--space-4);
    margin: 0;
  }
  dt {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  dd {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-xs);
    text-align: right;
  }
  dd.big {
    font-size: var(--text-xl);
    font-weight: var(--weight-medium);
  }
  dd small {
    margin-left: 6px;
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-regular);
  }
  .verdict {
    margin: 0;
    padding: var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-left: 2px solid var(--success);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-size: var(--text-s);
    line-height: var(--leading-normal);
  }
  .verdict.rejected {
    border-left-color: var(--danger);
  }
  .actions {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-3);
  }
  .lab-btn.primary {
    height: 30px;
    background: var(--primary-bg);
    border-color: var(--primary-border);
    color: var(--primary-fg);
  }
  .lab-btn.primary :global(.icon) {
    color: inherit;
  }
  .lab-btn.primary:hover {
    background: var(--primary-bg-hover);
    color: var(--primary-fg-hover);
  }
  .note {
    margin: auto 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-relaxed);
  }
</style>

<!--
  The Run band (Observe Run mode, wave 6b; web/lab/PROPOSAL.md 3.1 "Task band", 3.2 and 6,
  W6; BRAND 11.1 "Run = the live light curve (target and check)"; promoted from
  src/lab/workspace/observe/bands/RunBand.svelte): the live curve where the eye already is,
  under the image, which stays the hero.

  - The curve: LightCurvePlot variant "band", target and check facets (D25), fed by the live
    photometry store (the server's points, the same values as the drawer and the CSVs). Its
    tools sit in the band's header (CurveTools on the same CurveView), so the plot keeps the
    band's whole height. Attention rules of the run are drawn on it read-only (the period
    where a rule holds hatched from the frame where it fired, a dashed line and its name).
  - The mini column (RunMinis, from 640 px of band width): frames n / N on a time axis with
    the autofocus passes, the last frame's age against the cadence, HFD, stars and sky
    sparklines over the curve's time window, the HFD and star rules drawn with "Change
    rule…".
  - Below 150 px (BRAND 11.1): one summary row (the newest target value, the check scatter,
    the newest point's time, n / N, last-frame age, the rule that holds; after the run its
    last n / N, "no run" without one), and under it, when the band leaves room, the
    target's curve alone: the band is used, never an empty strip.
-->
<script lang="ts">
  import { filterLabel } from '../../format/filter';
  import type { RunBaseline } from '../../api/attention';
  import type { SequenceState } from '../../api/sequence';
  import type { ConditionsStore } from '../../charts/conditions.svelte';
  import { observedCadence } from '../../charts/conditions';
  import CurveKey from '../../charts/lightcurve/CurveKey.svelte';
  import LightCurvePlot, { type LightCurveApi } from '../../charts/lightcurve/LightCurvePlot.svelte';
  import { checkSigma } from '../../charts/lightcurve/facets';
  import { readoutAt } from '../../charts/lightcurve/readout';
  import type { LiveCurveStore } from '../../charts/lightcurve/store';
  import type { CurveView } from '../../charts/lightcurve/view.svelte';
  import AgeMeter from '../../charts/mini/AgeMeter.svelte';
  import Sparkline from '../../charts/mini/Sparkline.svelte';
  import type { SparkSpec } from '../../charts/mini/spark';
  import type { ChartInks } from '../../charts/ink';
  import NumText from '../../components/NumText.svelte';
  import { fixed, int } from '../../format/number';
  import AttentionMark from '../../shell/attention/AttentionMark.svelte';
  import { LEVEL_WORD } from '../../shell/attention/model';
  import RunMinis from './RunMinis.svelte';
  import { curveRules, miniWidth, miniWindow, ruleName, runCounts, runItems, type RunAttention } from './runband';

  interface Props {
    store: LiveCurveStore;
    /** The band's curve view (its tools are in the band header: CurveTools on the same view). */
    view: CurveView;
    /** Content height, CSS px (Band's children snippet). */
    height: number;
    compact: boolean;
    theme?: unknown;
    /** Frames are expected now (the run exposes): x to now, overdue hatching. */
    expecting?: boolean;
    targetKey?: string | null;
    checkKey?: string | null;
    notify?: (title: string, message?: string) => void;
    seq: SequenceState | null;
    /** Unix s, ticking once per second. */
    now: number;
    frameTimes?: readonly number[];
    marks?: readonly number[];
    afStep?: { done: number; total: number } | null;
    conditions: ConditionsStore;
    /** Attention items (the server's; the band keeps this run's). */
    items?: readonly RunAttention[];
    thresholds?: Record<string, unknown> | null;
    /** The run's baselines in force on the server (AttentionState.baselines). */
    baselines?: readonly RunBaseline[];
    onrule?: (rule: string) => void;
    /** The curve has no point: why, in words (the live status line). */
    emptyText?: string | null;
    /** Wall clock of the curve's now-line, unix s (the gallery passes a fixed one). */
    clock?: () => number;
    /** The full curve's API (the gallery's long-run check). */
    hooks?: (api: LightCurveApi) => void;
  }

  let {
    store,
    view,
    height,
    compact,
    theme,
    expecting = false,
    targetKey = null,
    checkKey = null,
    notify,
    seq,
    now,
    frameTimes = [],
    marks = [],
    afStep = null,
    conditions,
    items = [],
    thresholds = null,
    baselines = [],
    onrule,
    emptyText = null,
    clock = () => Date.now() / 1000,
    hooks,
  }: Props = $props();

  let bandW = $state(0);
  const minisW = $derived(miniWidth(bandW));
  const mine = $derived(runItems(items, seq));
  const rules = $derived(curveRules(mine));
  const firstT = $derived.by(() => {
    void conditions.version;
    return conditions.cols.n ? conditions.cols.cols.t[0] : null;
  });
  const span = $derived(miniWindow(view.range, seq?.started_t ?? null, firstT, now));

  // -- The one-row summary (below 150 px) ---------------------------------------------------
  let version = $state(0);
  $effect(() => {
    const s = store;
    version = s.version;
    return s.onChange(() => (version = s.version));
  });
  const keys = $derived({ target: targetKey, check: checkKey, filter: view.shownFilter });
  const newest = $derived.by(() => {
    void version;
    if (!compact) return null;
    const t = store.primary('target', keys.target, keys.filter) ?? store.primary('check', keys.check, keys.filter);
    if (!t || !t.n) return null;
    const c = t.cols;
    const cad = observedCadence(c.t, c.n);
    return readoutAt(store, c.t[c.n - 1], 'mag', keys, cad ? Math.max(1, cad / 2) : 30);
  });
  const sigma = $derived.by(() => {
    void version;
    return compact ? checkSigma(store, keys.check, keys.filter) : null;
  });
  const frames = $derived(frameTimes.length);
  const counts = $derived(runCounts(seq, frames));
  const cadence = $derived(seq?.observed_cadence_s ?? observedCadence(frameTimes, frames) ?? seq?.cadence_s ?? null);
  const lastAt = $derived(frames ? Math.max(frameTimes[frames - 1], seq?.last_frame_t ?? -Infinity) : (seq?.last_frame_t ?? null));
  const holding = $derived(mine.filter((a) => a.active !== false && a.level !== 'info').sort((a, b) => (a.level === 'critical' ? -1 : 0) - (b.level === 'critical' ? -1 : 0))[0] ?? null);
  /** Room under the summary row for the target's curve alone. */
  const SUMMARY_H = 34;
  const curveBelow = $derived(compact && height - SUMMARY_H >= 64);
  // 60-97 px (the drawer open at its default height: 70-78 px): the summary row on top and
  // the target's newest points as a strip under it, never one row centred in an empty band
  // (BRAND 11.1, the W5 carry-over the Field band got; wave 6b design review).
  const stripBelow = $derived(compact && !curveBelow && height >= 60);
  let stripW = $state(0);
  const STRIP_N = 120;
  const strip = (ink: ChartInks): SparkSpec | null => {
    void version;
    const t = store.primary('target', keys.target, keys.filter);
    if (!t || t.n < 2) return null;
    const c = t.cols;
    const i0 = Math.max(0, c.n - STRIP_N);
    const xs: number[] = [];
    const ys: number[] = [];
    for (let i = i0; i < c.n; i++) {
      if (!Number.isFinite(c.mag[i])) continue;
      xs.push(c.t[i]);
      ys.push(c.mag[i]);
    }
    // Magnitudes: brighter up, as the curve.
    return xs.length >= 2 ? { xs, ys, n: xs.length, color: ink.target.a(), lastDot: true, invert: true, dots: true } : null;
  };
</script>

{#if compact}
  <div class="compact" data-run-band="compact">
    <div class="summary num" style:height="{curveBelow || stripBelow ? SUMMARY_H : height}px">
      <span class="k">Light curve{#if view.shownFilter} · {filterLabel(view.shownFilter)}{/if}</span>
      {#if newest}
        {#if newest.target}<span class="g"><CurveKey shape="circle" color="var(--chart-1)" />{newest.target.value}<span class="m">{newest.target.what}</span></span>{/if}
        {#if sigma && Number.isFinite(sigma.sigma)}<span class="g"><CurveKey shape="triangle" color="var(--chart-3)" />σ<sub>{sigma.count}</sub>&nbsp;{fixed(sigma.sigma, 3)}</span>{/if}
        <span class="m" title="The newest point's mid-exposure (UTC)">{newest.utc}</span>
      {:else}
        <span class="m"><NumText text={emptyText ?? 'Waiting for the first measured frame'} /></span>
      {/if}
      <span class="div" aria-hidden="true"></span>
      <span class="k">Run</span><span class="g">{#if counts.total}{int(counts.done)}<span class="m"> / {int(counts.total)}</span>{:else}<span class="m">no run</span>{/if}</span>
      <AgeMeter age={lastAt === null ? null : Math.max(0, now - lastAt)} {cadence} {expecting} width={48} />
      {#if holding}
        <span class="g rule"><AttentionMark level={holding.level} size={10} />{ruleName(holding)} · {LEVEL_WORD[holding.level]}</span>
      {/if}
    </div>
    {#if stripBelow}
      <div class="strip-below" bind:clientWidth={stripW} aria-label="The target's newest points">
        {#if stripW > 0}<Sparkline spec={strip} width={stripW - 24} height={Math.max(20, height - SUMMARY_H - 10)} version={`${version}|${keys.filter}`} {theme} label="Target, newest {STRIP_N} points (brighter up)" />{/if}
      </div>
    {/if}
    {#if curveBelow}
      <div class="curve-below">
        <LightCurvePlot
          {store}
          {view}
          facets={['target']}
          variant="band"
          toolbar={false}
          {rules}
          {expecting}
          {theme}
          {targetKey}
          {checkKey}
          {notify}
          {clock}
          label="Live light curve, target"
          {emptyText}
        />
      </div>
    {/if}
  </div>
{:else}
  <div class="run" bind:clientWidth={bandW} style:grid-template-columns={minisW ? `minmax(0, 1fr) ${minisW}px` : 'minmax(0, 1fr)'} data-run-band="full">
    <div class="curve">
      <LightCurvePlot {store} {view} facets={['target', 'check']} variant="band" {rules} {expecting} {theme} {targetKey} {checkKey} {notify} {clock} {hooks} label="Live light curve" {emptyText} />
    </div>
    {#if minisW}
      <RunMinis {seq} {now} {frameTimes} {marks} {afStep} {conditions} {span} items={mine} {thresholds} {baselines} {height} {theme} {expecting} {onrule} />
    {/if}
  </div>
{/if}

<style>
  .run {
    display: grid;
    height: 100%;
    min-height: 0;
    min-width: 0;
  }
  .curve {
    position: relative;
    min-width: 0;
    min-height: 0;
  }
  .compact {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .summary {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--space-3);
    padding: 0 var(--space-3);
    color: var(--fg);
    font-size: var(--text-s);
    white-space: nowrap;
    overflow: hidden;
  }
  .curve-below {
    flex: 1;
    min-height: 0;
    border-top: var(--border-w) solid var(--border-soft);
  }
  .strip-below {
    flex: 1;
    min-height: 0;
    display: flex;
    align-items: center;
    padding: 0 var(--space-3);
    border-top: var(--border-w) solid var(--border-soft);
    background: var(--chart-surface);
  }
  .k {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .g {
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
  .g sub {
    font-size: 0.8em;
    vertical-align: -0.15em;
  }
  .m {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .rule {
    font-size: var(--text-xs);
  }
  .div {
    width: 1px;
    height: 14px;
    background: var(--border-soft);
    flex: none;
  }
</style>

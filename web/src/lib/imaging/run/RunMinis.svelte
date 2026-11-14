<!--
  The run's mini charts, beside the live curve in the Run band (web/lab/PROPOSAL.md 3.2
  "Mini-charts" and 6, W6; BRAND 10). Five rows, each with its value in text first (the
  chart adds the trend, never information found nowhere else):

  - Run: frames n / N on RunProgress (a time axis from the start to the end: the fill lags
    the now line when the run is slow or paused; autofocus passes are notches), and the
    sweep of a mid-run autofocus ("Autofocus · 4 of 9", the record's `autofocus`).
  - Last frame: its age against the observed cadence (AgeMeter: hatched and "overdue" past
    max(2 × cadence, cadence + 60 s) while frames are expected).
  - HFD, Stars, Sky: the newest value and a sparkline over the curve's time window, in
    neutral inks (conditions are not photometric roles). HFD and Stars draw their attention
    rule read-only: a dashed --warning line at the threshold, the stretch past it heavier with
    a rug, and the word "past rule" when the newest value is past it; "Change rule…" opens
    Settings › Alerts (a live chart never edits a rule, PROPOSAL 3.2).
-->
<script lang="ts">
  import type { SequenceState } from '../../api/sequence';
  import { observedCadence } from '../../charts/conditions';
  import type { ConditionsStore } from '../../charts/conditions.svelte';
  import type { ChartInks } from '../../charts/ink';
  import AgeMeter from '../../charts/mini/AgeMeter.svelte';
  import RunProgress from '../../charts/mini/RunProgress.svelte';
  import Sparkline from '../../charts/mini/Sparkline.svelte';
  import type { SparkSpec } from '../../charts/mini/spark';
  import IconButton from '../../components/IconButton.svelte';
  import { tooltip } from '../../components/tooltip';
  import { fixed, int } from '../../format/number';
  import { endAt } from '../../run/run';
  import AttentionMark from '../../shell/attention/AttentionMark.svelte';
  import { LEVEL_WORD } from '../../shell/attention/model';
  import { afText, latestFinite, metricThreshold, miniLayout, pastThreshold, ruleName, runCounts, METRIC_RULE, type RuleMetric, type RunAttention } from './runband';

  interface Props {
    seq: SequenceState | null;
    /** Unix s, ticking once per second. */
    now: number;
    frameTimes?: readonly number[];
    /** Autofocus passes of the run (unix s). */
    marks?: readonly number[];
    afStep?: { done: number; total: number } | null;
    conditions: ConditionsStore;
    /** The x window of the sparklines (the curve's view, else the run). */
    span: [number, number] | null;
    /** The run's attention items (the server's). */
    items?: readonly RunAttention[];
    /** The alerts.* values in force (AttentionState.thresholds). */
    thresholds?: Record<string, unknown> | null;
    /** Content height, CSS px. */
    height: number;
    theme?: unknown;
    /** Frames are expected now (running, not paused). */
    expecting?: boolean;
    /** "Change rule…": Settings › Alerts on that rule. */
    onrule?: (rule: string) => void;
  }

  let { seq, now, frameTimes = [], marks = [], afStep = null, conditions, span, items = [], thresholds = null, height, theme, expecting = false, onrule }: Props = $props();

  const L = $derived(miniLayout(height));
  let colW = $state(0);
  const sparkW = $derived(L.kind === 'stack' ? Math.max(60, colW - 24) : Math.max(40, Math.min(96, colW - 124)));

  // -- Run ------------------------------------------------------------------------------
  const n = $derived(frameTimes.length);
  const counts = $derived(runCounts(seq, n));
  const done = $derived(counts.done);
  const total = $derived(counts.total);
  const end = $derived(seq ? endAt(seq, now) : null);
  const af = $derived(seq?.state === 'autofocus' ? (afText(afStep) ?? 'Autofocus') : null);
  const cadence = $derived(seq?.observed_cadence_s ?? observedCadence(frameTimes, n) ?? seq?.cadence_s ?? null);
  const lastAt = $derived.by(() => {
    const mine = n ? frameTimes[n - 1] : null;
    const srv = seq?.last_frame_t ?? null;
    return mine === null ? srv : srv === null ? mine : Math.max(mine, srv);
  });
  const age = $derived(lastAt === null ? null : Math.max(0, now - lastAt));

  // -- Conditions ------------------------------------------------------------------------
  const from = $derived(seq?.started_t ?? null);
  const cols = $derived.by(() => {
    void conditions.version;
    const c = conditions.cols;
    return { n: c.n, t: c.cols.t, hfd: c.cols.hfd, stars: c.cols.stars, sky: c.cols.sky };
  });
  const latest = $derived.by(() => {
    void conditions.version;
    return { hfd: latestFinite(cols.hfd, cols.n), stars: latestFinite(cols.stars, cols.n), sky: latestFinite(cols.sky, cols.n) };
  });
  const th = $derived.by(() => {
    void conditions.version;
    const out = {} as Record<RuleMetric, ReturnType<typeof metricThreshold>>;
    for (const m of ['hfd', 'stars'] as const) out[m] = metricThreshold(m, items, thresholds, { t: cols.t, v: cols[m], n: cols.n }, from);
    return out;
  });
  /** The newest item of a rule (active first): its level mark beside the row. */
  function itemOf(rule: string): RunAttention | null {
    let best: RunAttention | null = null;
    for (const a of items) if (a.rule === rule && (!best || (a.active !== false && best.active === false) || (a.since ?? 0) > (best.since ?? 0))) best = a;
    return best && best.active !== false ? best : null;
  }

  type Row = { id: RuleMetric | 'sky'; label: string; value: string; unit: string; desc: string };
  const rows: Row[] = $derived([
    { id: 'hfd', label: 'HFD', value: latest.hfd === null ? '—' : fixed(latest.hfd, 2), unit: 'px', desc: 'Half-flux diameter per frame' },
    { id: 'stars', label: 'Stars', value: latest.stars === null ? '—' : int(latest.stars), unit: '', desc: 'Stars detected per frame' },
    { id: 'sky', label: 'Sky', value: latest.sky === null ? '—' : int(latest.sky), unit: 'ADU', desc: 'Median background per frame' },
  ]);

  const spec = (id: Row['id']) => (ink: ChartInks): SparkSpec | null => {
    if (!span || !cols.n) return null;
    const t = id === 'hfd' || id === 'stars' ? th[id] : null;
    return {
      xs: cols.t,
      ys: cols[id],
      n: cols.n,
      x0: span[0],
      x1: span[1],
      color: ink.fgMuted.a(),
      lastDot: true,
      ref: t?.value,
      refBelow: id === 'stars',
      refColor: t ? ink.warning.a(0.9) : undefined,
      markOut: !!t,
    };
  };
  const version = $derived(`${conditions.version}|${span?.[0]}|${span?.[1]}|${th.hfd?.value}|${th.stars?.value}`);
</script>

<div class="minis k-{L.kind}" bind:clientWidth={colW} role="group" aria-label="Run at a glance">
  <div class="row run">
    <div class="line">
      <span class="k">Run</span>
      <span class="v num">{#if total}{int(done)}<span class="of">/{int(total)}</span>{:else}<span class="of">no run</span>{/if}</span>
      {#if af && L.kind === 'row'}<span class="af num">{af}</span>{/if}
    </div>
    <span class="bar" style:height="{L.kind === 'stack' ? 8 : 6}px"><RunProgress {done} {total} start={seq?.started_t ?? null} {end} {now} times={frameTimes} {n} {marks} width={0} height={L.kind === 'stack' ? 8 : 6} /></span>
    {#if af && L.kind === 'stack'}<span class="af num">{af}</span>{/if}
  </div>
  <div class="row age-row">
    <div class="line">
      <span class="k">Last frame</span>
    </div>
    <AgeMeter {age} {cadence} {expecting} width={Math.max(48, Math.min(120, colW - (L.kind === 'stack' ? 96 : 150)))} />
  </div>
  {#each rows as r (r.id)}
    {@const t = r.id === 'sky' ? null : th[r.id]}
    {@const item = r.id === 'sky' ? null : itemOf(METRIC_RULE[r.id])}
    {@const past = r.id !== 'sky' && pastThreshold(r.id, r.id === 'hfd' ? latest.hfd : latest.stars, t)}
    <div class="row metric" data-metric={r.id}>
      <div class="line">
        <span class="k">{r.label}</span>
        <span class="v num">{r.value}{#if r.unit && r.value !== '—'}<span class="u">{r.unit}</span>{/if}</span>
        {#if item}
          <span class="flag" use:tooltip={{ text: `${ruleName(item)}: the server's rule holds (the attention list has its numbers)` }}><AttentionMark level={item.level} size={10} />{LEVEL_WORD[item.level]}</span>
        {:else if past}
          <span class="flag quiet">past rule</span>
        {/if}
        {#if t && onrule && r.id !== 'sky'}
          <span class="rule">
            <IconButton icon="settings" label="Change rule…" size="s" variant="ghost" tooltip="top" tooltipText="Change rule… {r.label}: {t.text}. Settings › Alerts (a live chart never edits a rule)" onclick={() => onrule?.(METRIC_RULE[r.id as RuleMetric])} />
          </span>
        {/if}
      </div>
      <Sparkline width={sparkW} height={L.sparkH} {version} {theme} spec={spec(r.id)} label="{r.desc}{t ? `, ${t.text}` : ''}, newest {r.value} {r.unit}" />
    </div>
  {/each}
</div>

<style>
  .minis {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-width: 0;
    padding: var(--space-1) var(--space-3) var(--space-1) var(--space-3);
    border-left: var(--border-w) solid var(--border-soft);
    background: var(--bg-2);
    overflow: hidden;
  }
  .row {
    display: flex;
    flex: 1 1 0;
    flex-direction: column;
    justify-content: center;
    gap: 3px;
    min-height: 0;
  }
  .row + .row {
    border-top: var(--border-w) solid var(--border-soft);
  }
  /* One line per row when the band is short: key, value, then the chart on the right. */
  .k-row .row {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
  }
  .line {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    min-width: 0;
    white-space: nowrap;
  }
  .k {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .v {
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
  }
  .v .of,
  .v .u {
    color: var(--text-muted);
    font-weight: var(--weight-regular);
  }
  .af {
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .flag {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .flag.quiet {
    color: var(--text-muted);
  }
  .rule {
    align-self: center;
    margin: -4px -6px -4px auto;
  }
  .bar {
    display: flex;
    flex: none;
  }
  .v .of {
    margin-left: 2px;
  }
  .v .u {
    margin-left: 3px;
  }
</style>

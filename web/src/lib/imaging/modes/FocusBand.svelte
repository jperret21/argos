<!--
  Focus band (owner decision D1; promoted from src/lab/workspace/observe/bands/
  FocusBand.svelte, web/lab/PROPOSAL.md 3.1 and 6, W3): the autofocus V-curve gets the
  larger part of the band (it was a 396 x 140 plot in the Qt Focuser dock), the HFD now
  and the decision as numbers, and the HFD trend beside it (the Conditions timeline on
  the focus metric, the last 30 minutes to now, D6).

  - HFD now is the server's metric of the frame on screen (frame_metrics, A26), never a
    value of another frame.
  - The V-curve shows the last autofocus of the session (the server keeps it), whatever
    its outcome, with its verdict in words.
  - Below 150 px: one summary row (autofocus state and step, HFD now, best position).
  - One home per value (design review of wave 3): the band owns the autofocus numbers
    (step, best, verified HFD); the focuser's position and target belong to the Focuser
    card, so the band no longer repeats them.
  - The trend shows min(30 min, the session) to now, and says which.
-->
<script lang="ts">
  import StatusBadge from '../../components/StatusBadge.svelte';
  import NumText from '../../components/NumText.svelte';
  import { fixed, int } from '../../format/number';
  import type { ConditionsStore } from '../../charts/conditions.svelte';
  import ConditionsTimeline from '../../charts/ConditionsTimeline.svelte';
  import type { ConditionsView } from '../../charts/conditionsView.svelte';
  import { verdict, type AutofocusRecord } from '../../charts/vcurve';
  import type { TimelinePeriod } from '../../charts/conditions';
  import { clockUtc } from '../../format/time';
  import VCurvePlot from '../../charts/VCurvePlot.svelte';
  import type { FrameMetricsRecord } from './exposure';

  interface Props {
    height: number;
    compact: boolean;
    af: AutofocusRecord | null;
    /** The server's metrics of the frame on screen (null: not arrived, or another frame). */
    metrics: FrameMetricsRecord | null;
    conditions: ConditionsStore;
    /** Autofocus runs of the session (they explain a gap in the trend). */
    periods?: readonly TimelinePeriod[];
    view: ConditionsView;
    expecting: boolean;
    theme: string;
  }

  let { height, compact, af, metrics, conditions, periods = [], view, expecting, theme }: Props = $props();

  const pos = (v: number) => int(Math.round(v));
  const px = (v: number) => `${fixed(v, 2)} px`;
  const v = $derived(verdict(af, pos, px));
  const step = $derived(af && af.state !== 'idle' ? `${af.samples?.length ?? 0} / ${af.total ?? '—'}` : '—');
  const best = $derived(af?.state === 'done' && af.best ? af.best : null);
  const TREND = ['focus'] as const;
  const running = $derived(af?.state === 'running' || af?.state === 'stopping');
  const title = $derived.by(() => {
    if (running) return 'V-curve · this autofocus';
    if (!af || af.state === 'idle') return 'V-curve · HFD against focuser steps';
    const end = af.ended_utc ? Date.parse(af.ended_utc) / 1000 : NaN;
    return `V-curve · last autofocus${Number.isFinite(end) ? ` · ${clockUtc(end, false)} UTC` : ''}`;
  });
  /** While it runs the readouts carry the numbers; the line says how the sweep was set up. */
  const line = $derived.by(() => {
    if (af?.state !== 'running') return v.text;
    const p = af.params;
    const parts = [
      af.start_position != null ? `From ${pos(af.start_position)}` : null,
      p?.half_range != null ? `±${pos(p.half_range)} steps` : null,
      p?.num_steps != null ? `${p.num_steps} positions` : null,
      p?.exposure_s != null ? `${fixed(p.exposure_s, 1)} s at gain ${p.gain ?? '—'}` : null,
    ].filter(Boolean);
    return parts.join(' · ');
  });
  // The trend: the last 30 minutes, or the session when it is shorter (no empty plot).
  const TREND_S = 1800;
  const span = $derived.by(() => {
    void conditions.version;
    const c = conditions.cols;
    return c.n ? Date.now() / 1000 - c.cols.t[0] : 0;
  });
  const trendWindow = $derived(span > TREND_S ? TREND_S : null);
</script>

{#if compact}
  <div class="row num" style:height="{height}px">
    <span class="k">Autofocus</span><span>{v.state}{af?.state === 'running' ? ` · ${step}` : ''}</span>
    <span class="k">HFD</span><span>{metrics?.hfd_px != null ? px(metrics.hfd_px) : '—'}</span>
    <span class="k">Best</span><span>{best ? pos(best.position) : '—'}</span>
  </div>
{:else}
  <div class="grid">
    <div class="vc">
      <div class="vc-head">
        <span class="micro">{title}</span>
        <StatusBadge tone={v.tone === 'stale' ? 'stale' : v.tone} label={v.state} plain />
      </div>
      <div class="plot">
        <VCurvePlot {af} {theme} />
      </div>
      <p class="verdict" class:bad={v.tone === 'error'}><NumText text={line} group /></p>
    </div>
    <div class="side">
      <dl class="num">
        <div>
          <dt>HFD now</dt>
          <dd class="big">{metrics?.hfd_px != null ? fixed(metrics.hfd_px, 2) : '—'}<span class="u">px</span></dd>
        </div>
        <div>
          <dt>{best ? 'Best · last AF' : 'Step'}</dt>
          <dd class="big">{best ? pos(best.position) : step}{#if best}<span class="u">steps</span>{/if}</dd>
        </div>
        <div>
          <dt>Verified HFD</dt>
          <dd>{best?.hfd_px != null ? fixed(best.hfd_px, 2) : '—'}<span class="u">px</span></dd>
        </div>
      </dl>
      <div class="trend">
        <ConditionsTimeline
          store={conditions}
          {view}
          {theme}
          {expecting}
          {periods}
          window={trendWindow}
          metrics={[...TREND]}
          scope={trendWindow ? 'last 30 min' : 'session'}
          label={trendWindow ? 'HFD and FWHM, the last 30 minutes' : 'HFD and FWHM, the session'}
        />
      </div>
    </div>
  </div>
{/if}

<style>
  .grid {
    display: grid;
    grid-template-columns: minmax(0, 58fr) minmax(0, 42fr);
    height: 100%;
    min-height: 0;
  }
  .vc {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    padding: var(--space-2) var(--space-2) var(--space-1) var(--space-3);
  }
  .vc-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    height: 18px;
    flex: none;
  }
  .plot {
    flex: 1;
    min-height: 0;
  }
  .verdict {
    flex: none;
    margin: 2px 0 0;
    color: var(--fg);
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .verdict.bad {
    font-weight: var(--weight-medium);
  }
  .side {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    border-left: var(--border-w) solid var(--border-soft);
  }
  dl {
    display: grid;
    grid-template-columns: repeat(3, auto);
    justify-content: space-between;
    gap: var(--space-3);
    margin: 0;
    padding: var(--space-2) var(--space-3);
    flex: none;
  }
  dt,
  .micro,
  .k {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
    white-space: nowrap;
  }
  dd {
    margin: 2px 0 0;
    color: var(--fg);
    font-size: var(--readout-s);
    white-space: nowrap;
  }
  dd.big {
    font-size: var(--readout);
    font-weight: var(--weight-medium);
  }
  .u {
    margin-left: var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    font-weight: var(--weight-regular);
  }
  .trend {
    flex: 1;
    min-height: 0;
    border-top: var(--border-w) solid var(--border-soft);
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: 0 var(--space-3);
    color: var(--fg);
    font-size: var(--text-s);
    white-space: nowrap;
    overflow: hidden;
  }
</style>

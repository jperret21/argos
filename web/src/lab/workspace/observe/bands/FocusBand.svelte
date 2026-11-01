<!--
  Focus band: the autofocus V-curve gets 60 % of the band (it was 396 x 140
  in the Focuser card), the HFD now and best in 22 px, and the HFD trend of
  the last 30 minutes beside it (the Conditions timeline filtered to HFD,
  D6). Steps still to measure are open ticks on the V-curve's axis.
-->
<script lang="ts">
  import Trend from '../../charts/Trend.svelte';
  import VCurve from '../../charts/VCurve.svelte';
  import { prng } from '../../model/field';
  import { fixed, int } from '../../model/format';
  import { sim } from '../../model/app.svelte';
  import { median } from '../../model/night';
  import { RULES } from '../../model/rules';

  interface Props {
    compact: boolean;
  }
  let { compact }: Props = $props();

  const done = $derived(sim.afRunning ? sim.afStep : sim.af.steps.length);
  const current = $derived(sim.af.steps[Math.max(0, done - 1)]);
  // During a run the band answers "what is the focus doing NOW": the run's
  // own HFD of the last 30 minutes (the rise that fired the rule shows here).
  const runHfd = $derived(sim.inRun && !sim.afRunning ? (sim.latest?.hfd ?? null) : null);
  const hfd0 = $derived(sim.records.length >= RULES.baselineFrames ? median(sim.records.slice(0, RULES.baselineFrames).map((r) => r.hfd)) : null);
  const trend = $derived.by(() => {
    if (sim.inRun) {
      const recent = sim.records.filter((r) => r.t >= sim.now - 1800);
      return { xs: recent.map((r) => r.t), ys: recent.map((r) => r.hfd) };
    }
    // Before a run (synthetic): HFD slowly rising as the night cools.
    const rand = prng(11);
    const xs: number[] = [];
    const ys: number[] = [];
    const t0 = sim.now - 1800;
    for (let i = 0; i < 30; i++) {
      xs.push(t0 + i * 60);
      ys.push(6.6 + i * 0.045 + (rand() - 0.5) * 0.35);
    }
    return { xs, ys };
  });
</script>

{#if compact}
  <div class="row num">
    <span class="k">AUTOFOCUS</span><span>step {done}/{sim.af.steps.length}</span>
    <span class="k">HFD</span><span>{fixed(current.hfd, 2)} px</span>
    <span class="k">BEST</span><span>{fixed(sim.af.bestHfd, 2)} px</span>
  </div>
{:else}
  <div class="grid">
    <div class="vc">
      <span class="title lab-caps">V-curve · this autofocus · HFD px against focuser steps</span>
      <div class="plot">
        <VCurve steps={sim.af.steps} {done} best={done >= sim.af.steps.length ? sim.af.best : null} bestHfd={sim.af.bestHfd} />
      </div>
    </div>
    <div class="side">
      <dl class="num">
        {#if runHfd !== null}
          <div><dt>HFD now · #{sim.latest?.n}</dt><dd class="big">{fixed(runHfd, 2)}<span class="u">px</span></dd></div>
          <div><dt>Best · last AF</dt><dd class="big">{fixed(sim.af.bestHfd, 2)}<span class="u">px</span></dd></div>
          <div><dt>Position</dt><dd>{int(sim.af.best)}<span class="u">steps</span></dd></div>
          <div><dt>Last AF</dt><dd>19:44</dd></div>
        {:else}
          <div><dt>HFD now</dt><dd class="big">{fixed(current.hfd, 2)}<span class="u">px</span></dd></div>
          <div><dt>Best so far</dt><dd class="big">{fixed(Math.min(...sim.af.steps.slice(0, done).map((s) => s.hfd)), 2)}<span class="u">px</span></dd></div>
          <div><dt>Position</dt><dd>{int(current.position)}<span class="u">steps</span></dd></div>
          <div><dt>Step</dt><dd>{done} / {sim.af.steps.length}</dd></div>
        {/if}
      </dl>
      <div class="trend">
        <Trend xs={trend.xs} ys={trend.ys} start={trend.xs[0] ?? sim.now - 1800} end={sim.now} digits={1} label="HFD" unit={sim.inRun ? 'px · this run, last 30 min' : 'px · last 30 min'} baseline={sim.inRun ? hfd0 : null} threshold={sim.inRun && hfd0 ? { y: RULES.hfdFactor * hfd0, label: 'rule 1.5× baseline' } : null} />
      </div>
    </div>
  </div>
{/if}

<style>
  .grid {
    display: grid;
    grid-template-columns: minmax(0, 58fr) minmax(0, 42fr);
    height: 100%;
  }
  .vc {
    position: relative;
    display: flex;
    flex-direction: column;
    min-width: 0;
    padding: var(--space-2) 0 var(--space-1) var(--space-2);
  }
  .title {
    padding: 0 0 var(--space-1) var(--space-2);
  }
  .plot {
    flex: 1;
    min-height: 0;
  }
  .side {
    display: flex;
    flex-direction: column;
    min-width: 0;
    border-left: var(--border-w) solid var(--border-soft);
  }
  dl {
    display: grid;
    grid-template-columns: repeat(4, auto);
    gap: var(--space-4);
    margin: 0;
    padding: var(--space-3) var(--space-4);
  }
  dt {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  dd {
    margin: 2px 0 0;
    color: var(--fg);
    font-size: var(--text-l);
  }
  dd.big {
    font-size: 22px;
    font-weight: var(--weight-medium);
  }
  .u {
    margin-left: var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-xs);
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
    height: 100%;
    padding: 0 var(--space-3);
    font-family: var(--font-mono);
    font-size: var(--text-s);
    color: var(--fg);
  }
  .k {
    color: var(--text-muted);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
  }
</style>

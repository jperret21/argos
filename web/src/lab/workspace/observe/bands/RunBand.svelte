<!--
  Run band: the live light curve where the eye already is (P2). Two facets
  (target, check) on the planned run window; a rule that fired hatches its
  period and labels its start. Compact form: the latest values in one row.
-->
<script lang="ts">
  import LightCurve from '../../charts/LightCurve.svelte';
  import { sim, ws } from '../../model/app.svelte';
  import { NAMED_STARS } from '../../model/field';
  import { fixed, mag, utc } from '../../model/format';
  import { RUN } from '../../model/night';

  interface Props {
    compact: boolean;
  }
  let { compact }: Props = $props();

  const check = NAMED_STARS.find((s) => s.role === 'check');
  const hfdRule = $derived(sim.attention.find((a) => a.rule === 'HFD rise') ?? null);
  const events = $derived(hfdRule ? [{ x: hfdRule.since, label: `HFD rule · ${utc(hfdRule.since, false)}` }] : []);
  // The degraded stretch starts 2 frames before the rule fires (3 in a row).
  const flagged = $derived.by((): [number, number][] => {
    if (!hfdRule?.frame) return [];
    const first = sim.night[hfdRule.frame - 3];
    return first ? [[first.t - 20, sim.now]] : [];
  });
  const end = $derived(Number.isFinite(sim.endsAt) ? Math.max(sim.endsAt, sim.now) : RUN.start + 3 * 3600);
  const last = $derived(sim.latest);
</script>

{#if compact}
  <div class="row num">
    <span class="k">LIGHT CURVE</span>
    {#if last}
      <span>#{last.n}</span>
      <span class="v">{mag(last.target, last.targetErr)}</span>
      <span class="k">TG</span>
      <span>check {fixed(last.check, 3)}</span>
      {#if hfdRule}<span class="flag">HFD rule since {utc(hfdRule.since, false)}</span>{/if}
    {/if}
    <span class="hint">H or a taller window shows the curve</span>
  </div>
{:else}
  <LightCurve
    records={sim.records}
    start={RUN.start}
    {end}
    now={sim.running ? sim.now : null}
    {events}
    {flagged}
    errors={ws.errorBars}
    targetName="RR Lyr"
    checkName={check?.name ?? null}
  />
{/if}

<style>
  .row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: 100%;
    padding: 0 var(--space-3);
    font-family: var(--font-mono);
    font-size: var(--text-s);
    color: var(--fg);
    white-space: nowrap;
  }
  .k {
    color: var(--text-muted);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
  }
  .v {
    font-weight: var(--weight-medium);
  }
  .flag {
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--warning);
    border-radius: var(--radius-s);
    font-family: var(--font-ui);
    font-size: var(--text-xs);
  }
  .hint {
    margin-left: auto;
    color: var(--text-muted);
    font-family: var(--font-ui);
    font-size: var(--text-xs);
  }
</style>

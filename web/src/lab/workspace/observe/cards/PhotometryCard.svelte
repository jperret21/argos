<!--
  Photometry card: the set (target, comparisons, check) with role shapes, the
  latest differential magnitude with its error, comparisons USED on the last
  frame against the set (the real run had 2 on five frames), the check
  star's scatter and the ensemble verdict in its three words (never a green
  tick that reads as "calibrated").
-->
<script lang="ts">
  import IconButton from '../../../../lib/components/IconButton.svelte';
  import { shapePath } from '../../charts/plugins';
  import { sim, ws } from '../../model/app.svelte';
  import { APERTURE_PX, NAMED_STARS } from '../../model/field';
  import { fixed } from '../../model/format';
  import { median, RUN } from '../../model/night';
  import Readouts from '../../ui/Readouts.svelte';

  const comps = NAMED_STARS.filter((s) => s.role === 'comparison');
  const check = NAMED_STARS.find((s) => s.role === 'check');
  const l = $derived(sim.latest);

  const checkSd = $derived.by(() => {
    const r = sim.records.slice(-15);
    if (r.length < 3) return NaN;
    const m = median(r.map((x) => x.check));
    return Math.sqrt(r.reduce((s, x) => s + (x.check - m) ** 2, 0) / (r.length - 1));
  });

  const verdict = $derived(!sim.inRun ? 'insufficient data' : sim.delivered < 10 ? `waiting ${sim.delivered}/10` : 'live preview consistent');
  const items = $derived(
    l
      ? [
          { k: 'RR Lyr · TG', v: fixed(l.target, 3), unit: `± ${fixed(l.targetErr, 3)}`, key: true },
          { k: 'Check σ (15)', v: fixed(checkSd, 3), unit: 'mag', key: true },
          { k: 'Comps used', v: `${l.compsUsed} / ${RUN.comparisons}`, flag: l.compsUsed < 3 ? 'low' : undefined },
          { k: 'Aperture', v: `${APERTURE_PX} px`, unit: '31″' },
        ]
      : [
          { k: 'Comparisons', v: `${comps.length}`, unit: 'in the set · aim 5' },
          { k: 'Check', v: check ? '1' : 'none', unit: check?.name?.slice(-3) ?? '' },
          { k: 'Aperture', v: `${APERTURE_PX} px`, unit: '31″' },
          { k: 'Verdict', v: 'waiting', unit: '0/10' },
        ],
  );
</script>

<div class="phot">
  <ul class="set" aria-label="Target set">
    <li>
      <svg viewBox="0 0 20 20" class="target" aria-label="target"><path d={shapePath('circle')} /></svg>
      <span class="name">RR Lyr</span>
    </li>
    <li>
      <svg viewBox="0 0 20 20" class="comparison" aria-label="comparisons"><path d={shapePath('square')} /></svg>
      <span class="name num">{comps.length}</span><span class="muted">comparisons</span>
    </li>
    <li>
      <svg viewBox="0 0 20 20" class="check" aria-label="check star"><path d={shapePath('triangle')} /></svg>
      <span class="name num">{check?.name?.slice(-3)}</span><span class="muted">check</span>
    </li>
  </ul>
  <Readouts {items} cols={2} />
  <p class="verdict"><span class="lab-caps">Ensemble</span> {verdict}</p>
  {#if ws.mode === 'field'}
    <div class="actions">
      <IconButton icon="recommend-comparisons" label="Recommend 5" showLabel size="s" onclick={() => ws.toast('Recommend: 5 of 11 candidates, B−V within 0.3 mag, within 25′', 'info')} />
      <IconButton icon="rerun-photometry" label="Refresh catalogue" size="s" variant="ghost" onclick={() => ws.toast('VSP sequence refreshed', 'ok')} />
    </div>
  {/if}
</div>

<style>
  .phot {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .set {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    gap: var(--space-4);
  }
  .set li {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    font-size: var(--text-s);
  }
  .set svg {
    width: 16px;
    height: 16px;
  }
  .set path {
    fill: none;
    stroke-width: 1.6;
  }
  .target path {
    stroke: var(--role-target);
  }
  .comparison path {
    stroke: var(--role-comparison);
  }
  .check path {
    stroke: var(--role-check);
  }
  .name {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .muted {
    color: var(--text-muted);
  }
  .verdict {
    margin: 0;
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .actions {
    display: flex;
    gap: var(--space-2);
  }
</style>

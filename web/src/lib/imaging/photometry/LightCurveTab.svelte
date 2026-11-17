<!--
  Light curve tab of the Observe drawer (M99, M95 live tab, 08 2.3 J; D25): the plot
  (LightCurvePlot, given by the caller: the same component as Review and the Run band; it
  names its facets and reads out the target and the check − catalogue V with its 15-point
  band). The ensemble verdict sits in the drawer's tab row (EnsembleVerdict) and the live
  status in the Field band, so the plot keeps the drawer's whole height.

  Empty: "No live photometry yet" with the sub-state in words (08 2.3 C).
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import Icon from '../../components/Icon.svelte';
  import type { TargetStar } from '../field/types';
  import { PICK_TARGET, curveFor, measuredCount, type StatusLine } from './present';
  import type { Curve } from './types';

  interface Props {
    stars: readonly TargetStar[];
    curves: readonly Curve[];
    line: StatusLine;
    /** The plot (LightCurvePlot), drawn when the target has points. */
    plot?: Snippet;
  }

  let { stars, curves, line, plot }: Props = $props();

  const target = $derived(stars.find((s) => s.role === 'target') ?? null);
  const tCurve = $derived(target ? curveFor(curves, target) : null);
  const n = $derived(measuredCount(tCurve));
</script>

<div class="lc">
  <div class="body">
    {#if target && n > 0 && plot}
      {@render plot()}
    {:else}
      <div class="empty">
        <Icon name="light-curve" size={32} />
        <p class="t">No live photometry yet</p>
        <p class="s">{target ? line.text : PICK_TARGET}</p>
      </div>
    {/if}
  </div>
</div>

<style>
  .lc {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .body {
    flex: 1;
    min-height: 0;
    position: relative;
  }
  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-1);
    height: 100%;
    color: var(--fg-muted);
    text-align: center;
  }
  .empty p {
    margin: 0;
  }
  .empty .t {
    color: var(--fg);
    font-size: var(--text-m, 14px);
    font-weight: var(--weight-medium);
  }
  .empty .s {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
</style>

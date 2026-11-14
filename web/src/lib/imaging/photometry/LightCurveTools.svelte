<!--
  The Light curve tab's tools in the drawer's tab row (wave 6b, the wave 5 carry-over): the
  ensemble verdict's word first (always in the tab row, W5 design review), then the curve's
  tools (CurveTools on the plot's CurveView: time axis, zoom, the zoom state's name, error
  bars, relative flux, Copy data), so the plot keeps the drawer's whole height. The row
  drops the least needed tools first when the drawer is narrow; the verdict stays.
-->
<script lang="ts">
  import CurveTools from '../../charts/lightcurve/CurveTools.svelte';
  import type { CurveView } from '../../charts/lightcurve/view.svelte';
  import EnsembleVerdict from './EnsembleVerdict.svelte';
  import type { Verdict } from './present';

  interface Props {
    view: CurveView;
    verdict: Verdict | null;
    minPoints?: number;
    /** No target: no verdict (the empty state says what to do). */
    showVerdict?: boolean;
  }

  let { view, verdict, minPoints = 10, showVerdict = true }: Props = $props();
</script>

<span class="lct">
  {#if showVerdict}<EnsembleVerdict {verdict} {minPoints} compact />{/if}
  <CurveTools {view} variant="drawer" />
</span>

<style>
  .lct {
    display: flex;
    flex: 1 1 0;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-2);
    min-width: 0;
  }
</style>

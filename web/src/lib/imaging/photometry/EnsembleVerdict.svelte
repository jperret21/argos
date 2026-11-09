<!--
  The ensemble verdict in one short line (the drawer's tab header, next to the plot's own
  readouts): "Ensemble · 3 of 4 stable", the full Qt verdict and the scientific note in the
  tooltip; "no assessment yet" before the first report. Words, never the tone alone.
-->
<script lang="ts">
  import Icon from '../../components/Icon.svelte';
  import NumText from '../../components/NumText.svelte';
  import type { Verdict } from './present';

  interface Props {
    verdict: Verdict | null;
    minPoints?: number;
  }

  let { verdict, minPoints = 10 }: Props = $props();
  const title = $derived(verdict ? verdict.line : `Ensemble: no assessment yet. The leave-one-out check runs after every measured frame (needs ${minPoints} points per comparison).`);
</script>

<span class="ev" class:ok={verdict?.tone === 'ok'} class:warn={verdict?.tone === 'warn'} {title}>
  <Icon name="comparison-quality" size={14} />
  <span class="k">Ensemble</span>
  <span class="w"><NumText text={verdict ? (verdict.counts ?? verdict.words) : 'no assessment yet'} /></span>
  <!-- The verdict's word always: "4 of 5 stable" alone read as a usable ensemble. -->
  {#if verdict}<span class="s"><NumText text={`· ${verdict.tone === 'ok' ? 'consistent' : verdict.tone === 'warn' ? 'not ready' : `waiting for ${minPoints} points`}`} /></span>{/if}
</span>

<style>
  .ev {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    min-width: 0;
    padding: 0 var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-s);
    white-space: nowrap;
  }
  .ev :global(.icon) {
    flex: none;
    color: var(--fg-muted);
  }
  .w {
    color: var(--fg);
    font-variant-numeric: var(--numeric);
  }
  .warn .s {
    color: var(--fg);
  }
</style>

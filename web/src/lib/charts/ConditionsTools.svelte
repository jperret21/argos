<!--
  Tools of the Conditions timeline, for the drawer header row (one 32 px row, no
  extra band): the metric chips (up to three plots; a fourth says why it cannot be
  added), Fit (F, the session to now) with the zoom state in words, and the age of
  the last frame against the observed cadence (AgeMeter: overdue only while frames
  are expected).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import IconButton from '../components/IconButton.svelte';
  import { tooltip } from '../components/tooltip';
  import { liveness } from './conditions';
  import type { ConditionsStore } from './conditions.svelte';
  import { MAX_FACETS, METRIC_ORDER, METRICS, type ConditionsView } from './conditionsView.svelte';
  import AgeMeter from './mini/AgeMeter.svelte';

  interface Props {
    store: ConditionsStore;
    view: ConditionsView;
    expecting?: boolean;
    clock?: () => number;
  }

  let { store, view, expecting = false, clock = () => Date.now() / 1000 }: Props = $props();

  let now = $state(untrack(() => clock()));
  $effect(() => {
    const t = setInterval(() => (now = clock()), 1000);
    return () => clearInterval(t);
  });
  const live = $derived.by(() => {
    void store.version;
    return liveness(store.cols, now, expecting);
  });
</script>

<div class="tools">
  <div class="chips" role="group" aria-label="Plots (up to {MAX_FACETS})">
    {#each METRIC_ORDER as id (id)}
      {@const on = view.metrics.includes(id)}
      {@const full = !on && view.metrics.length >= MAX_FACETS}
      <button
        type="button"
        class="chip"
        class:on
        aria-pressed={on}
        aria-disabled={full || (on && view.metrics.length === 1)}
        use:tooltip={{ text: METRICS[id].sub, reason: full ? 'Three plots at most: hide one first' : on && view.metrics.length === 1 ? 'One plot at least' : undefined }}
        onclick={() => view.toggle(id)}>{METRICS[id].label}</button
      >
    {/each}
  </div>
  <span class="state">{view.zoom ? 'Zoom kept · F fits' : 'Session to now'}</span>
  <IconButton icon="zoom-fit" label="Fit: the session to now" shortcut="F" size="s" variant="ghost" tooltip="top" onclick={() => view.fit()} />
  <AgeMeter age={live.age} cadence={live.cadence} {expecting} width={48} />
</div>

<style>
  .tools {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .chips {
    display: inline-flex;
    gap: 2px;
    padding: 2px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .chip {
    height: 20px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid transparent;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-xs);
    cursor: pointer;
  }
  .chip:hover {
    color: var(--fg);
  }
  .chip.on {
    background: var(--toggled-bg);
    border-color: var(--border);
    color: var(--fg);
  }
  .chip[aria-disabled='true']:not(.on) {
    color: var(--fg-disabled);
  }
  .chip:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .state {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
</style>

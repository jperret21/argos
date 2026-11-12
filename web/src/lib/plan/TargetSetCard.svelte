<!--
  Target set card (06 §2.1 row 1.13, §2.2 rows 1.13 #1-#3 and "Pick in field", §2.3.1; D24,
  M79): what the run will measure, keyed by the plan's object.

  - The header counts the roles by their shapes (target, comparisons, check: BRAND 10) and
    copies the set as TSV (Qt TargetTable's columns).
  - The list is TargetSetList (D24, the Observe Photometry card's): Remove is immediate with
    Undo, asked first during a run (the screen does it); Enter or a click opens the star in
    Observe. The set stays editable while a run is active (Q-P9: journalled in the run).
  - [variable-star Pick in field] opens Observe on the drawer's Variables tab (D7).
-->
<script lang="ts">
  import Card from '../components/Card.svelte';
  import Control from '../components/Control.svelte';
  import Icon from '../components/Icon.svelte';
  import { tooltip } from '../components/tooltip';
  import { fixed } from '../format/number';
  import type { TargetStar } from '../imaging/field/types';
  import { catalogV } from '../imaging/photometry/present';
  import TargetSetList from '../imaging/photometry/TargetSetList.svelte';
  import { roleCounts, targetSetTsv } from './targets';

  interface Props {
    stars: readonly TargetStar[];
    /** The set's object ("Unknown" when none). */
    object: string | null;
    removing?: string | null;
    onremove: (s: TargetStar) => void;
    onpick: (s: TargetStar) => void;
    onfield: () => void;
    oncopy: (tsv: string) => void;
    open?: boolean;
  }

  let { stars, object, removing = null, onremove, onpick, onfield, oncopy, open = $bindable(true) }: Props = $props();

  const counts = $derived(roleCounts(stars));
  const complete = $derived(counts.target > 0 && counts.comparison > 0);
  const vText = (s: TargetStar) => {
    const v = catalogV(s);
    return v === null ? null : `V ${fixed(v, 2)}`;
  };
</script>

<Card title="Target set" icon="target-star" collapsible bind:open persist="argos.card.plan.targets" fill>
  {#snippet status()}
    <span
      class="counts num"
      role="img"
      aria-label="{counts.target} target, {counts.comparison} comparison{counts.comparison === 1 ? '' : 's'}, {counts.check} check{complete ? '' : ': incomplete'}"
      use:tooltip={{ text: complete ? 'Target and comparisons set' : 'A target and at least one comparison are needed to measure', placement: 'top' }}
    >
      <span class="c"><Icon name="target-star" size={12} />{counts.target}</span>
      <span class="c"><Icon name="comparison-star" size={12} />{counts.comparison}</span>
      <span class="c"><Icon name="check-star" size={12} />{counts.check}</span>
    </span>
    <Control icon="copy" label="Copy the target set as TSV" size="xs" variant="ghost" tooltip="top" disabledReason={stars.length ? null : 'the set is empty'} onclick={() => oncopy(targetSetTsv(stars))} />
  {/snippet}
  {#snippet summary()}{object ?? 'no object'} · {stars.length} star{stars.length === 1 ? '' : 's'}{/snippet}

  <div class="body">
    {#if object && object !== 'Unknown'}<p class="obj">Set of <span class="name">{object}</span></p>{/if}
    <div class="list">
      <TargetSetList
        {stars}
        value={vText}
        valueTitle={() => 'Catalogue V magnitude'}
        foldComparisons
        {removing}
        empty="No photometry target yet. Find a variable star, or pick one in the solved field."
        {onremove}
        {onpick}
      />
    </div>
    <div class="actions">
      <Control icon="variable-star" label="Pick in field" showLabel size="s" variant="ghost" tooltipText="Opens Observe on the Variables tab of the solved field" onclick={onfield} />
    </div>
  </div>
</Card>

<style>
  .counts {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .c {
    display: inline-flex;
    align-items: center;
    gap: 2px;
  }
  .c :global(svg) {
    color: var(--fg-muted);
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-height: 0;
    height: 100%;
  }
  .obj {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .name {
    color: var(--fg);
  }
  .list {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
  }
  .actions {
    display: flex;
  }
</style>

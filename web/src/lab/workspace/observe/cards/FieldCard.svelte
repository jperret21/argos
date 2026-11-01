<!--
  Field card: the plate solution in numbers, live re-identification, and the
  Identify action (S).
-->
<script lang="ts">
  import IconButton from '../../../../lib/components/IconButton.svelte';
  import { sim, ws } from '../../model/app.svelte';
  import { PLATE_SCALE, ROTATION_DEG } from '../../model/field';
  import { fixed } from '../../model/format';
  import Readouts from '../../ui/Readouts.svelte';

  const items = $derived([
    { k: 'Scale', v: fixed(PLATE_SCALE, 2), unit: '″/px' },
    { k: 'Rotation', v: fixed(ROTATION_DEG, 1), unit: '°' },
    { k: 'Field', v: '43 × 76', unit: '′' },
    { k: 'Target', v: '1.5', unit: '′ from centre' },
  ]);
</script>

<div class="field">
  {#if sim.solved || sim.inRun}
    <Readouts {items} cols={2} />
    <p class="note">Live re-identification every 20 s · catalogues ready (VSX, VSP, Gaia DR3 to G 15)</p>
  {:else}
    <p class="note">Not identified yet. Identify uses ASTAP on the frame on screen.</p>
  {/if}
  <IconButton icon="plate-solve" label="Identify field" showLabel shortcut="S" onclick={() => ws.toast('Identify field (ASTAP)', 'info')} />
</div>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    align-items: flex-start;
  }
  .field :global(.wrap) {
    width: 100%;
  }
  .note {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>

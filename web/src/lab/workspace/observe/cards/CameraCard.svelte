<!--
  Camera card: exposure and gain (the app's NumberField: text input, decimal
  keyboard, no native spinner), frame type and filter as segmented choices,
  Shot (labelled, E). During a run the fields belong to the sequence and say
  so instead of looking editable.
-->
<script lang="ts">
  import IconButton from '../../../../lib/components/IconButton.svelte';
  import NumberField from '../../../../lib/components/NumberField.svelte';
  import Segmented from '../../../../lib/components/Segmented.svelte';
  import { sim, ws } from '../../model/app.svelte';
  import { fixed } from '../../model/format';
  import { RUN } from '../../model/night';

  let exposure = $state(2);
  let gain = $state(80);
  let frameType: 'light' | 'dark' | 'flat' | 'bias' = $state('light');
  let filter: 'ir' | 'lp' | 'dark' = $state('ir');
  const owned = $derived(sim.inRun && sim.running);
</script>

{#if owned}
  <p class="owned">
    Owned by the sequence: <span class="num">{fixed(RUN.exposure, 1)} s · gain {RUN.gain} · {RUN.filter}</span>. Change them in Plan
    after the run.
  </p>
{:else}
  <div class="cam">
    <div class="fields">
      <NumberField label="Exposure" bind:value={exposure} unit="s" min={0.001} max={600} step={0.5} decimals={1} settleMs={600} />
      <NumberField label="Gain" bind:value={gain} min={0} max={240} integer settleMs={600} />
    </div>
    <div class="seg">
      <span class="lab-caps">Frame</span>
      <Segmented
        label="Frame type"
        size="s"
        bind:value={frameType}
        options={[
          { value: 'light', label: 'Light' },
          { value: 'dark', label: 'Dark' },
          { value: 'flat', label: 'Flat' },
          { value: 'bias', label: 'Bias' },
        ]}
      />
    </div>
    <div class="seg">
      <span class="lab-caps">Filter</span>
      <Segmented
        label="Filter"
        size="s"
        bind:value={filter}
        options={[
          { value: 'ir', label: 'IR' },
          { value: 'lp', label: 'LP' },
          { value: 'dark', label: 'Dark' },
        ]}
      />
      <span class="hint">IR for photometry</span>
    </div>
    <div class="actions">
      <IconButton icon="capture" label="Shot" showLabel shortcut="E" onclick={() => ws.toast(`Shot: ${fixed(exposure, 1)} s, gain ${gain}`, 'info')} />
      <span class="last num">last shot 19:52:04 UTC · #{sim.liveSeq}</span>
    </div>
  </div>
{/if}

<style>
  .cam {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .fields {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3);
  }
  .seg {
    display: grid;
    grid-template-columns: 54px auto 1fr;
    align-items: center;
    gap: var(--space-2);
  }
  .hint {
    color: var(--text-muted);
    font-size: var(--text-xs);
    justify-self: end;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .last {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
  .owned {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .owned .num {
    color: var(--fg);
    font-family: var(--font-mono);
  }
</style>

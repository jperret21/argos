<!--
  Mount card. Readouts on one row in Framing (where pointing is the task, the
  Target block is open); during a run every motion is INTERLOCKED (proposal
  C7, server-side 409 run_active): Slew and Park are disabled with the reason,
  and one explicit path is offered, "Pause the run and slew", by
  hold-to-confirm. Park is hold-to-confirm (pointer) or Enter + inline
  confirmation (keyboard).
-->
<script lang="ts">
  import IconButton from '../../../../lib/components/IconButton.svelte';
  import Icon from '../../../../lib/components/Icon.svelte';
  import { sim, ws } from '../../model/app.svelte';
  import { TARGET_DEC, TARGET_RA_H } from '../../model/field';
  import { formatDec, formatRA } from '../../model/format';
  import HoldButton from '../../ui/HoldButton.svelte';
  import Readouts from '../../ui/Readouts.svelte';

  const lock = $derived(sim.running ? 'the sequence is running: a slew now breaks the time series' : null);
  const alt = $derived(sim.latest?.alt ?? 62.4);
  const items = $derived([
    { k: 'RA', v: formatRA(TARGET_RA_H + 0.0012) },
    { k: 'Dec', v: formatDec(TARGET_DEC + 0.06) },
    { k: 'Alt', v: `${alt.toFixed(2)}°` },
    { k: 'Az', v: '301.12°' },
  ]);
</script>

<div class="mount">
  <Readouts {items} cols={4} />
  <div class="target">
    <span class="lab-caps">Object</span>
    <button type="button" class="obj" onclick={() => (ws.overlay = 'palette')}>
      <Icon name="search" size={16} />
      <span class="name">RR Lyr</span>
      <span class="cat">RR Lyrae variable · VSX · cached</span>
    </button>
    <p class="away num">{formatRA(TARGET_RA_H)} {formatDec(TARGET_DEC)} · 0.08° from the pointing</p>
  </div>
  <div class="actions">
    <IconButton icon="goto" label="Slew" showLabel disabledReason={lock} onclick={() => ws.toast('Slewing to RR Lyr…', 'info')} />
    <IconButton icon="center-target" label="Centre" showLabel disabledReason={lock ?? (sim.solved ? null : 'identify the field first (S)')} onclick={() => ws.toast('Centring RR Lyr from the plate solution', 'info')} />
    <span class="grow"></span>
    {#if sim.parked}
      <IconButton icon="unpark" label="Unpark" showLabel onclick={() => sim.unpark()} />
    {:else}
      <HoldButton icon="park" label="Park" question="Park the mount?" consequence="Parking closes the Seestar arm and stops tracking." disabledReason={lock} onconfirm={() => sim.park()} />
    {/if}
  </div>
  {#if lock}
    <div class="interlock">
      <p>Mount moves are locked while the sequence runs.</p>
      <HoldButton
        icon="pause"
        label="Pause the run and slew"
        tone="secondary"
        question="Pause the run and slew?"
        consequence="The run pauses at the end of this frame, then the mount slews; the run stays paused."
        onconfirm={() => {
          sim.pause();
          ws.toast('Run pausing at the frame boundary, then slew', 'warn');
        }}
      />
    </div>
  {/if}
</div>

<style>
  .mount {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .target {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding-top: var(--space-2);
    border-top: var(--border-w) solid var(--border-soft);
  }
  .obj {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: var(--input-h);
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg-muted);
    cursor: pointer;
  }
  .name {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .cat {
    margin-left: auto;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .away {
    margin: 0;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
  .actions {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .grow {
    flex: 1;
  }
  .interlock {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-3);
    border: var(--border-w) dashed var(--border);
    border-radius: var(--radius-s);
  }
  .interlock p {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>

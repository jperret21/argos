<!--
  Focuser card: position, temperature, step size, in / out, Autofocus with
  its progress (the V-curve itself moved to the band in Focus mode, where it
  gets 60 % of the width).
-->
<script lang="ts">
  import IconButton from '../../../../lib/components/IconButton.svelte';
  import Segmented from '../../../../lib/components/Segmented.svelte';
  import { sim, ws } from '../../model/app.svelte';
  import { int } from '../../model/format';
  import Readouts from '../../ui/Readouts.svelte';

  let step: '10' | '50' | '100' | '500' = $state('50');
  const pos = $derived(sim.afRunning ? (sim.af.steps[Math.max(0, sim.afStep - 1)]?.position ?? 1305) : 1305);
  const items = $derived([
    { k: 'Position', v: int(pos), unit: 'steps' },
    { k: 'Temperature', v: '12.3', unit: '°C' },
  ]);
  const frac = $derived(sim.afStep / sim.af.steps.length);
</script>

<div class="foc">
  <Readouts {items} cols={2} />
  <div class="steps">
    <span class="lab-caps">Step</span>
    <Segmented
      label="Focus step"
      size="s"
      bind:value={step}
      options={[
        { value: '10', label: '10' },
        { value: '50', label: '50' },
        { value: '100', label: '100' },
        { value: '500', label: '500' },
      ]}
    />
    <span class="grow"></span>
    <IconButton icon="focus-out" label="Focus out by {step}" size="s" disabledReason={sim.afRunning ? 'autofocus is running' : null} onclick={() => ws.toast(`Focuser −${step}`, 'info')} />
    <IconButton icon="focus-in" label="Focus in by {step}" size="s" disabledReason={sim.afRunning ? 'autofocus is running' : null} onclick={() => ws.toast(`Focuser +${step}`, 'info')} />
  </div>
  <div class="af">
    {#if sim.afRunning}
      <IconButton icon="stop" label="Halt" showLabel glyphTone="danger" onclick={() => (sim.afRunning = false)} />
      <span class="prog"><span class="bar" style:--f={frac}></span></span>
      <span class="num">step {sim.afStep} / {sim.af.steps.length}</span>
    {:else}
      <IconButton icon="autofocus" label="Autofocus" showLabel onclick={() => ((sim.afStep = 0), (sim.afRunning = true))} />
      <span class="num muted">last: best {int(sim.af.best)} · HFD {sim.af.bestHfd.toFixed(2)} px</span>
    {/if}
  </div>
</div>

<style>
  .foc {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .steps,
  .af {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .grow {
    flex: 1;
  }
  .prog {
    flex: 1;
    height: 6px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: 1px;
    background: var(--bg-2);
    position: relative;
  }
  .bar {
    position: absolute;
    inset: 0;
    transform-origin: left;
    transform: scaleX(var(--f));
    background: var(--accent);
  }
  .num {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--fg);
  }
  .muted {
    color: var(--text-muted);
  }
</style>

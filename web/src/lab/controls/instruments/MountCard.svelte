<!--
  Mount card with the jog section and Park (proposal composing the lab
  controls at rail width): polled readouts, Tracking (labelled instrument
  toggle) with its rate, the jog pad, then the hardware row: Unpark / Park
  by hold-to-confirm. Every refusal says why (parked, run active, offline).
-->
<script lang="ts">
  import type { Tone } from '../../../lib/app/status';
  import Card from '../../../lib/components/Card.svelte';
  import StatusBadge from '../../../lib/components/StatusBadge.svelte';
  import Ctl from '../components/Ctl.svelte';
  import HoldButton from '../components/HoldButton.svelte';
  import Seg from '../components/Seg.svelte';
  import { fixed } from '../format';
  import type { MountSim } from '../sim.svelte';
  import type { Direction } from '../jog';
  import JogPad from './JogPad.svelte';

  type TrackRate = 'sidereal' | 'lunar' | 'solar';

  interface Props {
    sim: MountSim;
    /** A sequence is running: motion is refused (functional-spaces 4.11). */
    runActive?: boolean;
    pin?: { pressed?: Direction[]; stalled?: Direction[]; armed?: boolean; age?: number | null } | null;
    armed?: boolean;
  }

  let { sim, runActive = false, pin = null, armed = $bindable(false) }: Props = $props();

  let trackRate: TrackRate = $state('sidereal');
  const RATES = [
    { value: 'sidereal' as const, label: 'Sidereal' },
    { value: 'lunar' as const, label: 'Lunar' },
    { value: 'solar' as const, label: 'Solar', disabledReason: 'Not offered by this driver' },
  ];

  const moving = $derived(sim.rate.primary !== 0 || sim.rate.secondary !== 0);
  const runReason = 'The sequence is running: moving the mount breaks the time series';
  const jogReason = $derived(runActive ? runReason : null);

  const badge = $derived.by((): { tone: Tone; label: string } => {
    if (!sim.connected) return { tone: 'idle', label: 'Offline' };
    if (sim.parked) return { tone: 'idle', label: 'Parked' };
    if (moving || (pin?.pressed?.length ?? 0) > 0) return { tone: 'busy', label: 'Jogging' };
    return sim.tracking ? { tone: 'ok', label: 'Tracking' } : { tone: 'idle', label: 'Not tracking' };
  });

  // RA/Dec are not simulated here: fixed values in the BRAND 5 formats.
  const RA = '05h 35m 17.3s';
  const DEC = '−05° 23′ 28″';
</script>

<Card title="Mount" icon="mount">
  {#snippet status()}<StatusBadge tone={badge.tone} label={badge.label} />{/snippet}

  <div class="ro">
    <div><span class="k">RA</span><span class="v num">{RA}</span></div>
    <div><span class="k">Dec</span><span class="v num">{DEC}</span></div>
    <div><span class="k">Alt</span><span class="v num">{fixed(sim.alt, 2)}°</span></div>
    <div><span class="k">Az</span><span class="v num">{fixed(sim.az, 2)}°</span></div>
  </div>

  <div class="row">
    <Ctl
      icon="tracking"
      label="Tracking"
      showLabel
      size="s"
      pressed={sim.tracking}
      disabledReason={sim.parked ? 'Unpark the mount first' : runActive && sim.tracking ? runReason : null}
      onclick={() => (sim.tracking = !sim.tracking)}
    />
    <Seg label="Tracking rate" options={RATES} bind:value={trackRate} size="s" activation="manual" disabledReason={sim.parked ? 'Unpark the mount first' : null} />
  </div>

  <div class="section">
    <span class="k">Jog</span>
    <span class="rule"></span>
  </div>
  <JogPad {sim} bind:armed blockedReason={jogReason} {pin} />

  <div class="row hw">
    {#if sim.parked}
      <Ctl icon="unpark" label="Unpark" showLabel disabledReason={runActive ? runReason : null} onclick={() => sim.unpark()} />
    {:else}
      <HoldButton
        icon="park"
        label="Park"
        verb="park"
        caption={false}
        confirmTitle="Park the mount?"
        confirmBody="Parking physically closes the Seestar arm and stops tracking."
        busyLabel="Parking…"
        disabledReason={runActive ? runReason : null}
        onconfirm={() => sim.park()}
      />
    {/if}
    <span class="grow"></span>
    <span class="hint">Esc stops every axis</span>
  </div>
</Card>

<style>
  .ro {
    display: grid;
    grid-template-columns: 1.25fr 1fr;
    gap: var(--space-2) var(--space-4);
    padding: var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .ro > div {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .k {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .v {
    color: var(--fg);
    font-size: var(--text-xl);
    font-weight: var(--weight-medium);
    line-height: 1.2;
    white-space: nowrap;
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .row.hw {
    align-items: flex-start;
  }
  .grow {
    flex: 1;
  }
  .hint {
    align-self: center;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .section {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-bottom: -4px;
  }
  .rule {
    flex: 1;
    height: 1px;
    background: var(--border-soft);
  }
</style>

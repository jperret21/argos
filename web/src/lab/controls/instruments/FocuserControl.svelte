<!--
  Focuser card (proposal for spec 05 §2.3 D, rail width 396 px).

  - Readouts: polled position (17 px mono, the needle's number), commanded
    target with the taps still queued, focuser temperature and its drift
    since the last autofocus: refocusing is due when the tube has cooled,
    so the card says by how much.
  - Two-scale gauge (FocuserGauge): one tick = one tap.
  - Step size (segmented, mono), Out / In (tap = one step; hold repeats at
    12 steps/s, no acceleration: hardware). Taps during a move are QUEUED
    ("+300 queued") and sent as one move when the current one ends: no Move
    while moving, which some ASCOM drivers refuse.
  - Go to: a scrub field, Enter moves; out of range is refused in words,
    never clamped (Qt P6); never overwritten while edited (Qt P5).
  - Autofocus (icon + label: minutes of hardware) becomes "Stop AF" with
    the sweep's ring and "7/14"; Halt is ALWAYS available while connected,
    autofocus included (Qt P7), and Esc halts.
  Disabled reasons in words everywhere; the card keeps its layout in every
  state (no jumps).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import Card from '../../../lib/components/Card.svelte';
  import StatusBadge from '../../../lib/components/StatusBadge.svelte';
  import type { Tone } from '../../../lib/app/status';
  import Ctl from '../components/Ctl.svelte';
  import ScrubField from '../components/ScrubField.svelte';
  import Seg from '../components/Seg.svelte';
  import { fixed, grouped, signed, signedGrouped } from '../format';
  import type { FocuserSim } from '../sim.svelte';
  import { REPEAT } from '../values';
  import FocuserGauge from './FocuserGauge.svelte';

  type Step = '1' | '10' | '50' | '100' | '500' | '1000';

  interface Props {
    sim: FocuserSim;
    step?: Step;
  }

  let { sim, step = $bindable('100') }: Props = $props();

  const STEPS: { value: Step; label: string }[] = (['1', '10', '50', '100', '500', '1000'] as Step[]).map((v) => ({
    value: v,
    label: grouped(Number(v)),
  }));

  const stepN = $derived(Number(step));
  let goto = $state(untrack(() => sim.position));
  $effect(() => {
    if (sim.target !== null) goto = sim.target + sim.queued;
  });

  const offline = $derived(!sim.connected);
  const afRunning = $derived(sim.af !== null);
  const commonReason = $derived(offline ? 'Connect the focuser first' : afRunning ? 'Autofocus owns the focuser' : null);
  const finalTarget = $derived(sim.target === null ? null : sim.target + sim.queued);
  const outReason = $derived(commonReason ?? ((finalTarget ?? sim.position) - stepN < 0 ? 'At the travel limit 0' : null));
  const inReason = $derived(commonReason ?? ((finalTarget ?? sim.position) + stepN > sim.maxStep ? `At the travel limit ${grouped(sim.maxStep)}` : null));

  const badge = $derived.by((): { tone: Tone; label: string } => {
    if (offline) return { tone: 'idle', label: 'Offline' };
    if (afRunning) return { tone: 'active', label: 'Autofocus' };
    if (sim.moving) return { tone: 'busy', label: 'Moving' };
    return { tone: 'ok', label: 'Ready' };
  });

  const drift = $derived(sim.temperature - sim.afTemp);

  // Tap = one step; hold repeats (no acceleration on hardware).
  let repeatDelay: ReturnType<typeof setTimeout> | null = null;
  let repeatTimer: ReturnType<typeof setInterval> | null = null;
  let held: 'out' | 'in' | null = $state(null);

  function stepOnce(dir: 1 | -1): void {
    const base = finalTarget ?? sim.position;
    if (base + dir * stepN < 0 || base + dir * stepN > sim.maxStep) return stopRepeat();
    sim.step(dir * stepN);
  }

  function press(e: PointerEvent, dir: 1 | -1): void {
    if ((dir > 0 ? inReason : outReason) || e.button !== 0) return;
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    held = dir > 0 ? 'in' : 'out';
    stepOnce(dir);
    repeatDelay = setTimeout(() => {
      repeatTimer = setInterval(() => stepOnce(dir), REPEAT.interval);
    }, REPEAT.delay);
  }

  function stopRepeat(): void {
    if (repeatDelay) clearTimeout(repeatDelay);
    if (repeatTimer) clearInterval(repeatTimer);
    repeatDelay = repeatTimer = null;
    held = null;
  }

  function keyStep(e: MouseEvent, dir: 1 | -1): void {
    if (e.detail === 0) stepOnce(dir); // keyboard activation; pointer handled on press
  }

  const afProgress = $derived(sim.af ? sim.af.step / sim.af.total : null);
</script>

<Card title="Focuser" icon="focuser">
  {#snippet status()}<StatusBadge tone={badge.tone} label={badge.label} />{/snippet}

  <div class="readouts">
    <div class="ro">
      <span class="k">Position</span>
      <span class="v big num">{offline ? '—' : grouped(sim.position)}</span>
      <span class="sub num">{offline ? '' : sim.moving ? 'polled 2 Hz' : 'steps'}</span>
    </div>
    <div class="ro">
      <span class="k">Target</span>
      <span class="v num">{finalTarget === null || offline ? '—' : grouped(finalTarget)}</span>
      <span class="sub num">{sim.queued ? `${signedGrouped(sim.queued)} queued` : ''}</span>
    </div>
    <div class="ro">
      <span class="k">Temperature</span>
      <span class="v num">{offline ? '—' : `${fixed(sim.temperature, 1)} °C`}</span>
      <span class="sub num" class:warn={!offline && Math.abs(drift) >= 1.5}>{offline ? '' : `${signed(drift, 1)} °C since AF`}</span>
    </div>
  </div>

  <FocuserGauge position={sim.position} target={finalTarget} max={sim.maxStep} step={stepN} afBest={sim.afBest} {offline} />

  <div class="row">
    <span class="key">Step</span>
    <Seg label="Focus step" options={STEPS} bind:value={step} size="s" mono disabledReason={offline ? 'Connect the focuser first' : null} />
    <span class="grow"></span>
    <Ctl
      icon="focus-out"
      label="Focus out"
      tooltipText="Focus out: position −{grouped(stepN)}"
      hint={outReason ? null : 'Hold to repeat'}
      disabledReason={outReason}
      data-force={held === 'out' ? 'active' : undefined}
      onpointerdown={(e: PointerEvent) => press(e, -1)}
      onpointerup={stopRepeat}
      onpointercancel={stopRepeat}
      onlostpointercapture={stopRepeat}
      onclick={(e: MouseEvent) => keyStep(e, -1)}
    />
    <Ctl
      icon="focus-in"
      label="Focus in"
      tooltipText="Focus in: position +{grouped(stepN)}"
      hint={inReason ? null : 'Hold to repeat'}
      disabledReason={inReason}
      data-force={held === 'in' ? 'active' : undefined}
      onpointerdown={(e: PointerEvent) => press(e, 1)}
      onpointerup={stopRepeat}
      onpointercancel={stopRepeat}
      onlostpointercapture={stopRepeat}
      onclick={(e: MouseEvent) => keyStep(e, 1)}
    />
  </div>

  <div class="goto">
    <ScrubField
      label="Go to"
      bind:value={goto}
      min={0}
      max={sim.maxStep}
      step={stepN}
      integer
      pxPerStep={6}
      format={grouped}
      range="0–{grouped(sim.maxStep)}"
      appliedNote="moving"
      action={{ icon: 'focus-move', label: 'Move to this position' }}
      inline
      disabledReason={commonReason}
      oncommit={(v) => sim.moveTo(v)}
    />
  </div>

  <div class="actions">
    {#if afRunning}
      <Ctl
        icon="stop"
        label="Stop AF"
        showLabel
        progress={afProgress}
        progressText="step {sim.af?.step} of {sim.af?.total}"
        tooltipText="Cancel autofocus and return to the start position"
        onclick={() => sim.stopAutofocus()}
      >
        {#snippet trailing()}{sim.af?.step}/{sim.af?.total}{/snippet}
      </Ctl>
    {:else}
      <Ctl
        icon="autofocus"
        label="Autofocus"
        showLabel
        tooltipText="Autofocus: V-curve sweep, about 2 min"
        disabledReason={offline ? 'Connect the focuser and the camera first' : null}
        onclick={() => void sim.autofocus()}
      />
    {/if}
    <span class="grow"></span>
    <Ctl
      icon="stop"
      label="Halt"
      showLabel
      variant="danger"
      shortcut="Escape"
      tooltipText="Halt: stop where it is"
      disabledReason={offline ? 'Connect the focuser first' : null}
      onclick={() => sim.halt()}
    />
  </div>

  <p class="line" aria-live="polite">
    {#if sim.af}
      <span class="num">{sim.af.stage === 'coarse' ? 'Coarse' : sim.af.stage === 'fine' ? 'Fine' : 'Verify'} · step {sim.af.step} / {sim.af.total} · {grouped(sim.position)}</span>
    {:else if sim.message}
      <span>{sim.message}</span>
    {:else}
      <span class="muted">AF frames: 2.0 s, gain 80 (Camera)</span>
    {/if}
  </p>
</Card>

<style>
  .readouts {
    display: grid;
    grid-template-columns: 1.15fr 1fr 1.1fr;
    gap: var(--space-3);
  }
  .ro {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
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
    font-size: var(--text-m);
    line-height: 22px;
    white-space: nowrap;
  }
  .v.big {
    font-size: var(--text-xl);
    font-weight: var(--weight-medium);
  }
  .sub {
    height: 14px;
    color: var(--text-muted);
    font-size: var(--text-2xs);
    white-space: nowrap;
  }
  .sub.warn {
    color: var(--fg);
  }
  .sub.warn::before {
    content: '';
    display: inline-block;
    width: 5px;
    height: 5px;
    margin-right: 4px;
    border-radius: var(--radius-round);
    background: var(--warning);
    vertical-align: 1px;
  }

  .row,
  .actions {
    display: flex;
    align-items: center;
    gap: var(--space-1);
  }
  .key {
    margin-right: var(--space-2);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .grow {
    flex: 1;
  }
  .actions {
    gap: var(--space-2);
  }
  .goto {
    min-width: 0;
  }
  .line {
    min-height: 16px;
    margin: -4px 0 0;
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .line .muted {
    color: var(--text-muted);
  }
</style>

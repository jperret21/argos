<!--
  Plate 06: hold-to-confirm and progress inside buttons.
-->
<script lang="ts">
  import Ctl from '../components/Ctl.svelte';
  import HoldButton from '../components/HoldButton.svelte';
  import Panel from '../components/Panel.svelte';
  import { fixed } from '../format';
  import { clock, MountSim } from '../sim.svelte';
  import type { Hardware } from '../types';

  let { hw }: { hw: Hardware } = $props();

  const wait = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
  const mount = new MountSim();

  // -- Progress specimens (real elapsed time) ------------------------------------------
  $effect(() => {
    const exp = hw.exposure;
    exp.seconds = 10;
    exp.start(true);
    const release = clock.use();
    return () => {
      release();
      exp.stop();
    };
  });
  const expP = $derived(hw.exposure.startedAt === null ? null : Math.min(1, (clock.t - hw.exposure.startedAt) / 10_000));

  let connecting = $state(false);
  let solving = $state(false);
  let saved: string | null = $state(null);
  let exportP: number | null = $state(null);

  async function connect(): Promise<void> {
    connecting = true;
    await wait(2200);
    connecting = false;
  }
  async function solve(): Promise<void> {
    solving = true;
    await wait(2600);
    solving = false;
  }
  function takeShot(): void {
    saved = `Saved #${hw.exposure.frame}`;
    setTimeout(() => (saved = null), 2400);
  }
  function startExport(): void {
    if (exportP !== null) return;
    const t0 = performance.now();
    const tick = () => {
      const p = Math.min(1, (performance.now() - t0) / 4000);
      exportP = p;
      if (p < 1) requestAnimationFrame(tick);
      else setTimeout(() => (exportP = null), 900);
    };
    requestAnimationFrame(tick);
  }

  const PARK = {
    confirmTitle: 'Park the mount?',
    confirmBody: 'Parking physically closes the Seestar arm and stops tracking.',
  };
</script>

<div class="cols">
  <div class="col">
    <Panel
      code="F.1"
      title="Hold to confirm"
      note="Press and hold 0.7 s. The ring is the exact elapsed time; release or slide off before the end and nothing is sent, which the caption says. A tap teaches the gesture. Keyboard: Enter opens the confirmation in place."
      shot="hold"
    >
      <div class="live" data-shot="hold-live">
        <HoldButton icon="park" label="Park" verb="park" {...PARK} busyLabel="Parking… the arm is closing" doneLabel="Parked" onconfirm={() => wait(1600)} />
      </div>
      <div class="phases">
        <div class="ph"><span class="lab-eyebrow">Rest · the track says “hold”</span><HoldButton icon="park" label="Park" verb="park" {...PARK} pin={{ phase: 'rest' }} /></div>
        <div class="ph"><span class="lab-eyebrow">Holding · 46 %</span><HoldButton icon="park" label="Park" verb="park" {...PARK} pin={{ phase: 'holding', progress: 0.46 }} /></div>
        <div class="ph"><span class="lab-eyebrow">Released early</span><HoldButton icon="park" label="Park" verb="park" {...PARK} pin={{ phase: 'released' }} /></div>
        <div class="ph"><span class="lab-eyebrow">Tapped</span><HoldButton icon="park" label="Park" verb="park" {...PARK} pin={{ phase: 'tapped' }} /></div>
        <div class="ph"><span class="lab-eyebrow">Sent · busy</span><HoldButton icon="park" label="Park" verb="park" {...PARK} busyLabel="Parking… the arm is closing" pin={{ phase: 'busy' }} /></div>
        <div class="ph"><span class="lab-eyebrow">Unavailable</span><HoldButton icon="park" label="Park" verb="park" {...PARK} disabledReason="Connect the mount first" /></div>
      </div>
    </Panel>
  </div>

  <div class="col">
    <Panel
      code="F.2"
      title="Where a hold is worth it"
      note="Physical or hard to undo during a night, and a single large target. Everything else stays a plain click (README 3.3)."
      shot="uses"
    >
      <div class="uses">
        <div class="use">
          <span class="lab-eyebrow">Interlock during a run</span>
          <div class="pair">
            <Ctl icon="goto" label="Slew" showLabel variant="primary" size="l" disabledReason="The sequence is running: slewing now breaks the time series" />
            <HoldButton
              icon="pause"
              label="Pause the run and slew"
              verb="pause and slew"
              variant="primary"
              confirmTitle="Pause the run and slew?"
              confirmBody="The run pauses at the end of the current frame, then the mount slews to M 42. The run stays paused."
              busyLabel="Pausing at the frame boundary…"
              doneLabel="Paused · slewing"
              onconfirm={() => wait(1800)}
            />
          </div>
        </div>
        <div class="use">
          <span class="lab-eyebrow">Ends a run</span>
          <HoldButton
            icon="stop"
            label="Stop sequence"
            verb="stop the run"
            variant="danger"
            confirmTitle="Stop the sequence?"
            confirmBody="212 frames are saved. The exposure in progress (4.1 of 10 s) is discarded. Darks are not taken."
            confirmAction="Stop"
            cancelLabel="Keep running"
            busyLabel="Stopping…"
            doneLabel="Stopped · 212 frames saved"
            onconfirm={() => wait(1200)}
          />
          <p class="lab-note">The consequence the spec's dialog states (06 §2.3.6) is in the keyboard confirmation; the owner chooses dialog or hold (open question).</p>
        </div>
        <div class="use">
          <span class="lab-eyebrow">Keyboard path · Enter</span>
          <HoldButton
            icon="stop"
            label="Stop sequence"
            verb="stop the run"
            variant="danger"
            confirmTitle="Stop the sequence?"
            confirmBody="212 frames are saved. The exposure in progress (4.1 of 10 s) is discarded."
            confirmAction="Stop"
            cancelLabel="Keep running"
            pin={{ phase: 'confirm' }}
          />
        </div>
      </div>
    </Panel>
  </div>

  <div class="col">
    <Panel
      code="F.3"
      title="Progress and busy inside buttons"
      note="Timed: the ring, with the value in the tip. Untimed: the spinner. The width never changes; the result is said once, then leaves."
      shot="progress"
    >
      <div class="prog">
        <div class="pr">
          <Ctl icon="capture" label="Take one exposure" variant="secondary" progress={expP} progressText="{fixed((expP ?? 0) * 10, 1)} / 10.0 s" shortcut="E" onclick={takeShot} />
          <div class="t"><b>Exposure</b><span class="num">{fixed((expP ?? 0) * 10, 1)} / 10.0 s</span></div>
          {#if saved}<span class="done">{saved}</span>{/if}
        </div>
        <div class="pr">
          <Ctl icon="connect" label="Connect" showLabel variant="primary" busy={connecting} onclick={connect} />
          <div class="t"><b>Connect</b><span>{connecting ? 'checking 192.168.1.42…' : 'press to try'}</span></div>
        </div>
        <div class="pr">
          <Ctl icon="plate-solve" label="Identify field" variant="ghost" busy={solving} shortcut="S" onclick={solve} />
          <div class="t"><b>Identify field</b><span>{solving ? 'ASTAP solving…' : 'untimed: spinner'}</span></div>
        </div>
        <div class="pr">
          {#if mount.slewToGo !== null}
            <Ctl icon="abort" label="Abort" showLabel variant="danger" shortcut="Escape" onclick={() => mount.abortSlew()}>
              {#snippet trailing()}{fixed(mount.slewToGo ?? 0, 1)}° to go{/snippet}
            </Ctl>
          {:else}
            <Ctl icon="goto" label="Slew" showLabel variant="primary" onclick={() => mount.slew(12.4)} />
          {/if}
          <div class="t"><b>Slew → Abort</b><span>angle to go, polled at 2 Hz</span></div>
        </div>
        <div class="pr">
          <Ctl icon="stop" label="Stop AF" showLabel progress={7 / 14} progressText="step 7 of 14">
            {#snippet trailing()}7/14{/snippet}
          </Ctl>
          <div class="t"><b>Autofocus</b><span>steps done</span></div>
        </div>
        <div class="pr">
          <Ctl
            icon="export-aavso"
            label="Export"
            showLabel
            progress={exportP}
            progressText="{Math.round((exportP ?? 0) * 100)} %"
            onclick={startExport}
          >
            {#snippet trailing()}{#if exportP !== null}{Math.round(exportP * 100)} %{/if}{/snippet}
          </Ctl>
          <div class="t"><b>Export job</b><span>{exportP === null ? 'press: a 4 s job' : 'writing 212 rows'}</span></div>
        </div>
      </div>
    </Panel>
  </div>
</div>

<style>
  .cols {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 0.9fr);
    gap: var(--space-4);
    align-items: start;
  }
  .col {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    min-width: 0;
  }
  .live {
    padding: var(--space-4);
    margin-bottom: var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    --ctl-halo: var(--bg-2);
  }
  .phases {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-4) var(--space-4);
  }
  .ph {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .uses {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  .use {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .use + .use {
    padding-top: var(--space-3);
    border-top: var(--border-w) solid var(--border-soft);
  }
  .pair {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
  }
  .prog {
    display: flex;
    flex-direction: column;
  }
  .pr {
    display: grid;
    grid-template-columns: 150px minmax(0, 1fr) auto;
    justify-items: start;
    align-items: center;
    gap: var(--space-3);
    min-height: 52px;
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .pr:last-child {
    border-bottom: none;
  }
  .t {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .t b {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .done {
    color: var(--fg);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .done::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-right: 6px;
    border-radius: var(--radius-round);
    background: var(--success);
    vertical-align: 1px;
  }
</style>

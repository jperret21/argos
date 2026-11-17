<!--
  Run card (functional-spaces P4): "is my run fine?" answered in one place.
  State word, step, frames n / N with a true-proportion bar, the LAST-FRAME
  AGE with the observed cadence (the liveness signal: a frozen run looks
  like a healthy one between frames otherwise), end time and time left from
  the observed cadence, next autofocus, end-of-run action, the open
  attention items, Pause (no confirmation: it holds at a frame boundary and
  Resume undoes it) and Stop (inline confirmation saying what is kept).
  After the run it becomes the wrap-up: calibration from tonight's settings
  and cadence, Park by hold-to-confirm.
-->
<script lang="ts">
  import Button from '../../../../lib/components/Button.svelte';
  import IconButton from '../../../../lib/components/IconButton.svelte';
  import { sim, ws } from '../../model/app.svelte';
  import { duration, fixed, utc } from '../../model/format';
  import { RUN } from '../../model/night';
  import HoldButton from '../../ui/HoldButton.svelte';
  import LabIcon from '../../ui/LabIcon.svelte';
  import Readouts from '../../ui/Readouts.svelte';

  let confirmStop = $state(false);

  const ageLate = $derived(Number.isFinite(sim.cadence) && sim.lastAge > sim.cadence * 1.5);
  const items = $derived([
    {
      k: 'Last frame',
      v: `${sim.lastAge} s`,
      unit: 'ago',
      note: Number.isFinite(sim.cadence) ? `every ${fixed(sim.cadence, 1)} s (observed)` : '',
      key: true,
      flag: ageLate ? 'late' : undefined,
    },
    {
      k: 'Ends',
      v: Number.isFinite(sim.endsAt) ? utc(sim.endsAt, false) : '—',
      unit: 'UTC',
      note: sim.running ? `in ${duration(sim.endsAt - sim.now)}` : '',
      key: true,
    },
    { k: 'Next autofocus', v: 'off', muted: true },
    { k: 'End of run', v: RUN.endAction.toLowerCase(), muted: true },
  ]);

  const progress = $derived(sim.delivered / RUN.frames);
  const open = $derived(sim.unacked);
  const done = $derived(sim.runState === 'complete' || sim.runState === 'stopped');
  const darksMin = $derived(Number.isFinite(sim.cadence) ? (20 * sim.cadence) / 60 : NaN);
</script>

<div class="run">
  <p class="what">
    <span class="obj">{RUN.object}</span>
    <span class="meta">step 1 of 1 · {RUN.filter} · {fixed(RUN.exposure, 1)} s · gain {RUN.gain}</span>
  </p>

  <div class="frames">
    <span class="count num"><b>{sim.delivered}</b> / {RUN.frames}</span>
    <span class="bar" style:--f={progress} aria-hidden="true"></span>
    <span class="pct num">{Math.round(progress * 100)} %</span>
  </div>

  {#if !done}
    <Readouts {items} cols={2} />
  {/if}

  {#if open.length}
    <ul class="att">
      {#each open as a (a.id)}
        <li class="level-{a.level}">
          <LabIcon name="lab-attention" size={16} />
          <span class="t">{a.rule} · since {utc(a.since, false)}</span>
          {#if a.action}
            <button type="button" class="link" onclick={() => a.action && (a.action.to === 'watch' ? (ws.overlay = 'watch') : ws.setMode(a.action.to))}>{a.action.label}</button>
          {/if}
          <button type="button" class="link" onclick={() => sim.ack(a.id)}>Acknowledge</button>
        </li>
      {/each}
    </ul>
  {/if}

  {#if done}
    <div class="wrap-up">
      <p class="note">
        {sim.runState === 'complete' ? 'Complete' : 'Stopped'} · {sim.delivered} frames · {utc(RUN.start, false)}–{utc(sim.latest?.t ?? sim.now, false)} UTC. Tracking is still on.
      </p>
      <h3 class="lab-caps">Calibration for tonight's lights</h3>
      <div class="cal">
        <Button label="Take 20 darks" onclick={() => ws.toast('Darks: 20 × 10 s, gain 80, Dark slot (one-step sequence)', 'info')} />
        <span class="meta">10 s · gain 80 · about {Math.round(darksMin)} min at tonight's cadence</span>
      </div>
      <div class="cal">
        <Button label="Take 30 biases" onclick={() => ws.toast('Biases: 30 × shortest exposure, gain 80', 'info')} />
        <span class="meta">shortest exposure · gain 80</span>
      </div>
      <div class="actions">
        <HoldButton icon="park" label="Park" question="Park the mount?" consequence="Parking closes the Seestar arm and stops tracking." onconfirm={() => sim.park()} />
        <span class="meta">Session 20260925T200453Z_RR_Lyr · 3.0 GB</span>
      </div>
    </div>
  {:else if confirmStop}
    <div class="confirm" role="group" aria-label="Stop the run?">
      <p><strong>Stop the run?</strong> The {sim.delivered} frames saved so far stay in the session; the frame being exposed is discarded.</p>
      <div class="row">
        <Button label="Keep running" size="s" onclick={() => (confirmStop = false)} />
        <Button
          label="Stop"
          size="s"
          variant="danger"
          onclick={() => {
            confirmStop = false;
            sim.stop();
          }}
        />
      </div>
    </div>
  {:else}
    <div class="actions">
      {#if sim.runState === 'paused' || sim.runState === 'pausing'}
        <IconButton icon="start" label="Resume" showLabel onclick={() => sim.resume()} />
      {:else}
        <IconButton icon="pause" label="Pause" showLabel onclick={() => sim.pause()} tooltipText="Pause at the end of this frame" />
      {/if}
      <IconButton icon="stop" label="Stop…" showLabel variant="danger" onclick={() => (confirmStop = true)} />
      <span class="grow"></span>
      <span class="meta">{sim.runState === 'pausing' ? 'pausing at the end of this frame' : ''}</span>
    </div>
  {/if}
</div>

<style>
  .run {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .what {
    margin: 0;
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
  }
  .obj {
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  .meta {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .frames {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: var(--space-3);
  }
  .count {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-l);
  }
  .count b {
    color: var(--fg);
    font-size: var(--lab-readout-key);
    font-weight: var(--weight-medium);
  }
  .bar {
    position: relative;
    height: 6px;
    border-radius: 1px;
    background: var(--bg-2);
    border: var(--border-w) solid var(--border-soft);
  }
  .bar::before {
    content: '';
    position: absolute;
    inset: 0;
    transform-origin: left;
    transform: scaleX(var(--f));
    /* Neutral, as the chart lab's RunProgress: a run bar is a long fill, and
       brass stays for selection and deliberate actions (lab synthesis). */
    background: var(--fg-muted);
  }
  .pct {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
  .att {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .att li {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-2);
    border: var(--border-w) solid var(--warning);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .att li :global(.icon) {
    color: var(--warning);
  }
  .att li.level-critical {
    border-width: 2px;
    border-color: var(--danger);
  }
  .att .t {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .link {
    height: 22px;
    padding: 0 var(--space-2);
    border: none;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    text-decoration: underline;
    text-decoration-color: var(--border);
    text-underline-offset: 3px;
    cursor: pointer;
  }
  .link:hover {
    background: var(--hover-bg);
  }
  .actions {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .grow {
    flex: 1;
  }
  .confirm {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-3);
    border: var(--border-w) solid var(--danger);
    border-radius: var(--radius-s);
    background: var(--surface);
  }
  .confirm p {
    margin: 0;
    font-size: var(--text-s);
    color: var(--fg);
  }
  .row {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
  }
  .wrap-up {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .note {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
  }
  h3 {
    margin: var(--space-2) 0 0;
  }
  .cal {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
</style>

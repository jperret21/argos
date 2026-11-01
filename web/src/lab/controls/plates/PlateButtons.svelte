<!--
  Plate 01: buttons. The state matrix pins each state with data-force (the
  real hover / press / focus selectors are the same rules), so one
  screenshot shows them all; every control in it is also live.
-->
<script lang="ts">
  import Ctl from '../components/Ctl.svelte';
  import Panel from '../components/Panel.svelte';
  import TipStatic from '../components/TipStatic.svelte';
  import { reduced } from '../env.svelte';
  import { clock } from '../sim.svelte';
  import type { Hardware } from '../types';

  let { hw }: { hw: Hardware } = $props();

  type Col = 'rest' | 'hover' | 'active' | 'focus' | 'toggled' | 'unavailable' | 'busy' | 'error';
  const COLS: { id: Col; label: string }[] = [
    { id: 'rest', label: 'Rest' },
    { id: 'hover', label: 'Hover' },
    { id: 'active', label: 'Pressed' },
    { id: 'focus', label: 'Focus' },
    { id: 'toggled', label: 'Toggled' },
    { id: 'unavailable', label: 'Unavailable' },
    { id: 'busy', label: 'Busy' },
    { id: 'error', label: 'Error' },
  ];

  interface Row {
    id: string;
    name: string;
    use: string;
    icon?: string;
    label: string;
    showLabel: boolean;
    variant: 'ghost' | 'secondary' | 'primary' | 'danger';
    glyphTone?: 'danger';
    toggle: boolean;
    layoutToggle?: boolean;
    reason: string;
    error: string;
  }

  const ROWS: Row[] = [
    { id: 'ghost', name: 'Ghost', use: 'toolbar tool', icon: 'crosshair', label: 'Crosshair', showLabel: false, variant: 'ghost', toggle: true, reason: 'Open an image first', error: 'Overlay failed: no WCS' },
    { id: 'layout', name: 'Ghost layout', use: 'panels, strip', icon: 'panels', label: 'Panels', showLabel: false, variant: 'ghost', toggle: true, layoutToggle: true, reason: 'No panels in this section', error: 'Layout not saved' },
    { id: 'secondary', name: 'Secondary', use: 'hardware, labelled', icon: 'unpark', label: 'Unpark', showLabel: true, variant: 'secondary', toggle: false, reason: 'Connect the mount first', error: 'Unpark: mount did not answer in 10 s' },
    { id: 'toggle', name: 'Instrument toggle', use: 'tracking', icon: 'tracking', label: 'Tracking', showLabel: true, variant: 'secondary', toggle: true, reason: 'Unpark the mount first', error: 'Tracking: driver refused' },
    { id: 'primary', name: 'Primary', use: 'deliberate action', icon: 'goto', label: 'Slew', showLabel: true, variant: 'primary', toggle: false, reason: 'Unpark the mount first', error: 'Mount clock is 2.3 h off' },
    { id: 'danger', name: 'Danger', use: 'stops motion', icon: 'abort', label: 'Abort', showLabel: true, variant: 'danger', toggle: false, reason: 'Nothing is moving', error: 'Abort: no answer, retrying' },
    { id: 'stop', name: 'Routine stop', use: 'live view', icon: 'stop', label: 'Stop', showLabel: true, variant: 'secondary', glyphTone: 'danger', toggle: false, reason: 'Live view is off', error: 'Stop: camera busy' },
    { id: 'text', name: 'Text', use: 'dialog, confirm', label: 'Cancel', showLabel: true, variant: 'secondary', toggle: false, reason: 'Wait for the export', error: 'Could not close' },
  ];

  // Live ring specimens: the real elapsed time of a looping 4 s exposure.
  $effect(() => {
    const exp = hw.exposure;
    exp.seconds = 4;
    exp.start(true);
    const release = clock.use();
    return () => {
      release();
      exp.stop();
    };
  });
  const t = $derived(
    hw.exposure.startedAt === null ? 0 : Math.min(1, (clock.t - hw.exposure.startedAt) / (hw.exposure.seconds * 1000)),
  );
  const sweep = 7 / 14;

  let pressedDemo = $state(false);
  let lastClick = $state('—');
</script>

<div class="grid">
  <div class="left">
  <Panel
    code="A.1"
    title="State matrix"
    note="One component for icon, icon + label and text buttons (merges IconButton and Button). States are pinned here with the very rules hover, press and focus use; every button is also live."
    shot="matrix"
  >
    <div class="matrix" role="table" aria-label="Button states">
      <div class="mrow head" role="row">
        <span class="rh" role="columnheader"></span>
        {#each COLS as c (c.id)}<span class="ch" role="columnheader">{c.label}</span>{/each}
      </div>
      {#each ROWS as r (r.id)}
        <div class="mrow" role="row">
          <span class="rh" role="rowheader"><b>{r.name}</b><small>{r.use}</small></span>
          {#each COLS as c (c.id)}
            <span class="cell" role="cell">
              {#if c.id === 'toggled' && !r.toggle}
                <span class="na">—</span>
              {:else}
                <Ctl
                  icon={r.icon}
                  label={r.label}
                  showLabel={r.showLabel}
                  variant={r.variant}
                  glyphTone={r.glyphTone}
                  layoutToggle={r.layoutToggle}
                  pressed={r.toggle ? c.id === 'toggled' : undefined}
                  disabledReason={c.id === 'unavailable' ? r.reason : null}
                  busy={c.id === 'busy'}
                  error={c.id === 'error' ? r.error : null}
                  data-force={c.id === 'hover' || c.id === 'active' || c.id === 'focus' ? c.id : undefined}
                  size="s"
                />
              {/if}
            </span>
          {/each}
        </div>
      {/each}
    </div>
    <p class="legend">
      <span><b>Pressed</b> sinks by a 1 px black inner edge (no scale, no bounce).</span>
      <span><b>Unavailable</b> stays focusable; a press shows the reason at once.</span>
      <span><b>Busy</b> keeps the width.</span>
      <span><b>Error</b>: last attempt failed; outline + dot, the words in the tip.</span>
    </p>
  </Panel>

  <div class="pair2">
  <Panel code="A.4" title="Icon and label grammar (BRAND 7)" note="Frequent and reversible: icon only, the name and key in the tip. Moves hardware or ends something: icon + label. Dialogs: text." shot="grammar">
    <div class="grammar">
      <div class="g">
        <span class="lab-eyebrow">Frequent tool</span>
        <div class="pair">
          <Ctl icon="stretch-auto" label="Auto stretch" variant="ghost" pressed shortcut="A" data-force="hover" />
          <TipStatic text="Auto stretch" shortcut="A" />
        </div>
      </div>
      <div class="g">
        <span class="lab-eyebrow">Hardware</span>
        <div class="pair">
          <Ctl icon="goto" label="Slew" showLabel variant="primary" />
          <Ctl icon="abort" label="Abort" showLabel variant="danger" shortcut="Escape" />
        </div>
      </div>
      <div class="g">
        <span class="lab-eyebrow">Dialog</span>
        <div class="pair">
          <Ctl label="Cancel" />
          <Ctl label="Park" variant="primary" />
        </div>
      </div>
    </div>
  </Panel>

  <Panel code="A.5" title="Unavailable says why" note="aria-disabled, not disabled: the control keeps its tab stop, its tip states the reason, and a press shows the reason at once instead of doing nothing." shot="reason">
    <div class="reasons">
      <div class="pair">
        <Ctl icon="goto" label="Slew" showLabel variant="primary" disabledReason="Unpark the mount first" />
        <TipStatic text="Slew" reason="Unpark the mount first" />
      </div>
      <div class="pair">
        <Ctl icon="plate-solve" label="Identify field" variant="ghost" disabledReason="Take or open a full-resolution frame" />
        <TipStatic text="Identify field" reason="Take or open a full-resolution frame" />
      </div>
      <div class="pair">
        <Ctl icon="goto" label="Slew" showLabel variant="primary" error="Mount clock is 2.3 h off: correct the Seestar date and time" />
        <TipStatic text="Slew" error="Mount clock is 2.3 h off: correct the Seestar date and time" />
      </div>
    </div>
  </Panel>
  </div>
  </div>
  <div class="col">
    <Panel code="A.2" title="Sizes" note="Hit targets never under 24 px. L is for hardware held at night: hold-to-confirm, jog keys (44 px)." shot="sizes">
      <div class="sizes">
        {#each [{ s: 's', h: 30, i: 16 }, { s: 'm', h: 34, i: 20 }, { s: 'l', h: 40, i: 20 }] as z (z.s)}
          <div class="size">
            <span class="dim" style:height="{z.h}px"><span class="num">{z.h}</span></span>
            <Ctl icon="capture" label="Take one exposure" size={z.s as 's' | 'm' | 'l'} variant="secondary" shortcut="E" />
            <Ctl icon="park" label="Park" showLabel size={z.s as 's' | 'm' | 'l'} />
            <span class="cap-note num">{z.s.toUpperCase()} · icon {z.i}</span>
          </div>
        {/each}
      </div>
    </Panel>

    <Panel
      code="A.3"
      title="The time ring"
      note="One vocabulary: a ring is elapsed time. Track at rest = hold to confirm; arc = exposure, sweep or hold, exact and linear (never eased: it would misstate the time left)."
      shot="ring"
    >
      <div class="rings">
        <figure>
          <Ctl icon="capture" label="Take one exposure" variant="ghost" progress={t} progressText="{(t * 4).toFixed(1)} / 4.0 s" />
          <figcaption>Exposure<br /><span class="num">{(t * 4).toFixed(1)} / 4.0 s</span></figcaption>
        </figure>
        <figure>
          <Ctl icon="live" label="Live view" variant="ghost" pressed progress={t} progressText="frame {(t * 4).toFixed(1)} / 4.0 s" />
          <figcaption>Live frame<br /><span class="num">toggled</span></figcaption>
        </figure>
        <figure>
          <Ctl icon="stop" label="Stop AF" showLabel progress={sweep} progressText="step 7 of 14">
            {#snippet trailing()}7/14{/snippet}
          </Ctl>
          <figcaption>AF sweep<br /><span class="num">7 of 14</span></figcaption>
        </figure>
        <figure>
          <Ctl icon="park" label="Park" showLabel holdRing size="l" />
          <figcaption>Hold to park<br /><span class="num">track only</span></figcaption>
        </figure>
      </div>
      <p class="lab-note">{reduced() ? 'Reduced motion is on: the arcs advance in quarters.' : 'Reduced motion: the arcs advance in quarters; the numbers stay exact.'}</p>
    </Panel>
    <Panel code="A.6" title="Try it" note="Hover waits 500 ms, then neighbours answer at once; Tab shows tips immediately; press the unavailable one." shot="try">
      <div class="try">
        <Ctl icon="zoom-out" label="Zoom out" variant="ghost" shortcut="-" onclick={() => (lastClick = 'Zoom out')} />
        <Ctl icon="zoom-fit" label="Fit the whole frame" variant="ghost" shortcut="F" onclick={() => (lastClick = 'Fit')} />
        <Ctl icon="zoom-in" label="Zoom in" variant="ghost" shortcut="+" onclick={() => (lastClick = 'Zoom in')} />
        <span class="sep"></span>
        <Ctl icon="crosshair" label="Crosshair" variant="ghost" shortcut="X" pressed={pressedDemo} onclick={() => (pressedDemo = !pressedDemo)} />
        <Ctl icon="plate-solve" label="Identify field" variant="ghost" shortcut="S" disabledReason="Take or open a full-resolution frame" />
        <span class="sep"></span>
        <Ctl icon="unpark" label="Unpark" showLabel onclick={() => (lastClick = 'Unpark')} />
        <span class="last num">last: {lastClick}</span>
      </div>
    </Panel>
  </div>
</div>

<style>
  .grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 380px;
    gap: var(--space-4);
    align-items: start;
  }
  .left,
  .col {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    min-width: 0;
  }
  .pair2 {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: var(--space-4);
    align-items: stretch;
  }

  .matrix {
    display: flex;
    flex-direction: column;
  }
  .mrow {
    display: grid;
    grid-template-columns: 132px repeat(8, minmax(0, 1fr));
    align-items: center;
    min-height: 42px;
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .mrow:last-child {
    border-bottom: none;
  }
  .mrow.head {
    min-height: 24px;
  }
  .ch {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-align: center;
    text-transform: uppercase;
  }
  .rh {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .rh b {
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
  }
  .rh small {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .cell {
    display: flex;
    justify-content: center;
    padding: 6px 0;
  }
  .na {
    color: var(--fg-disabled);
    font-family: var(--font-mono);
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-4);
    margin: var(--space-3) 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .legend b {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }

  .sizes {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .size {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .dim {
    position: relative;
    width: 22px;
    border-right: var(--border-w) solid var(--border);
  }
  .dim::before,
  .dim::after {
    content: '';
    position: absolute;
    right: -4px;
    width: 7px;
    height: 1px;
    background: var(--border);
  }
  .dim::before {
    top: 0;
  }
  .dim::after {
    bottom: 0;
  }
  .dim span {
    position: absolute;
    top: 50%;
    right: 6px;
    transform: translateY(-50%);
    color: var(--text-muted);
    font-size: var(--text-2xs);
  }
  .cap-note {
    margin-left: auto;
    color: var(--text-muted);
    font-size: var(--text-2xs);
  }

  .rings {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-2);
    align-items: start;
  }
  figure {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-2);
    margin: 0;
  }
  figcaption {
    color: var(--fg);
    font-size: var(--text-xs);
    line-height: 1.35;
    text-align: center;
  }
  figcaption .num {
    color: var(--text-muted);
    font-size: var(--text-2xs);
  }

  .grammar {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .g {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .pair {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }

  .reasons {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .reasons .pair {
    display: grid;
    grid-template-columns: 112px minmax(0, 1fr);
    justify-items: start;
  }

  .try {
    display: flex;
    align-items: center;
    gap: 2px;
  }
  .sep {
    width: 1px;
    height: 18px;
    margin: 0 6px;
    background: var(--border-soft);
  }
  .last {
    margin-left: auto;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>

<!--
  Mount jog pad (proposal for spec 05 §2.3 C "Jog open", replaces the Qt
  pad and the floating Manual Control dialog).

  Dead-man everywhere: an axis moves only while its key is held. Release,
  sliding off the key, pointer cancel, window blur and a hidden tab stop it
  here; the client renews each moving axis every 250 ms and the server stops
  an axis not renewed within 1 s (spec A10). The meter under the pad shows
  the renewal age, so a link outage is visible before the server acts.
  Two axes tracked separately: Alt + and Az + jog diagonally, releasing
  Alt + stops altitude only (fixes Qt P22). Key words follow the mount's
  geometry (README Q-O4, accepted): Alt + / Alt − / Az − / Az + on an
  alt-az mount (the Seestar), N / S / W / E on an equatorial one. The pressed style follows the axis the
  server reports as moving, not the finger: if the server stopped it, the
  key says so even while it is still held.

  Keyboard: J arms the arrow keys (outlined pad, "armed" word); arrows also
  work whenever a pad key has focus. Key down starts, key up stops, auto
  repeat ignored. Esc stops everything. Rate: Slow / Normal / Fast with the
  value in °/s, manual activation (moving focus does not change the rate).
  The offset plot shows the polled pointing since the reset (5 Hz): data,
  so it jumps with each poll and never glides.
-->
<script lang="ts">
  import { isTypingTarget } from '../../../lib/app/shortcuts';
  import Icon from '../../../lib/components/Icon.svelte';
  import Ctl from '../components/Ctl.svelte';
  import Seg from '../components/Seg.svelte';
  import { fixed, signed } from '../format';
  import { DEADMAN_MS, DIRECTIONS, directionOfKey, JogHolds, RENEW_MS, type Axis, type Direction } from '../jog';
  import { clock, type MountSim } from '../sim.svelte';
  import { tip } from '../tip';

  type Rate = 'slow' | 'normal' | 'fast';

  interface Props {
    sim: MountSim;
    rate?: Rate;
    armed?: boolean;
    /** Why jogging is refused (parked, run active); null when allowed. */
    blockedReason?: string | null;
    /** Specimen: show these directions pressed. */
    pin?: { pressed?: Direction[]; stalled?: Direction[]; armed?: boolean; age?: number | null } | null;
    /** Mount geometry (MountState.alignment): axis words on alt-az, compass letters on EQ (Q-O4). */
    alignment?: 'altaz' | 'eq';
  }

  let { sim, rate = $bindable('normal'), armed = $bindable(false), blockedReason = null, pin = null, alignment = 'altaz' }: Props = $props();

  /** Visible key word and accessible name per direction (README Q-O4). */
  const WORDS: Record<'altaz' | 'eq', Record<Direction, { short: string; label: string }>> = {
    altaz: {
      north: { short: 'Alt+', label: 'Altitude +' },
      south: { short: 'Alt−', label: 'Altitude −' },
      west: { short: 'Az−', label: 'Azimuth −' },
      east: { short: 'Az+', label: 'Azimuth +' },
    },
    eq: {
      north: { short: 'N', label: DIRECTIONS.north.label },
      south: { short: 'S', label: DIRECTIONS.south.label },
      west: { short: 'W', label: DIRECTIONS.west.label },
      east: { short: 'E', label: DIRECTIONS.east.label },
    },
  };
  const words = $derived(WORDS[alignment]);

  const RATES: { value: Rate; label: string; detail: string; deg: number }[] = [
    { value: 'slow', label: 'Slow', detail: '0.5 °/s', deg: 0.5 },
    { value: 'normal', label: 'Normal', detail: '2 °/s', deg: 2 },
    { value: 'fast', label: 'Fast', detail: '5 °/s', deg: 5 },
  ];
  const rateDeg = $derived(RATES.find((r) => r.value === rate)?.deg ?? 2);

  const holds = new JogHolds();
  let version = $state(0);
  let renewTimer: ReturnType<typeof setInterval> | null = null;
  let padEl: HTMLDivElement | undefined = $state();

  const reason = $derived(blockedReason ?? (!sim.connected ? 'Connect the mount first' : sim.parked ? 'Unpark the mount first' : null));
  const showArmed = $derived(pin?.armed ?? armed);
  const moving = $derived(sim.rate.primary !== 0 || sim.rate.secondary !== 0);

  function apply(): void {
    version++;
    for (const axis of ['primary', 'secondary'] as Axis[]) {
      const s = holds.sign(axis);
      if (s === 0) sim.stop(axis);
      else sim.start(axis, s * rateDeg);
    }
    if (!holds.empty && !renewTimer) {
      renewTimer = setInterval(() => {
        for (const axis of ['primary', 'secondary'] as Axis[]) if (holds.sign(axis) !== 0) sim.renew(axis);
      }, RENEW_MS);
    } else if (holds.empty && renewTimer) {
      clearInterval(renewTimer);
      renewTimer = null;
    }
  }

  function stopAll(): void {
    holds.releaseAll();
    apply();
    sim.stopAll();
  }

  // A rate change applies to the axes moving now.
  $effect(() => {
    void rateDeg;
    if (!holds.empty) apply();
  });

  function isPressed(d: Direction): boolean {
    void version;
    if (pin?.pressed) return pin.pressed.includes(d);
    const axis = DIRECTIONS[d].axis;
    return sim.rate[axis] !== 0 && Math.sign(sim.rate[axis]) === DIRECTIONS[d].sign;
  }

  function heldOnly(d: Direction): boolean {
    void version;
    if (pin?.stalled) return pin.stalled.includes(d);
    const axis = DIRECTIONS[d].axis;
    return holds.active(axis) === d && sim.rate[axis] === 0;
  }

  // -- Pointer ------------------------------------------------------------------------

  function down(e: PointerEvent, d: Direction): void {
    if (reason || pin || e.button !== 0) return;
    e.preventDefault(); // no text selection, no focus steal on touch
    (e.currentTarget as HTMLElement).focus();
    holds.press(`pointer:${d}`, d);
    apply();
  }

  function up(d: Direction): void {
    holds.release(`pointer:${d}`);
    apply();
  }

  // -- Keyboard -----------------------------------------------------------------------

  function keyDown(e: KeyboardEvent, fromPad: boolean): void {
    if (e.key === 'Escape' && moving) {
      stopAll();
      return;
    }
    const d = directionOfKey(e.key);
    if (!d || e.metaKey || e.ctrlKey || e.altKey) return;
    if (!fromPad && (!armed || isTypingTarget(e.target))) return;
    e.preventDefault();
    if (e.repeat || reason) return;
    holds.press(`key:${e.key}`, d);
    apply();
  }

  function keyUp(e: KeyboardEvent): void {
    const d = directionOfKey(e.key);
    if (!d) return;
    holds.release(`key:${e.key}`);
    apply();
  }

  $effect(() => {
    if (pin) return; // a pinned specimen never listens to the keyboard
    const onDown = (e: KeyboardEvent) => {
      if (padEl?.contains(e.target as Node)) return; // handled by the pad itself
      if (e.key.toLowerCase() === 'j' && !e.metaKey && !e.ctrlKey && !e.altKey && !isTypingTarget(e.target)) {
        armed = !armed;
        if (!armed) stopAll();
        return;
      }
      keyDown(e, false);
    };
    const onBlur = () => stopAll();
    const onVis = () => {
      if (document.hidden) stopAll();
    };
    window.addEventListener('keydown', onDown);
    window.addEventListener('keyup', keyUp);
    window.addEventListener('blur', onBlur);
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.removeEventListener('keydown', onDown);
      window.removeEventListener('keyup', keyUp);
      window.removeEventListener('blur', onBlur);
      document.removeEventListener('visibilitychange', onVis);
      if (renewTimer) clearInterval(renewTimer);
      sim.stopAll();
    };
  });

  // -- Dead-man meter (renewal age), drawn at display rate only while moving -------------

  $effect(() => {
    if (!moving) return;
    return clock.use();
  });

  const age = $derived.by(() => {
    if (pin && pin.age !== undefined) return pin.age;
    if (!moving) return null;
    const last = Math.max(
      sim.rate.primary !== 0 ? sim.lastRenew.primary : 0,
      sim.rate.secondary !== 0 ? sim.lastRenew.secondary : 0,
    );
    return Math.max(0, clock.t - last);
  });

  // -- Offset plot ----------------------------------------------------------------------

  const SCOPE = 78;
  const RANGE = 2; // degrees at the edge
  const sx = (d: number) => SCOPE / 2 + (Math.max(-RANGE, Math.min(RANGE, d)) / RANGE) * (SCOPE / 2 - 6);
  const sy = (d: number) => SCOPE / 2 - (Math.max(-RANGE, Math.min(RANGE, d)) / RANGE) * (SCOPE / 2 - 6);
  const daz = $derived(sim.az - sim.origin.az);
  const dalt = $derived(sim.alt - sim.origin.alt);

  const KEYS: { d: Direction; icon: string; cell: string }[] = [
    { d: 'north', icon: 'jog-north', cell: 'n' },
    { d: 'west', icon: 'jog-west', cell: 'w' },
    { d: 'east', icon: 'jog-east', cell: 'e' },
    { d: 'south', icon: 'jog-south', cell: 's' },
  ];
</script>

<div class="jog" class:armed={showArmed}>
  <div class="top">
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions (arrow keys jog while a pad key has focus) -->
    <div class="pad" bind:this={padEl} role="group" aria-label="Jog the mount" onkeydown={(e) => keyDown(e, true)} onkeyup={keyUp}>
      {#each KEYS as k (k.d)}
        {@const pressed = isPressed(k.d)}
        <button
          type="button"
          class="key {k.cell}"
          class:stalled={heldOnly(k.d)}
          aria-label="Jog {words[k.d].label}"
          aria-pressed={pressed}
          aria-disabled={reason ? true : undefined}
          aria-keyshortcuts={DIRECTIONS[k.d].key}
          onpointerdown={(e) => down(e, k.d)}
          onpointerup={() => up(k.d)}
          onpointerleave={() => up(k.d)}
          onpointercancel={() => up(k.d)}
          oncontextmenu={(e) => e.preventDefault()}
          use:tip={{ text: `Jog ${words[k.d].label}`, shortcut: showArmed ? DIRECTIONS[k.d].key : undefined, reason, hint: reason ? null : 'Hold to move, release to stop', placement: k.cell === 's' ? 'bottom' : k.cell === 'n' ? 'top' : k.cell === 'w' ? 'left' : 'right' }}
        >
          <Icon name={k.icon} size={20} />
          <span class="letter">{words[k.d].short}</span>
        </button>
      {/each}
      <button
        type="button"
        class="key c stop"
        aria-label="Stop both axes"
        aria-keyshortcuts="Escape"
        onclick={stopAll}
        use:tip={{ text: 'Stop both axes', shortcut: 'Escape' }}
      >
        <Icon name="stop" size={20} />
      </button>
    </div>

    <div class="side">
      <span class="eyebrow">Rate</span>
      <Seg label="Jog rate" options={RATES} bind:value={rate} vertical activation="manual" size="s" />
      <Ctl
        icon="jog-pad"
        label="Arrow keys"
        showLabel
        size="s"
        pressed={showArmed}
        shortcut="J"
        tooltipText={showArmed ? 'Arrow keys jog the mount: J or Esc to disarm' : 'Let the arrow keys jog the mount'}
        disabledReason={reason}
        onclick={() => {
          armed = !armed;
          if (!armed) stopAll();
        }}
      />
    </div>

    <figure class="scope" aria-label="Pointing offset since reset: azimuth {signed(daz, 2)}°, altitude {signed(dalt, 2)}°">
      <svg width={SCOPE} height={SCOPE} viewBox="0 0 {SCOPE} {SCOPE}" aria-hidden="true">
        <circle class="ring" cx={SCOPE / 2} cy={SCOPE / 2} r={(SCOPE / 2 - 6) / 2} />
        <circle class="ring" cx={SCOPE / 2} cy={SCOPE / 2} r={SCOPE / 2 - 6} />
        <line class="axis" x1="6" y1={SCOPE / 2} x2={SCOPE - 6} y2={SCOPE / 2} />
        <line class="axis" x1={SCOPE / 2} y1="6" x2={SCOPE / 2} y2={SCOPE - 6} />
        {#each sim.trail as p, i (i)}
          <circle class="trail" cx={sx(p.daz)} cy={sy(p.dalt)} r="1" />
        {/each}
        <circle class="here" cx={sx(daz)} cy={sy(dalt)} r="3" />
      </svg>
      <figcaption class="num">±{RANGE}°</figcaption>
    </figure>
  </div>

  <div class="telemetry">
    <span class="t"><span class="k">ΔAz</span><span class="num">{signed(daz, 2)}°</span></span>
    <span class="t"><span class="k">ΔAlt</span><span class="num">{signed(dalt, 2)}°</span></span>
    <span class="deadman" class:low={age !== null && age > RENEW_MS * 2}>
      <span class="k">Dead-man</span>
      <span class="meter" aria-hidden="true"><span style:width="{age === null ? 0 : Math.max(0, 1 - age / DEADMAN_MS) * 100}%"></span></span>
      <span class="num">{age === null ? 'idle' : `${fixed(age / 1000, 2)} s`}</span>
    </span>
    <button type="button" class="reset" onclick={() => sim.resetTrail()} use:tip={{ text: 'Reset the offset to zero' }}>
      <Icon name="layout-reset" size={14} />
    </button>
  </div>

  <p class="status" aria-live="polite">
    {#if reason}
      <span class="reason">{reason}</span>
    {:else if sim.deadmanStop}
      <span class="bad">{sim.deadmanStop}. Release and press again.</span>
    {:else if moving}
      <span>Moving · release to stop</span>
    {:else if showArmed}
      <span><b>Armed</b> · arrows jog · <kbd class="cap">J</kbd> or <kbd class="cap">Esc</kbd> disarms</span>
    {:else}
      <span class="muted">Hold a key to move, release to stop · <kbd class="cap">J</kbd> arms the arrows</span>
    {/if}
  </p>
</div>

<style>
  .jog {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .top {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
  }

  .pad {
    display: grid;
    flex: none;
    grid-template-columns: repeat(3, var(--lab-jog-key));
    grid-template-rows: repeat(3, var(--lab-jog-key));
    gap: 4px;
    padding: 6px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    background: var(--bg-2);
    transition:
      border-color var(--duration-fast) var(--ease-standard),
      background-color var(--duration-fast) var(--ease-standard);
  }
  /* Armed: a brass edge (and the word below), never a brass area (BRAND 3). */
  .armed .pad {
    border-color: var(--accent);
    box-shadow: inset 0 0 0 1px var(--accent);
  }
  .n {
    grid-area: 1 / 2;
  }
  .w {
    grid-area: 2 / 1;
  }
  .c {
    grid-area: 2 / 2;
  }
  .e {
    grid-area: 2 / 3;
  }
  .s {
    grid-area: 3 / 2;
  }

  .key {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0;
    width: var(--lab-jog-key);
    height: var(--lab-jog-key);
    margin: 0;
    padding: 0;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg);
    color: var(--fg);
    cursor: pointer;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
    -webkit-touch-callout: none;
    transition:
      background-color var(--duration-instant) var(--ease-standard),
      border-color var(--duration-fast) var(--ease-standard),
      color var(--duration-fast) var(--ease-standard);
  }
  .letter {
    position: absolute;
    bottom: 2px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 9px;
    line-height: 1;
  }
  .key:hover:not([aria-disabled='true']) {
    background: var(--hover-bg);
  }
  .key:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
    z-index: 1;
  }
  /* Moving (as reported by the server): sunk, brass glyph and edge. */
  .key[aria-pressed='true'] {
    border-color: var(--toggled-border);
    background: var(--pressed-bg);
    box-shadow: var(--lab-pressed-inset);
    color: var(--toggled-fg);
  }
  .key[aria-pressed='true'] .letter {
    color: var(--toggled-fg);
  }
  /* Held but stopped by the server: sunk, no brass, dashed edge. */
  .key.stalled {
    border-style: dashed;
    border-color: var(--fg-muted);
    background: var(--pressed-bg);
    color: var(--fg-muted);
  }
  .key[aria-disabled='true'] {
    border-color: var(--border-soft);
    background: transparent;
    color: var(--fg-disabled);
    cursor: not-allowed;
  }
  .key[aria-disabled='true'] .letter {
    color: var(--fg-disabled);
  }
  .stop {
    color: var(--danger);
  }
  .stop:hover {
    border-color: var(--danger);
  }

  .side {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
  }
  .eyebrow,
  .k {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }

  .scope {
    position: relative;
    flex: none;
    margin: 0 0 0 auto;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .scope svg {
    display: block;
  }
  .scope figcaption {
    position: absolute;
    right: 4px;
    bottom: 2px;
    color: var(--text-muted);
    font-size: 9px;
  }
  .ring {
    fill: none;
    stroke: var(--border-soft);
    stroke-width: 1;
  }
  .axis {
    stroke: var(--border);
    stroke-width: 1;
  }
  .trail {
    fill: var(--fg-muted);
  }
  .here {
    fill: var(--fg);
    stroke: var(--bg-2);
    stroke-width: 1.5;
  }

  .telemetry {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-height: 24px;
  }
  .t {
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-1);
    min-width: 82px;
    font-size: var(--text-s);
    white-space: nowrap;
  }
  .k {
    font-family: var(--font-ui);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    letter-spacing: 0;
    text-transform: none;
  }
  .deadman {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    margin-left: auto;
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .meter {
    position: relative;
    width: 44px;
    height: 4px;
    border-radius: 1px;
    background: var(--bg-2);
    box-shadow: inset 0 0 0 1px var(--border-soft);
    overflow: hidden;
  }
  .meter span {
    position: absolute;
    inset: 0 auto 0 0;
    background: var(--fg-muted);
  }
  .deadman.low .meter span {
    background: var(--warning);
  }
  .deadman .num {
    min-width: 40px;
    color: var(--fg);
  }
  .reset {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border: none;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg-muted);
    cursor: pointer;
  }
  .reset:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .reset:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }

  .status {
    display: flex;
    align-items: center;
    min-height: 18px;
    margin: -4px 0 0;
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .status .muted,
  .status .reason {
    color: var(--text-muted);
  }
  .status b {
    font-weight: var(--weight-semibold);
  }
  .status :global(kbd.cap) {
    height: 14px;
    margin: 0 2px;
  }
  .reason::before,
  .bad::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-right: 6px;
    border-radius: var(--radius-round);
    vertical-align: 1px;
  }
  .reason::before {
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
  }
  .bad::before {
    background: var(--danger);
  }
</style>

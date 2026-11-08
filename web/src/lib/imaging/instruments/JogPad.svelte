<!--
  Mount jog pad (spec 05 §2.3 C "Jog open"; replaces the Qt pad and the
  floating Manual Control dialog). Promoted from src/lab/controls/
  instruments/JogPad.svelte (web/lab/PROPOSAL.md 3.3 "Jog pad", 6, W3) onto
  the server's jog (protocol.md A29-A30); the rules are jog.ts (JogDriver).

  Dead-man everywhere: an axis moves only while its key is held. Key up,
  pointer up or sliding off the key, window blur, a hidden tab, losing the
  event socket, disarming and unmounting stop it here; each moving axis is
  renewed every 250 ms and the server stops an axis not renewed within 1 s,
  or when this client's socket closes. The meter under the pad shows the
  renewal age, so a link outage is visible before the server acts.
  Two axes tracked separately (H3): Alt+ and Az+ held together jog
  diagonally; releasing Alt+ stops altitude only.
  Key words from the mount's geometry (MountState.alignment, Q-O4): Alt+ /
  Alt− / Az− / Az+ on an alt-az mount (the Seestar), N / S / W / E on an
  equatorial one.
  The pressed style (sunk, --toggled-fg glyph) follows the axis the SERVER
  reports as moving, not the finger; a key held while the server stopped its
  axis is dashed ("stalled": release and press again).
  Keyboard: J (the registry's observe.jog-arm; `armKey` lets the pad listen
  itself) arms the arrow keys (one brass edge on the pad and the word
  "Armed"; the "Arrow keys" toggle stays neutral, PROPOSAL 3.3); arrows also work whenever a pad key has focus. Key down starts,
  key up stops, auto-repeat ignored; arrows a focused control used itself
  (default prevented: a toolbar, a segmented, a number field) never jog.
  Esc stops both axes (and still reaches the registry: abort, D21). Rate:
  Slow / Normal / Fast with the value in °/s, manual activation.
  The offset scope shows the polled pointing since its reset: data, it
  jumps with each poll and never glides.
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { isTypingTarget } from '../../app/shortcuts';
  import Control from '../../components/Control.svelte';
  import Icon from '../../components/Icon.svelte';
  import Segmented from '../../components/Segmented.svelte';
  import { tooltip } from '../../components/tooltip';
  import { fixed, signed } from '../../format/number';
  import {
    DEADMAN_MS,
    DIRECTIONS,
    directionOfKey,
    JOG_RATES,
    JogDriver,
    keyWords,
    rateDeg,
    RENEW_MS,
    reportedMoving,
    type Direction,
    type JogRate,
    type JogTransport,
    type StopReason,
  } from './jog';
  import type { MountAlignment, MountJogView } from './types';
  import { formatDeltaDec, formatDeltaRA, isEquatorial, scopeRange } from './jog';

  interface Props {
    alignment?: MountAlignment;
    /** MountState.jog: what the server commands now. */
    report?: MountJogView | null;
    /** The REST and socket calls; null: an inert specimen. */
    transport?: JogTransport | null;
    /** The event socket is up (its loss stops every axis here too). */
    linked?: boolean;
    /** Why jogging is refused now (not connected, parked, a slew or a run in progress). */
    blockedReason?: string | null;
    /** Polled pointing for the offset scope (RA / Dec on an equatorial mount). */
    pointing?: { alt_deg: number | null; az_deg: number | null; ra_hours?: number | null; dec_deg?: number | null } | null;
    rate?: JogRate;
    armed?: boolean;
    /** Listen to J here (gallery); in the app the registry's observe.jog-arm toggles `armed`. */
    armKey?: boolean;
    /** Gallery: freeze pressed, stalled, armed and the renewal age. */
    pin?: { pressed?: Direction[]; stalled?: Direction[]; held?: Direction[]; armed?: boolean; age?: number | null; message?: string } | null;
  }

  let {
    alignment = 'altaz',
    report = null,
    transport = null,
    linked = true,
    blockedReason = null,
    pointing = null,
    rate = $bindable('normal'),
    armed = $bindable(false),
    armKey = false,
    pin = null,
  }: Props = $props();

  const words = $derived(keyWords(alignment));
  const rateOptions = JOG_RATES.map((r) => ({ value: r.value, label: r.label, detail: `${r.deg}°/s` }));

  let version = $state(0);
  const inert: JogTransport = { start: () => Promise.resolve(), stop: () => Promise.resolve() };
  let padSeq = 0;
  const driver = new JogDriver(
    {
      start: (a, r, s, renew) => (transport ?? inert).start(a, r, s, renew),
      stop: (a, s) => (transport ?? inert).stop(a, s),
      socketStop: () => transport?.socketStop?.(),
      // The page-wide counter when the app gives one (a remount never goes back to 0).
      nextSeq: () => (transport?.nextSeq ? transport.nextSeq() : ++padSeq),
    },
    () => version++,
  );

  let padEl: HTMLDivElement | undefined = $state();
  const reason = $derived(blockedReason ?? (linked ? null : 'No link to the ARGOS server'));
  const showArmed = $derived(pin?.armed ?? armed);

  const moving = $derived.by(() => {
    void version;
    return driver.moving;
  });

  function stopAll(why: StopReason): void {
    driver.stopAll(why);
  }

  // Rate: applies to the axes moving now.
  $effect(() => {
    const deg = rateDeg(rate, report?.max_rate_deg_s);
    untrack(() => driver.setRate(deg));
  });

  // The server's report: a stop it made itself stalls the held axis.
  $effect(() => {
    const r = report;
    untrack(() => driver.observe(r));
  });

  // Refused now (parked, slewing, link lost): stop everything here too.
  $effect(() => {
    const why = reason;
    if (why) untrack(() => driver.moving && stopAll(linked ? 'blocked' : 'socket'));
  });

  $effect(() => () => driver.dispose());

  function isPressed(d: Direction): boolean {
    void version;
    if (pin?.pressed) return pin.pressed.includes(d);
    if (report) return reportedMoving(report, d);
    const { axis, sign } = DIRECTIONS[d];
    return driver.sent[axis] !== 0 && Math.sign(driver.sent[axis]) === sign;
  }

  function isStalled(d: Direction): boolean {
    void version;
    if (pin?.stalled) return pin.stalled.includes(d);
    const { axis, sign } = DIRECTIONS[d];
    return driver.stalled[axis] !== 0 && Math.sign(driver.stalled[axis]) === sign && driver.holds.active(axis) === d;
  }

  /** Held here, not yet confirmed by the server's report (a sunk key, no brass). */
  function isHeld(d: Direction): boolean {
    void version;
    if (pin?.held) return pin.held.includes(d);
    if (pin) return false;
    return driver.holds.active(DIRECTIONS[d].axis) === d && !isPressed(d) && !isStalled(d);
  }

  // -- Pointer ------------------------------------------------------------------------------

  function down(e: PointerEvent, d: Direction): void {
    if (reason || pin || e.button !== 0) return;
    e.preventDefault(); // no text selection, no focus steal on touch
    (e.currentTarget as HTMLElement).focus();
    driver.press(`pointer:${d}`, d);
  }

  function up(d: Direction): void {
    driver.release(`pointer:${d}`);
  }

  // -- Keyboard -----------------------------------------------------------------------------

  function keyDown(e: KeyboardEvent, fromPad: boolean): void {
    if (e.key === 'Escape') {
      if (driver.moving) stopAll('escape'); // not swallowed: the registry still aborts a slew
      return;
    }
    if (e.key === 'Meta' || e.metaKey) {
      // macOS: no keyup reaches the page for an arrow released while Cmd is down.
      driver.releaseKeys();
      return;
    }
    const d = directionOfKey(e.key);
    if (!d || e.ctrlKey || e.altKey) return;
    if (!fromPad && (!armed || e.defaultPrevented || isTypingTarget(e.target))) return;
    e.preventDefault();
    if (e.repeat || reason || pin) return;
    driver.press(`key:${e.key}`, d);
  }

  function keyUp(e: KeyboardEvent): void {
    if (e.key === 'Meta') driver.releaseKeys();
    else if (directionOfKey(e.key)) driver.release(`key:${e.key}`);
  }

  function toggleArm(): void {
    armed = !armed;
    if (!armed) stopAll('disarm');
  }

  $effect(() => {
    if (pin) return; // a pinned specimen never listens
    const onDown = (e: KeyboardEvent) => {
      if (padEl?.contains(e.target as Node)) return; // the pad handles its own keys
      if (armKey && e.key.toLowerCase() === 'j' && !e.metaKey && !e.ctrlKey && !e.altKey && !e.defaultPrevented && !isTypingTarget(e.target)) {
        toggleArm();
        return;
      }
      keyDown(e, false);
    };
    const onUp = (e: KeyboardEvent) => {
      if (padEl?.contains(e.target as Node)) return;
      keyUp(e);
    };
    const onBlur = () => stopAll('blur');
    const onVis = () => {
      if (document.hidden) stopAll('hidden');
    };
    window.addEventListener('keydown', onDown);
    window.addEventListener('keyup', onUp);
    window.addEventListener('blur', onBlur);
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.removeEventListener('keydown', onDown);
      window.removeEventListener('keyup', onUp);
      window.removeEventListener('blur', onBlur);
      document.removeEventListener('visibilitychange', onVis);
    };
  });

  // -- Dead-man meter: the renewal age, drawn at display rate only while moving --------------

  let now = $state(0);
  $effect(() => {
    if (!moving) return;
    let raf = 0;
    const tick = (t: number) => {
      now = t;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  });
  const age = $derived.by(() => {
    if (pin && pin.age !== undefined) return pin.age;
    void version;
    return moving ? driver.renewalAge(now || undefined) : null;
  });
  const deadman = $derived((report?.deadman_s ?? DEADMAN_MS / 1000) * 1000);

  // -- Offset scope: polled pointing since the reset -----------------------------------------

  const SCOPE = 78;
  // The scope and the readout follow the key words' frame: RA / Dec on an equatorial
  // mount, Az / Alt otherwise (design review of wave 3). x, y in degrees on the sky.
  const eq = $derived(isEquatorial(alignment) && pointing?.ra_hours != null && pointing?.dec_deg != null);
  type Here = { x: number; y: number; d1: number; d2: number };
  let origin: { a: number; b: number; eq: boolean } | null = $state(null);
  let trail: { x: number; y: number }[] = $state([]);
  const wrap = (d: number) => ((((d + 180) % 360) + 360) % 360) - 180;
  const wrapH = (h: number) => ((((h + 12) % 24) + 24) % 24) - 12;
  function read(): { a: number; b: number; eq: boolean } | null {
    const p = pointing;
    if (!p) return null;
    if (eq) return { a: p.ra_hours!, b: p.dec_deg!, eq: true };
    if (p.alt_deg === null || p.az_deg === null) return null;
    return { a: p.az_deg, b: p.alt_deg, eq: false };
  }
  function offset(now: { a: number; b: number; eq: boolean }, o: { a: number; b: number }): Here {
    if (now.eq) {
      const dra = wrapH(now.a - o.a); // hours
      const ddec = now.b - o.b;
      // RA grows to the east: E on the right, as the pad's key (not the sky's east-left view).
      return { x: dra * 15 * Math.cos((now.b * Math.PI) / 180), y: ddec, d1: dra, d2: ddec };
    }
    const daz = wrap(now.a - o.a);
    const dalt = now.b - o.b;
    return { x: daz, y: dalt, d1: daz, d2: dalt };
  }
  const here = $derived.by((): Here | null => {
    const now = read();
    if (!now || !origin || origin.eq !== now.eq) return null;
    return offset(now, origin);
  });
  $effect(() => {
    const now = read();
    if (!now) return;
    untrack(() => {
      if (!origin || origin.eq !== now.eq) {
        origin = now;
        trail = [];
      } else {
        const pt = offset(now, origin);
        const last = trail[trail.length - 1];
        if (!last || last.x !== pt.x || last.y !== pt.y) trail = [...trail.slice(-79), { x: pt.x, y: pt.y }];
      }
    });
  });
  function resetScope(): void {
    origin = read();
    trail = [];
  }
  // The scale grows so the dot is never pinned on the rim (±2°, ±10°, ±45°, ±180°).
  const RANGE = $derived.by(() => {
    let m = here ? Math.max(Math.abs(here.x), Math.abs(here.y)) : 0;
    for (const p of trail) m = Math.max(m, Math.abs(p.x), Math.abs(p.y));
    return scopeRange(m);
  });
  const sx = (d: number) => SCOPE / 2 + (Math.max(-RANGE, Math.min(RANGE, d)) / RANGE) * (SCOPE / 2 - 6);
  const sy = (d: number) => SCOPE / 2 - (Math.max(-RANGE, Math.min(RANGE, d)) / RANGE) * (SCOPE / 2 - 6);
  const d1Text = $derived(here ? (eq ? formatDeltaRA(here.d1) : `${signed(here.d1, 2)}°`) : '—');
  const d2Text = $derived(here ? (eq ? formatDeltaDec(here.d2) : `${signed(here.d2, 2)}°`) : '—');

  const KEYS: { d: Direction; icon: string; cell: string; place: 'top' | 'bottom' | 'left' | 'right' }[] = [
    { d: 'north', icon: 'jog-north', cell: 'n', place: 'top' },
    { d: 'west', icon: 'jog-west', cell: 'w', place: 'left' },
    { d: 'east', icon: 'jog-east', cell: 'e', place: 'right' },
    { d: 'south', icon: 'jog-south', cell: 's', place: 'bottom' },
  ];

  const status = $derived.by((): { kind: 'reason' | 'bad' | 'plain' | 'armed' | 'muted'; text: string } => {
    void version;
    if (pin?.message) return { kind: 'bad', text: pin.message };
    if (reason) return { kind: 'reason', text: reason };
    if (driver.message) return { kind: driver.messageKind === 'error' ? 'bad' : 'reason', text: driver.message };
    if (report?.stop_pending?.length) {
      return { kind: 'bad', text: `The server is retrying a failed stop (${report.stop_pending.join(', ')} axis): use Abort if the mount still moves` };
    }
    if (moving || (pin?.pressed?.length ?? 0) > 0) return { kind: 'plain', text: 'Moving · release to stop' };
    if (showArmed) return { kind: 'armed', text: '' };
    return { kind: 'muted', text: '' };
  });
</script>

<div class="jog" class:armed={showArmed}>
  <div class="top">
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions (arrow keys jog while a pad key has focus) -->
    <div class="pad" bind:this={padEl} role="group" aria-label="Jog the mount" onkeydown={(e) => keyDown(e, true)} onkeyup={keyUp}>
      {#each KEYS as k (k.d)}
        <button
          type="button"
          class="key {k.cell}"
          class:stalled={isStalled(k.d)}
          class:held={isHeld(k.d)}
          aria-label="Jog {words[k.d].label}"
          aria-pressed={isPressed(k.d)}
          aria-disabled={reason ? true : undefined}
          aria-keyshortcuts={DIRECTIONS[k.d].key}
          onpointerdown={(e) => down(e, k.d)}
          onpointerup={() => up(k.d)}
          onpointerleave={() => up(k.d)}
          onpointercancel={() => up(k.d)}
          oncontextmenu={(e) => e.preventDefault()}
          use:tooltip={{
            text: `Jog ${words[k.d].label}`,
            shortcut: showArmed && !reason ? DIRECTIONS[k.d].key : undefined,
            reason,
            hint: reason ? null : 'Hold to move, release to stop',
            placement: k.place,
          }}
        >
          <Icon name={k.icon} size={20} />
          <span class="word">{words[k.d].short}</span>
        </button>
      {/each}
      <button
        type="button"
        class="key c stop"
        aria-label="Stop both axes"
        aria-keyshortcuts="Escape"
        onclick={() => stopAll('button')}
        use:tooltip={{ text: 'Stop both axes', shortcut: 'Escape' }}
      >
        <Icon name="stop" size={20} />
      </button>
    </div>

    <div class="side">
      <span class="eyebrow" aria-hidden="true">Rate</span>
      <Segmented label="Jog rate" options={rateOptions} bind:value={rate} vertical activation="manual" size="s" />
      <Control
        icon="jog-pad"
        label="Arrow keys"
        showLabel
        size="s"
        pressed={showArmed}
        layoutToggle
        shortcut="J"
        tooltipText={showArmed ? 'Arrow keys jog the mount: J to disarm' : 'Let the arrow keys jog the mount'}
        disabledReason={reason && !showArmed ? reason : null}
        onclick={toggleArm}
      />
    </div>

    <figure
      class="scope"
      aria-label={here ? `Pointing offset since reset: ${eq ? 'right ascension' : 'azimuth'} ${d1Text}, ${eq ? 'declination' : 'altitude'} ${d2Text}` : 'Pointing offset: no position yet'}
    >
      <svg width={SCOPE} height={SCOPE} viewBox="0 0 {SCOPE} {SCOPE}" aria-hidden="true">
        <circle class="ring" cx={SCOPE / 2} cy={SCOPE / 2} r={(SCOPE / 2 - 6) / 2} />
        <circle class="ring" cx={SCOPE / 2} cy={SCOPE / 2} r={SCOPE / 2 - 6} />
        <line class="axis" x1="6" y1={SCOPE / 2} x2={SCOPE - 6} y2={SCOPE / 2} />
        <line class="axis" x1={SCOPE / 2} y1="6" x2={SCOPE / 2} y2={SCOPE - 6} />
        {#each trail as p, i (i)}
          <circle class="trail" cx={sx(p.x)} cy={sy(p.y)} r="1" />
        {/each}
        {#if here}<circle class="here" cx={sx(here.x)} cy={sy(here.y)} r="3" />{/if}
      </svg>
      <figcaption class="num">±{RANGE}°</figcaption>
    </figure>
  </div>

  <div class="telemetry">
    <span class="t"><span class="k">{eq ? 'ΔRA' : 'ΔAz'}</span><span class="num">{d1Text}</span></span>
    <span class="t"><span class="k">{eq ? 'ΔDec' : 'ΔAlt'}</span><span class="num">{d2Text}</span></span>
    <span
      class="deadman"
      class:low={age !== null && age > RENEW_MS * 2}
      use:tooltip={{ text: 'Dead-man: time since the server last confirmed a renewal', hint: `It stops an axis left ${fixed(deadman / 1000, 1)} s without one` }}
    >
      <span class="k">Dead-man</span>
      <span class="meter" aria-hidden="true"><span style:width="{age === null ? 0 : Math.max(0, 1 - age / deadman) * 100}%"></span></span>
      <span class="num">{age === null ? 'idle' : `${fixed(age / 1000, 2)} s`}</span>
    </span>
    <button type="button" class="reset" aria-label="Reset the offset to zero" onclick={resetScope} use:tooltip={{ text: 'Reset the offset to zero' }}>
      <Icon name="layout-reset" size={14} />
    </button>
  </div>

  <p class="status kind-{status.kind}" aria-live="polite">
    {#if status.kind === 'armed'}
      <span><b>Armed</b> · arrows jog · <kbd class="cap">J</kbd> disarms · <kbd class="cap">Esc</kbd> stops</span>
    {:else if status.kind === 'muted'}
      <span>Hold a key to move, release to stop · <kbd class="cap">J</kbd> arms the arrows</span>
    {:else}
      <span>{status.text}</span>
    {/if}
  </p>
</div>

<style>
  .jog {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-width: 0;
  }
  .top {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
  }

  .pad {
    display: grid;
    flex: none;
    grid-template-columns: repeat(3, var(--jog-key));
    grid-template-rows: repeat(3, var(--jog-key));
    gap: 4px;
    padding: 6px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    background: var(--bg-2);
    transition:
      border-color var(--duration-fast) var(--ease-standard),
      box-shadow var(--duration-fast) var(--ease-standard);
  }
  /* Armed: one brass edge (and the word below), never a brass area (BRAND 3). */
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
    width: var(--jog-key);
    height: var(--jog-key);
    margin: 0;
    padding: 0 0 8px;
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
  .key.c {
    padding: 0;
  }
  .word {
    position: absolute;
    bottom: 3px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    line-height: 1;
  }
  .key:hover:not([aria-disabled='true']) {
    background: var(--hover-bg);
  }
  .key:active:not([aria-disabled='true']),
  .key.held {
    background: var(--pressed-bg);
    box-shadow: var(--pressed-inset);
  }
  /* Held here, the server not yet reporting the axis: sunk with a neutral edge (no brass until it moves). */
  .key.held {
    border-color: var(--fg-muted);
  }
  .key:focus-visible {
    z-index: 1;
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  /* Moving, as the server reports it: sunk, the toggled glyph and edge. */
  .key[aria-pressed='true'] {
    border-color: var(--toggled-border);
    background: var(--pressed-bg);
    box-shadow: var(--pressed-inset);
    color: var(--toggled-fg);
  }
  .key[aria-pressed='true'] .word {
    color: var(--toggled-fg);
  }
  /* Held, but the server stopped the axis: sunk, no brass, dashed edge. */
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
  .key[aria-disabled='true'] .word {
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
  .eyebrow {
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
    font-size: var(--text-2xs);
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
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .t {
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-1);
    min-width: 76px;
    font-size: var(--text-s);
    white-space: nowrap;
  }
  .k {
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
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
    margin: calc(-1 * var(--space-1)) 0 0;
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .kind-muted,
  .kind-reason {
    color: var(--text-muted);
  }
  .status b {
    font-weight: var(--weight-semibold);
  }
  .cap {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 14px;
    height: 14px;
    margin: 0 2px;
    padding: 0 3px;
    border: var(--border-w) solid var(--border);
    border-bottom-width: 2px;
    border-radius: var(--radius-s);
    background: var(--surface);
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    line-height: 1;
  }
  .kind-reason::before,
  .kind-bad::before {
    content: '';
    display: inline-block;
    flex: none;
    width: 6px;
    height: 6px;
    margin-right: 6px;
    border-radius: var(--radius-round);
  }
  .kind-reason::before {
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
  }
  .kind-bad::before {
    background: var(--danger);
  }
</style>

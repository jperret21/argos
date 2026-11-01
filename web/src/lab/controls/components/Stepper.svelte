<!--
  Stepper (proposal): − value + for small integer quantities (gain, frame
  count, binning factor, a sequence repeat). The value in the middle is a
  text field (type, arrows with Shift x10).

  Hold − or + to repeat: one step at once, then after 400 ms a step every
  80 ms, and x10 after 1.6 s of repeating ("x10" shows while it does).
  Nothing is sent while the button is held: one value goes 400 ms after the
  release (device values are never sent per step, README 3.4).
  At a limit the button is unavailable and says which limit ("Driver
  maximum 600").
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';
  import { tip } from '../tip';
  import { clamp, REPEAT, repeatFactor } from '../values';

  interface Props {
    label: string;
    value: number;
    min: number;
    max: number;
    step?: number;
    unit?: string;
    /** Who sets the limits ("driver"), for the reasons. */
    limitSource?: string;
    oncommit?: (v: number) => Promise<void> | void;
    disabledReason?: string | null;
    pin?: { accelerating?: boolean; pressed?: 'minus' | 'plus' } | null;
  }

  let {
    label,
    value = $bindable(),
    min,
    max,
    step = 1,
    unit,
    limitSource = 'driver',
    oncommit,
    disabledReason = null,
    pin = null,
  }: Props = $props();

  const id = `st-${Math.random().toString(36).slice(2, 9)}`;
  let draft: number | null = $state(null);
  let editing = $state(false);
  let text = $state('');
  let held: 'minus' | 'plus' | null = $state(null);
  let accelerating = $state(false);
  let sending = $state(false);

  const current = $derived(draft ?? value);
  const atMin = $derived(current <= min);
  const atMax = $derived(current >= max);
  const minusReason = $derived(disabledReason ?? (atMin ? `${cap(limitSource)} minimum ${min}` : null));
  const plusReason = $derived(disabledReason ?? (atMax ? `${cap(limitSource)} maximum ${max}` : null));
  const showAccel = $derived(pin?.accelerating ?? accelerating);
  const showHeld = $derived(pin?.pressed ?? held);

  function cap(s: string): string {
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  let delayTimer: ReturnType<typeof setTimeout> | null = null;
  let intervalTimer: ReturnType<typeof setInterval> | null = null;
  let sendTimer: ReturnType<typeof setTimeout> | null = null;
  let t0 = 0;

  function bump(dir: 1 | -1, factor: number): void {
    const next = clamp(Math.round((current + dir * step * factor) / step) * step, min, max);
    draft = next;
    text = String(next);
  }

  function scheduleSend(): void {
    if (sendTimer) clearTimeout(sendTimer);
    sendTimer = setTimeout(async () => {
      if (draft === null || draft === value) {
        draft = null;
        return;
      }
      const v = draft;
      sending = true;
      try {
        await oncommit?.(v);
        value = v;
      } finally {
        sending = false;
        draft = null;
      }
    }, 400);
  }

  function stopRepeat(): void {
    if (delayTimer) clearTimeout(delayTimer);
    if (intervalTimer) clearInterval(intervalTimer);
    delayTimer = intervalTimer = null;
    if (held) scheduleSend();
    held = null;
    accelerating = false;
  }

  function press(e: PointerEvent, dir: 1 | -1): void {
    const reason = dir > 0 ? plusReason : minusReason;
    if (reason || e.button !== 0 || pin) return;
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    if (sendTimer) clearTimeout(sendTimer);
    held = dir > 0 ? 'plus' : 'minus';
    t0 = performance.now();
    bump(dir, 1);
    delayTimer = setTimeout(() => {
      intervalTimer = setInterval(() => {
        const f = repeatFactor(performance.now() - t0);
        accelerating = f > 1;
        bump(dir, f);
        if ((dir > 0 && current >= max) || (dir < 0 && current <= min)) stopRepeat();
      }, REPEAT.interval);
    }, REPEAT.delay);
  }

  /** Keyboard activation (Enter / Space): one step; the key's own repeat repeats. */
  function keyClick(e: MouseEvent, dir: 1 | -1): void {
    if (e.detail !== 0) return; // pointer clicks are handled on press
    if (dir > 0 ? plusReason : minusReason) return;
    bump(dir, 1);
    scheduleSend();
  }

  function onKey(e: KeyboardEvent): void {
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      bump(e.key === 'ArrowUp' ? 1 : -1, e.shiftKey ? 10 : 1);
      scheduleSend();
    } else if (e.key === 'Enter') {
      const v = Number(text);
      if (Number.isFinite(v) && v >= min && v <= max) {
        draft = Math.round(v / step) * step;
        scheduleSend();
      }
    } else if (e.key === 'Escape') {
      draft = null;
      text = String(value);
    }
  }

  $effect(() => () => {
    stopRepeat();
    if (sendTimer) clearTimeout(sendTimer);
  });
</script>

<div class="stepper" class:inert={!!disabledReason}>
  <div class="head">
    <label for={id}>{label}</label>
    {#if showAccel}<span class="accel num">×10</span>{/if}
  </div>
  <div class="row" class:dirty={draft !== null && draft !== value}>
    <button
      type="button"
      class="side"
      class:held={showHeld === 'minus'}
      class:inert={!!minusReason}
      aria-label="Decrease {label.toLowerCase()}"
      aria-disabled={minusReason ? true : undefined}
      aria-controls={id}
      onpointerdown={(e) => press(e, -1)}
      onpointerup={stopRepeat}
      onpointercancel={stopRepeat}
      onlostpointercapture={stopRepeat}
      onclick={(e) => keyClick(e, -1)}
      use:tip={{ text: `Decrease ${label.toLowerCase()}`, reason: minusReason, hint: minusReason ? null : 'Hold to repeat' }}
    >
      <Icon name="remove" size={16} />
    </button>
    <div class="mid">
      <input
        {id}
        type="text"
        inputmode="numeric"
        autocomplete="off"
        spellcheck="false"
        value={editing ? text : String(current)}
        readonly={!!disabledReason}
        aria-disabled={disabledReason ? true : undefined}
        aria-busy={sending || undefined}
        onfocus={() => {
          editing = true;
          text = String(current);
        }}
        onblur={() => (editing = false)}
        oninput={(e) => (text = e.currentTarget.value)}
        onkeydown={onKey}
      />
      {#if unit}<span class="unit">{unit}</span>{/if}
    </div>
    <button
      type="button"
      class="side"
      class:held={showHeld === 'plus'}
      class:inert={!!plusReason}
      aria-label="Increase {label.toLowerCase()}"
      aria-disabled={plusReason ? true : undefined}
      aria-controls={id}
      onpointerdown={(e) => press(e, 1)}
      onpointerup={stopRepeat}
      onpointercancel={stopRepeat}
      onlostpointercapture={stopRepeat}
      onclick={(e) => keyClick(e, 1)}
      use:tip={{ text: `Increase ${label.toLowerCase()}`, reason: plusReason, hint: plusReason ? null : 'Hold to repeat' }}
    >
      <Icon name="add" size={16} />
    </button>
  </div>
  <div class="help num">
    {#if disabledReason}
      <span class="reason">{disabledReason}</span>
    {:else if sending}
      <span>Sending…</span>
    {:else if draft !== null && draft !== value}
      <span>Sends on release</span>
    {:else}
      <span>{min}–{max} · {limitSource}</span>
    {/if}
  </div>
</div>

<style>
  .stepper {
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-width: 0;
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 17px;
  }
  label {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .accel {
    padding: 0 4px;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-size: var(--text-2xs);
    line-height: 14px;
  }
  .row {
    display: grid;
    grid-template-columns: var(--input-h) 1fr var(--input-h);
    height: var(--input-h);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    transition: border-color var(--duration-fast) var(--ease-standard);
  }
  .row:hover {
    border-color: var(--fg-muted);
  }
  .row.dirty {
    border-style: dashed;
    border-color: var(--fg-muted);
  }
  .side {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    margin: 0;
    padding: 0;
    border: none;
    background: transparent;
    color: var(--fg-muted);
    cursor: pointer;
    touch-action: none;
    transition:
      background-color var(--duration-instant) var(--ease-standard),
      color var(--duration-fast) var(--ease-standard);
  }
  .side:first-child {
    border-right: var(--border-w) solid var(--border-soft);
  }
  .side:last-child {
    border-left: var(--border-w) solid var(--border-soft);
  }
  .side:hover:not(.inert) {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .side:active:not(.inert),
  .side.held:not(.inert) {
    background: var(--pressed-bg);
    box-shadow: var(--lab-pressed-inset);
    color: var(--fg);
  }
  .side:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .side.inert {
    color: var(--fg-disabled);
    cursor: not-allowed;
  }
  .mid {
    position: relative;
    display: flex;
    align-items: center;
  }
  input {
    width: 100%;
    height: 100%;
    padding: 0 var(--space-3);
    border: none;
    background: transparent;
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-m);
    font-variant-numeric: var(--numeric);
    text-align: center;
    caret-color: var(--accent);
  }
  input:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 0;
  }
  .unit {
    position: absolute;
    right: var(--space-2);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-s);
    pointer-events: none;
  }
  .help {
    height: 18px;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: 18px;
    white-space: nowrap;
  }
  .reason::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-right: 6px;
    border-radius: var(--radius-round);
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
    vertical-align: 1px;
  }
  .inert .row {
    border-color: var(--border-soft);
    background: transparent;
  }
  .inert input {
    color: var(--fg-disabled);
  }
</style>

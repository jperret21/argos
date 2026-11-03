<!--
  Stepper: − value + for small integer quantities (gain, frame count, a
  binning factor, a sequence repeat). Promoted from
  src/lab/controls/components/Stepper.svelte (web/lab/PROPOSAL.md 3.3, W2).

  - The value in the middle is a text field (type a value, Enter; arrows step
    with Shift ×10).
  - Hold − or + to repeat: one step at once, then after --repeat-delay a step
    every --repeat-interval, ×10 after 1.6 s of repeating ("×10" shows while
    it does). Nothing is sent while the button is held: ONE value goes 400 ms
    after the release (commit.svelte.ts; device values are never sent per
    step, README 3.4).
  - At a limit the button is unavailable and names the limit ("Driver
    maximum 600"); its press shows that reason at once (tooltip.ts).
  - States as NumberField: not sent (dashed), sending, refused (the server's
    words, Esc reverts), unavailable (reason).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { betweenText, int, parseNumber } from '../format/number';
  import { CommitModel } from './commit.svelte';
  import Icon from './Icon.svelte';
  import { tooltip } from './tooltip';
  import { clamp, REPEAT, repeatFactor } from './values';

  interface Props {
    label: string;
    value: number;
    min: number;
    max: number;
    step?: number;
    unit?: string;
    /** Who sets the limits ("driver"), for the reasons. */
    limitSource?: string;
    /** Send one value; reject with the server's words to refuse it. */
    send?: (v: number) => Promise<unknown> | unknown;
    onchange?: (v: number) => void;
    disabledReason?: string | null;
    /** Pause after the release (or the last key step) before the one value is sent. */
    settleMs?: number;
    /** Specimen only: freeze a state. */
    pin?: { accelerating?: boolean; held?: 'minus' | 'plus'; phase?: 'dirty' | 'sending' | 'refused'; message?: string } | null;
  }

  let {
    label,
    value = $bindable(),
    min,
    max,
    step = 1,
    unit,
    limitSource = 'driver',
    send,
    onchange,
    disabledReason = null,
    settleMs = 400,
    pin = null,
  }: Props = $props();

  const id = `st-${Math.random().toString(36).slice(2, 9)}`;
  const model = new CommitModel<number>(
    untrack(() => value),
    {
      get send() {
        return send ? (v: number) => send!(v) : undefined;
      },
      onapplied: (v) => {
        value = v;
        onchange?.(v);
      },
    },
  );
  $effect(() => {
    const v = value;
    untrack(() => model.sync(v));
  });

  let editing = $state(false);
  let text = $state('');
  let held: 'minus' | 'plus' | null = $state(null);
  let accelerating = $state(false);

  const current = $derived(model.current);
  const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
  const minusReason = $derived(disabledReason ?? (current <= min ? `${cap(limitSource)} minimum ${int(min)}` : null));
  const plusReason = $derived(disabledReason ?? (current >= max ? `${cap(limitSource)} maximum ${int(max)}` : null));
  const phase = $derived(pin?.phase ?? model.phase);
  const showAccel = $derived(pin?.accelerating ?? accelerating);
  const showHeld = $derived(pin?.held ?? held);

  let delayTimer: ReturnType<typeof setTimeout> | null = null;
  let intervalTimer: ReturnType<typeof setInterval> | null = null;
  let t0 = 0;

  function bump(dir: 1 | -1, factor: number): void {
    const next = clamp(Math.round((current + dir * step * factor) / step) * step, min, max);
    text = String(next);
    model.edit(next); // held: nothing is sent yet
  }

  function stopRepeat(): void {
    if (delayTimer) clearTimeout(delayTimer);
    if (intervalTimer) clearInterval(intervalTimer);
    delayTimer = intervalTimer = null;
    if (held && model.hasDraft) model.offer(model.current, settleMs);
    held = null;
    accelerating = false;
  }

  function press(e: PointerEvent, dir: 1 | -1): void {
    const reason = dir > 0 ? plusReason : minusReason;
    if (reason || e.button !== 0 || pin) return;
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    held = dir > 0 ? 'plus' : 'minus';
    t0 = performance.now();
    bump(dir, 1);
    delayTimer = setTimeout(() => {
      intervalTimer = setInterval(() => {
        const f = repeatFactor(performance.now() - t0);
        accelerating = f > 1;
        bump(dir, f);
        if ((dir > 0 && model.current >= max) || (dir < 0 && model.current <= min)) stopRepeat();
      }, REPEAT.interval);
    }, REPEAT.delay);
  }

  /** Keyboard activation (Enter / Space on − or +): one step; the key's own repeat repeats. */
  function keyClick(e: MouseEvent, dir: 1 | -1): void {
    if (e.detail !== 0) return; // pointer clicks are handled on press
    if (dir > 0 ? plusReason : minusReason) return;
    bump(dir, 1);
    model.offer(model.current, settleMs);
  }

  function onKey(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      if (model.phase !== 'idle') {
        e.preventDefault();
        model.revert();
        text = String(model.current);
      }
      return;
    }
    if (disabledReason) return;
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      const dir = e.key === 'ArrowUp' ? 1 : -1;
      if (dir > 0 ? plusReason : minusReason) return;
      bump(dir, e.shiftKey ? 10 : 1);
      model.offer(model.current, settleMs);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const v = parseNumber(text, { integer: true }); // whole numbers: "1,000" is 1 000
      if (v !== null && Number.isFinite(v) && v >= min && v <= max) void model.commit(Math.round(v / step) * step);
    }
  }

  $effect(() => () => {
    stopRepeat();
    model.dispose();
  });

  const typed = $derived.by(() => {
    if (!editing) return null;
    const v = parseNumber(text, { integer: true });
    if (v === null) return 'Enter a number';
    if (v < min || v > max) return `${label} must be between ${betweenText(min, max)}`;
    return null;
  });
</script>

<div class="stepper" class:inert={!!disabledReason}>
  <div class="head">
    <label for={id}>{label}</label>
    {#if showAccel}<span class="accel num">×10</span>{/if}
  </div>
  <div class="row" class:dirty={phase === 'dirty'} class:bad={phase === 'refused' || !!typed}>
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
      use:tooltip={{ text: `Decrease ${label.toLowerCase()}`, reason: minusReason, hint: minusReason ? null : 'Hold to repeat' }}
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
        role="spinbutton"
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={current}
        aria-valuetext="{current}{unit ? ` ${unit}` : ''}"
        value={editing ? text : int(current)}
        readonly={!!disabledReason}
        aria-disabled={disabledReason ? true : undefined}
        aria-busy={phase === 'sending' || undefined}
        aria-invalid={phase === 'refused' || !!typed || undefined}
        aria-describedby="{id}-help"
        data-escape={model.phase !== 'idle' ? 'local' : undefined}
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
      use:tooltip={{ text: `Increase ${label.toLowerCase()}`, reason: plusReason, hint: plusReason ? null : 'Hold to repeat' }}
    >
      <Icon name="add" size={16} />
    </button>
  </div>
  <div class="help num" id="{id}-help">
    {#if disabledReason}
      <span class="msg reason">{disabledReason}</span>
    {:else if typed}
      <span class="msg bad">{typed}</span>
    {:else if phase === 'refused'}
      <span class="msg bad">{pin?.message ?? model.refused}</span><span class="aside"><kbd class="cap">Esc</kbd> reverts</span>
    {:else if phase === 'sending'}
      <span class="msg">Sending…</span>
    {:else if phase === 'dirty'}
      <span class="msg">{held || pin?.held ? 'Sends on release' : 'Not sent'}</span>
    {:else}
      <span class="msg">{int(min)}–{int(max)}{unit ? ` ${unit}` : ''} · {limitSource}</span>
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
  .row.bad {
    border-style: solid;
    border-color: var(--danger);
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
    box-shadow: var(--pressed-inset);
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
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-2);
    min-height: 16px;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: 16px;
  }
  .msg {
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  /* A refusal or a reason is never cut (BRAND 8): up to three lines, the line grows. */
  .msg.bad,
  .msg.reason {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    white-space: normal;
    text-overflow: clip;
    overflow-wrap: anywhere;
  }
  .msg.bad {
    color: var(--fg);
  }
  .msg.bad::before,
  .msg.reason::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-right: 6px;
    border-radius: var(--radius-round);
    vertical-align: 1px;
  }
  .msg.bad::before {
    background: var(--danger);
  }
  .msg.reason::before {
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
  }
  .aside {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: 3px;
  }
  .cap {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 14px;
    height: 14px;
    padding: 0 3px;
    border: var(--border-w) solid var(--border);
    border-bottom-width: 2px;
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    line-height: 1;
  }
  .inert .row {
    border-color: var(--border-soft);
    background: transparent;
  }
  .inert input {
    color: var(--fg-disabled);
  }
</style>

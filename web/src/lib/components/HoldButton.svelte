<!--
  Hold-to-confirm button (BRAND 7 "Physical action that is hard to undo at
  night", owner D4; web/lab/PROPOSAL.md 3.1 and 6, W3; promoted from
  src/lab/controls/components/HoldButton.svelte, the ring version, which
  replaces the workspace lab's fill version). For Park (it closes the Seestar
  arm and stops tracking) and Watch's Pause.

  Pointer: press and hold for --hold-duration (700 ms). The ring around the
  glyph (its track drawn at rest = "this one is held") fills with the exact
  elapsed time, linear; releasing or sliding off before the end sends
  nothing and says so ("Released · nothing sent"), and the ring drains in
  --hold-drain. A quick tap teaches the gesture in the caption.
  Keyboard and assistive technology: Enter / Space never start a timed hold;
  they open the inline two-button confirmation in place, focus on Cancel
  (README 3.3); Esc closes it (and, as everywhere, still aborts a slew: the
  key is not swallowed, D21).
  The label NEVER changes while held (its width neither); the caption under
  the button does (aria-live). Reduced motion: the ring advances in quarters,
  the countdown stays exact. Built on Control (holdRing + progress), so its
  states are the product's one implementation. The pure rules are in hold.ts.

  `pin` freezes a phase for the gallery (no pointer needed).
-->
<script lang="ts">
  import NumText from './NumText.svelte';
  import { untrack } from 'svelte';
  import Control from './Control.svelte';
  import {
    canOpenConfirm,
    canStartHold,
    DONE_MS,
    DRAIN_MS,
    holdCaption,
    holdFraction,
    holdHint,
    HOLD_MS,
    RELEASED_MS,
    releaseOutcome,
    slidOff,
    type HoldPhase,
  } from './hold';
  import { reducedMotion } from './motion.svelte';
  import { refusalText } from './commit.svelte';

  interface Props {
    icon: string;
    label: string;
    variant?: 'secondary' | 'primary' | 'danger';
    size?: 'm' | 'l';
    holdMs?: number;
    /** Verb for the captions: "park" -> "Hold 0.7 s to park". */
    verb: string;
    /** Inline confirmation (keyboard path): the question and what it does. */
    confirmTitle: string;
    confirmBody: string;
    confirmAction?: string;
    cancelLabel?: string;
    busyLabel?: string;
    doneLabel?: string;
    /** Runs the action; reject with the server's words to show the failure. */
    onconfirm?: () => Promise<unknown> | unknown;
    disabledReason?: string | null;
    /** Show the caption line under the button (rails); off in toolbars. */
    caption?: boolean;
    /** Gallery: freeze a phase (and a hold fraction). */
    pin?: { phase: HoldPhase; progress?: number; failure?: string } | null;
    /** Stretch to the container's width. */
    wide?: boolean;
  }

  let {
    icon,
    label,
    variant = 'secondary',
    size = 'l',
    holdMs = HOLD_MS,
    verb,
    confirmTitle,
    confirmBody,
    confirmAction,
    cancelLabel = 'Cancel',
    busyLabel,
    doneLabel,
    onconfirm,
    disabledReason = null,
    caption = true,
    pin = null,
    wide = false,
  }: Props = $props();

  const uid = `hold-${Math.random().toString(36).slice(2, 9)}`;
  let phase = $state<HoldPhase>('rest');
  let live = $state(0);
  let drain = $state(0);
  let failure: string | null = $state(null);
  let flash = $state(false);
  let btn: HTMLButtonElement | null = $state(null);
  let cancelBtn: HTMLButtonElement | null = $state(null);

  let t0 = 0;
  let raf = 0;
  let drainRaf = 0;
  let pointerId: number | null = null;
  let phaseTimer: ReturnType<typeof setTimeout> | null = null;

  const shown = $derived<HoldPhase>(pin?.phase ?? phase);
  const unavailable = $derived(!!disabledReason);
  const progress = $derived.by(() => {
    if (pin) return pin.progress ?? (pin.phase === 'holding' ? 0.45 : null);
    if (phase === 'holding') return live;
    return drain > 0.001 ? drain : null;
  });
  const remaining = $derived(((1 - (progress ?? 0)) * holdMs) / 1000);
  const shownFailure = $derived(pin?.failure ?? failure);
  const cap = $derived(
    holdCaption(shown, {
      verb,
      label,
      holdMs,
      remainingS: remaining,
      busyLabel,
      doneLabel,
      failure: shownFailure,
      disabledReason,
    }),
  );

  function later(next: HoldPhase, ms: number): void {
    if (phaseTimer) clearTimeout(phaseTimer);
    phaseTimer = setTimeout(() => {
      phase = next;
      phaseTimer = null;
    }, ms);
  }

  function stopLoop(): void {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
  }

  function tick(now: number): void {
    live = holdFraction(now - t0, holdMs);
    if (live >= 1) {
      stopLoop();
      void complete();
      return;
    }
    raf = requestAnimationFrame(tick);
  }

  /** The ring empties linearly from where the hold stopped (instant under reduced motion). */
  function startDrain(from: number): void {
    if (drainRaf) cancelAnimationFrame(drainRaf);
    const ms = reducedMotion() ? 0 : DRAIN_MS;
    if (ms === 0 || from <= 0) {
      drain = 0;
      return;
    }
    const start = performance.now();
    const step = (now: number) => {
      const k = Math.min(1, (now - start) / ms);
      drain = from * (1 - k);
      drainRaf = k < 1 ? requestAnimationFrame(step) : 0;
    };
    drain = from;
    drainRaf = requestAnimationFrame(step);
  }

  function onPointerDown(e: PointerEvent): void {
    if (pin || e.button !== 0 || !canStartHold(phase, unavailable)) return;
    if (phaseTimer) clearTimeout(phaseTimer);
    pointerId = e.pointerId;
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    failure = null;
    phase = 'holding';
    t0 = performance.now();
    live = 0;
    drain = 0;
    raf = requestAnimationFrame(tick);
  }

  function release(): void {
    if (phase !== 'holding') return;
    stopLoop();
    const was = live;
    pointerId = null;
    phase = releaseOutcome(was);
    live = 0;
    startDrain(was);
    later('rest', RELEASED_MS);
  }

  function onPointerUp(e: PointerEvent): void {
    if (e.pointerId === pointerId) release();
  }

  function onPointerMove(e: PointerEvent): void {
    if (phase !== 'holding' || e.pointerId !== pointerId || !btn) return;
    if (slidOff(btn.getBoundingClientRect(), e.clientX, e.clientY)) release();
  }

  async function complete(): Promise<void> {
    if (phaseTimer) clearTimeout(phaseTimer);
    phase = 'busy';
    flash = true;
    setTimeout(() => (flash = false), 120);
    live = 0;
    try {
      await onconfirm?.();
      phase = 'done';
      later('rest', DONE_MS);
    } catch (err) {
      failure = refusalText(err);
      phase = 'failed';
    }
  }

  function onKeyDown(e: KeyboardEvent): void {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    e.preventDefault();
    if (pin || !canOpenConfirm(phase, unavailable)) return;
    if (phaseTimer) clearTimeout(phaseTimer);
    phase = 'confirm';
    queueMicrotask(() => cancelBtn?.focus());
  }

  function closeConfirm(): void {
    phase = 'rest';
    queueMicrotask(() => btn?.focus());
  }

  // A reason that appears while the confirmation is open closes it (the action can no longer run).
  $effect(() => {
    if (unavailable) untrack(() => phase === 'confirm' && (phase = 'rest'));
  });

  $effect(() => () => {
    stopLoop();
    if (drainRaf) cancelAnimationFrame(drainRaf);
    if (phaseTimer) clearTimeout(phaseTimer);
  });

  const hint = $derived(holdHint(verb, holdMs));
</script>

<div class="hold" class:wide>
  <Control
    bind:el={btn}
    {icon}
    {label}
    showLabel
    {variant}
    {size}
    holdRing
    {progress}
    busy={shown === 'busy'}
    error={shown === 'failed' ? shownFailure : null}
    {disabledReason}
    {hint}
    tooltip={caption ? 'none' : 'bottom'}
    data-force={flash ? 'active' : shown === 'holding' ? 'hover' : undefined}
    aria-describedby={caption ? `${uid}-cap` : undefined}
    aria-expanded={shown === 'confirm'}
    aria-controls={shown === 'confirm' ? `${uid}-confirm` : undefined}
    class={wide ? 'hold-wide' : ''}
    onpointerdown={onPointerDown}
    onpointerup={onPointerUp}
    onpointercancel={release}
    onlostpointercapture={release}
    onpointermove={onPointerMove}
    onkeydown={onKeyDown}
    oncontextmenu={(e: MouseEvent) => e.preventDefault()}
  />

  {#if caption}
    <p class="caption tone-{cap.tone}" id="{uid}-cap" aria-live="polite">
      <span class="ctext"><NumText text={cap.text} /></span>
      {#if cap.count}<span class="count" aria-hidden="true">{cap.count}</span>{/if}
    </p>
  {/if}

  {#if shown === 'confirm'}
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions (Esc closes the inline confirmation) -->
    <div
      class="confirm"
      id="{uid}-confirm"
      role="group"
      aria-labelledby="{uid}-title"
      aria-describedby="{uid}-body"
      tabindex="-1"
      onkeydown={(e) => {
        if (e.key === 'Escape') {
          // Not swallowed: the registry still aborts a slew on the same press (D21).
          e.preventDefault();
          closeConfirm();
        }
      }}
    >
      <p class="title" id="{uid}-title">{confirmTitle}</p>
      <p class="body" id="{uid}-body">{confirmBody}</p>
      <div class="actions">
        <Control bind:el={cancelBtn} label={cancelLabel} size="s" tooltip="none" onclick={closeConfirm} />
        <Control
          label={confirmAction ?? label}
          size="s"
          variant={variant === 'danger' ? 'danger' : 'primary'}
          tooltip="none"
          onclick={() => {
            void complete();
            queueMicrotask(() => btn?.focus());
          }}
        />
      </div>
    </div>
  {/if}
</div>

<style>
  .hold {
    display: inline-flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-1);
    min-width: 0;
  }
  .hold.wide {
    display: flex;
    align-items: stretch;
  }
  .hold :global(.hold-wide) {
    width: 100%;
    justify-content: flex-start;
  }

  .caption {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    min-height: 15px;
    margin: 0;
    color: var(--fg);
    font-size: var(--text-xs);
    line-height: 15px;
    white-space: nowrap;
  }
  .tone-muted .ctext,
  .tone-reason .ctext,
  .count {
    color: var(--text-muted);
  }
  .count {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .tone-reason .ctext::before,
  .tone-failed .ctext::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-right: 6px;
    border-radius: var(--radius-round);
    vertical-align: 1px;
  }
  /* The tooltip's vocabulary: hollow ring = a reason, danger dot = what failed. */
  .tone-reason .ctext::before {
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
  }
  .tone-failed .ctext::before {
    background: var(--danger);
  }
  .tone-failed {
    white-space: normal;
  }

  .confirm {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    width: min(340px, 100%);
    min-width: 260px;
    padding: var(--space-3) var(--space-4) var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg-2);
    animation: in var(--duration-base) var(--ease-out);
  }
  .confirm:focus {
    outline: none;
  }
  @keyframes in {
    from {
      opacity: 0;
      transform: translateY(-4px);
    }
  }
  .title {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-m);
    font-weight: var(--weight-semibold);
  }
  .body {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
    line-height: var(--leading-normal);
    text-wrap: pretty;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }
</style>

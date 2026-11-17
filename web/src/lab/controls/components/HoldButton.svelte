<!--
  Hold-to-confirm (proposal; functional-spaces 4.11): for actions that are
  physical and hard to undo during a night (Park closes the Seestar arm,
  Pause-and-slew breaks a time series, Stop ends a run).

  Pointer: press and hold for --lab-hold (700 ms). The ring around the glyph
  (track drawn at rest = "this one is held") fills with the exact elapsed
  time, linear; releasing or sliding off before the end sends nothing and
  says so ("Released · nothing sent"); the ring drains in 150 ms.
  Keyboard and assistive technology: Enter / Space never start a timed hold
  (hard for some users); they open the inline confirmation in place, focus
  on Cancel (README 3.3). A quick tap teaches the gesture in the caption.
  Reduced motion: the ring advances in quarters, the countdown stays.

  `pin` freezes a state for the specimen (no pointer needed).
-->
<script lang="ts">
  import { Tween } from 'svelte/motion';
  import { dur } from '../env.svelte';
  import { fixed } from '../format';
  import Ctl from './Ctl.svelte';

  type Phase = 'rest' | 'holding' | 'confirm' | 'busy' | 'released' | 'tapped' | 'done' | 'failed';

  interface Props {
    icon: string;
    label: string;
    variant?: 'secondary' | 'primary' | 'danger';
    size?: 'm' | 'l';
    holdMs?: number;
    /** Verb for the captions: "park" -> "Hold to park". */
    verb: string;
    /** Inline confirmation (keyboard path). */
    confirmTitle: string;
    confirmBody: string;
    confirmAction?: string;
    cancelLabel?: string;
    busyLabel?: string;
    doneLabel?: string;
    onconfirm?: () => Promise<void> | void;
    disabledReason?: string | null;
    /** Show the caption line under the button (rails); off in toolbars. */
    caption?: boolean;
    /** Specimen: freeze a phase (and a hold fraction). */
    pin?: { phase: Phase; progress?: number } | null;
    /** Stretch to the container's width. */
    wide?: boolean;
  }

  let {
    icon,
    label,
    variant = 'secondary',
    size = 'l',
    holdMs = 700,
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
  let phase = $state<Phase>('rest');
  let live = $state(0);
  let failure: string | null = $state(null);
  let flash = $state(false);
  const drain = new Tween(0);
  let btn: HTMLButtonElement | null = $state(null);
  let cancelBtn: HTMLButtonElement | undefined = $state();

  let t0 = 0;
  let raf = 0;
  let pointerId: number | null = null;
  let phaseTimer: ReturnType<typeof setTimeout> | null = null;

  const shownPhase = $derived(pin?.phase ?? phase);
  const progress = $derived(
    pin ? (pin.progress ?? (pin.phase === 'holding' ? 0.45 : null)) : phase === 'holding' ? live : drain.current > 0.001 ? drain.current : null,
  );
  const remaining = $derived(((1 - (progress ?? 0)) * holdMs) / 1000);

  function later(next: Phase, ms: number): void {
    if (phaseTimer) clearTimeout(phaseTimer);
    phaseTimer = setTimeout(() => {
      phase = next;
      phaseTimer = null;
    }, ms);
  }

  function stopLoop(): void {
    cancelAnimationFrame(raf);
    raf = 0;
  }

  function tick(now: number): void {
    live = Math.min(1, (now - t0) / holdMs);
    if (live >= 1) {
      stopLoop();
      void complete();
      return;
    }
    raf = requestAnimationFrame(tick);
  }

  function onPointerDown(e: PointerEvent): void {
    if (disabledReason || pin || phase === 'busy' || e.button !== 0) return;
    if (phaseTimer) clearTimeout(phaseTimer);
    pointerId = e.pointerId;
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    failure = null;
    phase = 'holding';
    t0 = performance.now();
    live = 0;
    void drain.set(0, { duration: 0 });
    raf = requestAnimationFrame(tick);
  }

  function release(sent: boolean): void {
    if (phase !== 'holding') return;
    stopLoop();
    const was = live;
    pointerId = null;
    if (sent) return;
    // A tap (no real hold) teaches the gesture; a real hold says nothing was sent.
    phase = was < 0.18 ? 'tapped' : 'released';
    void drain.set(was, { duration: 0 }).then(() => drain.set(0, { duration: dur(150) }));
    live = 0;
    later('rest', 1800);
  }

  function onPointerUp(e: PointerEvent): void {
    if (e.pointerId === pointerId) release(false);
  }

  function onPointerMove(e: PointerEvent): void {
    if (phase !== 'holding' || e.pointerId !== pointerId || !btn) return;
    const r = btn.getBoundingClientRect();
    const slop = 8;
    if (e.clientX < r.left - slop || e.clientX > r.right + slop || e.clientY < r.top - slop || e.clientY > r.bottom + slop) {
      release(false); // slid off: cancel
    }
  }

  async function complete(): Promise<void> {
    phase = 'busy';
    flash = true;
    setTimeout(() => (flash = false), 120);
    live = 0;
    try {
      await onconfirm?.();
      phase = 'done';
      later('rest', 2200);
    } catch (err) {
      failure = err instanceof Error ? err.message : String(err);
      phase = 'failed';
    }
  }

  function onKeyDown(e: KeyboardEvent): void {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    e.preventDefault();
    if (disabledReason || pin || phase === 'busy') return;
    phase = 'confirm';
    queueMicrotask(() => cancelBtn?.focus());
  }

  function closeConfirm(): void {
    phase = 'rest';
    queueMicrotask(() => btn?.focus());
  }

  $effect(() => () => {
    stopLoop();
    if (phaseTimer) clearTimeout(phaseTimer);
  });

  const hint = $derived(`Hold ${fixed(holdMs / 1000, 1)} s to ${verb} · Enter to confirm`);
</script>

<div class="hold" class:wide>
  <Ctl
    bind:el={btn}
    {icon}
    {label}
    showLabel
    {variant}
    {size}
    holdRing
    {progress}
    busy={shownPhase === 'busy'}
    error={shownPhase === 'failed' ? failure : null}
    {disabledReason}
    {hint}
    tooltip={caption ? 'none' : 'bottom'}
    data-force={flash ? 'active' : shownPhase === 'holding' ? 'hover' : undefined}
    aria-describedby={caption ? `${uid}-cap` : undefined}
    aria-expanded={shownPhase === 'confirm'}
    aria-controls={shownPhase === 'confirm' ? `${uid}-confirm` : undefined}
    class={wide ? 'hold-wide' : ''}
    onpointerdown={onPointerDown}
    onpointerup={onPointerUp}
    onpointercancel={() => release(false)}
    onlostpointercapture={() => release(false)}
    onpointermove={onPointerMove}
    onkeydown={onKeyDown}
    oncontextmenu={(e) => e.preventDefault()}
  />

  {#if caption}
    <p class="caption" id="{uid}-cap" aria-live="polite">
      {#if disabledReason}
        <span class="reason">{disabledReason}</span>
      {:else if shownPhase === 'holding'}
        <span>Keep holding</span><span class="num count" aria-hidden="true">{fixed(remaining, 1)} s</span>
      {:else if shownPhase === 'busy'}
        <span>{busyLabel ?? `${label}…`}</span>
      {:else if shownPhase === 'released'}
        <span>Released · nothing sent</span>
      {:else if shownPhase === 'tapped'}
        <span>Hold to {verb}, or press Enter</span>
      {:else if shownPhase === 'done'}
        <span>{doneLabel ?? 'Done'}</span>
      {:else if shownPhase === 'failed'}
        <span class="failed">{failure}</span>
      {:else}
        <span class="muted">{hint}</span>
      {/if}
    </p>
  {/if}

  {#if shownPhase === 'confirm'}
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions (Esc closes the inline confirmation) -->
    <div
      class="confirm"
      id="{uid}-confirm"
      role="group"
      aria-labelledby="{uid}-title"
      tabindex="-1"
      onkeydown={(e) => {
        if (e.key === 'Escape') {
          e.stopPropagation();
          closeConfirm();
        }
      }}
    >
      <p class="title" id="{uid}-title">{confirmTitle}</p>
      <p class="body">{confirmBody}</p>
      <div class="actions">
        <button type="button" class="tbtn" bind:this={cancelBtn} onclick={closeConfirm}>{cancelLabel}</button>
        <button
          type="button"
          class="tbtn"
          class:primary={variant !== 'danger'}
          class:danger={variant === 'danger'}
          onclick={() => {
            void complete();
            queueMicrotask(() => btn?.focus());
          }}>{confirmAction ?? label}</button
        >
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
  .caption .muted {
    color: var(--text-muted);
  }
  .caption .count {
    color: var(--text-muted);
  }
  .caption .reason {
    color: var(--text-muted);
  }
  .caption .failed::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-right: 6px;
    border-radius: var(--radius-round);
    background: var(--danger);
    vertical-align: 1px;
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

  /* Text buttons of the confirmation (BRAND 7 row 3). */
  .tbtn {
    height: 26px;
    min-width: 64px;
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
    cursor: pointer;
    transition: background-color var(--duration-instant) var(--ease-standard);
  }
  .tbtn:hover {
    background: var(--hover-bg);
  }
  .tbtn:active {
    background: var(--pressed-bg);
    box-shadow: var(--lab-pressed-inset);
  }
  .tbtn.primary {
    border-color: var(--primary-border);
    background: var(--primary-bg);
    color: var(--primary-fg);
  }
  .tbtn.primary:hover {
    border-color: var(--primary-bg-hover);
    background: var(--primary-bg-hover);
    color: var(--primary-fg-hover);
  }
  .tbtn.danger {
    border-color: var(--danger);
    background: var(--surface);
  }
  .tbtn.danger:hover {
    background: var(--danger);
    color: var(--on-danger);
  }
  .tbtn:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }
</style>

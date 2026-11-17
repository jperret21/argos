<!--
  Control button, refreshed (proposal to merge IconButton and Button): one
  component for icon-only, icon + label and text-only buttons, with every
  state of BRAND 8 plus three the instrument needs:

  - progress (0..1): a time ring around the glyph (exposure, sweep), the
    value in words in the tooltip and aria-valuetext of the ring's label;
  - error: the last attempt failed. Danger outline + a corner dot, the
    message in the tooltip and aria-describedby; cleared by the next try;
  - key hint: the shortcut's cap drawn on the control while the observer
    holds Mod (hints.svelte.ts).

  Unavailable = aria-disabled + reason (still focusable, the press explains
  itself at once, tip.ts). `disabled` (hard) only where there is no reason
  to give. Busy keeps the width (the spinner replaces the glyph).
  States can be pinned for the specimen with data-force="hover|active|focus".
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLButtonAttributes } from 'svelte/elements';
  import { ariaShortcut, formatShortcut } from '../../../lib/app/shortcuts';
  import Icon from '../../../lib/components/Icon.svelte';
  import { reduced } from '../env.svelte';
  import { hintsVisible } from '../hints.svelte';
  import { tip, type TipPlacement } from '../tip';
  import Ring from './Ring.svelte';

  type Variant = 'ghost' | 'secondary' | 'primary' | 'danger';

  interface Props extends Omit<HTMLButtonAttributes, 'children' | 'disabled' | 'aria-pressed'> {
    icon?: string;
    label: string;
    showLabel?: boolean;
    variant?: Variant;
    size?: 's' | 'm' | 'l';
    /** Toggle state (aria-pressed); undefined for a push button. */
    pressed?: boolean;
    /** A layout toggle (panels, strip): on state without brass. */
    layoutToggle?: boolean;
    /** Only the glyph in --danger (a routine stop: live view). */
    glyphTone?: 'danger';
    busy?: boolean;
    progress?: number | null;
    progressText?: string;
    /** Hold-to-confirm: the ring's track is drawn at rest (the affordance). */
    holdRing?: boolean;
    error?: string | null;
    disabled?: boolean;
    disabledReason?: string | null;
    shortcut?: string;
    tooltip?: TipPlacement | 'none';
    tooltipText?: string;
    hint?: string | null;
    /** Content after the label (a count, "7/14"). */
    trailing?: Snippet;
    el?: HTMLButtonElement | null;
  }

  let {
    icon,
    label,
    showLabel = false,
    variant = 'secondary',
    size = 'm',
    pressed,
    layoutToggle = false,
    glyphTone,
    busy = false,
    progress = null,
    progressText,
    holdRing = false,
    error = null,
    disabled = false,
    disabledReason = null,
    shortcut,
    tooltip = 'bottom',
    tooltipText,
    hint = null,
    trailing,
    el = $bindable(null),
    onclick,
    class: className = '',
    ...rest
  }: Props = $props();

  const uid = `ctl-${Math.random().toString(36).slice(2, 9)}`;
  const soft = $derived(!disabled && !!disabledReason);
  const inert = $derived(disabled || soft);
  const textShown = $derived(showLabel || !icon);
  const ringSize = $derived(size === 's' ? 24 : size === 'l' ? 30 : 28);
  const glyphPx = $derived(size === 's' ? 16 : 20);
  const tipText = $derived(
    progressText && progress !== null ? `${tooltipText ?? label} · ${progressText}` : (tooltipText ?? label),
  );
  // A labelled control needs a tip only when it adds something.
  const tipOn = $derived(
    tooltip !== 'none' && (!textShown || !!shortcut || soft || !!error || !!hint || !!tooltipText || progress !== null),
  );

  function handleClick(e: MouseEvent & { currentTarget: EventTarget & HTMLButtonElement }) {
    if (busy || soft) {
      e.preventDefault();
      return;
    }
    onclick?.(e);
  }
</script>

<button
  bind:this={el}
  {...rest}
  type="button"
  class="ctl v-{variant} s-{size} {className}"
  class:text-only={!icon}
  class:icon-only={!textShown}
  class:glyph-danger={glyphTone === 'danger'}
  class:layout-toggle={layoutToggle}
  class:is-busy={busy || (progress !== null && !holdRing)}
  class:has-ring={holdRing || progress !== null}
  class:ring-hold={holdRing}
  class:is-inert={inert}
  class:has-error={!!error}
  aria-label={textShown ? undefined : label}
  aria-pressed={pressed === undefined ? undefined : pressed}
  aria-busy={busy || (progress !== null && !holdRing) || undefined}
  aria-disabled={soft || undefined}
  aria-describedby={error ? `${uid}-err` : undefined}
  aria-keyshortcuts={shortcut ? ariaShortcut(shortcut) : undefined}
  {disabled}
  onclick={handleClick}
  use:tip={{
    text: tipText,
    shortcut: soft ? undefined : shortcut,
    reason: soft ? disabledReason : null,
    error,
    hint,
    placement: tooltip === 'none' ? 'bottom' : tooltip,
    disabled: !tipOn,
  }}
>
  {#if icon}
    <span class="glyph" style:--ring="{ringSize}px">
      {#if busy && progress === null}
        <svg class="spinner" class:still={reduced()} viewBox="0 0 24 24" width={glyphPx} height={glyphPx} aria-hidden="true">
          <path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" />
        </svg>
      {:else}
        <Icon name={icon} size={glyphPx} />
      {/if}
      {#if progress !== null || holdRing}
        <Ring
          size={ringSize}
          value={progress}
          track={holdRing && !busy}
          stepped={reduced()}
          tone={variant === 'danger' ? 'danger' : 'accent'}
        />
      {/if}
    </span>
  {/if}
  {#if textShown}
    <span class="text">{label}</span>
  {/if}
  {#if trailing}
    <span class="trailing">{@render trailing()}</span>
  {/if}
  {#if error}
    <span class="err-dot" aria-hidden="true"></span>
    <span id="{uid}-err" class="visually-hidden">{error}</span>
  {/if}
  {#if shortcut && !inert && hintsVisible()}
    <kbd class="cap keyhint" aria-hidden="true">{formatShortcut(shortcut)}</kbd>
  {/if}
</button>

<style>
  .ctl {
    --h: var(--control-h-m);
    --pad: var(--space-2);
    --bg-c: transparent;
    --fg-c: var(--fg);
    --glyph-c: var(--fg-c);
    --text-c: var(--fg-c);
    --edge: var(--border);
    --inset: none;

    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    min-width: var(--h);
    height: var(--h);
    padding: 0 var(--pad);
    margin: 0;
    border: var(--border-w) solid var(--edge);
    border-radius: var(--radius-s);
    background: var(--bg-c);
    box-shadow: var(--inset);
    color: var(--fg-c);
    font-family: var(--font-ui);
    font-size: var(--text-m);
    font-weight: var(--weight-medium);
    line-height: var(--leading-tight);
    white-space: nowrap;
    cursor: pointer;
    user-select: none;
    -webkit-user-select: none;
    -webkit-tap-highlight-color: transparent;
    touch-action: manipulation;
    transition:
      background-color var(--duration-instant) var(--ease-standard),
      border-color var(--duration-fast) var(--ease-standard),
      color var(--duration-fast) var(--ease-standard),
      box-shadow var(--duration-instant) var(--ease-standard);
  }

  .s-s {
    --h: var(--control-h-s);
  }
  .s-l {
    --h: var(--lab-control-h-l);
    --pad: var(--space-3);
  }
  .icon-only {
    padding: 0;
  }
  .ctl:not(.icon-only):not(.text-only) {
    padding: 0 calc(var(--pad) + var(--space-1)) 0 var(--pad);
  }
  .text-only {
    min-width: 72px;
    padding: 0 var(--space-4);
  }
  .text-only.s-s {
    min-width: 0;
    padding: 0 var(--space-3);
    font-size: var(--text-s);
  }

  .glyph {
    position: relative;
    display: inline-flex;
    flex: none;
    align-items: center;
    justify-content: center;
    color: var(--glyph-c);
  }
  .has-ring .glyph {
    /* Room for the ring; the label does not move when a ring appears. */
    width: var(--ring);
    height: var(--ring);
    margin: 0 calc((var(--ring) - 20px) / -2);
  }
  .s-s.has-ring .glyph {
    margin: 0 calc((var(--ring) - 16px) / -2);
  }
  /* A hold ring is always there: it takes its own room (no overlap). */
  .ring-hold .glyph,
  .s-s.ring-hold .glyph {
    margin: 0 -2px 0 -4px;
  }
  .text {
    color: var(--text-c);
  }
  .trailing {
    display: inline-flex;
    align-items: center;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    font-variant-numeric: var(--numeric);
  }

  /* -- Variants (BRAND 8) ------------------------------------------------------- */

  .v-ghost {
    --fg-c: var(--fg-muted);
    --text-c: var(--fg);
    --edge: transparent;
  }
  .v-primary {
    --bg-c: var(--primary-bg);
    --fg-c: var(--primary-fg);
    --edge: var(--primary-border);
  }
  .v-danger {
    --bg-c: var(--surface);
    --edge: var(--danger);
    --glyph-c: var(--danger);
    --text-c: var(--fg);
  }
  .glyph-danger {
    --glyph-c: var(--danger);
  }

  /* Hover */
  .ctl:is(:hover, [data-force~='hover']):not(.is-inert) {
    --bg-c: var(--hover-bg);
  }
  .v-ghost:is(:hover, [data-force~='hover']):not(.is-inert) {
    --fg-c: var(--fg);
  }
  .v-primary:is(:hover, [data-force~='hover']):not(.is-inert) {
    --bg-c: var(--primary-bg-hover);
    --fg-c: var(--primary-fg-hover);
    --edge: var(--primary-bg-hover);
  }
  .v-danger:is(:hover, [data-force~='hover']):not(.is-inert) {
    --bg-c: var(--danger);
    --glyph-c: var(--on-danger);
    --text-c: var(--on-danger);
  }

  /* Pressed: darker fill and a 1 px black inner edge (no scale, no bounce). */
  .ctl:is(:active, [data-force~='active']):not(.is-inert) {
    --bg-c: var(--pressed-bg);
    --inset: var(--lab-pressed-inset);
  }
  .v-primary:is(:active, [data-force~='active']):not(.is-inert) {
    --bg-c: var(--accent-deep);
    --fg-c: var(--on-accent-deep);
    --edge: var(--accent-deep);
  }
  .v-danger:is(:active, [data-force~='active']):not(.is-inert) {
    --bg-c: var(--danger);
    --glyph-c: var(--on-danger);
    --text-c: var(--on-danger);
  }

  /* Toggled on: same glyph, brass state; ghost toggles without outline. */
  .ctl[aria-pressed='true'] {
    --bg-c: var(--toggled-bg);
    --fg-c: var(--toggled-fg);
    --glyph-c: var(--toggled-fg);
    --text-c: var(--toggled-fg);
    --edge: var(--toggled-border);
  }
  .v-ghost[aria-pressed='true'] {
    --edge: transparent;
  }
  .layout-toggle[aria-pressed='true'] {
    --fg-c: var(--fg);
    --glyph-c: var(--fg);
    --text-c: var(--fg);
  }
  .ctl[aria-pressed='true']:is(:hover, [data-force~='hover']):not(.is-inert) {
    --bg-c: var(--hover-bg);
  }

  /* Focus: always on top of any state. */
  .ctl:is(:focus-visible, [data-force~='focus']) {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }

  /* Unavailable */
  .ctl:disabled,
  .ctl.is-inert {
    --fg-c: var(--fg-disabled);
    --glyph-c: var(--fg-disabled);
    --text-c: var(--fg-disabled);
    --edge: var(--border-soft);
    --bg-c: transparent;
    cursor: not-allowed;
  }
  .v-primary:is(:disabled, .is-inert) {
    --bg-c: var(--surface);
  }
  .v-ghost:is(:disabled, .is-inert) {
    --edge: transparent;
  }

  /* Error: the last attempt failed (outline + corner dot; words in the tip). */
  .has-error:not(.is-inert) {
    --edge: var(--danger);
  }
  .err-dot {
    position: absolute;
    top: -4px;
    right: -4px;
    width: 8px;
    height: 8px;
    border-radius: var(--radius-round);
    background: var(--danger);
    box-shadow: 0 0 0 2px var(--ctl-halo, var(--bg));
  }

  .is-busy {
    cursor: progress;
  }

  /* Busy: the logo-like arc, 0.9 s per turn; a still arc under reduced motion. */
  .spinner {
    fill: none;
    stroke: currentColor;
    stroke-width: 1.5;
    stroke-linecap: round;
    animation: spin 0.9s linear infinite;
  }
  .spinner.still {
    animation: none;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .spinner {
      animation: none;
    }
  }

  /* Key hint (hold Mod): the cap sits on the control's lower right corner. */
  .keyhint {
    position: absolute;
    right: -5px;
    bottom: -6px;
    z-index: 1;
    min-width: 15px;
    height: 15px;
    padding: 0 3px;
    border-color: var(--accent);
    background: var(--bg);
    color: var(--fg);
    pointer-events: none;
    animation: hint-in var(--duration-fast) var(--ease-out);
  }
  @keyframes hint-in {
    from {
      opacity: 0;
    }
  }
</style>

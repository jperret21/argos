<!--
  Control: the one button of the UI (web/lab/PROPOSAL.md 3.3, BRAND 7 and 8;
  promoted from src/lab/controls/components/Ctl.svelte). Icon-only, icon +
  label and text-only buttons share one implementation, so their states
  cannot drift. IconButton and Button are thin wrappers over it.

  States, each double-coded (never colour alone):
  - rest, hover, pressed (fill + --pressed-inset: a 1 px black inner top edge,
    no scale), keyboard focus (ring on top of any state);
  - toggled (`pressed` -> aria-pressed): same glyph, the toggled style;
    `layoutToggle` keeps the fill with an --fg glyph (no brass);
  - unavailable + reason (`disabledReason`): aria-disabled, STILL focusable,
    the reason in the tooltip's second line and aria-describedby, and a press
    shows it at once (tooltip.ts). `disabled` (hard) only where no reason
    exists;
  - busy: the spinner replaces the glyph (before the label of a text button)
    without changing the width; aria-busy; clicks swallowed, focus kept;
  - error (the last attempt failed): --danger outline + a 6 px corner dot,
    the device's words in the tooltip and aria-describedby;
  - progress (0..1): a time ring around the glyph, the exact elapsed
    fraction, linear, butt caps; quarters under reduced motion;
  - hold ring: the ring's track at rest = this control is hold-to-confirm
    (HoldButton, W3, drives `progress`);
  - key hint: while Cmd / Ctrl is held alone (app/keyhints.svelte.ts) the
    shortcut is drawn as a neutral cap on the control's corner.

  Sizes: xs 24 px (compact text buttons), s 30, m 34, l 40 (hold targets).
  `data-force="hover|active|focus"` pins a state for the gallery.
  Tokens only, so every theme, Night Red included, holds.
-->
<script lang="ts">
  import { onMount, type Snippet } from 'svelte';
  import type { HTMLButtonAttributes } from 'svelte/elements';
  import { ensureKeyHints, keyHintsVisible } from '../app/keyhints.svelte';
  import { ariaShortcut, formatShortcut } from '../app/shortcuts';
  import Icon from './Icon.svelte';
  import { reducedMotion } from './motion.svelte';
  import Ring from './Ring.svelte';
  import { tooltip as tooltipAction, type TooltipPlacement } from './tooltip';

  export type ControlVariant = 'ghost' | 'secondary' | 'primary' | 'danger';
  export type ControlSize = 'xs' | 's' | 'm' | 'l';

  interface Props extends Omit<HTMLButtonAttributes, 'children' | 'disabled' | 'aria-pressed'> {
    icon?: string;
    /** Accessible name; the visible text of a text button (or `children`). */
    label?: string;
    /** Custom visible text of a text button (the accessible name stays the content). */
    children?: Snippet;
    /** Show the label next to the icon. */
    showLabel?: boolean;
    variant?: ControlVariant;
    size?: ControlSize;
    /** Toggle state (aria-pressed); leave undefined for a push button. */
    pressed?: boolean;
    /** A toggle of the layout (panels, band): on state without brass. */
    layoutToggle?: boolean;
    /** Only the glyph in --danger (a routine stop: live view). */
    glyphTone?: 'danger';
    busy?: boolean;
    /** Elapsed fraction of a timed operation (0..1), or null. */
    progress?: number | null;
    /** The progress in words ("3.2 of 10 s"), for the tooltip and screen readers. */
    progressText?: string;
    /** Hold-to-confirm: the ring's track is drawn at rest. */
    holdRing?: boolean;
    /** What failed on the last attempt (cleared by the caller on the next success). */
    error?: string | null;
    disabled?: boolean;
    /** Why it cannot act now: aria-disabled, still focusable, explained on press. */
    disabledReason?: string | null;
    /** Shortcut spec from the registry ("E", "Shift+A"): tooltip cap, aria-keyshortcuts, key hint. */
    shortcut?: string;
    /** Tooltip side, or 'none'. A labelled control only gets one when it adds something. */
    tooltip?: TooltipPlacement | 'none';
    /** Tooltip text when it should differ from the accessible name. */
    tooltipText?: string;
    /** How to use it when it is not a plain click ("Hold to park"). */
    hint?: string | null;
    /** Draw the key-hint cap while Mod is held (default true). */
    keyHint?: boolean;
    /** Gallery only: draw the key-hint cap now. */
    forceKeyHint?: boolean;
    /** Content after the label (a count, "7/14"). */
    trailing?: Snippet;
    el?: HTMLButtonElement | null;
  }

  let {
    icon,
    label = '',
    children,
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
    keyHint = true,
    forceKeyHint = false,
    trailing,
    el = $bindable(null),
    type = 'button',
    onclick,
    class: className = '',
    ...rest
  }: Props = $props();

  onMount(() => {
    if (shortcut !== undefined) ensureKeyHints();
  });

  const uid = `ctl-${Math.random().toString(36).slice(2, 9)}`;
  const soft = $derived(!disabled && !!disabledReason);
  const inert = $derived(disabled || soft);
  const textShown = $derived(showLabel || !icon);
  const running = $derived(busy || (progress !== null && !holdRing));
  const glyphPx = $derived(size === 'xs' || size === 's' ? 16 : 20);
  const ringPx = $derived(size === 'xs' ? 20 : size === 's' ? 24 : size === 'l' ? 30 : 28);
  const tipText = $derived.by(() => {
    const base = tooltipText ?? label;
    if (progressText && progress !== null) return `${base} · ${progressText}`;
    // A text button drawn from `children` with no label still explains itself.
    return base || (soft ? 'Unavailable' : '');
  });
  const tipOn = $derived(
    tooltip !== 'none' &&
      !!tipText &&
      (!textShown || !!shortcut || soft || !!error || !!hint || !!tooltipText || progress !== null),
  );
  /** The tooltip's second line, for screen readers too (a tooltip holds nothing found nowhere else). */
  const why = $derived(error || (soft ? disabledReason : null) || hint || null);
  const describedBy = $derived(
    [why ? `${uid}-why` : '', progressText && progress !== null ? `${uid}-progress` : ''].filter(Boolean).join(' ') ||
      undefined,
  );
  const capShown = $derived(keyHint && !!shortcut && !inert && (forceKeyHint || keyHintsVisible()));

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
  {type}
  class="ctl v-{variant} s-{size} {className}"
  class:text-only={!icon}
  class:icon-only={!textShown}
  class:glyph-danger={glyphTone === 'danger'}
  class:layout-toggle={layoutToggle}
  class:is-busy={running}
  class:has-ring={holdRing || progress !== null}
  class:ring-hold={holdRing}
  class:is-inert={inert}
  class:has-error={!!error}
  aria-label={icon && label ? label : undefined}
  aria-pressed={pressed === undefined ? undefined : pressed}
  aria-busy={running || undefined}
  aria-disabled={soft || undefined}
  aria-describedby={describedBy}
  aria-keyshortcuts={shortcut ? ariaShortcut(shortcut) : undefined}
  {disabled}
  onclick={handleClick}
  use:tooltipAction={{
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
    <span class="glyph" style:--ring="{ringPx}px" style:--glyph="{glyphPx}px">
      {#if busy && progress === null}
        <svg class="spinner" class:still={reducedMotion()} viewBox="0 0 24 24" width={glyphPx} height={glyphPx} aria-hidden="true">
          <path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" />
        </svg>
      {:else}
        <Icon name={icon} size={glyphPx} />
      {/if}
      {#if progress !== null || holdRing}
        <Ring
          size={ringPx}
          value={progress}
          track={holdRing && !busy}
          stepped={reducedMotion()}
          tone={variant === 'danger' ? 'danger' : variant === 'primary' ? 'current' : 'accent'}
        />
      {/if}
    </span>
  {:else if busy}
    <svg class="spinner text-spinner" class:still={reducedMotion()} viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
      <path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" />
    </svg>
  {/if}
  {#if textShown}
    <span class="text">{#if children}{@render children()}{:else}{label}{/if}</span>
  {/if}
  {#if trailing}
    <span class="trailing">{@render trailing()}</span>
  {/if}
  {#if error}
    <span class="err-dot" aria-hidden="true"></span>
  {/if}
  {#if why}
    <span id="{uid}-why" class="visually-hidden">{why}</span>
  {/if}
  {#if progressText && progress !== null}
    <span id="{uid}-progress" class="visually-hidden">{progressText}</span>
  {/if}
  {#if capShown && shortcut}
    <kbd class="keyhint" aria-hidden="true">{formatShortcut(shortcut)}</kbd>
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
    flex: none;
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

  .s-xs {
    --h: 24px;
  }
  .s-s {
    --h: var(--control-h-s);
  }
  .s-l {
    --h: var(--control-h-l);
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
  .text-only.s-xs {
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
    width: var(--glyph);
    height: var(--glyph);
    color: var(--glyph-c);
  }
  /* Room for the ring around the glyph; the label does not move when it appears. */
  .has-ring .glyph {
    width: var(--ring);
    height: var(--ring);
    margin: 0 calc((var(--ring) - var(--glyph)) / -2);
  }
  /* A hold ring is always drawn: it takes its own room (no overlap with the label). */
  .ring-hold .glyph {
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

  /* -- Variants (BRAND 8) -------------------------------------------------------- */

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
  .glyph-danger:not(.is-inert) {
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

  /* Pressed: darker fill and a 1 px black inner top edge (no scale, no bounce). */
  .ctl:is(:active, [data-force~='active']):not(.is-inert) {
    --bg-c: var(--pressed-bg);
    --inset: var(--pressed-inset);
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

  /* Toggled on: same glyph, brass state; ghost toggles without outline (several
     toolbar toggles can be on at once: brass outlines would single nothing out). */
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
  /* "Without brass" holds for an outlined layout toggle too (W3: the jog pad's
     "Arrow keys", whose armed state is the pad's one brass edge). */
  .layout-toggle[aria-pressed='true']:not(.v-ghost) {
    --edge: var(--border);
  }
  .ctl[aria-pressed='true']:is(:hover, [data-force~='hover']):not(.is-inert) {
    --bg-c: var(--hover-bg);
  }

  /* Focus: on top of any state, never removed. */
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

  /* Error: the last attempt failed (outline + corner dot; the words in the tip). */
  .has-error:not(.is-inert) {
    --edge: var(--danger);
  }
  .err-dot {
    position: absolute;
    top: -3px;
    right: -3px;
    width: 6px;
    height: 6px;
    border-radius: var(--radius-round);
    background: var(--danger);
    pointer-events: none;
  }

  .is-busy {
    cursor: progress;
  }

  /* Busy: the logo-like arc, 1.5 stroke, 0.9 s per turn; a still arc under reduced motion. */
  .spinner {
    flex: none;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.5;
    stroke-linecap: round;
    animation: spin 0.9s linear infinite;
  }
  .spinner.still {
    animation: none;
  }
  /* A text button keeps its width: the spinner sits in the left padding, the
     label moves over into it. */
  .text-spinner {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 6px;
    margin: auto 0;
  }
  .text-only.is-busy .text {
    transform: translateX(8px);
  }
  .text-only.s-xs .text-spinner {
    left: 3px;
  }
  .text-only.s-xs.is-busy .text {
    transform: translateX(7px);
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

  /* Key hint (Mod held alone): a neutral cap on the lower-right corner, never
     brass (it appears on every control at once). */
  .keyhint {
    position: absolute;
    right: -5px;
    bottom: -6px;
    z-index: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: var(--cap-h);
    height: var(--cap-h);
    padding: 0 3px;
    border: var(--border-w) solid var(--border);
    border-bottom-width: 2px;
    border-radius: var(--radius-s);
    background: var(--surface);
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    line-height: 1;
    pointer-events: none;
    animation: hint-in var(--duration-fast) var(--ease-out);
  }
  @keyframes hint-in {
    from {
      opacity: 0;
    }
  }
</style>

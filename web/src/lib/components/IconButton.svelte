<!--
  Icon-first button: the symbol is the control, the text is its accessible
  name and its tooltip (BRAND.md sections 7 and 8).

  - `label` is required: it becomes aria-label and the tooltip (and the
    visible text with `showLabel`).
  - `shortcut` (spec such as "E", "Shift+A", "Escape") is shown in the tooltip
    and exposed as aria-keyshortcuts. Wiring the key itself is the caller's job.
  - `pressed` (boolean) makes it a toggle button (aria-pressed): same glyph on
    and off, the toggled style carries the state.
  - `busy` swaps the glyph for the logo-like spinner arc, sets aria-busy and
    swallows clicks while the request runs, but keeps focus.
  - `disabledReason` disables the button with aria-disabled instead of the
    disabled attribute, so it stays focusable and its tooltip says why.
  - `glyphTone="danger"` draws only the glyph in --danger on a secondary
    button: a routine stop (live view) that should not light a red outline
    for the whole session; the full danger style stays for motion.
  - `layoutToggle`: a toggle of the screen's layout (panels, strip), on most
    of the time. Its on state is the fill alone with an --fg glyph: brass
    stays for instrument state (live, auto stretch), so it still singles
    something out (BRAND 3 and 8).
  States use tokens only (var(--…)), so every theme including Night Red holds.
-->
<script lang="ts">
  import type { HTMLButtonAttributes } from 'svelte/elements';
  import { ariaShortcut } from '../app/shortcuts';
  import Icon from './Icon.svelte';
  import { tooltip as tooltipAction, type TooltipPlacement } from './tooltip';

  type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';
  type Size = 's' | 'm' | 'l';

  interface Props extends Omit<HTMLButtonAttributes, 'children' | 'aria-pressed' | 'disabled'> {
    icon: string;
    label: string;
    shortcut?: string;
    showLabel?: boolean;
    variant?: Variant;
    size?: Size;
    /** Toggle state; leave undefined for a plain push button. */
    pressed?: boolean;
    busy?: boolean;
    disabled?: boolean;
    /** Why the action is unavailable: disables it and becomes the tooltip. */
    disabledReason?: string | null;
    /** Tooltip side, or 'none'. Labelled buttons only get one for a shortcut or a reason. */
    tooltip?: TooltipPlacement | 'none';
    /** Tooltip text when it should differ from the accessible name. */
    tooltipText?: string;
    /** Colour of the glyph alone (the outline and label keep the variant's). */
    glyphTone?: 'danger';
    /** Toggle of the layout, not of the instrument: neutral on state. */
    layoutToggle?: boolean;
  }

  let {
    icon,
    label,
    shortcut,
    showLabel = false,
    variant = 'secondary',
    size = 'm',
    pressed,
    busy = false,
    disabled = false,
    disabledReason = null,
    tooltip = 'bottom',
    tooltipText,
    glyphTone,
    layoutToggle = false,
    type = 'button',
    onclick,
    class: className = '',
    ...rest
  }: Props = $props();

  const softDisabled = $derived(!disabled && !!disabledReason);
  const inert = $derived(disabled || softDisabled);
  const tipText = $derived(
    softDisabled ? `${tooltipText ?? label}: ${disabledReason}` : (tooltipText ?? label),
  );
  const tipOn = $derived(
    tooltip !== 'none' && (!showLabel || !!shortcut || softDisabled || !!tooltipText),
  );

  function handleClick(e: MouseEvent & { currentTarget: EventTarget & HTMLButtonElement }) {
    if (busy || softDisabled) {
      e.preventDefault();
      return;
    }
    onclick?.(e);
  }
</script>

<button
  {...rest}
  {type}
  class="icon-button {variant} size-{size} {className}"
  class:labelled={showLabel}
  class:glyph-danger={glyphTone === 'danger'}
  class:layout-toggle={layoutToggle}
  class:is-busy={busy}
  class:is-inert={inert}
  aria-label={label}
  aria-pressed={pressed === undefined ? undefined : pressed}
  aria-busy={busy || undefined}
  aria-disabled={softDisabled || undefined}
  aria-keyshortcuts={shortcut ? ariaShortcut(shortcut) : undefined}
  {disabled}
  onclick={handleClick}
  use:tooltipAction={{
    text: tipText,
    shortcut: softDisabled ? undefined : shortcut,
    placement: tooltip === 'none' ? 'bottom' : tooltip,
    disabled: !tipOn,
  }}
>
  <span class="glyph">
    {#if busy}
      <svg class="spinner" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" />
      </svg>
    {:else}
      <Icon name={icon} {size} />
    {/if}
  </span>
  {#if showLabel}
    <span class="text">{label}</span>
  {/if}
</button>

<style>
  .icon-button {
    --btn-icon: var(--icon-m);
    --btn-h: var(--control-h-m);
    --btn-pad: var(--space-2);
    --btn-bg: transparent;
    --btn-fg: var(--fg);
    --btn-glyph: var(--btn-fg);
    --btn-text: var(--btn-fg);
    --btn-border: var(--border);

    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    min-width: var(--btn-h);
    height: var(--btn-h);
    padding: 0 var(--btn-pad);
    margin: 0;
    border: var(--border-w) solid var(--btn-border);
    border-radius: var(--radius-s);
    background: var(--btn-bg);
    color: var(--btn-fg);
    font: inherit;
    font-family: var(--font-ui);
    font-size: var(--text-m);
    font-weight: var(--weight-medium);
    line-height: var(--leading-tight);
    white-space: nowrap;
    cursor: pointer;
    transition:
      background-color var(--duration-fast) var(--ease-standard),
      border-color var(--duration-fast) var(--ease-standard),
      color var(--duration-fast) var(--ease-standard);
    -webkit-tap-highlight-color: transparent;
  }

  .size-s {
    --btn-icon: var(--icon-s);
    --btn-h: var(--control-h-s);
  }
  .size-l {
    --btn-icon: var(--icon-l);
    --btn-h: calc(var(--icon-l) + 2 * var(--space-2) + 2 * var(--border-w));
  }
  .labelled {
    padding: 0 calc(var(--btn-pad) + var(--space-1)) 0 var(--btn-pad);
  }

  .glyph {
    display: inline-flex;
    width: var(--btn-icon);
    height: var(--btn-icon);
    align-items: center;
    justify-content: center;
    color: var(--btn-glyph);
  }
  .glyph :global(.icon) {
    width: var(--btn-icon);
    height: var(--btn-icon);
  }
  .text {
    color: var(--btn-text);
  }

  /* -- Variants: BRAND.md section 8 ----------------------------------------- */

  /* Secondary (outlined): --border outline, --fg content. */
  .secondary:hover:not(.is-inert) {
    --btn-bg: var(--hover-bg);
  }
  .secondary:active:not(.is-inert) {
    --btn-bg: var(--pressed-bg);
  }

  /* Ghost / toolbar: glyph --fg-muted at rest, --fg on hover. */
  .ghost {
    --btn-fg: var(--fg-muted);
    --btn-text: var(--fg);
    --btn-border: transparent;
  }
  .ghost:hover:not(.is-inert) {
    --btn-bg: var(--hover-bg);
    --btn-fg: var(--fg);
  }
  .ghost:active:not(.is-inert) {
    --btn-bg: var(--pressed-bg);
  }

  /* Primary (deliberate): brass fill, dark content; outlined in Night Red. */
  .primary {
    --btn-bg: var(--primary-bg);
    --btn-fg: var(--primary-fg);
    --btn-border: var(--primary-border);
  }
  .primary:hover:not(.is-inert) {
    --btn-bg: var(--primary-bg-hover);
    --btn-fg: var(--primary-fg-hover);
    --btn-border: var(--primary-bg-hover);
  }
  .primary:active:not(.is-inert) {
    --btn-bg: var(--accent-deep);
    --btn-fg: var(--on-accent-deep);
    --btn-border: var(--accent-deep);
  }

  /* Danger: outline and glyph in --danger, the label stays --fg (AA). */
  .danger {
    --btn-bg: var(--surface);
    --btn-border: var(--danger);
    --btn-glyph: var(--danger);
    --btn-text: var(--fg);
  }
  .danger:hover:not(.is-inert),
  .danger:active:not(.is-inert) {
    --btn-bg: var(--danger);
    --btn-glyph: var(--on-danger);
    --btn-text: var(--on-danger);
  }

  .glyph-danger:not(.is-inert) {
    --btn-glyph: var(--danger);
  }

  /* Toggled on: same glyph, brass state. Ghost (toolbar) toggles take the
     fill and the brass glyph without the outline: several can be on at once,
     and brass outlines everywhere would no longer single anything out
     (BRAND 3 and 8). */
  .icon-button[aria-pressed='true'] {
    --btn-bg: var(--toggled-bg);
    --btn-fg: var(--toggled-fg);
    --btn-text: var(--toggled-fg);
    --btn-glyph: var(--toggled-fg);
    --btn-border: var(--toggled-border);
  }
  .ghost[aria-pressed='true'] {
    --btn-border: transparent;
  }
  .layout-toggle[aria-pressed='true'] {
    --btn-fg: var(--fg);
    --btn-text: var(--fg);
    --btn-glyph: var(--fg);
  }
  .icon-button[aria-pressed='true']:hover:not(.is-inert) {
    --btn-bg: var(--hover-bg);
  }

  .icon-button:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }

  .icon-button:disabled,
  .icon-button.is-inert {
    --btn-fg: var(--fg-disabled);
    --btn-glyph: var(--fg-disabled);
    --btn-text: var(--fg-disabled);
    --btn-border: var(--border-soft);
    --btn-bg: transparent;
    cursor: not-allowed;
  }
  .primary:disabled,
  .primary.is-inert {
    --btn-bg: var(--surface);
  }
  .ghost:disabled,
  .ghost.is-inert {
    --btn-border: transparent;
  }

  .is-busy {
    cursor: progress;
  }

  /* Busy: a logo-like arc, 1.5 stroke, 0.9 s per turn; static when motion is reduced. */
  .spinner {
    width: var(--btn-icon);
    height: var(--btn-icon);
    fill: none;
    stroke: currentColor;
    stroke-width: 1.5;
    stroke-linecap: round;
    animation: spin 0.9s linear infinite;
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
</style>

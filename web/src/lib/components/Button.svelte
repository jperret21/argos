<!--
  Text-only button (BRAND 7, row 3): dialog OK / Cancel, confirmations, form
  submits. Same variants and states as IconButton (BRAND 8): primary is the
  deliberate action (brass fill; outlined in Night Red), danger keeps its
  label --fg at rest with a --danger outline.

  - `busy` puts the spinner before the label (the label stays: the observer
    keeps reading what is in progress) without changing the width, sets
    aria-busy and swallows clicks (BRAND 8, as IconButton).
  - `disabledReason` disables it with aria-disabled (still focusable) and
    shows the reason in the tooltip.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLButtonAttributes } from 'svelte/elements';
  import { tooltip as tooltipAction } from './tooltip';

  type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';

  interface Props extends Omit<HTMLButtonAttributes, 'children' | 'disabled'> {
    label?: string;
    children?: Snippet;
    variant?: Variant;
    size?: 's' | 'm';
    busy?: boolean;
    disabled?: boolean;
    disabledReason?: string | null;
  }

  let {
    label,
    children,
    variant = 'secondary',
    size = 'm',
    busy = false,
    disabled = false,
    disabledReason = null,
    type = 'button',
    onclick,
    class: className = '',
    ...rest
  }: Props = $props();

  const soft = $derived(!disabled && !!disabledReason);

  function handleClick(e: MouseEvent & { currentTarget: EventTarget & HTMLButtonElement }) {
    if (busy || soft) {
      e.preventDefault();
      return;
    }
    onclick?.(e);
  }
</script>

<button
  {...rest}
  {type}
  class="button {variant} size-{size} {className}"
  class:is-busy={busy}
  class:is-inert={disabled || soft}
  {disabled}
  aria-busy={busy || undefined}
  aria-disabled={soft || undefined}
  onclick={handleClick}
  use:tooltipAction={{ text: disabledReason ?? '', placement: 'top', disabled: !soft }}
>
  <span class="text">{#if children}{@render children()}{:else}{label}{/if}</span>
  {#if busy}
    <svg class="spinner" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" />
    </svg>
  {/if}
</button>

<style>
  .button {
    --b-bg: transparent;
    --b-fg: var(--fg);
    --b-border: var(--border);
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 72px;
    height: var(--control-h-s);
    padding: 0 var(--space-4);
    margin: 0;
    border: var(--border-w) solid var(--b-border);
    border-radius: var(--radius-s);
    background: var(--b-bg);
    color: var(--b-fg);
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
  }
  .size-s {
    min-width: 0;
    height: 24px;
    padding: 0 var(--space-3);
    font-size: var(--text-s);
  }

  .secondary:hover:not(.is-inert) {
    --b-bg: var(--hover-bg);
  }
  .secondary:active:not(.is-inert) {
    --b-bg: var(--pressed-bg);
  }

  .ghost {
    --b-border: transparent;
  }
  .ghost:hover:not(.is-inert) {
    --b-bg: var(--hover-bg);
  }

  .primary {
    --b-bg: var(--primary-bg);
    --b-fg: var(--primary-fg);
    --b-border: var(--primary-border);
  }
  .primary:hover:not(.is-inert) {
    --b-bg: var(--primary-bg-hover);
    --b-fg: var(--primary-fg-hover);
    --b-border: var(--primary-bg-hover);
  }
  .primary:active:not(.is-inert) {
    --b-bg: var(--accent-deep);
    --b-fg: var(--on-accent-deep);
    --b-border: var(--accent-deep);
  }

  /* Danger: outline in --danger, label --fg at rest (BRAND 4.2). */
  .danger {
    --b-bg: var(--surface);
    --b-border: var(--danger);
  }
  .danger:hover:not(.is-inert),
  .danger:active:not(.is-inert) {
    --b-bg: var(--danger);
    --b-fg: var(--on-danger);
  }

  .button:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }

  .button:disabled,
  .button.is-inert {
    --b-fg: var(--fg-disabled);
    --b-border: var(--border-soft);
    --b-bg: transparent;
    cursor: not-allowed;
  }
  .primary:disabled,
  .primary.is-inert {
    --b-bg: var(--surface);
  }
  .ghost:disabled,
  .ghost.is-inert {
    --b-border: transparent;
  }

  .is-busy {
    cursor: progress;
  }
  /* The label moves over into the padding to make room: the width never changes. */
  .button {
    --busy-left: 6px;
    --busy-shift: 8px;
  }
  .size-s {
    --busy-left: 3px;
    --busy-shift: 7px;
  }
  .is-busy .text {
    transform: translateX(var(--busy-shift));
  }

  .spinner {
    position: absolute;
    top: 0;
    bottom: 0;
    left: var(--busy-left);
    width: 12px;
    height: 12px;
    margin: auto 0;
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

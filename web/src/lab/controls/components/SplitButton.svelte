<!--
  Split button (proposal): the action on the left, its options on the right
  (lib Menu: token-drawn, keyboard, type-ahead, disabled items say why).

  - The main part does the action with the CURRENT options; the options
    in use are visible on it ("2.0 s" after the glyph), so the button says
    what it will do before it is pressed.
  - The chevron part opens the menu (ArrowDown on the main part opens it
    too, as in native split buttons); choosing an option never runs the
    action: one press, one outcome.
  - Both parts share the variant, the hover is per part, one outline.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import { ariaShortcut, formatShortcut } from '../../../lib/app/shortcuts';
  import Icon from '../../../lib/components/Icon.svelte';
  import Menu from '../../../lib/components/Menu.svelte';
  import type { MenuChoice, MenuEntry } from '../../../lib/components/menu';
  import { reduced } from '../env.svelte';
  import { hintsVisible } from '../hints.svelte';
  import { tip } from '../tip';
  import Ring from './Ring.svelte';

  interface Props {
    icon: string;
    label: string;
    /** Visible text on the main part (a label, or the option in use). */
    text?: string;
    /** Mono detail after the text ("2.0 s"). */
    detail?: string;
    variant?: 'ghost' | 'secondary' | 'primary';
    size?: 's' | 'm';
    shortcut?: string;
    items: readonly MenuEntry[];
    menuLabel: string;
    onaction?: () => void;
    onselect?: (item: MenuChoice) => void;
    busy?: boolean;
    progress?: number | null;
    progressText?: string;
    disabledReason?: string | null;
    /** Specimen: show the menu open (live) or a part hovered. */
    open?: boolean;
    force?: 'main' | 'menu' | null;
    extra?: Snippet;
  }

  let {
    icon,
    label,
    text,
    detail,
    variant = 'ghost',
    size = 'm',
    shortcut,
    items,
    menuLabel,
    onaction,
    onselect,
    busy = false,
    progress = null,
    progressText,
    disabledReason = null,
    open = $bindable(false),
    force = null,
    extra,
  }: Props = $props();

  let group: HTMLDivElement | undefined = $state();
  let chevron: HTMLButtonElement | undefined = $state();
  const inert = $derived(!!disabledReason);
  const menuId = `split-${Math.random().toString(36).slice(2, 9)}`;
  const glyphPx = $derived(size === 's' ? 16 : 20);
  const ringPx = $derived(size === 's' ? 24 : 28);
</script>

<div class="split v-{variant} s-{size}" class:inert class:open bind:this={group} role="group" aria-label={label}>
  <button
    type="button"
    class="main"
    class:hov={force === 'main'}
    class:icon-only={!text}
    aria-label={text ? undefined : label}
    aria-busy={busy || progress !== null || undefined}
    aria-disabled={inert || undefined}
    aria-keyshortcuts={shortcut ? ariaShortcut(shortcut) : undefined}
    onclick={() => !inert && !busy && onaction?.()}
    onkeydown={(e) => {
      if (e.key === 'ArrowDown' && !inert) {
        e.preventDefault();
        open = true;
      }
    }}
    use:tip={{
      text: progress !== null && progressText ? `${label} · ${progressText}` : label,
      shortcut: inert ? undefined : shortcut,
      reason: disabledReason,
      hint: inert ? null : '↓ options',
    }}
  >
    <span class="glyph" class:ringed={progress !== null} style:--ring="{ringPx}px">
      {#if busy && progress === null}
        <svg class="spinner" class:still={reduced()} viewBox="0 0 24 24" width={glyphPx} height={glyphPx} aria-hidden="true">
          <path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" />
        </svg>
      {:else}
        <Icon name={icon} size={glyphPx} />
      {/if}
      {#if progress !== null}<Ring size={ringPx} value={progress} stepped={reduced()} />{/if}
    </span>
    {#if text}<span class="text">{text}</span>{/if}
    {#if detail}<span class="detail num">{detail}</span>{/if}
    {#if extra}{@render extra()}{/if}
    {#if shortcut && !inert && hintsVisible()}
      <kbd class="cap keyhint" aria-hidden="true">{formatShortcut(shortcut)}</kbd>
    {/if}
  </button>
  <span class="divider" aria-hidden="true"></span>
  <button
    type="button"
    class="chev"
    class:hov={force === 'menu'}
    bind:this={chevron}
    aria-label="{label} options"
    aria-haspopup="menu"
    aria-expanded={open}
    aria-controls={open ? menuId : undefined}
    aria-disabled={inert || undefined}
    onclick={() => !inert && (open = !open)}
    use:tip={{ text: `${label} options`, disabled: open || inert }}
  >
    <span class="chev-glyph"><Icon name="disclosure" size={16} /></span>
  </button>
</div>

<Menu
  bind:open
  anchor={chevron}
  placeAt={group}
  {items}
  label={menuLabel}
  id={menuId}
  start="checked"
  onselect={(item) => onselect?.(item)}
/>

<style>
  .split {
    --h: var(--control-h-m);
    --edge: var(--border);
    position: relative;
    display: inline-flex;
    align-items: stretch;
    height: var(--h);
    border: var(--border-w) solid var(--edge);
    border-radius: var(--radius-s);
    background: transparent;
  }
  .s-s {
    --h: var(--control-h-s);
  }
  .v-ghost {
    --edge: transparent;
  }
  .v-ghost:hover:not(.inert),
  .v-ghost.open {
    --edge: var(--border-soft);
  }
  .v-primary {
    --edge: var(--primary-border);
  }

  .main,
  .chev {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    margin: 0;
    border: none;
    background: transparent;
    color: var(--fg-muted);
    font-size: var(--text-m);
    font-weight: var(--weight-medium);
    white-space: nowrap;
    cursor: pointer;
    transition:
      background-color var(--duration-instant) var(--ease-standard),
      color var(--duration-fast) var(--ease-standard);
  }
  .main {
    min-width: calc(var(--h) - 2px);
    padding: 0 var(--space-2) 0 var(--space-2);
    border-radius: 1px 0 0 1px;
  }
  .main:not(.icon-only) {
    padding-right: var(--space-3);
  }
  .chev {
    width: 18px;
    padding: 0;
    border-radius: 0 1px 1px 0;
  }
  .v-secondary .main,
  .v-secondary .chev {
    color: var(--fg);
  }
  .v-primary .main,
  .v-primary .chev {
    background: var(--primary-bg);
    color: var(--primary-fg);
  }
  .text {
    color: var(--fg);
  }
  .v-primary .text {
    color: var(--primary-fg);
  }
  .detail {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .v-primary .detail {
    color: var(--primary-fg);
  }

  .main:is(:hover, .hov):not([aria-disabled='true']),
  .chev:is(:hover, .hov):not([aria-disabled='true']) {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .v-primary .main:is(:hover, .hov),
  .v-primary .chev:is(:hover, .hov) {
    background: var(--primary-bg-hover);
    color: var(--primary-fg-hover);
  }
  .main:active:not([aria-disabled='true']),
  .chev:active:not([aria-disabled='true']),
  .chev[aria-expanded='true'] {
    background: var(--pressed-bg);
    box-shadow: var(--lab-pressed-inset);
  }
  .main:focus-visible,
  .chev:focus-visible {
    z-index: 1;
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }

  .divider {
    width: 1px;
    margin: 6px 0;
    background: var(--border-soft);
  }
  .v-ghost .divider {
    background: var(--border-soft);
  }
  .v-primary .divider {
    margin: 0;
    background: var(--primary-border);
  }

  .glyph {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .glyph.ringed {
    width: var(--ring);
    height: var(--ring);
    margin: 0 calc((var(--ring) - 20px) / -2);
  }
  .chev-glyph {
    display: inline-flex;
    transition: transform var(--duration-fast) var(--ease-standard);
  }
  .open .chev-glyph {
    transform: rotate(180deg);
  }

  .inert .main,
  .inert .chev {
    color: var(--fg-disabled);
    cursor: not-allowed;
  }
  .inert .text {
    color: var(--fg-disabled);
  }

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

  .keyhint {
    position: absolute;
    right: -5px;
    bottom: -6px;
    z-index: 2;
    min-width: 15px;
    height: 15px;
    padding: 0 3px;
    border-color: var(--accent);
    background: var(--bg);
    color: var(--fg);
    pointer-events: none;
  }
</style>

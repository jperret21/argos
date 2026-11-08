<!--
  Split button (BRAND 7 "An action with options"; web/lab/PROPOSAL.md 3.3 and
  6, W3; promoted from src/lab/controls/components/SplitButton.svelte): the
  action on the left, its options on the right (lib Menu: token-drawn,
  keyboard, type-ahead, unavailable items say why).

  - The main part does the action with the CURRENT options, and those
    options are written on it ("2.0 s" after the glyph): the button says
    what it will do before it is pressed (Capture, Autofocus).
  - The chevron opens the options; ArrowDown on the main part opens them
    too (as native split buttons). Choosing an option NEVER runs the
    action: one press, one outcome.
  - States as Control (BRAND 8): rest, hover per part, pressed
    (--pressed-inset), focus ring per part, unavailable with the reason
    (aria-disabled, still focusable, explained on press), busy (spinner,
    width unchanged), progress (the time ring: an exposure, a sweep), error
    (danger edge + corner dot, the words in the tooltip), key-hint cap
    (neutral). The options stay reachable while the action cannot run
    (`optionsReason` is separate): an observer may set the next exposure
    before the camera is connected.
  - `force` pins a part's hover and `open` shows the menu (gallery).
  Tokens only (every theme, Night Red included).
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { ensureKeyHints, keyHintsVisible } from '../app/keyhints.svelte';
  import { ariaShortcut, formatShortcut } from '../app/shortcuts';
  import Icon from './Icon.svelte';
  import Menu from './Menu.svelte';
  import type { MenuChoice, MenuEntry } from './menu';
  import { reducedMotion } from './motion.svelte';
  import Ring from './Ring.svelte';
  import { splitMainName } from './split';
  import { tooltip } from './tooltip';

  interface Props {
    icon: string;
    /** The action ("Capture", "Autofocus"): accessible name and tooltip. */
    label: string;
    /** Visible text on the main part (default: none, icon only). */
    text?: string;
    /** The options in use, in mono after the text ("2.0 s", "2.0 s · 80"). */
    detail?: string;
    /** The widest `detail` it can show: its width is reserved (no reflow when the value changes). */
    detailMin?: string;
    variant?: 'ghost' | 'secondary' | 'primary';
    size?: 's' | 'm';
    shortcut?: string;
    items: readonly MenuEntry[];
    /** Accessible name of the menu (default "<label> options"). */
    menuLabel?: string;
    onaction?: () => void;
    onselect?: (item: MenuChoice) => void;
    busy?: boolean;
    /** Elapsed fraction of the running action (0..1), or null. */
    progress?: number | null;
    progressText?: string;
    /** Why the action cannot run now. */
    disabledReason?: string | null;
    /** The main part stays pressable while it shows progress: it STOPS the running action (Autofocus -> Stop AF). */
    stoppable?: boolean;
    /** Why the options cannot be changed now (default: they can). */
    optionsReason?: string | null;
    /** What failed on the last attempt. */
    error?: string | null;
    /** Gallery: the menu open, a part hovered, the key-hint cap. */
    open?: boolean;
    force?: 'main' | 'menu' | null;
    forceKeyHint?: boolean;
    /** Tooltip side. */
    placement?: 'top' | 'bottom' | 'left' | 'right';
  }

  let {
    icon,
    label,
    text,
    detailMin,
    detail,
    variant = 'secondary',
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
    stoppable = false,
    optionsReason = null,
    error = null,
    open = $bindable(false),
    force = null,
    forceKeyHint = false,
    placement = 'bottom',
  }: Props = $props();

  onMount(() => {
    if (shortcut) ensureKeyHints();
  });

  const uid = `split-${Math.random().toString(36).slice(2, 9)}`;
  let group: HTMLDivElement | undefined = $state();
  let chevron: HTMLButtonElement | undefined = $state();

  const inert = $derived(!!disabledReason);
  const optionsInert = $derived(!!optionsReason);
  const running = $derived(busy || progress !== null);
  const glyphPx = $derived(size === 's' ? 16 : 20);
  const ringPx = $derived(size === 's' ? 24 : 28);
  const name = $derived(splitMainName(label, text, detail));
  const why = $derived(error || disabledReason || null);
  const capShown = $derived(!!shortcut && !inert && (forceKeyHint || keyHintsVisible()));

  function act(): void {
    if (inert || (running && !(stoppable && !busy))) return;
    onaction?.();
  }

  function openMenu(): void {
    if (optionsInert) return;
    open = true;
  }
</script>

<div
  class="split v-{variant} s-{size}"
  class:inert
  class:open
  class:has-error={!!error && !inert}
  bind:this={group}
  role="group"
  aria-label={label}
>
  <button
    type="button"
    class="main"
    class:hov={force === 'main'}
    class:icon-only={!text && !detail}
    class:ringed={progress !== null}
    aria-label={name}
    aria-busy={running || undefined}
    aria-disabled={inert || undefined}
    aria-keyshortcuts={shortcut ? ariaShortcut(shortcut) : undefined}
    aria-describedby={why || (progressText && progress !== null) ? `${uid}-why` : undefined}
    onclick={act}
    onkeydown={(e) => {
      if (e.key === 'ArrowDown' && !e.altKey && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        openMenu();
      }
    }}
    use:tooltip={{
      text: progress !== null && progressText ? `${name} · ${progressText}` : name,
      shortcut: inert ? undefined : shortcut,
      reason: disabledReason,
      error,
      hint: inert || optionsInert ? null : '↓ shows the options',
      placement,
    }}
  >
    <span class="glyph" style:--ring="{ringPx}px" style:--glyph="{glyphPx}px">
      {#if busy && progress === null}
        <svg class="spinner" class:still={reducedMotion()} viewBox="0 0 24 24" width={glyphPx} height={glyphPx} aria-hidden="true">
          <path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" />
        </svg>
      {:else}
        <Icon name={icon} size={glyphPx} />
      {/if}
      {#if progress !== null}
        <Ring size={ringPx} value={progress} stepped={reducedMotion()} tone={variant === 'primary' ? 'current' : 'accent'} />
      {/if}
    </span>
    {#if text}<span class="text">{text}</span>{/if}
    {#if detail}
      <span class="detail" class:alone={!text} class:sized={!!detailMin}>
        {#if detailMin}<span class="sizer" aria-hidden="true">{detailMin}</span>{/if}<span class="cur">{detail}</span>
      </span>
    {/if}
    {#if capShown && shortcut}
      <kbd class="keyhint" aria-hidden="true">{formatShortcut(shortcut)}</kbd>
    {/if}
  </button>
  <span class="divider" aria-hidden="true"></span>
  <button
    type="button"
    class="chev"
    class:hov={force === 'menu'}
    bind:this={chevron}
    aria-label={menuLabel ?? `${label} options`}
    aria-haspopup="menu"
    aria-expanded={open}
    aria-controls={open ? `${uid}-menu` : undefined}
    aria-disabled={optionsInert || undefined}
    onclick={() => (optionsInert ? undefined : (open = !open))}
    use:tooltip={{ text: menuLabel ?? `${label} options`, reason: optionsReason, disabled: open, placement }}
  >
    <span class="chev-glyph"><Icon name="disclosure" size={16} /></span>
  </button>
  {#if error && !inert}<span class="err-dot" aria-hidden="true"></span>{/if}
  {#if why || (progressText && progress !== null)}
    <span id="{uid}-why" class="visually-hidden">{why ?? progressText}</span>
  {/if}
</div>

<Menu
  bind:open
  anchor={chevron}
  placeAt={group}
  {items}
  label={menuLabel ?? `${label} options`}
  id="{uid}-menu"
  start="checked"
  onselect={(item) => onselect?.(item)}
/>

<style>
  .split {
    --h: var(--control-h-m);
    --edge: var(--border);
    --part-fg: var(--fg);
    position: relative;
    display: inline-flex;
    flex: none;
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
    --part-fg: var(--fg-muted);
  }
  .v-ghost:hover:not(.inert),
  .v-ghost.open {
    --edge: var(--border-soft);
  }
  .v-primary {
    --edge: var(--primary-border);
  }
  .has-error {
    --edge: var(--danger);
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
    color: var(--part-fg);
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
      color var(--duration-fast) var(--ease-standard);
  }
  .main {
    /* 2 px more than Control: the time ring around the glyph keeps clear of the options text. */
    gap: calc(var(--space-2) + 2px);
    min-width: calc(var(--h) - 2px);
    padding: 0 var(--space-3) 0 var(--space-2);
    border-radius: 1px 0 0 1px;
  }
  .main.icon-only {
    padding: 0;
  }
  .chev {
    width: 18px;
    padding: 0;
    border-radius: 0 1px 1px 0;
  }
  .v-primary .main,
  .v-primary .chev {
    background: var(--primary-bg);
    color: var(--primary-fg);
  }
  .text {
    color: var(--fg);
  }
  .detail {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    font-variant-numeric: var(--numeric);
  }
  /* The widest value reserves the width; the value in use sits over it, left-aligned. */
  .detail.sized {
    display: inline-grid;
  }
  .detail.sized > * {
    grid-area: 1 / 1;
    white-space: nowrap;
  }
  .detail .sizer {
    visibility: hidden;
  }
  /* The options written alone after the glyph ("2.0 s") read as the button's text. */
  .detail.alone {
    color: var(--fg);
    font-size: var(--text-s);
  }
  /* On brass the words take the part's own colour, so hover and press keep them legible (Night Red included). */
  .v-primary .text,
  .v-primary .detail {
    color: inherit;
  }

  .glyph {
    position: relative;
    display: inline-flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: var(--glyph);
    height: var(--glyph);
  }
  .ringed .glyph {
    width: var(--ring);
    height: var(--ring);
    margin: 0 calc((var(--ring) - var(--glyph)) / -2);
  }

  /* Hover per part; the group's edge shows on a ghost split. */
  .main:is(:hover, .hov):not([aria-disabled='true']),
  .chev:is(:hover, .hov):not([aria-disabled='true']) {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .v-primary .main:is(:hover, .hov):not([aria-disabled='true']),
  .v-primary .chev:is(:hover, .hov):not([aria-disabled='true']) {
    background: var(--primary-bg-hover);
    color: var(--primary-fg-hover);
  }
  /* Pressed: darker fill and the 1 px black inner top edge (no scale). */
  .main:active:not([aria-disabled='true']),
  .chev:active:not([aria-disabled='true']),
  .chev[aria-expanded='true'] {
    background: var(--pressed-bg);
    box-shadow: var(--pressed-inset);
  }
  .v-primary .main:active:not([aria-disabled='true']) {
    background: var(--accent-deep);
    color: var(--on-accent-deep);
  }
  .main:focus-visible,
  .chev:focus-visible {
    z-index: 1;
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }

  .divider {
    flex: none;
    width: 1px;
    margin: 6px 0;
    background: var(--border-soft);
  }
  .v-primary .divider {
    margin: 0;
    background: var(--primary-border);
  }

  .chev-glyph {
    display: inline-flex;
    transition: transform var(--duration-fast) var(--ease-standard);
  }
  .open .chev-glyph {
    transform: rotate(180deg);
  }

  /* Unavailable: the action part only (the options may stay usable). */
  .main[aria-disabled='true'],
  .chev[aria-disabled='true'] {
    color: var(--fg-disabled);
    cursor: not-allowed;
  }
  .main[aria-disabled='true'] .text,
  .main[aria-disabled='true'] .detail {
    color: var(--fg-disabled);
  }
  .v-primary .main[aria-disabled='true'],
  .v-primary.inert .chev {
    background: var(--surface);
    color: var(--fg-disabled);
  }
  .v-primary.inert {
    --edge: var(--border-soft);
  }
  .main[aria-busy='true'] {
    cursor: progress;
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

  /* Key hint (Mod held alone): neutral cap, never brass (as Control). */
  .keyhint {
    position: absolute;
    right: -5px;
    bottom: -6px;
    z-index: 2;
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
  }
</style>

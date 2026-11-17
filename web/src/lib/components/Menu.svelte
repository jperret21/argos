<!--
  Menu (README 3.1: context and dropdown menus; Help popover, Presets, the
  viewer's context menu, plot cell menus). Token-drawn, never a native menu
  (Night Red), WAI-ARIA menu pattern:

  - ↑ / ↓ move (wrapping), Home / End jump, typing letters jumps to the next
    item that starts with them, Enter or Space chooses, Escape closes, Tab
    closes; focus returns to the trigger.
  - Disabled items stay focusable and say why (second line), so a keyboard
    or screen-reader user learns the reason too; choosing one does nothing.
  - Anchored to an element (`anchor`) or to a point (`point`, right-click).
  - Items: actions, checkbox / radio items (aria-checked, a drawn check),
    separators and group headers; `header` adds a non-interactive top block
    (the Help popover's version line).
  - `preview` draws it in place with `previewActive` highlighted (gallery).
-->
<script lang="ts">
  import NumText from './NumText.svelte';
  import type { Snippet } from 'svelte';
  import { formatShortcut } from '../app/shortcuts';
  import { FocusReturn, focusTargetOf } from './focus';
  import Icon from './Icon.svelte';
  import { type CloseReason, floating, layer, portal } from './layers';
  import { isTypeaheadKey, navTarget, Typeahead } from './listnav';
  import { entryLabel, isChoice, type MenuAction, type MenuChoice, type MenuEntry } from './menu';
  import type { Placement } from './position';

  interface Props {
    open?: boolean;
    /** The trigger: focus returns to it, a press on it does not count as outside. */
    anchor?: HTMLElement | null;
    /** Position next to this element instead of the trigger (a rail footer row). */
    placeAt?: HTMLElement | null;
    point?: { x: number; y: number } | null;
    items: readonly MenuEntry[];
    /** Accessible name of the menu ("Help", "Image"). */
    label: string;
    onselect?: (item: MenuChoice) => void;
    header?: Snippet;
    placement?: Placement;
    minWidth?: number;
    /** Where the cursor starts: first item, last item (opened with ↑), or the checked one. */
    start?: 'first' | 'last' | 'checked';
    /** Keep the menu open after a checkbox item is toggled. */
    keepOpenOnCheck?: boolean;
    onclose?: (reason: CloseReason) => void;
    preview?: boolean;
    previewActive?: number;
    id?: string;
  }

  let {
    open = $bindable(false),
    anchor = null,
    placeAt = null,
    point = null,
    items,
    label,
    onselect,
    header,
    placement = 'bottom-start',
    minWidth = 220,
    start = 'first',
    keepOpenOnCheck = false,
    onclose,
    preview = false,
    previewActive = -1,
    id = `menu-${Math.random().toString(36).slice(2, 9)}`,
  }: Props = $props();

  let active = $state(-1);
  const typeahead = new Typeahead();
  /** Where focus goes back when the menu closes (set while it is open). */
  let back: FocusReturn | null = null;
  const skip = (i: number) => !isChoice(items[i]);
  let menuEl: HTMLElement | undefined = $state();

  function itemEl(i: number): HTMLElement | null {
    return menuEl?.querySelector<HTMLElement>(`[data-index="${i}"]`) ?? null;
  }

  function moveTo(i: number): void {
    if (i < 0) return;
    active = i;
    itemEl(i)?.focus({ preventScroll: false });
  }

  function close(reason: CloseReason): void {
    open = false;
    onclose?.(reason);
  }

  function choose(i: number): void {
    const item = items[i];
    if (!item || !isChoice(item) || item.disabledReason) return;
    if (item.kind === 'checkbox' && keepOpenOnCheck) {
      onselect?.(item);
      return;
    }
    // Focus goes back to the trigger before the action runs, so a dialog the
    // action opens remembers the trigger and returns focus to it.
    back?.restore();
    back = null;
    close('action');
    onselect?.(item);
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Escape') return; // the layer stack closes the top layer
    e.stopPropagation(); // keys used in a menu are not shortcuts ("E" is type-ahead here)
    const target = navTarget(e.key, items.length, active, skip);
    if (target !== null) {
      e.preventDefault();
      moveTo(target);
      return;
    }
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      choose(active);
      return;
    }
    if (e.key === 'Tab') {
      e.preventDefault();
      close('tab');
      return;
    }
    if (isTypeaheadKey(e)) {
      e.preventDefault();
      const i = typeahead.push(e.key, items.map(entryLabel), active, skip);
      if (i >= 0) moveTo(i);
    }
  }

  function startIndex(): number {
    if (start === 'checked') {
      const i = items.findIndex((e) => checkedOf(e) === true);
      if (i >= 0) return i;
    }
    return navTarget(start === 'last' ? 'End' : 'Home', items.length, -1, skip) ?? -1;
  }

  function behaviour(node: HTMLElement) {
    back = new FocusReturn(document, focusTargetOf(anchor));
    typeahead.reset();
    queueMicrotask(() => {
      const i = startIndex();
      if (i >= 0) moveTo(i);
      else node.focus();
    });
    return {
      destroy() {
        const pending = back;
        back = null;
        const a = document.activeElement;
        if (pending && (!a || a === document.body || !a.isConnected)) queueMicrotask(() => pending.restore());
      },
    };
  }

  function checkedOf(e: MenuEntry): boolean | undefined {
    return isChoice(e) && (e.kind === 'checkbox' || e.kind === 'radio') ? e.checked : undefined;
  }

  function isDanger(e: MenuChoice): boolean {
    return (e.kind === undefined || e.kind === 'item') && !!(e as MenuAction).danger;
  }

  function roleOf(e: MenuChoice): 'menuitem' | 'menuitemcheckbox' | 'menuitemradio' {
    return e.kind === 'checkbox' ? 'menuitemcheckbox' : e.kind === 'radio' ? 'menuitemradio' : 'menuitem';
  }
</script>

{#snippet list(live: boolean)}
  <div
    class="menu"
    class:preview={!live}
    {id}
    role="menu"
    aria-label={label}
    tabindex="-1"
    style:min-width="{minWidth}px"
    bind:this={menuEl}
    onkeydown={live ? onKeydown : undefined}
  >
    {#if header}<div class="header" role="presentation">{@render header()}</div>{/if}
    {#each items as e, i (e.id ?? `${e.kind}-${i}`)}
      {#if e.kind === 'separator'}
        <div class="sep" role="separator"></div>
      {:else if e.kind === 'header'}
        <div class="group" role="presentation">{e.label}</div>
      {:else}
        {@const checked = checkedOf(e)}
        {@const disabled = !!e.disabledReason}
        <div
          class="item"
          class:active={live ? active === i : previewActive === i}
          class:disabled
          class:danger={isDanger(e)}
          role={roleOf(e)}
          aria-checked={checked}
          aria-disabled={disabled || undefined}
          tabindex="-1"
          data-index={i}
          onclick={() => live && choose(i)}
          onpointermove={() => {
            if (live && active !== i) moveTo(i);
          }}
        >
          <span class="lead" aria-hidden="true">
            {#if checked !== undefined}
              <span class="check" class:on={checked} class:radio={e.kind === 'radio'}></span>
            {:else if e.icon}
              <Icon name={e.icon} size="s" />
            {/if}
          </span>
          <span class="text">
            <span class="label"><NumText text={e.label} /></span>
            {#if e.disabledReason || e.detail}
              <span class="detail">{e.disabledReason ?? e.detail}</span>
            {/if}
          </span>
          {#if e.shortcut}<kbd class="kbd">{formatShortcut(e.shortcut)}</kbd>{/if}
        </div>
      {/if}
    {/each}
  </div>
{/snippet}

{#if open}
  {#if preview}
    {@render list(false)}
  {:else}
    <div
      class="float"
      use:portal
      use:floating={{ anchor: placeAt ?? anchor, point, placement, gap: 4 }}
      use:layer={{ kind: 'menu', anchor, onclose: close }}
      use:behaviour
    >
      {@render list(true)}
    </div>
  {/if}
{/if}

<style>
  .float {
    z-index: var(--z-popover);
  }

  .menu {
    display: flex;
    flex-direction: column;
    max-width: min(360px, calc(100vw - 16px));
    max-height: calc(100vh - 16px);
    padding: var(--space-1) 0;
    overflow-y: auto;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg);
    box-shadow: var(--shadow-2);
    color: var(--fg);
    font-size: var(--text-m);
    animation: enter var(--duration-base) var(--ease-out);
  }
  .menu:focus {
    outline: none;
  }
  .menu.preview {
    animation: none;
  }

  .header {
    padding: var(--space-2) var(--space-4) var(--space-3);
    margin-bottom: var(--space-1);
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }

  .group {
    padding: var(--space-2) var(--space-4) var(--space-1);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }

  .sep {
    height: 1px;
    margin: var(--space-1) 0;
    background: var(--border-soft);
  }

  .item {
    display: grid;
    grid-template-columns: 16px minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-3);
    min-height: 28px;
    padding: var(--space-1) var(--space-4) var(--space-1) var(--space-3);
    color: var(--fg);
    cursor: pointer;
    outline: none;
  }
  .item.active {
    background: var(--hover-bg);
  }
  .item:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: calc(-1 * var(--focus-ring-w));
  }
  .item.disabled {
    cursor: not-allowed;
  }
  .item.disabled .label,
  .item.disabled .lead {
    color: var(--fg-disabled);
  }

  .lead {
    display: inline-flex;
    width: 16px;
    height: 16px;
    align-items: center;
    justify-content: center;
    color: var(--fg-muted);
  }
  .item.active .lead {
    color: var(--fg);
  }
  .danger .lead {
    color: var(--danger);
  }

  /* Drawn marks (no Unicode check glyphs, BRAND 4.3). */
  .check {
    width: 12px;
    height: 12px;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
  }
  .check.radio {
    border-radius: var(--radius-round);
  }
  .check.on {
    position: relative;
    border-color: var(--fg);
  }
  .check.on::after {
    content: '';
    position: absolute;
    left: 3px;
    top: 0;
    width: 4px;
    height: 7px;
    border: solid var(--fg);
    border-width: 0 1.5px 1.5px 0;
    transform: rotate(45deg);
  }
  .check.radio.on::after {
    left: 2px;
    top: 2px;
    width: 6px;
    height: 6px;
    border: none;
    border-radius: var(--radius-round);
    background: var(--fg);
    transform: none;
  }

  .text {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .detail {
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-tight);
  }

  .kbd {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }

  @keyframes enter {
    from {
      opacity: 0;
      transform: translateY(4px);
    }
  }
</style>

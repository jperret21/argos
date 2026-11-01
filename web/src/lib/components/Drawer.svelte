<!--
  Bottom drawer of a section (README 1.1, 3.1; D5, D17): tabs (the Log tab
  exists in every section), the active tab's tools on the same 32 px row,
  a close button, and a height handle. The drawer shrinks the section; it
  never covers the image.

  - Tabs: WAI-ARIA tabs (← → Home End move between tabs, the panel follows),
    a problem badge per tab (count of unseen warnings and errors).
  - Height: drag the handle, or focus it and use ↑ ↓ (16 px, Shift 64 px),
    Home / End (min / max). Between `minHeight` (160 px) and `maxHeight`
    (half the section, given by the parent). `resizable={false}` hides the
    handle when the parent's layout fixes the height.
  - State (open, tab, height) belongs to the caller, typically a
    SectionLayout (argos.drawer.<section>).
-->
<script lang="ts" module>
  export interface DrawerTab {
    id: string;
    label: string;
    icon?: string;
    /** Unseen problems (warnings, errors): drawn as a count badge. */
    badge?: number | null;
  }
</script>

<script lang="ts">
  import type { Snippet } from 'svelte';
  import { clampDrawerHeight, DRAWER_MIN_HEIGHT } from '../app/panels';
  import Icon from './Icon.svelte';
  import IconButton from './IconButton.svelte';

  interface Props {
    /** Accessible name of the region ("Observe drawer"). */
    label: string;
    tabs: readonly DrawerTab[];
    tab: string;
    height?: number;
    minHeight?: number;
    maxHeight?: number;
    resizable?: boolean;
    /** The active tab's tools, right of the tabs (filters, search, copy…). */
    tools?: Snippet<[string]>;
    /** The active tab's content. */
    children: Snippet<[string]>;
    ontab?: (id: string) => void;
    onheight?: (px: number) => void;
    onclose?: () => void;
    /** Shortcut shown on the close button's tooltip (L for the log, D for the drawer). */
    closeShortcut?: string;
  }

  let {
    label,
    tabs,
    tab = $bindable(),
    height = $bindable(216),
    minHeight = DRAWER_MIN_HEIGHT,
    maxHeight = 480,
    resizable = true,
    tools,
    children,
    ontab,
    onheight,
    onclose,
    closeShortcut,
  }: Props = $props();

  const uid = `drw-${Math.random().toString(36).slice(2, 9)}`;
  const current = $derived(tabs.find((t) => t.id === tab) ?? tabs[0]);
  let tabList: HTMLElement | undefined = $state();

  function setTab(id: string, focus = false): void {
    if (id !== tab) {
      tab = id;
      ontab?.(id);
    }
    if (focus) queueMicrotask(() => tabList?.querySelector<HTMLElement>(`[data-tab="${id}"]`)?.focus());
  }

  function onTabKey(e: KeyboardEvent): void {
    const i = tabs.findIndex((t) => t.id === current?.id);
    let next = -1;
    if (e.key === 'ArrowRight') next = (i + 1) % tabs.length;
    else if (e.key === 'ArrowLeft') next = (i - 1 + tabs.length) % tabs.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = tabs.length - 1;
    if (next < 0) return;
    e.preventDefault();
    e.stopPropagation();
    setTab(tabs[next].id, true);
  }

  function setHeight(px: number): void {
    const h = clampDrawerHeight(px, maxHeight, minHeight);
    if (h !== height) {
      height = h;
      onheight?.(h);
    }
  }

  function onHandleKey(e: KeyboardEvent): void {
    const step = e.shiftKey ? 64 : 16;
    let h: number | null = null;
    if (e.key === 'ArrowUp') h = height + step;
    else if (e.key === 'ArrowDown') h = height - step;
    else if (e.key === 'Home') h = maxHeight;
    else if (e.key === 'End') h = minHeight;
    if (h === null) return;
    e.preventDefault();
    e.stopPropagation();
    setHeight(h);
  }

  function onHandleDown(e: PointerEvent & { currentTarget: HTMLElement }): void {
    if (e.button !== 0) return;
    const handle = e.currentTarget;
    const startY = e.clientY;
    const startH = height;
    handle.setPointerCapture(e.pointerId);
    const move = (ev: PointerEvent) => setHeight(startH + (startY - ev.clientY));
    const up = () => {
      handle.removeEventListener('pointermove', move);
      handle.removeEventListener('pointerup', up);
      handle.removeEventListener('pointercancel', up);
    };
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', up);
    handle.addEventListener('pointercancel', up);
  }
</script>

<section class="drawer" aria-label={label} style:height={resizable ? `${height}px` : undefined}>
  {#if resizable}
    <!-- A focusable separator with a value is a widget (WAI-ARIA window
         splitter); the linter only knows the static separator. -->
    <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
    <div
      class="handle"
      role="separator"
      aria-orientation="horizontal"
      aria-label="Drawer height"
      aria-valuenow={height}
      aria-valuemin={minHeight}
      aria-valuemax={maxHeight}
      tabindex="0"
      onkeydown={onHandleKey}
      onpointerdown={onHandleDown}
    ></div>
  {/if}
  <header>
    <div class="tabs" role="tablist" aria-label="{label} tabs" bind:this={tabList}>
      {#each tabs as t (t.id)}
        {@const selected = t.id === current?.id}
        <button
          type="button"
          class="tab"
          class:selected
          role="tab"
          id="{uid}-tab-{t.id}"
          data-tab={t.id}
          aria-selected={selected}
          aria-controls="{uid}-panel"
          tabindex={selected ? 0 : -1}
          onclick={() => setTab(t.id)}
          onkeydown={onTabKey}
        >
          {#if t.icon}<Icon name={t.icon} size="s" />{/if}
          <span>{t.label}</span>
          {#if t.badge}
            <span class="badge num" aria-label="{t.badge} new warnings or errors">{t.badge}</span>
          {/if}
        </button>
      {/each}
    </div>
    <div class="tools">
      {#if tools && current}{@render tools(current.id)}{/if}
    </div>
    {#if onclose}
      <IconButton
        icon="close"
        label="Close the drawer"
        variant="ghost"
        size="s"
        tooltip="top"
        shortcut={closeShortcut}
        onclick={() => onclose?.()}
      />
    {/if}
  </header>
  <div class="panel" id="{uid}-panel" role="tabpanel" aria-labelledby="{uid}-tab-{current?.id}">
    {#if current}{@render children(current.id)}{/if}
  </div>
</section>

<style>
  .drawer {
    position: relative;
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    border-top: var(--border-w) solid var(--border);
    background: var(--bg-2);
  }

  .handle {
    position: absolute;
    top: -4px;
    left: 0;
    right: 0;
    z-index: 1;
    height: 8px;
    cursor: row-resize;
    outline: none;
  }
  .handle:hover::after,
  .handle:focus-visible::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    top: 3px;
    height: 2px;
    background: var(--fg-muted);
  }
  .handle:focus-visible::after {
    background: var(--focus-ring);
  }

  header {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: 32px;
    padding: 0 var(--space-1) 0 0;
    border-bottom: var(--border-w) solid var(--border-soft);
  }

  .tabs {
    display: flex;
    align-self: stretch;
  }

  .tab {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: 0 var(--space-4);
    border: none;
    border-right: var(--border-w) solid var(--border-soft);
    background: transparent;
    color: var(--text-muted);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
    white-space: nowrap;
    cursor: pointer;
  }
  .tab :global(.icon) {
    color: var(--fg-muted);
  }
  .tab:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  /* Always one tab selected, as a segmented choice: no brass (BRAND 8). */
  .tab.selected {
    background: var(--bg);
    color: var(--fg);
  }
  .tab.selected::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    bottom: -1px;
    height: 2px;
    background: var(--fg);
  }
  .tab.selected :global(.icon) {
    color: var(--fg);
  }
  .tab:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -2px;
  }

  .badge {
    min-width: 18px;
    padding: 0 var(--space-1);
    border: var(--border-w) solid var(--danger);
    border-radius: var(--radius-round);
    color: var(--fg);
    font-size: var(--text-2xs);
    line-height: 14px;
    text-align: center;
  }

  .tools {
    display: flex;
    flex: 1;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-2);
    min-width: 0;
  }

  .panel {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
</style>

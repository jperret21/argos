<!--
  Toolbar built from data, with priority overflow (web/lab/PROPOSAL.md 3.3
  and 6, W3; promoted from src/lab/controls/components/Toolbar.svelte;
  README 1.1 "toolbars take one row each", BRAND 11.1 "no dead bands").

  - One row, groups separated by a rule; run-critical tools (priority
    Infinity) never move. When the row is too narrow, the lowest
    priorities leave first, from the end of their group, into an overflow
    menu whose trigger shows HOW MANY tools it holds ("3"), so nothing
    disappears silently. In the menu, toggles keep their state (check
    marks) and every tool its shortcut: the keyboard path is unchanged.
  - Natural widths are measured ONCE from the row itself, per tool and per
    text it shows (labels and readouts change width, icons do not), or
    declared (`ToolDef.width`). No hidden copy of the toolbar. The fit is
    pure (toolbar.ts, unit-tested).
  - Keyboard: ONE tab stop for the row (roving tabindex): Tab enters on the
    last focused tool, ← → move between tools and the parts of a split
    button, Home / End jump, ↓ on a split button opens its options. The
    shortcuts of the registry keep working from anywhere.
  Tools are Control (button, toggle) and SplitButton, so their states
  (unavailable + reason, busy, progress ring, error, key hint) are the
  product's one implementation.
-->
<script lang="ts">
  import Control from './Control.svelte';
  import Icon from './Icon.svelte';
  import Menu from './Menu.svelte';
  import type { MenuChoice } from './menu';
  import SplitButton from './SplitButton.svelte';
  import { estimateWidth, fitToolbar, overflowItems, rovingTarget, widthKey, type ToolDef } from './toolbar';
  import { tooltip } from './tooltip';

  interface Props {
    label: string;
    tools: readonly ToolDef[];
    /** A tool was pressed (or chosen in the overflow menu). */
    onact?: (id: string) => void;
    /** A split button's option was chosen (never runs the action). */
    onoption?: (toolId: string, item: MenuChoice) => void;
    /** m: 34 px controls in a --toolbar-h row; s: 30 px controls in a 40 px row. */
    size?: 's' | 'm';
    /** Gallery: open the overflow menu. */
    overflowOpen?: boolean;
    /** Gallery: open this split button's menu. */
    splitOpen?: string | null;
    /** Inside another bar (Observe: between the mode bar and Arrange): no own border, height or background. */
    embedded?: boolean;
  }

  let { label, tools, onact, onoption, size = 'm', overflowOpen = $bindable(false), splitOpen = null, embedded = false }: Props = $props();

  const GAP = 2;
  const SEP = 13; // 1 px rule + 2 × 6 px margins
  const OVERFLOW = 48; // trigger + its margin

  let host: HTMLDivElement | undefined = $state();
  let trigger: HTMLButtonElement | undefined = $state();
  let available = $state(Infinity);
  /** Measured natural widths, by widthKey (what the tool shows), and by id (stale fallback). */
  const measured = new Map<string, number>();
  const lastById = new Map<string, number>();
  let version = $state(0);
  /** The part that holds the row's tab stop. */
  let current: HTMLElement | null = null;

  const controlPx = $derived(size === 's' ? 30 : 34);

  function widthOf(t: ToolDef): number {
    void version;
    if (t.width !== undefined) return t.width;
    return measured.get(widthKey(t)) ?? lastById.get(t.id) ?? estimateWidth(t, controlPx);
  }

  $effect(() => {
    if (!host || typeof ResizeObserver !== 'function') return;
    const el = host;
    const inner = () => {
      const cs = getComputedStyle(el);
      // Content box, minus 2 px of slack for sub-pixel rounding.
      return el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - 2;
    };
    const ro = new ResizeObserver(() => (available = inner()));
    ro.observe(el);
    available = inner();
    return () => ro.disconnect();
  });

  const fit = $derived(
    fitToolbar(
      tools.map((t) => ({ id: t.id, group: t.group, width: widthOf(t), priority: t.priority })),
      { available, gap: GAP, separator: SEP, overflow: OVERFLOW },
    ),
  );

  const startTools = $derived(tools.filter((t) => !t.end && fit.visible.has(t.id)));
  const endTools = $derived(tools.filter((t) => t.end && fit.visible.has(t.id)));
  const hiddenTools = $derived(tools.filter((t) => !fit.visible.has(t.id)));
  const menuItems = $derived(overflowItems(hiddenTools));

  // Measure each shown tool once per thing it shows; then refit.
  $effect(() => {
    void startTools;
    void endTools;
    if (!host) return;
    let changed = false;
    for (const slot of host.querySelectorAll<HTMLElement>('[data-tool]')) {
      const t = tools.find((x) => x.id === slot.dataset.tool);
      if (!t || t.width !== undefined) continue;
      const key = widthKey(t);
      const w = slot.offsetWidth;
      if (w > 0 && measured.get(key) !== w) {
        measured.set(key, w);
        lastById.set(t.id, w);
        changed = true;
      }
    }
    if (changed) version++;
    syncTabStops();
  });

  /** The focusable parts of the row, in order (tools, split parts, the overflow trigger). */
  function parts(): HTMLElement[] {
    if (!host) return [];
    return [...host.querySelectorAll<HTMLElement>('button')].filter((b) => !(b as HTMLButtonElement).disabled);
  }

  function syncTabStops(): void {
    const list = parts();
    if (!list.length) return;
    const stop = current && list.includes(current) ? current : list[0];
    for (const p of list) p.tabIndex = p === stop ? 0 : -1;
  }

  function onFocusIn(e: FocusEvent): void {
    const t = e.target as HTMLElement;
    if (!host?.contains(t) || t.tagName !== 'BUTTON') return;
    current = t;
    syncTabStops();
  }

  function onKey(e: KeyboardEvent): void {
    if (e.altKey || e.metaKey || e.ctrlKey) return;
    const list = parts();
    const i = list.indexOf(e.target as HTMLElement);
    if (i < 0) return;
    const j = rovingTarget(e.key, i, list.length);
    if (j === null) return;
    e.preventDefault(); // also tells the jog pad these arrows were used here
    current = list[j];
    syncTabStops();
    list[j].focus();
  }

  /** A separator before a tool that starts a new group (within one side). */
  function sepBefore(list: readonly ToolDef[], i: number): boolean {
    return i > 0 && list[i - 1].group !== list[i].group;
  }
</script>

{#snippet tool(t: ToolDef)}
  <span class="slot" data-tool={t.id}>
    {#if t.kind === 'split'}
      <SplitButton
        icon={t.icon}
        label={t.label}
        text={t.showLabel ? (t.buttonText ?? t.label) : undefined}
        detail={t.text}
        detailMin={t.textMin}
        variant={t.variant === 'danger' ? 'secondary' : (t.variant ?? 'ghost')}
        {size}
        shortcut={t.shortcut}
        items={t.items ?? []}
        busy={t.busy}
        progress={t.progress ?? null}
        progressText={t.progressText}
        disabledReason={t.disabledReason ?? null}
        stoppable={t.stoppable}
        optionsReason={t.optionsReason ?? null}
        error={t.error ?? null}
        open={splitOpen === t.id}
        onaction={() => onact?.(t.id)}
        onselect={(item) => onoption?.(t.id, item)}
      />
    {:else if t.kind === 'readout'}
      <button
        type="button"
        class="readout"
        aria-label="{t.label}: {t.text ?? ''}"
        onclick={() => onact?.(t.id)}
        use:tooltip={{ text: t.label, shortcut: t.shortcut }}>{t.text}</button
      >
    {:else}
      <Control
        icon={t.icon}
        label={t.label}
        showLabel={t.showLabel}
        variant={t.variant ?? 'ghost'}
        {size}
        pressed={t.kind === 'toggle' ? !!t.pressed : undefined}
        layoutToggle={t.layoutToggle}
        glyphTone={t.glyphTone}
        shortcut={t.shortcut}
        busy={t.busy}
        progress={t.progress ?? null}
        progressText={t.progressText}
        error={t.error ?? null}
        disabledReason={t.disabledReason ?? null}
        onclick={() => onact?.(t.id)}
      />
    {/if}
  </span>
{/snippet}

<!-- svelte-ignore a11y_interactive_supports_focus (roving tabindex: the tools hold the one tab stop, the row itself is not one) -->
<div class="toolbar s-{size}" class:embedded role="toolbar" aria-label={label} bind:this={host} onfocusin={onFocusIn} onkeydown={onKey}>
  <div class="side">
    {#each startTools as t, i (t.id)}
      {#if sepBefore(startTools, i)}<span class="sep" aria-hidden="true"></span>{/if}
      {@render tool(t)}
    {/each}
  </div>
  <span class="flex"></span>
  {#if hiddenTools.length}
    <button
      type="button"
      class="more"
      bind:this={trigger}
      aria-haspopup="menu"
      aria-expanded={overflowOpen}
      aria-label="{hiddenTools.length} more {hiddenTools.length === 1 ? 'tool' : 'tools'}"
      onclick={() => (overflowOpen = !overflowOpen)}
      use:tooltip={{
        text: `${hiddenTools.length} more ${hiddenTools.length === 1 ? 'tool' : 'tools'}`,
        hint: 'The window is too narrow to show them all',
        disabled: overflowOpen,
      }}
    >
      <span class="count">{hiddenTools.length}</span>
      <Icon name="disclosure" size={16} />
    </button>
  {/if}
  <div class="side">
    {#each endTools as t, i (t.id)}
      {#if i === 0 && hiddenTools.length}<span class="sep" aria-hidden="true"></span>{/if}
      {#if sepBefore(endTools, i)}<span class="sep" aria-hidden="true"></span>{/if}
      {@render tool(t)}
    {/each}
  </div>
</div>

<Menu
  bind:open={overflowOpen}
  anchor={trigger}
  items={menuItems}
  label="More tools"
  placement="bottom-end"
  minWidth={240}
  onselect={(item) => onact?.(item.id)}
/>

<style>
  .toolbar {
    position: relative;
    display: flex;
    align-items: center;
    min-width: 0;
    height: var(--toolbar-h);
    padding: 0 var(--space-2);
    /* Clip sideways only: focus rings and key-hint caps stay visible above and below. */
    overflow: clip visible;
    border-bottom: var(--border-w) solid var(--border);
    background: var(--bg);
  }
  .toolbar.s-s {
    height: 40px;
  }
  .toolbar.embedded {
    flex: 1;
    height: 100%;
    padding: 0;
    border-bottom: 0;
    background: transparent;
  }
  .side {
    display: flex;
    flex: none;
    align-items: center;
    gap: 2px;
  }
  .slot {
    display: inline-flex;
    flex: none;
  }
  .flex {
    flex: 1;
    min-width: 0;
  }
  .sep {
    flex: none;
    width: 1px;
    height: 18px;
    margin: 0 6px;
    background: var(--border-soft);
  }

  .readout {
    height: var(--control-h-m);
    min-width: 48px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid transparent;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-s);
    font-variant-numeric: var(--numeric);
    cursor: pointer;
    transition: background-color var(--duration-instant) var(--ease-standard);
  }
  .s-s .readout {
    height: var(--control-h-s);
  }
  .readout:hover {
    background: var(--hover-bg);
  }
  .readout:active {
    background: var(--pressed-bg);
    box-shadow: var(--pressed-inset);
  }
  .readout:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }

  .more {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: 2px;
    height: var(--control-h-m);
    margin-left: 4px;
    padding: 0 4px 0 8px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg-muted);
    cursor: pointer;
  }
  .s-s .more {
    height: var(--control-h-s);
  }
  .more:hover,
  .more[aria-expanded='true'] {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .more:active {
    background: var(--pressed-bg);
    box-shadow: var(--pressed-inset);
  }
  .more:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }
  .count {
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-s);
    font-variant-numeric: var(--numeric);
  }
</style>

<!--
  Toolbar with priority overflow (proposal; README 1.1 "toolbars take one
  row each"). One row, groups separated by a rule, run-critical tools
  never move (priority Infinity). When the row is too narrow, the lowest
  priorities leave first, from the end of their group, into an overflow
  menu whose trigger shows HOW MANY tools it holds ("3"), so nothing
  disappears silently. In the menu, toggles keep their state (check marks)
  and every tool keeps its shortcut, so the keyboard path is unchanged.

  Natural widths are measured once from a hidden copy of the row
  (labels change width, icons do not); the fit itself is pure
  (overflow.ts, unit-tested). Keys: Tab enters the row, the tools keep
  their own tab stops (a toolbar of 15 buttons is still quick with the
  shortcuts; roving focus is a possible refinement).
-->
<script lang="ts">
  import Icon from '../../../lib/components/Icon.svelte';
  import Menu from '../../../lib/components/Menu.svelte';
  import type { MenuChoice, MenuEntry } from '../../../lib/components/menu';
  import { fitToolbar } from '../overflow';
  import { tip } from '../tip';
  import type { ToolDef } from '../types';
  import Ctl from './Ctl.svelte';
  import SplitButton from './SplitButton.svelte';

  interface Props {
    label: string;
    tools: readonly ToolDef[];
    onact?: (id: string) => void;
    onoption?: (toolId: string, item: MenuChoice) => void;
    size?: 's' | 'm';
    /** Specimen: open the overflow menu. */
    overflowOpen?: boolean;
    /** Specimen: open a split button's menu. */
    splitOpen?: string | null;
  }

  let { label, tools, onact, onoption, size = 'm', overflowOpen = $bindable(false), splitOpen = null }: Props = $props();

  let host: HTMLDivElement | undefined = $state();
  let measureRow: HTMLDivElement | undefined = $state();
  let available = $state(10_000);
  let widths: Record<string, number> = $state({});
  let trigger: HTMLButtonElement | undefined = $state();

  const GAP = 2;
  const SEP = 13;
  const OVERFLOW = 48;

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

  $effect(() => {
    void tools.map((t) => `${t.id}:${t.text ?? ''}:${t.showLabel ?? ''}`).join('|');
    if (!measureRow) return;
    const next: Record<string, number> = {};
    for (const el of measureRow.querySelectorAll<HTMLElement>('[data-tool]')) {
      next[el.dataset.tool!] = el.offsetWidth;
    }
    widths = next;
  });

  const fit = $derived(
    fitToolbar(
      tools.map((t) => ({ id: t.id, group: t.group, width: widths[t.id] ?? 34, priority: t.priority })),
      { available, gap: GAP, separator: SEP, overflow: OVERFLOW },
    ),
  );

  const startTools = $derived(tools.filter((t) => !t.end && fit.visible.has(t.id)));
  const endTools = $derived(tools.filter((t) => t.end && fit.visible.has(t.id)));
  const hiddenTools = $derived(tools.filter((t) => !fit.visible.has(t.id)));

  const menuItems = $derived.by((): MenuEntry[] => {
    const out: MenuEntry[] = [];
    let group: string | null = null;
    for (const t of hiddenTools) {
      if (t.group !== group) {
        if (group !== null) out.push({ kind: 'separator', id: `sep-${t.id}` });
        group = t.group;
      }
      if (t.kind === 'toggle') {
        out.push({ kind: 'checkbox', id: t.id, label: t.label, checked: !!t.pressed, shortcut: t.shortcut, disabledReason: t.disabledReason ?? null });
      } else {
        out.push({ id: t.id, label: t.label, icon: t.icon, shortcut: t.shortcut, disabledReason: t.disabledReason ?? null });
      }
    }
    return out;
  });

  /** A separator before a tool that starts a new group (within one side). */
  function sepBefore(list: readonly ToolDef[], i: number): boolean {
    return i > 0 && list[i - 1].group !== list[i].group;
  }
</script>

{#snippet tool(t: ToolDef, live: boolean)}
  {#if t.kind === 'split'}
    <SplitButton
      icon={t.icon}
      label={t.label}
      detail={t.text}
      {size}
      shortcut={t.shortcut}
      items={t.items ?? []}
      menuLabel="{t.label} options"
      busy={t.busy}
      progress={t.progress ?? null}
      progressText={t.progressText}
      disabledReason={t.disabledReason ?? null}
      open={live && splitOpen === t.id}
      onaction={() => onact?.(t.id)}
      onselect={(item) => onoption?.(t.id, item)}
    />
  {:else if t.kind === 'readout'}
    <button
      type="button"
      class="readout num"
      aria-label="{t.label}: {t.text}"
      onclick={() => onact?.(t.id)}
      use:tip={{ text: t.label, shortcut: t.shortcut }}>{t.text}</button
    >
  {:else}
    <Ctl
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
      disabledReason={t.disabledReason ?? null}
      onclick={() => onact?.(t.id)}
    />
  {/if}
{/snippet}

<div class="toolbar s-{size}" role="toolbar" aria-label={label} bind:this={host}>
  <div class="side">
    {#each startTools as t, i (t.id)}
      {#if sepBefore(startTools, i)}<span class="sep" aria-hidden="true"></span>{/if}
      {@render tool(t, true)}
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
      aria-label="{hiddenTools.length} more tools"
      onclick={() => (overflowOpen = !overflowOpen)}
      use:tip={{ text: `${hiddenTools.length} more tools`, hint: 'The window is too narrow to show them all', disabled: overflowOpen }}
    >
      <span class="count num">{hiddenTools.length}</span>
      <Icon name="disclosure" size={16} />
    </button>
  {/if}
  <div class="side">
    {#each endTools as t, i (t.id)}
      {#if i === 0 && hiddenTools.length}<span class="sep" aria-hidden="true"></span>{/if}
      {#if sepBefore(endTools, i)}<span class="sep" aria-hidden="true"></span>{/if}
      {@render tool(t, true)}
    {/each}
  </div>

  <!-- Hidden copy for natural widths (never focusable, never read). -->
  <div class="measure" bind:this={measureRow} aria-hidden="true" inert>
    {#each tools as t (t.id)}
      <span data-tool={t.id}>{@render tool(t, false)}</span>
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
    height: 46px;
    padding: 0 var(--space-2);
    border-bottom: var(--border-w) solid var(--border);
    background: var(--bg);
    --ctl-halo: var(--bg);
  }
  .toolbar.s-s {
    height: 40px;
  }
  .side {
    display: flex;
    align-items: center;
    gap: 2px;
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
    font-size: var(--text-s);
    cursor: pointer;
    transition: background-color var(--duration-instant) var(--ease-standard);
  }
  .s-s .readout {
    height: var(--control-h-s);
  }
  .readout:hover {
    background: var(--hover-bg);
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
  .more:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: var(--focus-ring-offset);
  }
  .count {
    color: var(--fg);
    font-size: var(--text-s);
  }

  .measure {
    position: absolute;
    top: 0;
    left: 0;
    display: flex;
    gap: 2px;
    visibility: hidden;
    pointer-events: none;
    white-space: nowrap;
  }
  .measure > span {
    display: inline-flex;
  }
</style>

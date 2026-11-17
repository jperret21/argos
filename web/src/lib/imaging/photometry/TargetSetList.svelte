<!--
  TargetSetList (D24, M79): the one view of the target set, in the Observe Photometry card
  (and the Plan Target set card in wave 6). Replaces Qt's TargetTable (target_table.py:27).

  - One row per star: its role's shape (as on the image, BRAND 10), its name (mono), its
    AUID when the name is not the AUID, a value on the right (the newest magnitude, given by
    the caller), and Remove.
  - Remove is immediate with an Undo toast; during a run the caller asks first (D24, 08 P12).
  - Rows are linked to the image: hovering or focusing a row rings its star (the field's
    hover link), a click (or Enter) selects it on the image; a star hovered on the image
    marks its row.
  - In the rail card the comparisons fold into one row ("5 comparisons · VSP 4, manual 1")
    that opens in place (remembered per viewer), so the card fits without scrolling.
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { loadPref, savePref } from '../../app/prefs';
  import IconButton from '../../components/IconButton.svelte';
  import NumText from '../../components/NumText.svelte';
  import RoleGlyph from '../field/RoleGlyph.svelte';
  import type { TargetStar } from '../field/types';
  import { PICK_TARGET, comparisonSplit } from './present';

  interface Props {
    stars: readonly TargetStar[];
    /** Text at the right of a row (the newest magnitude), or null. */
    value?: (s: TargetStar) => string | null;
    /** Tooltip of that value. */
    valueTitle?: (s: TargetStar) => string | undefined;
    /** The row marked from the image (its set key). */
    hotKey?: string | null;
    /** Fold the comparisons into one row (rail card). */
    foldComparisons?: boolean;
    /** Why Remove is unavailable now (null: available). */
    removeReason?: string | null;
    /** The star being removed (its button is busy). */
    removing?: string | null;
    empty?: string;
    onremove?: (s: TargetStar) => void;
    onhover?: (s: TargetStar | null) => void;
    onpick?: (s: TargetStar) => void;
  }

  let {
    stars,
    value,
    valueTitle,
    hotKey = null,
    foldComparisons = false,
    removeReason = null,
    removing = null,
    empty = PICK_TARGET,
    onremove,
    onhover,
    onpick,
  }: Props = $props();

  const PREF = 'argos.photometry.set.comparisons';
  let expanded = $state(loadPref(PREF, (v): v is boolean => typeof v === 'boolean', false));
  $effect(() => {
    const e = expanded;
    untrack(() => savePref(PREF, e));
  });

  const ORDER: Record<string, number> = { target: 0, comparison: 1, check: 2 };
  const sorted = $derived([...stars].sort((a, b) => (ORDER[a.role] ?? 3) - (ORDER[b.role] ?? 3)));
  const comps = $derived(sorted.filter((s) => s.role === 'comparison'));
  const split = $derived(comparisonSplit(stars));
  const folded = $derived(foldComparisons && comps.length > 2 && !expanded);
  const shown = $derived(folded ? sorted.filter((s) => s.role !== 'comparison') : sorted);
  /** Where the folded comparisons row sits: after the targets. */
  const foldAt = $derived(shown.findIndex((s) => s.role !== 'target'));

  const nameOf = (s: TargetStar) => s.display_name || s.name || s.auid || s.key;
  const roleWord: Record<string, string> = { target: 'Target', comparison: 'Comparison', check: 'Check star' };

  function key(e: KeyboardEvent, s: TargetStar): void {
    const rows = [...((e.currentTarget as HTMLElement).closest('ul')?.querySelectorAll<HTMLElement>('li[data-row] .pick') ?? [])];
    const i = rows.indexOf(e.currentTarget as HTMLElement);
    if (e.key === 'ArrowDown') rows[Math.min(rows.length - 1, i + 1)]?.focus();
    else if (e.key === 'ArrowUp') rows[Math.max(0, i - 1)]?.focus();
    else if (e.key === 'Enter' || e.key === ' ') onpick?.(s);
    else if ((e.key === 'Delete' || e.key === 'Backspace') && onremove && !removeReason) onremove(s);
    else return;
    e.preventDefault();
  }
</script>

{#snippet foldRow()}
  <li class="fold">
    <RoleGlyph role="comparison" />
    <button type="button" class="disclose" aria-expanded={!folded} onclick={() => (expanded = !expanded)} title={folded ? 'Show the comparison stars' : 'Fold the comparison stars into one row'}>
      <svg class="caret" class:open={!folded} viewBox="0 0 10 10" aria-hidden="true"><path d="M3.5 2.5 6 5 3.5 7.5" /></svg>
      <span class="num">{comps.length}</span> comparison{comps.length === 1 ? '' : 's'}<span class="muted"><NumText text={split.text.includes('(') ? ` · ${split.text.slice(split.text.indexOf('(') + 1, -1)}` : ''} /></span>
    </button>
  </li>
{/snippet}

{#if !stars.length}
  <p class="empty">{empty}</p>
{:else}
  <ul class="set" aria-label="Target set">
    {#each shown as s, i (s.key)}
      {#if foldComparisons && comps.length > 2 && i === foldAt && s.role !== 'target'}
        {@render foldRow()}
      {/if}
      <li data-row class:hot={hotKey === s.key} class:busy={removing === s.key}>
        <button
          type="button"
          class="pick"
          aria-label="{roleWord[s.role] ?? s.role}: {nameOf(s)}. Enter selects it on the image{onremove ? ', Delete removes it' : ''}."
          onpointerenter={() => onhover?.(s)}
          onpointerleave={() => onhover?.(null)}
          onfocus={() => onhover?.(s)}
          onblur={() => onhover?.(null)}
          onclick={() => onpick?.(s)}
          onkeydown={(e) => key(e, s)}
        >
          <RoleGlyph role={s.role} />
          <span class="name" title={s.auid && s.auid !== nameOf(s) ? `AUID ${s.auid}` : undefined}>{nameOf(s)}</span>
          {#if s.auid && s.auid !== nameOf(s)}<span class="auid">{s.auid}</span>{/if}
          <span class="grow"></span>
          {#if value}
            {@const v = value(s)}
            {#if v}<span class="value num" title={valueTitle?.(s)}>{v}</span>{/if}
          {/if}
        </button>
        {#if onremove}
          <span class="act">
            <IconButton
              icon="remove"
              label="Remove {nameOf(s)} from the target set"
              tooltipText="Remove from the target set (Undo in the toast)"
              size="s"
              variant="ghost"
              tabindex={-1}
              busy={removing === s.key}
              disabledReason={removeReason}
              onclick={() => onremove?.(s)}
            />
          </span>
        {/if}
      </li>
    {/each}
    {#if foldComparisons && comps.length > 2 && foldAt < 0}
      {@render foldRow()}
    {/if}
  </ul>
{/if}

<style>
  .set {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
  }
  li {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    min-height: 24px;
    border-radius: var(--radius-s);
    font-size: var(--text-s);
  }
  li[data-row]:hover,
  li.hot {
    background: var(--hover-bg);
  }
  .pick {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex: 1;
    min-width: 0;
    height: 24px;
    padding: 0 var(--space-1);
    border: 0;
    border-radius: var(--radius-s);
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .pick:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: calc(-1 * var(--focus-ring-w));
  }
  .name {
    color: var(--fg);
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }
  .auid {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .grow {
    flex: 1;
  }
  .value {
    color: var(--fg);
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
    white-space: nowrap;
  }
  /* Remove shows with the row's hover or focus; the row keyboard has Delete. */
  .act {
    opacity: 0;
    display: inline-flex;
  }
  li:hover .act,
  li:focus-within .act,
  li.busy .act {
    opacity: 1;
  }
  @media (hover: none) {
    .act {
      opacity: 1;
    }
  }
  .fold {
    padding-left: var(--space-1);
  }
  .disclose {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 22px;
    padding: 0 var(--space-1);
    border: 0;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font: inherit;
    font-size: var(--text-s);
    cursor: pointer;
  }
  .disclose:hover {
    background: var(--hover-bg);
  }
  .disclose:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -2px;
  }
  .caret {
    width: 10px;
    height: 10px;
    transition: transform var(--duration-fast) var(--ease-standard);
  }
  .caret.open {
    transform: rotate(90deg);
  }
  .caret path {
    fill: none;
    stroke: var(--fg-muted);
    stroke-width: 1.4;
  }
  .muted {
    color: var(--text-muted);
  }
  .num {
    font-variant-numeric: var(--numeric);
  }
  .empty {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
</style>

<!--
  Variables tab of the Observe drawer (D7, M78; A50): every VSX variable of the solved field,
  to pick the photometry target from a list. Replaces Qt's VariableTable
  (variable_table.py:58) with its filter and its rules:

  - "Filter by designation or type…" (case- and space-insensitive: "XX Cyg" matches
    "xxcyg") and "Brightest mag ≤" (Any by default; a star without a range is then left out),
    the count "n of N stars"; the filter also drives the image's variable markers (D7);
  - a virtual table (constant DOM whatever the count) in catalogue order (brightest first),
    sorted by a header click; the set role as its shape instead of Qt's "●"; suspected
    variables muted (the dashed circle's convention);
  - hovering a row rings the star on the image; a click selects the row (and the star on
    the image); "Set as target", Enter or a double click gives it the target role, exactly as
    its circle's Target button (auto-comparisons included), with Undo.
-->
<script lang="ts">
  import IconButton from '../../components/IconButton.svelte';
  import NumberField from '../../components/NumberField.svelte';
  import SearchField from '../../components/SearchField.svelte';
  import type { Column } from '../../components/table';
  import VirtualTable from '../../components/VirtualTable.svelte';
  import { fixed } from '../../format/number';
  import RoleGlyph from '../field/RoleGlyph.svelte';
  import type { FieldVariable } from './types';
  import { filterVariables, variablesCount } from './present';

  interface Props {
    /** A50 rows, or null before a solution. */
    rows: readonly FieldVariable[] | null;
    /** The field is being identified (the empty state says so). */
    solving?: boolean;
    error?: string | null;
    query: string;
    magLimit: number | null;
    /** Row marked from the image (its marker key). */
    hotKey?: string | null;
    /** Why Set as target is unavailable (null: available). */
    targetReason?: string | null;
    busy?: boolean;
    onquery?: (q: string) => void;
    onmaglimit?: (v: number | null) => void;
    onhover?: (r: FieldVariable | null) => void;
    onpick?: (r: FieldVariable) => void;
    ontarget?: (r: FieldVariable) => void;
    oncopy?: (tsv: string, n: number) => void;
  }

  let { rows, solving = false, error = null, query, magLimit, hotKey = null, targetReason = null, busy = false, onquery, onmaglimit, onhover, onpick, ontarget, oncopy }: Props = $props();

  const all = $derived(rows ?? []);
  const kept = $derived(filterVariables(all, query, magLimit));
  let selected: string | null = $state(null);
  const selRow = $derived(kept.find((r) => r.key === selected) ?? null);

  const num = (v: number | null | undefined, d: number) => (v === null || v === undefined || !Number.isFinite(v) ? '' : fixed(v, d));
  const ROLE_ORDER: Record<string, number> = { target: 0, comparison: 1, check: 2 };
  const COLS: Column<FieldVariable>[] = [
    { id: 'role', label: 'In set', hideLabel: true, value: (r) => (r.in_set_role ? ROLE_ORDER[r.in_set_role] : null), width: '30px', title: 'Its role in the target set' },
    { id: 'name', label: 'Name', value: (r) => r.name, width: 'minmax(120px, 1.4fr)' },
    { id: 'type', label: 'Type', value: (r) => r.var_type ?? '', format: (r) => r.var_type || '?', width: '96px', title: 'VSX variability type' },
    { id: 'mag', label: 'Mag', value: (r) => r.brightest_mag, format: (r) => r.mag_text || '?', width: 'minmax(110px, 1fr)', title: 'VSX range (sorted by its bright end)' },
    { id: 'period', label: 'Period d', numeric: true, value: (r) => r.period_d, format: (r) => (r.period_d ? String(+r.period_d.toPrecision(6)) : ''), width: '92px', title: 'Period, days (VSX)' },
    { id: 'sep', label: 'Sep ′', numeric: true, value: (r) => r.sep_arcmin, format: (r) => num(r.sep_arcmin, 1), width: '64px', title: 'Separation from the solved field centre, arcmin' },
  ];

  const emptyText = $derived(
    rows === null
      ? solving
        ? 'Identifying the field…'
        : error
          ? `Could not read the variables: ${error}`
          : 'Identify the field (S) to list its VSX variables.'
      : all.length
        ? 'No variable matches the filter.'
        : 'No VSX variable in this field.',
  );
</script>

<div class="vars">
  <div class="filters">
    <SearchField label="Filter the variables" value={query} placeholder="Filter by designation or type…" width="240px" oninput={(v) => onquery?.(v)} />
    <span class="lim">
      <span class="lim-label" aria-hidden="true">Brightest mag ≤</span>
      <NumberField
        hideLabel
        label="Brightest mag ≤"
        value={magLimit}
        nullable
        placeholder="Any"
        min={0}
        max={20}
        step={0.5}
        decimals={1}
        width="72px"
        send={(v: number | null) => onmaglimit?.(v === 0 ? null : v)}
      />
    </span>
    <span class="count num" aria-live="polite">{rows === null ? '—' : variablesCount(kept.length, all.length)}</span>
    <span class="grow"></span>
    <IconButton
      icon="target-star"
      label="Set as target"
      showLabel
      size="s"
      variant="secondary"
      {busy}
      disabledReason={targetReason ?? (selRow ? null : 'select a variable in the list first')}
      tooltipText="Make this variable the photometry target (comparisons are picked automatically when none are chosen yet). Same action as its circle on the image."
      onclick={() => selRow && ontarget?.(selRow)}
    />
  </div>
  <VirtualTable
    label="VSX variables of the field"
    columns={COLS}
    rows={kept}
    rowKey={(r) => r.key}
    bind:selected
    highlight={hotKey}
    empty={emptyText}
    onhover={(r) => onhover?.(r)}
    onselect={(r) => r && onpick?.(r)}
    onactivate={(r) => (targetReason ? undefined : ontarget?.(r))}
    {oncopy}
  >
    {#snippet cell(r: FieldVariable, col: Column<FieldVariable>)}
      {#if col.id === 'role'}
        {#if r.in_set_role}<RoleGlyph role={r.in_set_role} label="In the set: {r.in_set_role}" />{/if}
      {:else}
        <span class:suspected={r.suspected} class:mono={col.id === 'name' || col.id === 'mag'} title={r.suspected && col.id === 'name' ? 'Suspected variable (VSX)' : undefined}>{col.format ? col.format(r) : String(col.value?.(r) ?? '')}</span>
      {/if}
    {/snippet}
  </VirtualTable>
</div>

<style>
  .vars {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .vars > :global(.vt) {
    flex: 1;
  }
  .filters {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    flex: none;
    min-height: 34px;
    padding: var(--space-1) var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .lim {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  .lim-label {
    color: var(--text-muted);
    font-size: var(--text-s);
    white-space: nowrap;
  }
  .count {
    color: var(--text-muted);
    font-size: var(--text-s);
    white-space: nowrap;
  }
  .grow {
    flex: 1;
  }
  .mono {
    font-family: var(--font-mono);
  }
  .suspected {
    color: var(--text-muted);
  }
</style>

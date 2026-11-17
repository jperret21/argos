<!--
  Rail card "Ensemble" (decision D5; 07 E10 "Comparison quality", 08 1.6 #3 and 1.13; README
  M89): the comparisons of the filter shown, compact: name, status in words (never a colour
  alone), scatter, valid points; the verdict line (`selection_status` and the scientific
  note, fixes 08 P15). Read-only (Review never edits the ensemble: D3; on the live run the
  note says where to edit it). A row press shows the star's cell (unhides it when hidden,
  fixes 07 P10). All the columns are in the drawer's Ensemble tab.
-->
<script lang="ts">
  import Card from '../../components/Card.svelte';
  import Table from '../../components/Table.svelte';
  import type { Column } from '../../components/table';
  import StatusBadge from '../../components/StatusBadge.svelte';
  import { tooltip } from '../../components/tooltip';
  import { fixed, int } from '../../format/number';
  import type { QualityReport } from '../source';
  import { verdictText, type EnsembleRow } from '../rail';

  interface Props {
    rows: readonly EnsembleRow[];
    report: QualityReport | null;
    /** The live run: edits live in Observe (D3). */
    live?: boolean;
    selected?: string | null;
    onstar?: (cellId: string) => void;
    oncopy?: (tsv: string, rows: number) => void;
  }
  let { rows, report, live = false, selected = null, onstar, oncopy }: Props = $props();

  const columns: Column<EnsembleRow>[] = [
    { id: 'name', label: 'Comparison', value: (r) => r.name, width: 'auto' },
    { id: 'status', label: 'Status', value: (r) => r.status, width: '11ch' },
    { id: 'scatter', label: 'σ', title: 'Scatter, mag (robust second differences)', value: (r) => r.scatter, format: (r) => fixed(r.scatter, 3), numeric: true, width: '7ch' },
    { id: 'n', label: 'N', title: 'Valid points (vetting), else points in the curve', value: (r) => r.nValid ?? r.n, format: (r) => int(r.nValid ?? r.n), numeric: true, width: '5ch' },
  ];
  const stable = $derived(rows.filter((r) => r.ok && r.status !== '—').length);
</script>

<Card title="Ensemble" icon="comparison-quality" collapsible persist="review.ensemble">
  {#snippet status()}
    {#if rows.length}<StatusBadge tone={report && stable < rows.length ? 'busy' : 'idle'} label={report ? `${stable}/${rows.length} stable` : `${rows.length} comparisons`} plain />{/if}
  {/snippet}
  {#if rows.length}
    <p class="verdict" use:tooltip={{ text: report?.scientific_note || 'No photometry_quality.json for this filter: σ estimated here as uncertainty.py does' }}>{verdictText(report)}</p>
    <Table label="Comparison stars" {columns} {rows} rowKey={(r) => r.cellId} {selected} density="compact" maxHeight="216px" onselect={(r) => r && onstar?.(r.cellId)} onactivate={(r) => onstar?.(r.cellId)} {oncopy}>
      {#snippet cell(r, col)}
        {#if col.id === 'status'}
          <span class="st" class:warn={!r.ok}>{r.status}</span>
        {:else if col.id === 'name'}
          <span class="nm" title={r.auid && r.auid !== r.name ? `${r.name} · ${r.auid}` : r.name}>{r.name}</span>
        {:else}
          {col.format ? col.format(r) : String(col.value?.(r) ?? '')}
        {/if}
      {/snippet}
    </Table>
    {#if live}<p class="note">Edit the ensemble in Observe (Photometry card, Ensemble tab).</p>{/if}
  {:else}
    <p class="empty">{live ? 'No comparison measured yet.' : 'No comparison star in this source.'}</p>
  {/if}
</Card>

<style>
  .verdict {
    margin: 0 0 var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .st {
    color: var(--text-muted);
  }
  .st.warn {
    color: var(--fg);
    text-decoration: underline dotted var(--warning);
    text-underline-offset: 3px;
  }
  .nm {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .note,
  .empty {
    margin: var(--space-2) 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .empty {
    margin: 0;
    font-size: var(--text-s);
  }
</style>

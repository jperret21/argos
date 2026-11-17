<!--
  Ensemble table (M97, 08 1.6 / 1.13; drawer tab "Ensemble" on Observe, D3: the only place
  with ensemble edits besides the Photometry card). Replaces Qt's ComparisonEnsembleTable
  (comparison_table.py:54) and shows what Qt computed but never showed (S17, 08 P14-P16):

  - the verdict line: the report's `selection_status` in Qt's words, "n of m stable", the
    minimum number of points, and its `scientific_note` verbatim (never a tick that reads as
    "calibrated");
  - one row per comparison: catalogue V and B−V, its leave-one-out status (Qt's labels:
    Stable / Unstable / Noisy / Waiting for N points) with the samples, scatter and median
    formal error (4 decimals, as Qt), its newest leave-one-out magnitude and the residual
    against catalogue V, and the field's flags in words ("variable?" for a VSX star: it
    stays eligible, owner decision 2); the check star last, without a verdict;
  - rows linked to the image (hover rings the star, a click selects it), Remove with Undo
    (asked first during a run), ⌘/Ctrl+C or the Copy button copies Qt's TSV columns first;
  - Qt's count line under the table, word for word.
-->
<script lang="ts">
  import IconButton from '../../components/IconButton.svelte';
  import Icon from '../../components/Icon.svelte';
  import NumText from '../../components/NumText.svelte';
  import type { Column } from '../../components/table';
  import VirtualTable from '../../components/VirtualTable.svelte';
  import { fixed, mag } from '../../format/number';
  import RoleGlyph from '../field/RoleGlyph.svelte';
  import { residualText, scatterText, type EnsembleRow, type Verdict } from './present';

  interface Props {
    rows: readonly EnsembleRow[];
    verdict: Verdict | null;
    /** The report's minimum number of points (photometry.comparison_validation_min_points). */
    minPoints: number;
    /** Qt's count line (countLine). */
    countText: string;
    /** Row marked from the image (set key). */
    hotKey?: string | null;
    /** The row the Inspector shows. */
    selected?: string | null;
    removeReason?: string | null;
    removing?: string | null;
    onremove?: (r: EnsembleRow) => void;
    onhover?: (r: EnsembleRow | null) => void;
    onpick?: (r: EnsembleRow) => void;
    oncopy?: (tsv: string, n: number) => void;
  }

  let { rows, verdict, minPoints, countText, hotKey = null, selected = null, removeReason = null, removing = null, onremove, onhover, onpick, oncopy }: Props = $props();

  const num = (v: number | null, d: number) => (v === null ? '—' : fixed(v, d));
  const COLS: Column<EnsembleRow>[] = $derived([
    { id: 'role', label: 'Role', hideLabel: true, value: (r) => (r.role === 'check' ? 1 : 0), width: '28px', sortable: false },
    { id: 'name', label: 'Star', value: (r) => r.name, width: 'minmax(120px, 1.3fr)', title: 'AUID (the VSP label when there is none)' },
    { id: 'v', label: 'V', numeric: true, value: (r) => r.v, format: (r) => num(r.v, 2), width: '54px', title: 'Catalogue V (VSP)' },
    { id: 'bv', label: 'B−V', numeric: true, value: (r) => r.bv, format: (r) => num(r.bv, 2), width: '54px', title: 'Catalogue B − V (VSP)' },
    { id: 'n', label: 'N', numeric: true, value: (r) => r.n, format: (r) => (r.n === null ? '—' : String(r.n)), width: '44px', title: `Valid leave-one-out points (the verdict needs ${minPoints})` },
    { id: 'scatter', label: 'Scatter', numeric: true, value: (r) => r.scatter, format: (r) => scatterText(r.scatter), width: '66px', title: 'Scatter of its leave-one-out curve, mag (Qt "Scatter (mag)")' },
    { id: 'formal', label: 'Formal', numeric: true, value: (r) => r.formal, format: (r) => scatterText(r.formal), width: '66px', title: 'Median formal error of its leave-one-out curve, mag' },
    { id: 'last', label: 'Leave-one-out', numeric: true, value: (r) => r.lastMag, format: (r) => (r.lastMag === null ? '—' : mag(r.lastMag, r.lastErr)), width: '118px', title: 'Its newest magnitude, calibrated against the other comparisons' },
    { id: 'residual', label: 'O − C', numeric: true, value: (r) => r.residual, format: (r) => residualText(r.residual), width: '62px', title: 'Observed − catalogue: its newest leave-one-out magnitude minus catalogue V, mag (near 0 for a good comparison)' },
    { id: 'status', label: 'Status', value: (r) => r.label, width: '132px', title: `Leave-one-out status: Stable needs ${minPoints} valid points, a scatter and a formal error within the limits` },
    { id: 'flags', label: 'Flags', value: (r) => r.flags.join(', '), width: 'minmax(80px, 1fr)', title: 'The field’s words for the star: Δ(B−V), far, clipped, blended, variable? (VSX)', wrap: true },
    { id: 'act', label: 'Remove', hideLabel: true, value: () => null, width: '32px', sortable: false },
  ]);

  const counts = $derived(verdict?.counts ? ` · ${verdict.counts}` : '');
</script>

<div class="ens">
  <p class="verdict" class:ok={verdict?.tone === 'ok'} class:warn={verdict?.tone === 'warn'} title={verdict?.line ?? undefined}>
    <Icon name="comparison-quality" size={16} />
    {#if verdict}
      <span class="words"><NumText text={`Ensemble: ${verdict.words}${counts}`} /></span>
      <span class="min"><NumText text={`· min ${minPoints} points`} /></span>
      {#if verdict.note}<span class="note">{verdict.note}</span>{/if}
    {:else}
      <span class="words">Ensemble: no assessment yet</span>
      <span class="note">The leave-one-out check runs after every measured frame (needs {minPoints} points per comparison).</span>
    {/if}
  </p>
  <VirtualTable
    label="Ensemble: comparisons and check star"
    columns={COLS}
    {rows}
    rowKey={(r) => r.key}
    {selected}
    highlight={hotKey}
    empty="No comparison or check star in the set yet: click a star on the image to give it a role, or use Recommend."
    onhover={(r) => onhover?.(r)}
    onselect={(r) => r && onpick?.(r)}
    onactivate={(r) => onpick?.(r)}
    {oncopy}
  >
    {#snippet cell(r: EnsembleRow, col: Column<EnsembleRow>)}
      {#if col.id === 'role'}
        <RoleGlyph role={r.role} label={r.role === 'check' ? 'Check star' : 'Comparison'} />
      {:else if col.id === 'name'}
        <span class="mono" class:check={r.role === 'check'} title={r.auid && r.auid !== r.name ? `AUID ${r.auid}` : undefined}>{r.name}</span>
      {:else if col.id === 'status'}
        <span class="status {r.tone}" class:check={r.role === 'check'}>
          {#if r.role !== 'check'}<span class="dot" aria-hidden="true"></span>{/if}{r.label}
        </span>
      {:else if col.id === 'flags'}
        <span class="flags" class:none={!r.flags.length}>{r.flags.length ? r.flags.join(', ') : '—'}</span>
      {:else if col.id === 'last'}
        <span class:stale={r.onLastFrame === false} title={r.onLastFrame === false ? 'Not measured on the newest frame: this is an earlier point' : undefined}>{r.lastMag === null ? '—' : mag(r.lastMag, r.lastErr)}</span>
      {:else if col.id === 'act'}
        {#if onremove}
          <span class="rm" class:busy={removing === r.key}><IconButton
            icon="remove"
            label="Remove {r.name} from the ensemble"
            tooltipText="Remove from the ensemble (Undo in the toast)"
            size="s"
            variant="ghost"
            tabindex={-1}
            busy={removing === r.key}
            disabledReason={removeReason}
            onclick={(e) => {
              e.stopPropagation();
              onremove?.(r);
            }}
          /></span>
        {/if}
      {:else}
        {col.format ? col.format(r) : ''}
      {/if}
    {/snippet}
  </VirtualTable>
  <p class="count"><NumText text={countText} /></p>
</div>

<style>
  .ens {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .ens > :global(.vt) {
    flex: 1;
  }
  /* The verdict on one line, Qt's scientific note wrapped under it (never cut). */
  .verdict {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0 var(--space-2);
    flex: none;
    min-height: 28px;
    margin: 0;
    padding: 4px var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .verdict :global(.icon) {
    color: var(--fg-muted);
    flex: none;
  }
  .words {
    font-weight: var(--weight-medium);
  }
  .min {
    color: var(--text-muted);
  }
  .note {
    flex-basis: 100%;
    padding-left: 24px;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .count {
    flex: none;
    margin: 0;
    padding: var(--space-1) var(--space-3);
    border-top: var(--border-w) solid var(--border-soft);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .mono {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .check {
    color: var(--text-muted);
  }
  .status {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex: none;
    background: var(--status-idle);
  }
  .status.ok .dot {
    background: var(--status-ok);
  }
  .status.warn .dot {
    background: var(--warning);
  }
  .status.warn {
    color: var(--fg);
  }
  .flags {
    color: var(--fg);
  }
  .flags.none {
    color: var(--text-muted);
  }
  .stale {
    color: var(--text-muted);
  }
  /* Remove shows on the row's hover, its selection or its focus (the remove glyph is a bar
     that would read as "no value" in a column of dashes). */
  .rm {
    display: inline-flex;
    opacity: 0;
  }
  :global(.tr:hover) .rm,
  :global(.tr.selected) .rm,
  .rm:focus-within,
  .rm.busy {
    opacity: 1;
  }
  @media (hover: none) {
    .rm {
      opacity: 1;
    }
  }
</style>

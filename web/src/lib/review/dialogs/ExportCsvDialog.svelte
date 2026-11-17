<!--
  Export CSV (web/spec/07-review-analysis.md 2.2 rows 1.10 #28, #30; README A79; protocol.md
  "CSV export (A79)"): the lossless measurements file the fixed core writes
  (`write_curves_csv`: star_id, role, name, auid + the 15 point columns), Qt's "Export
  measurements".

  - One filter per file (S61: the file has no filter column, so two filters' curves of one
    star would read back as one curve): with several, the observer chooses.
  - The curves of that filter, every role, ticked by default, grouped target / check /
    comparison with their role glyph and point count.
  - Destination: a file (default `<session>/<object>_<filter>_photometry.csv`, Browse…) or a
    download; an existing file asks "Replace?" inline (D29).
  - Export starts the `export` job (A79) and closes the dialog; the server's refusals (409
    no_points, multiple_filters, unknown_curve) are shown in its words.
-->
<script lang="ts">
  import { showTail } from '../../components/tail';
  import { untrack } from 'svelte';
  import Button from '../../components/Button.svelte';
  import Checkbox from '../../components/Checkbox.svelte';
  import Dialog from '../../components/Dialog.svelte';
  import FilePicker from '../../components/FilePicker.svelte';
  import type { FsLister } from '../../components/filepicker';
  import Icon from '../../components/Icon.svelte';
  import IconButton from '../../components/IconButton.svelte';
  import Segmented from '../../components/Segmented.svelte';
  import TextField from '../../components/TextField.svelte';
  import { int } from '../../format/number';
  import RoleGlyph from '../../imaging/field/RoleGlyph.svelte';
  import type { Role } from '../../viewer/overlay/layers';
  import type { Source } from '../landing/landing';
  import { csvBlock, csvBody, csvCountText, csvCurves, csvDefaultName, exportTarget, filterName, filtersOf, initialFilter, joinPath, type CurveRef, type Destination } from './aavso';
  import type { CsvBody, ExportTarget, JobStart } from './api';

  interface Props {
    open?: boolean;
    source: Source;
    sourceLabel: string;
    object: string | null;
    curves: readonly CurveRef[];
    /** The folder the default file goes in (the session's; null: a download by default). */
    folder: string | null;
    start: (body: CsvBody, target: ExportTarget) => Promise<JobStart>;
    onstarted?: (start: JobStart) => void;
    list: FsLister;
    filterNames?: readonly string[];
    /** The filter R1 shows (the dialog starts on it). */
    filter?: string | null;
    /** The curve keys R1 asks for (empty: every curve of the filter). */
    keys?: readonly string[];
    preview?: boolean;
  }

  let { open = $bindable(false), source, sourceLabel, object, curves, folder, start, onstarted, list, filterNames = [], filter: askedFilter = null, keys: askedKeys = [], preview = false }: Props = $props();

  const filters = $derived(filtersOf(curves, ['target', 'comparison', 'check']));
  let filter = $state<string | null>(null);
  let ticked = $state<string[]>([]);
  let dest = $state<Destination>('file');
  let path = $state('');
  let pathTouched = $state(false);
  let replace = $state(false);
  let busy = $state(false);
  let startError = $state<string | null>(null);

  const shown = $derived(csvCurves(curves, filter));
  const allCurves = $derived(shown.length > 0 && shown.every((c) => ticked.includes(c.key)));
  const chosen = $derived(shown.filter((c) => ticked.includes(c.key)));
  const ROLES: Role[] = ['target', 'check', 'comparison'];

  $effect(() => {
    if (!open) return;
    untrack(() => {
      filter = askedFilter && filters.includes(askedFilter) ? askedFilter : initialFilter(filters);
      firstTick = true;
      dest = folder ? 'file' : 'download';
      pathTouched = false;
      replace = false;
      startError = null;
    });
  });
  let firstTick = true;
  $effect(() => {
    const s = shown;
    if (!open) return;
    untrack(() => {
      const asked = firstTick ? s.filter((c) => askedKeys.includes(c.key)) : [];
      ticked = (asked.length ? asked : s).map((c) => c.key);
      firstTick = false;
    });
  });
  $effect(() => {
    const name = csvDefaultName(object, filter);
    if (!pathTouched && folder) untrack(() => (path = joinPath(folder, name)));
  });

  const block = $derived(csvBlock(curves, { filter, keys: ticked, allCurves }, dest, path));

  async function doExport(overwrite = false): Promise<void> {
    if (block || busy) return;
    busy = true;
    startError = null;
    try {
      const s = await start(csvBody(source, { filter, keys: ticked, allCurves }), exportTarget(dest, path, overwrite));
      replace = false;
      open = false;
      onstarted?.(s);
    } catch (err) {
      const code = (err as { code?: string } | null)?.code;
      if (code === 'file_exists') replace = true;
      else startError = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
    }
  }

  let pickerOpen = $state(false);
  const dirOf = (p: string) => (p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : null);
  const nameOf = (p: string) => (p.includes('/') ? p.slice(p.lastIndexOf('/') + 1) : p);
</script>

<Dialog bind:open title="Export measurements (CSV)" subtitle={sourceLabel} size="l" {preview} initialFocus=".primary-export button">
  <div class="form">
    <span class="k">Filter</span>
    <div class="v">
      {#if filters.length > 1}
        <Segmented label="Filter to export" size="s" mono options={filters.map((f) => ({ value: f, label: filterName(f, filterNames) }))} value={filter ?? ''} onchange={(v: string) => (filter = v)} />
        <span class="muted">one filter per file (the file has no filter column)</span>
      {:else}
        <span class="num">{filterName(filters[0] ?? '', filterNames)}</span>
      {/if}
    </div>

    <span class="k">Curves</span>
    <div class="v col">
      {#if !shown.length}
        <span class="muted">{filters.length > 1 && !filter ? 'Choose a filter first.' : 'No measurements to export.'}</span>
      {/if}
      {#each ROLES as role (role)}
        {#each shown.filter((c) => c.role === role) as c (c.key)}
          <div class="curve">
            <Checkbox label={c.name} checked={ticked.includes(c.key)} onchange={(on) => (ticked = on ? [...ticked, c.key] : ticked.filter((k) => k !== c.key))} />
            <RoleGlyph {role} size={14} />
            <span class="num muted">{int(c.n)} {c.n === 1 ? 'point' : 'points'}</span>
          </div>
        {/each}
      {/each}
      {#if shown.length}<span class="num muted count">{csvCountText(chosen)}</span>{/if}
    </div>

    <span class="k">Columns</span>
    <div class="v"><span class="muted">star_id, role, name, auid + the 15 point columns (JD UTC, BJD TDB, mag, errors, airmass, flags…), lossless</span></div>

    <span class="k">Save to</span>
    <div class="v col">
      <Segmented
        label="Save to"
        size="s"
        options={[
          { value: 'file', label: 'File' },
          { value: 'download', label: 'Download' },
        ]}
        value={dest}
        onchange={(v: Destination) => (dest = v)}
      />
      {#if dest === 'file'}
        <div class="path" use:showTail={path}>
          <TextField
            label="File"
            hideLabel
            mono
            value={path}
            placeholder="/…/RR_Lyr_ir_photometry.csv"
            oninput={(e) => {
              path = (e.currentTarget as HTMLInputElement).value;
              pathTouched = true;
              replace = false;
            }}
          />
          <IconButton icon="browse" label="Browse…" size="s" tooltip="top" onclick={() => (pickerOpen = true)} />
        </div>
      {:else}
        <span class="muted">The browser saves the file the server writes (kept 10 minutes).</span>
      {/if}
    </div>
  </div>

  {#snippet footer()}
    <div class="foot">
      {#if replace}
        <span class="warn-line" role="alert"><Icon name="attention" size={14} />{nameOf(path)} exists. Replace it?</span>
        <span class="grow"></span>
        <Button label="Keep it" variant="secondary" onclick={() => (replace = false)} />
        <Button label="Replace" variant="danger" {busy} onclick={() => void doExport(true)} />
      {:else}
        <span class="reason" class:error={!!startError} role={startError ? 'alert' : undefined}>{startError ?? block ?? ''}</span>
        <span class="grow"></span>
        <Button label="Cancel" variant="secondary" onclick={() => (open = false)} />
        <span class="primary-export"><Button label="Export" variant="primary" {busy} disabledReason={block} onclick={() => void doExport(false)} /></span>
      {/if}
    </div>
  {/snippet}
</Dialog>

{#if pickerOpen}
  <FilePicker
    bind:open={pickerOpen}
    mode="save-file"
    title="Export measurements to…"
    start={dirOf(path) ?? folder}
    {list}
    defaultName={nameOf(path) || csvDefaultName(object, filter)}
    filters={[{ label: 'CSV (.csv)', ext: ['.csv'] }]}
    onchoose={(p) => {
      path = p;
      pathTouched = true;
      replace = false;
    }}
  />
{/if}

<style>
  .form {
    display: grid;
    grid-template-columns: 96px minmax(0, 1fr);
    gap: var(--space-3) var(--space-4);
    align-items: baseline;
    font-size: var(--text-s);
  }
  .k {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .v {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .v.col {
    flex-direction: column;
    align-items: flex-start;
  }
  .curve {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .count {
    margin-top: var(--space-1);
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .muted {
    color: var(--text-muted);
  }
  .warn-line {
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-1);
  }
  .warn-line :global(svg) {
    flex: none;
    align-self: center;
    color: var(--warning);
  }
  .path {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
  }
  .path :global(.field) {
    flex: 1;
  }
  .foot {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    min-width: 0;
  }
  .reason {
    min-width: 0;
    overflow: hidden;
    color: var(--text-muted);
    font-size: var(--text-xs);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .reason.error {
    color: var(--fg);
    white-space: normal;
  }
  .grow {
    flex: 1;
  }
</style>

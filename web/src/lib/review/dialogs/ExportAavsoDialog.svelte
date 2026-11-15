<!--
  Export AAVSO extended format (web/spec/07-review-analysis.md WF-E, 2.4; README M92, A77, A78,
  S11, Q-R2, Q-R3; protocol.md "AAVSO preview (A77) and export (A78)").

  - Every choice asks the server's preview again (A77, never writes): the dialog shows what the
    fixed core writer would write, its head in mono, the rows per target and the points left
    out (saturated, suspect, non-finite, undated: always left out, with counts, Q-R3, S56,
    S58, S60), the check star giving KNAME / KMAG, OBSCODE, FILT (with the server's warning
    when it does not fit the frames' filter, export allowed), CHART, and the airmass note
    when the run's Settings site was wrong.
  - One filter at a time (S53): with curves in several filters the observer chooses one; only
    that filter's targets and check star are listed.
  - Refusals come first and in the server's words: an unset observer code blocks the Export
    (Q-R2: "Set your AAVSO observer code in Settings first…", with Open Settings), as do a
    curve whose star or role is unknown (S10), no target, every point left out.
  - Destination: a file (default `<session>/<object>_<filter>_aavso.txt`, editable, Browse…)
    or a download; an existing file asks "Replace?" inline (never overwritten silently, D29).
  - Export starts the `export` job (A78) and closes the dialog; the job strip and a toast
    tell the outcome.
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
  import Spinner from '../../components/Spinner.svelte';
  import TextField from '../../components/TextField.svelte';
  import { int } from '../../format/number';
  import RoleGlyph from '../../imaging/field/RoleGlyph.svelte';
  import type { Source } from '../landing/landing';
  import {
    aavsoBody,
    bandReason,
    curvesIn,
    excludedText,
    exportBlock,
    exportTarget,
    filterName,
    filtersOf,
    initialFilter,
    otherNotes,
    flagWarnings,
    flaggedPointText,
    rowsText,
    type CurveRef,
    type Destination,
  } from './aavso';
  import type { AavsoBody, AavsoPreview, ExportTarget, JobStart } from './api';

  interface Props {
    open?: boolean;
    source: Source;
    /** One line: what is exported ("RR Lyr · 20260925T200453Z_RR_Lyr · session photometry"). */
    sourceLabel: string;
    curves: readonly CurveRef[];
    /** A77 (the shared client's, or a fixture in the gallery). */
    getPreview: (body: AavsoBody, signal?: AbortSignal) => Promise<AavsoPreview>;
    /** A78: start the job; reject with the server's ApiError (409 file_exists, refusals). */
    start: (body: AavsoBody, target: ExportTarget) => Promise<JobStart>;
    /** The job started (the integrator shows it in the job strip). */
    onstarted?: (start: JobStart) => void;
    /** Settings › Observer and site at the observer code. */
    onsettings?: () => void;
    /** The FilePicker's listing (A11). */
    list: FsLister;
    /** The wheel's filter names, for labels ("IR"). */
    filterNames?: readonly string[];
    /** Where Browse starts when the preview proposes no file. */
    defaultDir?: string | null;
    /** The filter R1 shows (the dialog starts on it; null: the only one, else the observer chooses). */
    filter?: string | null;
    /** The target keys R1 asks for (empty: every target of the filter). */
    keys?: readonly string[];
    /** Gallery: draw in place. */
    preview?: boolean;
  }

  let {
    open = $bindable(false),
    source,
    sourceLabel,
    curves,
    getPreview,
    start,
    onstarted,
    onsettings,
    list,
    filterNames = [],
    defaultDir = null,
    filter: askedFilter = null,
    keys: askedKeys = [],
    preview = false,
  }: Props = $props();

  // -- Choices -----------------------------------------------------------------------------------
  const filters = $derived(filtersOf(curves));
  let filter = $state<string | null>(null);
  let ticked = $state<string[]>([]);
  let useCheck = $state(true);
  let checkKey = $state<string | null>(null);
  let filt = $state('');
  let chart = $state('');
  let dest = $state<Destination>('file');
  let path = $state('');
  let pathTouched = $state(false);

  const targets = $derived(curvesIn(curves, 'target', filter));
  const checks = $derived(curvesIn(curves, 'check', filter));
  const allTargets = $derived(targets.length > 0 && targets.every((t) => ticked.includes(t.key)));

  // Reset the choices each time the dialog opens (and when the filter changes: its curves).
  $effect(() => {
    if (!open) return;
    untrack(() => {
      filter = askedFilter && filters.includes(askedFilter) ? askedFilter : initialFilter(filters);
      firstTick = true;
      filt = '';
      chart = '';
      dest = 'file';
      pathTouched = false;
      replace = false;
      startError = null;
    });
  });
  let firstTick = true;
  $effect(() => {
    const ts = targets;
    const cs = checks;
    if (!open) return;
    untrack(() => {
      const asked = firstTick ? ts.filter((t) => askedKeys.includes(t.key) && t.exportable !== false) : [];
      // An unidentified curve (S10) starts unticked so the others can be sent; when none is
      // identified they stay ticked and the server's refusal says why.
      const ok = ts.filter((t) => t.exportable !== false);
      ticked = (asked.length ? asked : ok.length ? ok : ts).map((t) => t.key);
      firstTick = false;
      checkKey = cs[0]?.key ?? null;
    });
  });

  // -- Preview (A77) -----------------------------------------------------------------------------
  let pv = $state<AavsoPreview | null>(null);
  let pvError = $state<string | null>(null);
  let pending = $state(false);
  const body = $derived(aavsoBody(source, { filter, keys: ticked, allTargets, checkKey, useCheck, filt: bandReason(filt) ? '' : filt, chart }));

  $effect(() => {
    if (!open) return;
    if (filters.length > 1 && !filter) {
      pv = null;
      return;
    }
    const b = body;
    const controller = new AbortController();
    pending = true;
    const timer = setTimeout(() => {
      getPreview(b, controller.signal)
        .then((p) => {
          if (controller.signal.aborted) return;
          pv = p;
          pvError = null;
          if (!pathTouched && p.default_path) path = p.default_path;
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted) return;
          pvError = err instanceof Error ? err.message : String(err);
        })
        .finally(() => {
          if (!controller.signal.aborted) pending = false;
        });
    }, 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  });

  // -- Export (A78) --------------------------------------------------------------------------------
  let busy = $state(false);
  let replace = $state(false);
  let startError = $state<string | null>(null);
  const block = $derived(pvError ? `Preview failed: ${pvError}` : exportBlock(pv, { filter, keys: ticked, allTargets, filt }, filters, dest, path, pending));
  const obscodeRefused = $derived.by(() => pv?.refusal?.code === 'obscode_unset');

  async function doExport(overwrite = false): Promise<void> {
    if (block || busy) return;
    busy = true;
    startError = null;
    try {
      const s = await start(body, exportTarget(dest, path, overwrite));
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

  // -- Browse --------------------------------------------------------------------------------------
  let pickerOpen = $state(false);
  const dirOf = (p: string) => (p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : null);
  const nameOf = (p: string) => (p.includes('/') ? p.slice(p.lastIndexOf('/') + 1) : p);
  const label = (t: string | null) => filterName(t, filterNames);
</script>

<Dialog bind:open title="Export AAVSO extended format" subtitle={sourceLabel} size="l" {preview} initialFocus=".primary-export button">
  <div class="form">
    {#if filters.length > 1}
      <span class="k">Filter</span>
      <div class="v">
        <Segmented
          label="Filter to report"
          size="s"
          mono
          options={filters.map((f) => ({ value: f, label: label(f) }))}
          value={filter ?? ''}
          onchange={(v: string) => (filter = v)}
        />
        <span class="hint">one band per AAVSO report</span>
      </div>
    {:else}
      <span class="k">Filter</span>
      <div class="v"><span class="num">{label(filter ?? filters[0] ?? '')}</span></div>
    {/if}

    <span class="k">Targets</span>
    <div class="v col">
      {#if !targets.length}
        <span class="muted">{filters.length > 1 && !filter ? 'Choose a filter first.' : 'No target curve in this source.'}</span>
      {/if}
      {#each targets as t (t.key)}
        {@const line = pv?.targets.find((x) => x.key === t.key)}
        <div class="target">
          <Checkbox
            label={t.name}
            checked={ticked.includes(t.key)}
            disabledReason={t.exportable === false ? (t.problem ?? 'the star or role of this curve is unknown') : null}
            onchange={(on) => (ticked = on ? [...ticked, t.key] : ticked.filter((k) => k !== t.key))}
          />
          <RoleGlyph role="target" size={14} />
          <span class="num muted">{line ? `${rowsText(line.rows)} of ${int(line.points)}` : `${int(t.n)} points`}</span>
        </div>
      {/each}
    </div>

    <span class="k">Check star</span>
    <div class="v">
      {#if filters.length > 1 && !filter}
        <span class="muted">Choose a filter first.</span>
      {:else if checks.length}
        <Checkbox label={checks.find((c) => c.key === checkKey)?.name ?? checks[0].name} checked={useCheck} onchange={(on) => (useCheck = on)} />
        <RoleGlyph role="check" size={14} />
        <span class="muted">{useCheck ? (pv?.check ? `KNAME ${pv.check.kname} · KMAG on ${rowsText(pv.check.kmag_rows)}` : 'KNAME / KMAG from its ensemble magnitude') : 'KNAME / KMAG = na'}</span>
      {:else}
        <span class="muted">No check star in this filter → KNAME / KMAG = na</span>
      {/if}
    </div>

    <span class="k">OBSCODE</span>
    <div class="v">
      {#if pv && !pv.obscode_set}
        <span class="warn-line" role="alert"><Icon name="attention" size={14} />Unset: {pv.refusal?.code === 'obscode_unset' ? pv.refusal.message : 'set your AAVSO observer code in Settings.'}</span>
        {#if onsettings}<IconButton icon="settings" label="Open Settings" showLabel size="s" variant="secondary" onclick={() => onsettings?.()} />{/if}
      {:else}
        <span class="num">{pv?.obscode ?? '…'}</span><span class="muted">from Settings</span>
      {/if}
    </div>

    <span class="k">FILT</span>
    <div class="v">
      <span class="field-s"><TextField label="FILT" hideLabel mono value={filt} placeholder={pv?.band_source === 'settings' ? pv.band : 'TG'} error={bandReason(filt)} oninput={(e) => (filt = (e.currentTarget as HTMLInputElement).value)} /></span>
      <span class="muted">{filt.trim() ? 'typed' : 'Settings band'}</span>
      {#if pv?.band_note}<span class="warn-line"><Icon name="attention" size={14} />{pv.band_note}</span>{/if}
    </div>

    <span class="k">CHART</span>
    <div class="v">
      <span class="field-s"><TextField label="CHART" hideLabel mono value={chart} placeholder={pv?.chart && pv.chart !== 'na' ? pv.chart : 'na'} oninput={(e) => (chart = (e.currentTarget as HTMLInputElement).value)} /></span>
      <span class="muted">{chart.trim() ? 'typed' : pv?.chart_source === 'targets' ? 'from the comparison sequence (targets.json)' : 'no chart known: na'}</span>
    </div>

    <span class="k">DATE</span>
    <div class="v"><span class="muted">JD UTC at mid-exposure · MTYPE STD · CNAME ENSEMBLE · TRANS NO</span></div>

    {#if pv}
      {@const left = excludedText(pv.excluded)}
      <span class="k">Rows</span>
      <div class="v col">
        <span><span class="num">{rowsText(pv.rows)}</span>{#if left}<span class="muted">{` · ${left}`}</span>{/if}</span>
        {#if pv.airmass.state === 'mismatch' && pv.airmass.message}
          <span class="warn-line"><Icon name="attention" size={14} />{pv.airmass.message}</span>
        {/if}
        {#each flagWarnings(pv) as w (w.code)}
          <span class="warn-line"><Icon name="attention" size={14} />{w.message}</span>
        {/each}
        {#if pv.flagged_points.length}
          <span class="note num">{pv.flagged_points.map(flaggedPointText).join(' · ')}</span>
        {/if}
        {#each otherNotes(pv) as n, i (i)}<span class="note">{n}</span>{/each}
      </div>
    {/if}

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
            placeholder="/…/object_filter_aavso.txt"
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

  <section class="head" aria-label="Preview of the file">
    <div class="head-title">
      <span class="eyebrow">Preview</span>
      {#if pending}<Spinner size={12} /><span class="muted">updating…</span>{/if}
    </div>
    {#if pv && pv.head}
      <pre class="num">{pv.head}</pre>
    {:else if pv?.refusal}
      <p class="muted">Nothing would be written: {pv.refusal.message}</p>
    {:else if pvError}
      <p class="error" role="alert">Preview failed: {pvError}</p>
    {:else}
      <p class="muted">{filters.length > 1 && !filter ? 'Choose a filter to see the file.' : 'Preparing…'}</p>
    {/if}
  </section>

  {#snippet footer()}
    <div class="foot">
      {#if replace}
        <span class="warn-line" role="alert"><Icon name="attention" size={14} />{nameOf(path)} exists. Replace it?</span>
        <span class="grow"></span>
        <Button label="Keep it" variant="secondary" onclick={() => (replace = false)} />
        <Button label="Replace" variant="danger" busy={busy} onclick={() => void doExport(true)} />
      {:else}
        <span class="reason" class:error={!!startError} role={startError ? 'alert' : undefined}>{startError ?? (obscodeRefused ? '' : (block ?? ''))}</span>
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
    title="Export AAVSO to…"
    start={dirOf(path) ?? defaultDir}
    {list}
    defaultName={nameOf(path) || `${pv?.object ?? 'target'}_aavso.txt`}
    filters={[{ label: 'AAVSO report (.txt)', ext: ['.txt'] }]}
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
  .target {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .muted,
  .hint {
    color: var(--text-muted);
  }
  .hint {
    font-size: var(--text-xs);
  }
  .note {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .warn-line {
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-1);
    color: var(--fg);
  }
  .warn-line :global(svg) {
    flex: none;
    align-self: center;
    color: var(--warning);
  }
  .field-s {
    width: 120px;
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
  .head {
    margin-top: var(--space-4);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  .head-title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .eyebrow {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  pre {
    max-height: 132px;
    margin: 0;
    padding: var(--space-2) var(--space-3);
    overflow: auto;
    color: var(--fg);
    font-size: var(--text-xs);
    line-height: var(--leading-normal);
    white-space: pre;
  }
  .head p {
    margin: 0;
    padding: var(--space-2) var(--space-3);
    font-size: var(--text-s);
  }
  .error {
    color: var(--fg);
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

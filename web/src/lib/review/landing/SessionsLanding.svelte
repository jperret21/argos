<!--
  Review R0, the landing (web/spec/07-review-analysis.md 2.1, WF-A, 2.4 states; README M80,
  M94, M103, D3, D19, Q-R4, Q-R5): what can be reviewed.

  - Toolbar (one row): [Open folder…] (a session folder anywhere, by the in-app FilePicker,
    Q-R4), [Import CSV…] (a curve CSV becomes a pseudo-session, A70), [Open FITS] (R2, icon
    only, ⌘/Ctrl+O in Review), the sessions folder (mono, full path in the tooltip), Refresh;
    at the right the scope (All, Photometry, Issues) and the search (object, date, folder,
    filter; "/" focuses it).
  - The live run (D3), while a sequence is under way: one row above the list, read-only,
    "Open" shows it on the plot wall.
  - Recent: the last sources opened (sessions, CSVs, FITS), per viewer; × forgets one.
  - The list (A67): Started (UTC), Object, Lights, Filters, Curves (T target, C comparison,
    K check), Quality report, Issues (a count that opens the server's lines), Folder. Newest
    first; sortable; Enter or a double click opens; the row being opened shows a spinner.
  - States: loading (skeleton rows, aria-busy), link down ("Waiting for the ARGOS server"),
    error (inline banner with the server's words + Retry; the last list stays), empty ("No
    sessions in {root}" + Open folder… / Import CSV…), a missing folder, a paged list.
  Props-driven (no app context), so the gallery shows every state; the integrator passes the
  LandingStore's fields and handles `onopen` (A68 / A70 / R2).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import type { SessionPage, SessionSummary } from '../../api/types';
  import type { ShortcutRegistry } from '../../app/shortcuts';
  import FilePicker from '../../components/FilePicker.svelte';
  import { ANY_FILTER, FITS_FILTER, type FileFilter, type FsLister, type PickerMode } from '../../components/filepicker';
  import Icon from '../../components/Icon.svelte';
  import IconButton from '../../components/IconButton.svelte';
  import Popover from '../../components/Popover.svelte';
  import SearchField from '../../components/SearchField.svelte';
  import Segmented from '../../components/Segmented.svelte';
  import Spinner from '../../components/Spinner.svelte';
  import Table from '../../components/Table.svelte';
  import type { Column } from '../../components/table';
  import { tooltip } from '../../components/tooltip';
  import { int } from '../../format/number';
  import { middleEllipsis } from '../../format/path';
  import {
    curvesSpoken,
    curvesText,
    emptyText,
    filterSessions,
    filtersText,
    issueCount,
    KIND_ICON,
    KIND_WORD,
    pagingNote,
    SCOPES,
    startedMs,
    startedText,
    type LiveSource,
    type RecentItem,
    type ReviewSource,
    type Scope,
  } from './landing';

  interface Props {
    page: SessionPage | null;
    loading?: boolean;
    /** The last list request failed (the server's words); the last list stays. */
    error?: string | null;
    /** The server link is down: nothing can be listed or opened. */
    linkDown?: boolean;
    /** The live run (D3), while a sequence is under way. */
    live?: LiveSource | null;
    recent?: readonly RecentItem[];
    query?: string;
    scope?: Scope;
    /** Path being opened (its row shows a spinner). */
    opening?: string | null;
    /** The last open failed: inline banner (07 2.4 "Error"). */
    openError?: { path: string; message: string } | null;
    /** The FilePicker's listing (A11). */
    list: FsLister;
    /**
     * Open a source. A promise keeps the FilePicker busy; resolving to a string shows that
     * refusal in the picker and keeps it open (FilePicker contract).
     */
    onopen: (source: ReviewSource) => unknown;
    onrefresh?: () => void;
    onforget?: (item: RecentItem) => void;
    onquery?: (q: string) => void;
    onscope?: (s: Scope) => void;
    ondismisserror?: () => void;
    /** Settings › Storage (the sessions folder). */
    onsettings?: () => void;
    /** Shortcut shown on Open FITS (the registry's). */
    openFitsKey?: string;
    /** The registry: R0 binds "/" (search.focus, scope analyze.r0) while mounted. */
    shortcuts?: ShortcutRegistry | null;
    /** Gallery: open the issues popover of this row. */
    previewIssues?: string | null;
  }

  let {
    page,
    loading = false,
    error = null,
    linkDown = false,
    live = null,
    recent = [],
    query = $bindable(''),
    scope = $bindable('all'),
    opening = null,
    openError = null,
    list,
    onopen,
    onrefresh,
    onforget,
    onquery,
    onscope,
    ondismisserror,
    onsettings,
    openFitsKey = 'Mod+O',
    shortcuts = null,
    previewIssues = null,
  }: Props = $props();

  const CSV_FILTER: FileFilter = { label: 'Curve CSV (.csv)', ext: ['.csv'] };

  const sessions = $derived(page?.sessions ?? []);
  const shown = $derived(filterSessions(sessions, query, scope));
  const filtered = $derived(!!query.trim() || scope !== 'all');
  const paging = $derived(page ? pagingNote(page.total, sessions.length) : null);
  const root = $derived(page?.root ?? null);
  let selected = $state<string | null>(null);

  // -- Issues popover --------------------------------------------------------------------------
  let issuesFor = $state.raw<SessionSummary | null>(null);
  let issuesAnchor = $state<HTMLElement | null>(null);
  let issuesOpen = $state(false);
  $effect(() => {
    if (!previewIssues) return;
    const s = sessions.find((x) => x.path === previewIssues) ?? null;
    untrack(() => {
      issuesFor = s;
      issuesOpen = !!s;
    });
  });

  function showIssues(s: SessionSummary, el: HTMLElement): void {
    issuesFor = s;
    issuesAnchor = el;
    issuesOpen = true;
  }

  // -- File picker -------------------------------------------------------------------------------
  type Pick = 'folder' | 'csv' | 'fits';
  let pick = $state<Pick | null>(null);
  let pickerOpen = $state(false);
  const PICKS: Record<Pick, { mode: PickerMode; title: string; filters?: FileFilter[]; kind: 'session' | 'import' | 'fits' }> = {
    folder: { mode: 'open-folder', title: 'Open a session folder', kind: 'session' },
    csv: { mode: 'open-file', title: 'Import a curve CSV', filters: [CSV_FILTER, ANY_FILTER], kind: 'import' },
    fits: { mode: 'open-file', title: 'Open a FITS frame', filters: [FITS_FILTER, ANY_FILTER], kind: 'fits' },
  };
  function openPicker(p: Pick): void {
    pick = p;
    pickerOpen = true;
  }
  /** Exposed to the integrator: ⌘/Ctrl+O in Review opens the FITS picker here. */
  export function pickFits(): void {
    openPicker('fits');
  }

  const offline = $derived(linkDown ? 'the ARGOS server is not reachable' : null);

  // -- Keys (scope analyze.r0): "/" focuses the search ------------------------------------------
  let rootEl = $state<HTMLDivElement | undefined>();
  $effect(() => {
    const reg = shortcuts;
    if (!reg) return;
    const off = reg.handle('search.focus', () => queueMicrotask(() => rootEl?.querySelector<HTMLInputElement>('.toolbar input')?.focus()));
    return off;
  });

  /** "6/6 stable", "3/8": the vetting verdict, not the word "report" (design review). */
  function qualityText(s: SessionSummary): string {
    if (s.quality) return `${s.quality.stable}/${s.quality.total}${s.quality.stable === s.quality.total ? ' stable' : ''}`;
    return s.has_quality ? 'report' : '—';
  }

  // -- Columns -----------------------------------------------------------------------------------
  const columns: Column<SessionSummary>[] = [
    { id: 'started', label: 'Started (UTC)', value: (s) => startedMs(s.started_utc), format: (s) => startedText(s.started_utc), numeric: true, width: '19ch' },
    { id: 'object', label: 'Object', value: (s) => s.object || null, width: '14ch' },
    { id: 'lights', label: 'Lights', value: (s) => s.lights, format: (s) => int(s.lights), numeric: true, width: '7ch' },
    { id: 'filters', label: 'Filters', value: (s) => filtersText(s.filters), width: '10ch' },
    { id: 'curves', label: 'Curves', title: 'Photometry CSVs: T target, C comparison, K check', value: (s) => s.curves.target * 1e6 + s.curves.comparison * 1e3 + s.curves.check, format: (s) => curvesText(s.curves), width: '13ch' },
    { id: 'quality', label: 'Quality', title: 'Comparison vetting (photometry_quality.json): comparisons stable of those vetted', value: (s) => (s.quality ? s.quality.stable / Math.max(1, s.quality.total) : s.has_quality ? -1 : null), format: (s) => qualityText(s), width: '10ch' },
    { id: 'issues', label: 'Issues', value: (s) => issueCount(s), numeric: true, width: '7ch' },
    { id: 'folder', label: 'Folder', value: (s) => s.folder },
  ];
</script>

<div class="r0" aria-busy={loading || undefined} bind:this={rootEl}>
  <div class="toolbar" role="toolbar" aria-label="Review sessions">
    <IconButton icon="open-session" label="Open folder…" showLabel variant="secondary" size="s" disabledReason={offline} onclick={() => openPicker('folder')} />
    <IconButton icon="open-file" label="Import CSV…" showLabel variant="secondary" size="s" disabledReason={offline} onclick={() => openPicker('csv')} />
    <IconButton icon="open-image" label="Open FITS" shortcut={openFitsKey} size="s" tooltip="bottom" disabledReason={offline} onclick={() => openPicker('fits')} />
    <span class="divider" aria-hidden="true"></span>
    <span class="root num" use:tooltip={{ text: root ? `Sessions folder: ${root}` : 'No sessions folder', placement: 'bottom' }}>
      {root ? middleEllipsis(root, 48) : '—'}
    </span>
    <IconButton icon="refresh" label="Refresh the list" size="s" tooltip="bottom" busy={loading} disabledReason={offline} onclick={() => onrefresh?.()} />
    {#if onsettings}
      <IconButton icon="settings" label="Sessions folder in Settings" size="s" tooltip="bottom" onclick={() => onsettings?.()} />
    {/if}
    <span class="grow"></span>
    <Segmented label="Show" size="s" options={SCOPES} value={scope} onchange={(v: Scope) => { scope = v; onscope?.(v); }} />
    <SearchField
      label="Search the sessions"
      value={query}
      placeholder="Search: object, date, folder…"
      width="240px"
      count={filtered && sessions.length ? `${int(shown.length)} of ${int(sessions.length)}` : null}
      oninput={(v) => {
        query = v;
        onquery?.(v);
      }}
    />
  </div>

  {#if linkDown}
    <div class="banner" role="status">
      <Icon name="network" size={16} />
      <span>Waiting for the ARGOS server: the list and the files come back when it answers.</span>
    </div>
  {:else if error}
    <div class="banner error" role="alert">
      <Icon name="network" size={16} />
      <span class="msg">Could not list the sessions: {error}</span>
      <IconButton icon="refresh" label="Retry" showLabel size="s" variant="secondary" onclick={() => onrefresh?.()} />
    </div>
  {/if}
  {#if openError}
    <div class="banner error" role="alert">
      <Icon name="open-session" size={16} />
      <span class="msg">Could not open <span class="num">{middleEllipsis(openError.path, 60)}</span>: {openError.message}</span>
      {#if ondismisserror}<IconButton icon="close" label="Dismiss" size="s" variant="ghost" tooltip="bottom" onclick={() => ondismisserror?.()} />{/if}
    </div>
  {/if}

  {#if live}
    <section class="live" aria-label="Live run">
      <span class="eyebrow">Live run</span>
      <Icon name="live" size={16} />
      <span class="live-id">{live.object || 'Unnamed object'}</span>
      <span class="num muted">{live.started_utc ? `started ${startedText(live.started_utc).slice(11, 19)} UTC` : ''}</span>
      <span class="num muted">· {int(live.frames)} {live.frames === 1 ? 'frame' : 'frames'}</span>
      <span class="state">· {live.state}</span>
      <span class="muted note">read-only here: the ensemble is edited in Observe</span>
      <span class="grow"></span>
      <IconButton icon="nav-analyze" label="Review the live run" showLabel size="s" variant="secondary" disabledReason={offline} onclick={() => onopen({ kind: 'live' })} />
    </section>
  {/if}

  {#if recent.length}
    <section class="recent" aria-label="Recent">
      <span class="eyebrow">Recent</span>
      <ul>
        {#each recent as item (item.kind + item.path)}
          <li class="chip">
            <button
              type="button"
              class="chip-open"
              aria-disabled={offline ? 'true' : undefined}
              use:tooltip={{ text: `${KIND_WORD[item.kind]}: ${item.path}`, reason: offline, placement: 'bottom' }}
              onclick={() => {
                if (!offline) onopen({ kind: item.kind, path: item.path });
              }}
            >
              <Icon name={KIND_ICON[item.kind]} size={16} />
              <span class="chip-label">{item.label}</span>
            </button>
            {#if onforget}
              <button type="button" class="chip-x" aria-label="Forget {item.label}" use:tooltip={{ text: 'Forget', placement: 'bottom' }} onclick={() => onforget?.(item)}>
                <Icon name="close" size={12} />
              </button>
            {/if}
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  <div class="list">
    {#if !loading && page && !sessions.length}
      <div class="empty">
        <Icon name="open-session" size={48} />
        <p class="title">{emptyText(root, page.exists, false)}</p>
        <p class="hint">Open a session folder elsewhere, or import a curve CSV.</p>
        <div class="cta">
          <IconButton icon="open-session" label="Open folder…" showLabel variant="secondary" disabledReason={offline} onclick={() => openPicker('folder')} />
          <IconButton icon="open-file" label="Import CSV…" showLabel variant="secondary" disabledReason={offline} onclick={() => openPicker('csv')} />
        </div>
      </div>
    {:else}
      <Table
        label="Sessions"
        {columns}
        rows={shown}
        rowKey={(s) => s.path}
        bind:selected
        persist="review.sessions"
        loading={loading && !page}
        empty={emptyText(root, page?.exists ?? true, filtered)}
        maxHeight="100%"
        onactivate={(s) => {
          if (!offline) onopen({ kind: 'session', path: s.path });
        }}
      >
        {#snippet cell(s: SessionSummary, col: Column<SessionSummary>)}
          {#if col.id === 'issues'}
            {@const n = issueCount(s)}
            {#if n}
              <button type="button" class="issues num" aria-haspopup="dialog" aria-label="{n} {n === 1 ? 'issue' : 'issues'}: show" onclick={(e) => showIssues(s, e.currentTarget)}>
                <Icon name="attention" size={12} />{int(n)}
              </button>
            {:else}
              <span class="muted" aria-label="no issue">–</span>
            {/if}
          {:else if col.id === 'curves'}
            <span class="num" aria-label={curvesSpoken(s.curves)} class:muted={curvesText(s.curves) === 'none'}>{curvesText(s.curves)}</span>
          {:else if col.id === 'quality'}
            {#if s.quality}
              <span class="quality num" use:tooltip={{ text: `${s.quality.stable} of ${s.quality.total} comparisons stable (photometry_quality.json)` }}><span class="qdot" class:warn={s.quality.stable < s.quality.total} aria-hidden="true"></span>{qualityText(s)}</span>
            {:else}
              <span class:muted={!s.has_quality}>{qualityText(s)}</span>
            {/if}
          {:else if col.id === 'folder'}
            <span class="folder" use:tooltip={{ text: s.path, placement: 'top' }}>
              {#if opening === s.path}<Spinner size={12} /><span class="visually-hidden">Opening</span>{/if}
              <span class="num">{s.folder}</span>
            </span>
          {:else}
            {col.format ? col.format(s) : String(col.value?.(s) ?? '—')}
          {/if}
        {/snippet}
      </Table>
      {#if paging}<p class="paging">{paging}</p>{/if}
    {/if}
  </div>
</div>

<Popover bind:open={issuesOpen} anchor={issuesAnchor} title={issuesFor ? `${issuesFor.folder} · ${issueCount(issuesFor)} ${issueCount(issuesFor) === 1 ? 'issue' : 'issues'}` : 'Issues'} placement="bottom-end" width={360} preview={!!previewIssues}>
  {#if issuesFor}
    <ul class="issue-list">
      {#each issuesFor.issues as line, i (i)}
        <li><Icon name="attention" size={12} /><span>{line}</span></li>
      {/each}
    </ul>
  {/if}
</Popover>

{#if pick}
  {@const p = PICKS[pick]}
  <FilePicker
    bind:open={pickerOpen}
    mode={p.mode}
    title={p.title}
    start={root}
    {list}
    filters={p.filters}
    countFits={pick === 'folder'}
    onchoose={(path) => onopen({ kind: p.kind, path })}
    onclose={() => (pick = null)}
  />
{/if}

<style>
  .r0 {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-width: 0;
    min-height: 0;
    background: var(--bg);
  }
  .toolbar {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--space-2);
    height: var(--toolbar-h);
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border);
    background: var(--bg);
    min-width: 0;
  }
  .divider {
    width: var(--border-w);
    height: 20px;
    background: var(--border);
  }
  .root {
    min-width: 0;
    overflow: hidden;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-s);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .grow {
    flex: 1;
  }
  .banner {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--space-2);
    min-height: 32px;
    padding: var(--space-1) var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .banner.error {
    box-shadow: inset 3px 0 0 var(--danger);
  }
  .banner .msg {
    flex: 1;
    min-width: 0;
  }
  .eyebrow {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
    white-space: nowrap;
  }
  .live,
  .recent {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--space-2);
    min-height: 36px;
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    font-size: var(--text-s);
    min-width: 0;
  }
  .live-id {
    font-weight: var(--weight-medium);
  }
  .live .note {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .muted {
    color: var(--text-muted);
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .recent ul {
    display: flex;
    gap: var(--space-2);
    min-width: 0;
    margin: 0;
    padding: 0;
    overflow: hidden;
    list-style: none;
  }
  .chip {
    display: inline-flex;
    flex: none;
    align-items: center;
    max-width: 280px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--surface);
  }
  .chip-open,
  .chip-x {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 24px;
    border: none;
    background: transparent;
    color: var(--fg);
    font: inherit;
    cursor: pointer;
  }
  .chip-open {
    min-width: 0;
    padding: 0 var(--space-2);
  }
  .chip-open :global(svg) {
    flex: none;
    color: var(--fg-muted);
  }
  .chip-label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .chip-x {
    padding: 0 var(--space-1);
    color: var(--fg-muted);
  }
  .chip-open:hover,
  .chip-x:hover {
    background: var(--hover-bg);
  }
  .chip-open:focus-visible,
  .chip-x:focus-visible,
  .issues:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .list {
    display: flex;
    flex: 1 1 0;
    flex-direction: column;
    min-height: 0;
  }
  .list :global(.table-wrap),
  .list > :global(:first-child) {
    min-height: 0;
  }
  .issues {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 20px;
    padding: 0 var(--space-1);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-s);
    cursor: pointer;
  }
  .issues :global(svg) {
    color: var(--warning);
  }
  .issues:hover {
    background: var(--hover-bg);
  }
  .folder {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    min-width: 0;
  }
  .paging {
    flex: none;
    margin: 0;
    padding: var(--space-1) var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .empty {
    display: flex;
    flex: 1;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    color: var(--fg-muted);
    text-align: center;
  }
  .empty .title {
    margin: var(--space-2) 0 0;
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  .empty .hint {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .empty .cta {
    display: flex;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }
  .issue-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: var(--text-s);
  }
  .issue-list li {
    display: grid;
    grid-template-columns: 12px minmax(0, 1fr);
    gap: var(--space-2);
    align-items: baseline;
  }
  .issue-list :global(svg) {
    color: var(--warning);
  }
  .quality {
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
  .qdot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--text-muted);
  }
  .qdot.warn {
    background: var(--warning);
  }
</style>

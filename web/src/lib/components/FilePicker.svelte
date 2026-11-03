<!--
  In-app file picker (web/spec/README.md 3.6, D20, 01 2.3.12): replaces the
  18 Qt QFileDialog sites in every build and theme (an OS dialog is grey in
  Night Red). Backed by the server's read-only listing (`list`, A11), which
  only lists the observer's home and the ARGOS data folders: the Places
  column shows exactly the roots the server allows, and a typed path outside
  them is refused by the server with its words (shown inline).

  Layout (640 px dialog): breadcrumb + refresh; Places | entries (name, size
  or FITS count, modified UTC); the path field (open modes) or the file name
  (save); hidden files toggle, type; [Cancel] [Open | Choose folder | Save].

  Keyboard: the list is one tab stop (aria-activedescendant): ↑ ↓ Home End
  PgUp PgDn move, letters jump (type-ahead), Enter opens a folder or chooses
  a file, Backspace or Alt+↑ goes to the parent folder. The path field takes
  an absolute path: Enter goes to that folder, or selects that file. Esc =
  Cancel. Save mode asks "Replace?" inline before overwriting a file.

  `preview` + `previewListing` draw it in place (gallery).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import Checkbox from './Checkbox.svelte';
  import Control from './Control.svelte';
  import Dialog from './Dialog.svelte';
  import {
    ANY_FILTER,
    baseName,
    breadcrumbs,
    type FileFilter,
    folderDetail,
    formatMtime,
    formatSize,
    type FsLister,
    type FsListing,
    isAbsolute,
    joinPath,
    normalizePlaces,
    parentOf,
    pickerChoice,
    type PickerMode,
    PRIMARY_LABEL,
    visibleEntries,
    withSuffix,
  } from './filepicker';
  import { isTypeaheadKey, navTarget, Typeahead } from './listnav';
  import { refusalText } from './commit.svelte';
  import { middlePath } from './pathfield';
  import { tooltip } from './tooltip';

  interface Props {
    open?: boolean;
    mode: PickerMode;
    /** The task ("Choose the sessions folder"). */
    title: string;
    /** Where it opens (the field's current value, or a default folder). */
    start?: string | null;
    list: FsLister;
    /** File types (open-file, save-file); the first is the default. */
    filters?: readonly FileFilter[];
    /** Save mode: the proposed name. */
    defaultName?: string;
    /** Count FITS files in folders (choosing a frames folder). */
    countFits?: boolean;
    onchoose?: (path: string) => void;
    onclose?: () => void;
    preview?: boolean;
    previewListing?: FsListing | null;
    previewSelected?: string | null;
    previewError?: string | null;
  }

  let {
    open = $bindable(false),
    mode,
    title,
    start = null,
    list,
    filters = [ANY_FILTER],
    defaultName = '',
    countFits = false,
    onchoose,
    onclose,
    preview = false,
    previewListing = null,
    previewSelected = null,
    previewError = null,
  }: Props = $props();

  const uid = `fp-${Math.random().toString(36).slice(2, 9)}`;
  let listing: FsListing | null = $state(untrack(() => previewListing));
  let loading = $state(false);
  let error: string | null = $state(untrack(() => previewError));
  let filterIndex = $state(0);
  let showHidden = $state(false);
  let active = $state(-1);
  let typed = $state(untrack(() => previewListing?.path ?? ''));
  let saveName = $state(untrack(() => defaultName));
  let confirmReplace = $state(false);
  let listEl: HTMLElement | undefined = $state();
  const typeahead = new Typeahead();
  let controller: AbortController | null = null;

  const filter = $derived(filters[filterIndex] ?? ANY_FILTER);
  const places = $derived(normalizePlaces(listing?.places));
  const home = $derived(places.find((p) => p.id === 'home' || p.label.toLowerCase() === 'home')?.path ?? null);
  const crumbs = $derived(listing ? breadcrumbs(listing.path, home) : []);
  const rows = $derived(listing ? visibleEntries(listing.entries, mode, filter, showHidden) : []);
  const selected = $derived(active >= 0 ? (rows[active] ?? null) : null);
  const choice = $derived(pickerChoice(mode, listing, selected, saveName, filter));

  async function go(path: string | null, select: string | null = null): Promise<boolean> {
    controller?.abort();
    const ctrl = new AbortController();
    controller = ctrl;
    loading = true;
    try {
      const next = await list(
        {
          path,
          kind: mode === 'open-folder' ? 'dir' : 'file',
          ext: mode === 'open-file' || mode === 'save-file' ? [...filter.ext] : null,
          counts: countFits ? 'fits' : null,
          hidden: showHidden,
        },
        ctrl.signal,
      );
      if (ctrl.signal.aborted) return false;
      listing = next;
      error = null;
      confirmReplace = false;
      typed = next.path;
      const shown = visibleEntries(next.entries, mode, filter, showHidden);
      active = select ? shown.findIndex((e) => e.name === select) : -1;
      queueMicrotask(scrollActive);
      return true;
    } catch (err) {
      if (ctrl.signal.aborted) return false;
      error = refusalText(err); // the previous listing stays
      return false;
    } finally {
      if (controller === ctrl) loading = false;
    }
  }

  // Open: list the start folder (or the file's folder) once per opening.
  $effect(() => {
    if (!open || preview) return;
    untrack(() => {
      saveName = defaultName;
      filterIndex = 0;
      void openAt(start);
    });
  });

  /** A typed or start path: a folder is listed; a file selects it in its folder. */
  async function openAt(path: string | null): Promise<void> {
    if (path === null || !path.trim()) {
      await go(null);
      return;
    }
    if (await go(path)) return;
    const parent = parentOf(path);
    if (parent === null) return;
    const firstError = error;
    const name = baseName(path);
    if (await go(parent, name)) {
      if (mode === 'save-file') saveName = name;
    } else {
      error = firstError;
    }
  }

  function scrollActive(): void {
    if (!listEl || active < 0) return;
    listEl.querySelector<HTMLElement>(`#${uid}-opt-${active}`)?.scrollIntoView({ block: 'nearest' });
  }

  function activate(i: number): void {
    const e = rows[i];
    if (!e || !listing) return;
    if (e.kind === 'dir') void go(joinPath(listing.path, e.name));
    else if (mode !== 'open-folder') choose();
  }

  function choose(): void {
    if (!choice.path) return;
    if (mode === 'save-file' && choice.exists && !confirmReplace) {
      confirmReplace = true;
      return;
    }
    const path = mode === 'save-file' && listing ? joinPath(listing.path, withSuffix(saveName, filter)) : choice.path;
    open = false;
    onchoose?.(path);
  }

  function onListKey(e: KeyboardEvent): void {
    if (!listing) return;
    if (e.key === 'Backspace' || (e.key === 'ArrowUp' && e.altKey)) {
      e.preventDefault();
      if (listing.parent) void go(listing.parent, baseName(listing.path));
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      if (active >= 0) activate(active);
      else choose();
      return;
    }
    const next = navTarget(e.key, rows.length, active, undefined, { wrap: false, page: 8 });
    if (next !== null) {
      e.preventDefault();
      active = next;
      if (mode === 'save-file' && rows[next]?.kind === 'file') saveName = rows[next].name;
      queueMicrotask(scrollActive);
      return;
    }
    if (isTypeaheadKey(e)) {
      const i = typeahead.push(e.key, rows.map((r) => r.name), active);
      if (i >= 0) {
        active = i;
        queueMicrotask(scrollActive);
      }
    }
  }

  function onTypedKey(e: KeyboardEvent): void {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const t = typed.trim();
    if (!t) return;
    if (!isAbsolute(t)) {
      error = 'Type an absolute path (starting with / or ~)';
      return;
    }
    void openAt(t);
  }

  function close(): void {
    controller?.abort();
    onclose?.();
  }

  $effect(() => () => controller?.abort());

  const primaryReason = $derived(loading && !listing ? 'the folder is still loading' : choice.reason);
</script>

<Dialog bind:open {title} size="l" {preview} onclose={close} initialFocus="#{uid}-list">
  <div class="picker">
    <div class="crumbs" aria-label="Folder">
      <nav class="trail" aria-label="Path">
        {#each crumbs as c, i (c.path)}
          {#if i > 0}<span class="sep" aria-hidden="true">/</span>{/if}
          {#if i === crumbs.length - 1}
            <span class="crumb current" aria-current="location">{c.label}</span>
          {:else}
            <button type="button" class="crumb" onclick={() => void go(c.path)}>{c.label}</button>
          {/if}
        {/each}
      </nav>
      <Control
        icon="refresh"
        label="Refresh"
        variant="ghost"
        size="s"
        busy={loading}
        onclick={() => void go(listing?.path ?? start)}
      />
    </div>

    <div class="panes">
      <ul class="places" aria-label="Places">
        {#each places as p (p.path)}
          <li>
            <button
              type="button"
              class="place"
              class:current={listing?.path === p.path}
              class:missing={p.exists === false}
              aria-current={listing?.path === p.path ? 'location' : undefined}
              aria-disabled={p.exists === false || undefined}
              use:tooltip={{ text: p.path, reason: p.exists === false ? 'does not exist yet' : null, placement: 'right' }}
              onclick={() => p.exists !== false && void go(p.path)}
            >
              <span class="place-label">{p.label}</span>
            </button>
          </li>
        {/each}
      </ul>

      <div class="list-wrap">
        <div class="head" aria-hidden="true">
          <span>Name</span>
          <span class="r">{countFits ? 'Size / FITS' : 'Size'}</span>
          <span class="r">Modified (UTC)</span>
        </div>
        <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
        <div
          id="{uid}-list"
          class="list"
          role="listbox"
          tabindex="0"
          aria-label="Contents of {listing ? baseName(listing.path) : 'the folder'}"
          aria-busy={loading || undefined}
          aria-activedescendant={active >= 0 ? `${uid}-opt-${active}` : undefined}
          bind:this={listEl}
          onkeydown={onListKey}
        >
          {#if listing && listing.parent}
            <!-- svelte-ignore a11y_click_events_have_key_events (keys: the listbox, Backspace) -->
            <div
              class="row parent"
              role="option"
              aria-selected="false"
              tabindex="-1"
              onclick={() => listing?.parent && void go(listing.parent, baseName(listing.path))}
            >
              <span class="name">..</span><span></span><span></span>
            </div>
          {/if}
          {#each rows as e, i (e.name)}
            <!-- svelte-ignore a11y_click_events_have_key_events (keys: the listbox, aria-activedescendant) -->
            <div
              id="{uid}-opt-{i}"
              class="row"
              class:dir={e.kind === 'dir'}
              class:active={i === active || (preview && previewSelected === e.name)}
              role="option"
              aria-selected={i === active || (preview && previewSelected === e.name)}
              tabindex="-1"
              onclick={() => {
                active = i;
                if (mode === 'save-file' && e.kind === 'file') saveName = e.name;
              }}
              ondblclick={() => activate(i)}
            >
              <span class="name">{e.name}{e.kind === 'dir' ? '/' : ''}</span>
              <span class="r num">{e.kind === 'dir' ? folderDetail(e) : formatSize(e.size)}</span>
              <span class="r num">{formatMtime(e.mtime)}</span>
            </div>
          {:else}
            <p class="empty">
              {#if loading && !listing}Loading…{:else if mode === 'open-folder'}No folders here.{:else}No {filter.ext.length ? filter.label : 'files'} here.{/if}
            </p>
          {/each}
        </div>
      </div>
    </div>

    {#if error}
      <p class="error" role="alert">{error}</p>
    {:else if listing?.truncated}
      <p class="note">More than 5 000 entries: only the first 5 000 are listed. Type a path to go further.</p>
    {/if}

    {#if mode === 'save-file'}
      <label class="line">
        <span class="key">Name</span>
        <input class="mono" type="text" autocomplete="off" spellcheck="false" bind:value={saveName} oninput={() => (confirmReplace = false)} />
      </label>
      {#if confirmReplace}
        <p class="replace" role="alert">
          <span>{withSuffix(saveName, filter)} already exists in this folder. Replace it?</span>
        </p>
      {/if}
    {:else}
      <label class="line">
        <span class="key">Path</span>
        <input
          class="mono"
          type="text"
          autocomplete="off"
          spellcheck="false"
          bind:value={typed}
          use:middlePath={{ value: typed }}
          onkeydown={onTypedKey}
          aria-describedby="{uid}-typed-help"
        />
      </label>
      <span id="{uid}-typed-help" class="visually-hidden">Type an absolute path and press Enter to go there.</span>
    {/if}
  </div>

  {#snippet footer()}
    <div class="foot-left">
      <Checkbox
        label="Hidden files"
        size="s"
        bind:checked={showHidden}
        onchange={() => {
          active = -1;
          if (!preview && listing) void go(listing.path); // the server leaves them out unless asked
        }}
      />
      {#if filters.length > 1}
        <div class="types" role="radiogroup" aria-label="File type">
          {#each filters as f, i (f.label)}
            <button
              type="button"
              role="radio"
              aria-checked={i === filterIndex}
              class="type"
              class:on={i === filterIndex}
              onclick={() => {
                filterIndex = i;
                active = -1;
              }}>{f.label}</button
            >
          {/each}
        </div>
      {:else if filter.ext.length}
        <span class="type-fact">{filter.label}</span>
      {/if}
    </div>
    <Control label="Cancel" size="s" onclick={() => (open = false)} />
    <Control
      label={confirmReplace ? 'Replace' : PRIMARY_LABEL[mode]}
      variant={confirmReplace ? 'danger' : 'primary'}
      size="s"
      disabledReason={primaryReason}
      onclick={choose}
    />
  {/snippet}
</Dialog>

<style>
  .picker {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .crumbs {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .trail {
    display: flex;
    flex: 1;
    align-items: center;
    gap: 2px;
    min-width: 0;
    overflow: hidden;
    font-family: var(--font-mono);
    font-size: var(--text-s);
    white-space: nowrap;
  }
  .sep {
    color: var(--text-muted);
  }
  .crumb {
    flex: none;
    padding: 2px 4px;
    border: none;
    border-radius: var(--radius-s);
    background: none;
    color: var(--text-muted);
    font: inherit;
    cursor: pointer;
  }
  .crumb:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .crumb:focus-visible,
  .place:focus-visible,
  .type:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .crumb.current {
    flex: 0 1 auto;
    overflow: hidden;
    color: var(--fg);
    cursor: default;
    text-overflow: ellipsis;
  }

  .panes {
    display: grid;
    grid-template-columns: 140px minmax(0, 1fr);
    height: 300px;
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    overflow: hidden;
  }
  .places {
    margin: 0;
    padding: var(--space-1);
    overflow: auto;
    border-right: var(--border-w) solid var(--border-soft);
    background: var(--bg-2);
    list-style: none;
  }
  .place {
    display: flex;
    width: 100%;
    height: var(--row-h);
    align-items: center;
    padding: 0 var(--space-2);
    border: none;
    border-radius: var(--radius-s);
    background: none;
    color: var(--fg);
    font: inherit;
    font-size: var(--text-s);
    text-align: left;
    cursor: pointer;
  }
  .place:hover {
    background: var(--hover-bg);
  }
  .place.current {
    background: var(--toggled-bg);
  }
  .place.missing {
    color: var(--fg-disabled);
    cursor: not-allowed;
  }
  .note {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .place-label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .list-wrap {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
  }
  .head,
  .row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 92px 128px;
    align-items: center;
    gap: var(--space-3);
    padding: 0 var(--space-3);
  }
  .head {
    flex: none;
    height: var(--row-h);
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
  }
  .r {
    text-align: right;
  }
  .list {
    flex: 1;
    min-height: 0;
    overflow: auto;
    outline: none;
  }
  /* Roving focus (design review): the focused list never rings the whole
     region in brass (5 467 px); the active row carries the focus: its 2 px
     bar in the focus colour and the toggled fill. With no active row (the
     current folder is the choice) the list shows a neutral 1 px inset edge,
     so the focus stays visible without brass. */
  .list:focus-visible:not(:has(.row.active)) {
    box-shadow: inset 0 0 0 1px var(--fg-muted);
  }
  .row {
    height: var(--row-h);
    font-size: var(--text-s);
    cursor: default;
  }
  .row:hover {
    background: var(--hover-bg);
  }
  .row.active {
    background: var(--toggled-bg);
    box-shadow: inset 2px 0 0 var(--fg-muted);
  }
  .list:focus-visible .row.active {
    box-shadow: inset 2px 0 0 var(--focus-ring);
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .row.dir .name,
  .parent .name {
    font-weight: var(--weight-medium);
  }
  .row .num {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .empty {
    margin: 0;
    padding: var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-s);
  }

  .error,
  .replace {
    display: flex;
    align-items: baseline;
    gap: 6px;
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
  }
  .error::before,
  .replace::before {
    content: '';
    flex: none;
    width: 6px;
    height: 6px;
    border-radius: var(--radius-round);
    background: var(--danger);
    transform: translateY(-1px);
  }
  .replace::before {
    background: var(--warning);
  }

  .line {
    display: grid;
    grid-template-columns: 44px minmax(0, 1fr);
    align-items: center;
    gap: var(--space-3);
  }
  .key {
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .line input {
    height: var(--input-h);
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .line input:hover {
    border-color: var(--fg-muted);
  }
  .line input:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 2px;
  }
  .mono {
    font-family: var(--font-mono);
  }

  .foot-left {
    display: flex;
    flex: 1;
    align-items: center;
    gap: var(--space-4);
    min-width: 0;
  }
  .type-fact {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .types {
    display: inline-flex;
    gap: 2px;
  }
  .type {
    height: 22px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: none;
    color: var(--text-muted);
    font: inherit;
    font-size: var(--text-xs);
    cursor: pointer;
  }
  .type.on {
    border-color: var(--border);
    background: var(--toggled-bg);
    color: var(--fg);
  }
</style>

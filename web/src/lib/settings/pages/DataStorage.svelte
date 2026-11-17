<!--
  Settings › Data & storage (02 1.10, 1.11, W7; M31-M34). The sessions and
  presets folders (path fields: the server says "does not exist, it will be
  created" or refuses "not writable"; [browse] opens the in-app FilePicker),
  then the five catalogue caches (A83): what each holds, where it lives, how
  much is in it. [browse] picks another location (one PATCH of its
  data_paths.* key, applied to the core at once); [Clear…] asks first
  (W10a: nothing is downloaded now, the next lookup fetches fresh data) and
  deletes locally. Never uploaded.
-->
<script lang="ts">
  import type { CacheInfo, KeyMeta } from '../../api/types';
  import { useApp } from '../../app/state.svelte';
  import ConfirmDialog from '../../components/ConfirmDialog.svelte';
  import Control from '../../components/Control.svelte';
  import FilePicker from '../../components/FilePicker.svelte';
  import { formatSize } from '../../components/filepicker';
  import { isDefault } from '../../components/settings';
  import { int } from '../../format/number';
  import SettingsBlock from '../SettingsBlock.svelte';

  interface Props {
    query?: string;
  }
  let { query = '' }: Props = $props();

  const app = useApp();
  const CACHE_KEYS = [
    'data_paths.object_catalogue_cache',
    'data_paths.exoplanet_cache',
    'data_paths.aavso_cache_directory',
    'data_paths.gaia_cache_directory',
    'data_paths.field_catalogue_cache_directory',
  ];

  let caches: CacheInfo[] = $state.raw([]);
  let error: string | null = $state(null);
  let rowError: Record<string, string> = $state({});
  let busy: string | null = $state(null);
  let confirm: CacheInfo | null = $state.raw(null);
  let confirmOpen = $state(false);
  let picking: CacheInfo | null = $state.raw(null);
  let pickerOpen = $state(false);

  const watched = $derived(CACHE_KEYS.map((k) => String(app.configValues?.[k] ?? '')).join('|'));

  async function refresh(): Promise<void> {
    try {
      caches = (await app.client.caches()).caches;
      error = null;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }
  $effect(() => {
    void watched;
    if (app.linkOpen) void refresh();
  });

  function contents(c: CacheInfo): string {
    if (!c.exists || c.files === 0) return 'empty';
    const what = c.path_kind === 'file' ? 'cached' : `${int(c.files)} ${c.files === 1 ? 'file' : 'files'}`;
    return `${what} · ${formatSize(c.bytes)}`;
  }

  /** "…/Argos/cache/object_resolver.json": the end of the path, which tells caches apart. */
  function shortPath(p: string): string {
    const parts = p.split('/').filter(Boolean);
    return parts.length > 3 ? `…/${parts.slice(-3).join('/')}` : p;
  }

  async function setLocation(c: CacheInfo, path: string): Promise<void> {
    const before = app.configValues?.[c.key];
    busy = `path:${c.kind}`;
    rowError = { ...rowError, [c.kind]: '' };
    try {
      const r = await app.patchConfig({ [c.key]: path });
      const w = r.warnings.find((x) => x.key === c.key);
      if (w) rowError = { ...rowError, [c.kind]: w.message };
      if (typeof before === 'string') {
        app.undo.push({ title: `${c.label}: new location`, detail: `Was ${before}`, undo: () => app.patchConfig({ [c.key]: before }) });
      }
    } catch (err) {
      const fields = (err as { fields?: Record<string, string> | null }).fields;
      rowError = { ...rowError, [c.kind]: fields?.[c.key] ?? (err instanceof Error ? err.message : String(err)) };
    } finally {
      busy = null;
    }
  }

  async function clear(c: CacheInfo): Promise<void> {
    busy = `clear:${c.kind}`;
    try {
      const r = await app.client.clearCache(c.kind);
      caches = caches.map((x) => (x.kind === c.kind ? r.cache : x));
      app.toast('info', `Cleared the ${c.label}`, `${int(r.removed)} ${r.removed === 1 ? 'file' : 'files'} removed. Nothing was downloaded.`);
    } catch (err) {
      app.reportError('Clear cache', err);
    } finally {
      busy = null;
    }
  }

  const metaOf = (key: string): KeyMeta | undefined => app.configMeta?.[key];
</script>

<div class="page">
  <SettingsBlock title="Folders" keys={['sessions_path', 'data_paths.sequence_presets_directory']} {query} hideEmpty={!!query} />
  {#if query}
    <SettingsBlock title="Catalogue caches" keys={CACHE_KEYS} {query} hideEmpty />
  {:else}
    <section class="caches" aria-labelledby="caches-title">
      <div class="head">
        <h3 class="title" id="caches-title">Catalogue caches</h3>
        <p class="caption">Never uploaded. Clearing makes the next lookup fetch fresh data.</p>
      </div>
      {#if error}<p class="error">{error}</p>{/if}
      <div class="table" role="table" aria-label="Catalogue caches">
        <div class="row header" role="row">
          <span role="columnheader">Cache</span>
          <span role="columnheader">Location</span>
          <span role="columnheader" class="r">Contents</span>
          <span role="columnheader"><span class="visually-hidden">Actions</span></span>
        </div>
        {#each caches as c (c.kind)}
          {@const m = metaOf(c.key)}
          {@const changed = m ? !isDefault(app.configValues?.[c.key], m) : false}
          <div class="row" role="row" data-key={c.key}>
            <span role="cell" class="label">
              {m?.label ?? c.label}
              <span class="sub">{c.label}</span>
            </span>
            <span role="cell" class="path mono" title={c.path}>
              {shortPath(c.path)}
              {#if changed}<span class="custom">custom location</span>{/if}
            </span>
            <span role="cell" class="r num">{contents(c)}</span>
            <span role="cell" class="actions">
              <Control
                icon="browse"
                label="Choose the location of the {c.label}…"
                size="xs"
                variant="ghost"
                tooltip="top"
                tooltipText="Choose location…"
                busy={busy === `path:${c.kind}`}
                onclick={() => {
                  picking = c;
                  pickerOpen = true;
                }}
              />
              {#if changed && m}
                <Control
                  label="Reset"
                  size="xs"
                  variant="ghost"
                  tooltip="top"
                  tooltipText="Back to the default location: {String(m.default)}"
                  onclick={() => void setLocation(c, String(m.default))}
                />
              {/if}
              <Control
                icon="clear"
                label="Clear…"
                showLabel
                size="xs"
                variant="ghost"
                busy={busy === `clear:${c.kind}`}
                disabledReason={!c.exists || c.files === 0 ? 'the cache is empty' : null}
                onclick={() => {
                  confirm = c;
                  confirmOpen = true;
                }}
              />
            </span>
            {#if rowError[c.kind]}<p class="row-note" role="status">{rowError[c.kind]}</p>{/if}
          </div>
        {:else}
          <p class="empty">Reading the caches…</p>
        {/each}
      </div>
    </section>
  {/if}
</div>

{#if confirm}
  <ConfirmDialog
    bind:open={confirmOpen}
    title="Clear the {confirm.label}?"
    confirmLabel="Clear cache"
    destructive
    onconfirm={() => clear(confirm!)}
  >
    <p>
      {confirm.path_kind === 'file' ? 'The cache file' : `${int(confirm.files)} ${confirm.files === 1 ? 'file' : 'files'}`} in
      <span class="mono">{confirm.path}</span>.
    </p>
    <p>Nothing is downloaded now; the next matching lookup fetches fresh data if the internet is available.</p>
  </ConfirmDialog>
{/if}

{#if picking}
  <!-- A file cache keeps its file name: the folder is chosen (02 1.10 #7: never a save dialog). -->
  {@const file = picking.path_kind === 'file' ? (picking.path.split('/').pop() ?? '') : ''}
  <FilePicker
    bind:open={pickerOpen}
    mode="open-folder"
    title={file ? `Choose the folder of the ${picking.label} (${file})` : `Choose the folder of the ${picking.label}`}
    start={file ? picking.path.slice(0, picking.path.length - file.length - 1) : picking.path}
    list={app.listFiles}
    onchoose={(p) => picking && void setLocation(picking, file ? `${p.replace(/\/$/, '')}/${file}` : p)}
    onclose={() => (picking = null)}
  />
{/if}

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }
  .caches {
    max-width: var(--page-max-w);
  }
  .head {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 0 var(--space-3);
    padding-bottom: var(--space-2);
    border-bottom: var(--border-w) solid var(--border);
  }
  .title {
    margin: 0;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .caption {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .table {
    display: flex;
    flex-direction: column;
  }
  .row {
    display: grid;
    grid-template-columns: minmax(0, 13fr) minmax(0, 15fr) 112px 168px;
    align-items: center;
    gap: 2px var(--space-4);
    min-height: 40px;
    padding: var(--space-1) 0 var(--space-1) var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
    font-size: var(--text-s);
  }
  .row.header {
    min-height: var(--row-h);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .label {
    display: flex;
    flex-direction: column;
    min-width: 0;
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .sub {
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-regular);
  }
  .path {
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: hidden;
    color: var(--fg);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .custom {
    color: var(--text-muted);
    font-family: var(--font-ui);
    font-size: var(--text-xs);
  }
  .mono {
    font-family: var(--font-mono);
    font-size: var(--text-s);
  }
  .r {
    text-align: right;
  }
  .actions {
    display: inline-flex;
    justify-content: flex-end;
    gap: 2px;
  }
  .row-note {
    grid-column: 2 / -1;
    margin: 0;
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .error,
  .empty {
    margin: var(--space-2) 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  p {
    margin: 0 0 var(--space-2);
  }
</style>

<!--
  Saved sites (02 1.7 #11-#15, W3; key `site.favorites`): a table instead of
  the Qt combo (values visible), the current default marked "Default".
  Row actions: [bookmark] Set as default (writes the four site keys, Undo),
  [remove] Remove (immediate + Undo toast, 6 s; README 3.3: no
  confirmation). Below: a name field and [bookmark Save current site]; a
  saved site of the same name (any case) is replaced, as in Qt
  (configuration_page.py:954-972). Every change is one PATCH of the whole
  list; another client's change arrives through the `config` event.
-->
<script lang="ts">
  import { useApp } from '../app/state.svelte';
  import Control from '../components/Control.svelte';
  import Table from '../components/Table.svelte';
  import type { Column } from '../components/table';
  import { fixed, signed } from '../format/number';
  import {
    currentSite,
    type Favorite,
    favoritesOf,
    isDefaultFavorite,
    removeFavorite,
    siteChanges,
    siteText,
    upsertFavorite,
  } from './sites';

  const app = useApp();
  const favorites = $derived(favoritesOf(app.configValues?.['site.favorites']));
  const site = $derived(currentSite(app.configValues));

  let name = $state('');
  let busy: string | null = $state(null);
  let message: { tone: 'info' | 'error'; text: string } | null = $state.raw(null);

  const columns: Column<Favorite>[] = [
    { id: 'name', label: 'Name', value: (f) => f.name },
    { id: 'latitude', label: 'Latitude', numeric: true, value: (f) => f.latitude, format: (f) => `${signed(f.latitude, 5)}°`, width: '118px' },
    { id: 'longitude', label: 'Longitude', numeric: true, value: (f) => f.longitude, format: (f) => `${signed(f.longitude, 5)}°`, width: '124px' },
    { id: 'elevation', label: 'Elev.', title: 'Elevation, m', numeric: true, value: (f) => f.elevation, format: (f) => `${fixed(f.elevation, 0, { group: true })} m`, width: '76px' },
    { id: 'actions', label: 'Actions', hideLabel: true, sortable: false, width: '72px' },
  ];

  async function writeList(list: Favorite[]): Promise<void> {
    await app.patchConfig({ 'site.favorites': list.map((f) => ({ ...f })) });
  }

  async function setDefault(f: Favorite): Promise<void> {
    const before = currentSite(app.configValues);
    busy = `default:${f.name}`;
    message = null;
    try {
      await app.patchConfig(siteChanges(f));
      app.undo.push({
        title: `Default site: ${f.name}`,
        detail: `Was ${siteText(before)}`,
        undo: () => app.patchConfig(siteChanges(before)),
      });
    } catch (err) {
      message = { tone: 'error', text: err instanceof Error ? err.message : String(err) };
    } finally {
      busy = null;
    }
  }

  async function remove(f: Favorite): Promise<void> {
    const before = favorites;
    busy = `remove:${f.name}`;
    message = null;
    try {
      await writeList(removeFavorite(before, f.name));
      app.undo.push({ title: `Removed the saved site ${f.name}`, undo: () => writeList(before) });
    } catch (err) {
      message = { tone: 'error', text: err instanceof Error ? err.message : String(err) };
    } finally {
      busy = null;
    }
  }

  async function saveCurrent(): Promise<void> {
    const n = name.trim() || site.name.trim();
    if (!n) {
      message = { tone: 'error', text: 'Name the site before saving it.' };
      return;
    }
    const before = favorites;
    const { list, replaced } = upsertFavorite(before, { ...site, name: n });
    busy = 'save';
    message = null;
    try {
      await writeList(list);
      name = '';
      message = { tone: 'info', text: replaced ? `Updated the saved site ${n}.` : `Saved the current site as ${n}.` };
    } catch (err) {
      message = { tone: 'error', text: err instanceof Error ? err.message : String(err) };
    } finally {
      busy = null;
    }
  }
</script>

<div class="saved-sites" data-key="site.favorites">
  <Table
    label="Saved sites"
    {columns}
    rows={favorites}
    rowKey={(f) => f.name}
    selectable={false}
    empty="No saved sites yet."
    maxHeight="196px"
  >
    {#snippet cell(row, col)}
      {#if col.id === 'name'}
        <span class="name">
          <span>{row.name}</span>
          {#if isDefaultFavorite(row, site)}<span class="chip">Default</span>{/if}
        </span>
      {:else if col.id === 'actions'}
        <span class="actions">
          <Control
            icon="bookmark"
            label="Set {row.name} as the default site"
            size="xs"
            variant="ghost"
            tooltip="top"
            tooltipText="Set as default site"
            busy={busy === `default:${row.name}`}
            disabledReason={isDefaultFavorite(row, site) ? 'it is the default site already' : null}
            onclick={() => void setDefault(row)}
          />
          <Control
            icon="remove"
            label="Remove the saved site {row.name}"
            size="xs"
            variant="ghost"
            tooltip="top"
            tooltipText="Remove (Undo for 6 s)"
            busy={busy === `remove:${row.name}`}
            onclick={() => void remove(row)}
          />
        </span>
      {:else if col.id === 'latitude'}
        <span class="num">{signed(row.latitude, 5)}°</span>
      {:else if col.id === 'longitude'}
        <span class="num">{signed(row.longitude, 5)}°</span>
      {:else if col.id === 'elevation'}
        <span class="num">{fixed(row.elevation, 0, { group: true })} m</span>
      {/if}
    {/snippet}
  </Table>
  <div class="save">
    <label class="visually-hidden" for="fav-name">Name for the current site</label>
    <input
      id="fav-name"
      type="text"
      maxlength="80"
      autocomplete="off"
      placeholder={site.name ? `Name for the current site (default: ${site.name})` : 'Name for the current site'}
      bind:value={name}
      onkeydown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          void saveCurrent();
        }
      }}
    />
    <Control
      icon="bookmark"
      label="Save current site"
      showLabel
      size="s"
      variant="secondary"
      busy={busy === 'save'}
      onclick={() => void saveCurrent()}
    />
  </div>
  {#if message}
    <p class="message tone-{message.tone}" role={message.tone === 'error' ? 'alert' : 'status'}>{message.text}</p>
  {/if}
</div>

<style>
  .saved-sites {
    max-width: var(--page-max-w);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
  }
  .name {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  .chip {
    padding: 0 var(--space-1);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    font-family: var(--font-mono);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .actions {
    display: inline-flex;
    gap: 2px;
  }
  .save {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-3);
    border-top: var(--border-w) solid var(--border-soft);
  }
  .save input {
    height: var(--input-h);
    min-width: 0;
    padding: 0 var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font: inherit;
    font-size: var(--text-m);
  }
  .save input::placeholder {
    color: var(--text-muted);
  }
  .save input:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .message {
    margin: 0;
    padding: 0 var(--space-3) var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .message.tone-error {
    color: var(--fg);
  }
</style>

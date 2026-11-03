<!--
  Settings (F5; web/spec/02-connection-and-settings.md 2.3 W3-W8, 2.4; README
  1.2, D13; M27-M37). Category list (208 px) | form (max 880 px) | "About
  this setting" column (260 px, only at 1440 px and wider, Q-C8).

  - Nine categories (D13); the selected one is remembered per viewer
    (argos.settings.category). ↑ ↓ Home End move in the list; "/" focuses
    the filter, which searches every category at once (label, help, key,
    unit, where it is used) and shows the matching fields in place.
  - Every field comes from the server's config meta (SettingsForm): one
    PATCH per commit, refused with the server's words under the field.
    The header says "Saved" for 2 s after a commit of this page, and names
    a change made by another window or program as it arrives (the field
    itself follows, unless it holds a draft: "Changed elsewhere").
  - A category with an attention item (Q-G11) carries the mark of its
    level (BRAND 8): the upright attention mark (a bar over a dot) when the
    site is missing or disagrees with the mount, the hollow ring for info
    (no AAVSO code). The same StatusBadge levels in the intro list.
  - Restore defaults (Q-C6): the category's settings back to the shipped
    defaults in one commit, after a confirmation, with Undo. Saved sites and
    the electron gain table are data, never reset; the observer's own
    values (name, AAVSO code, site: meta.personal) have no default to go
    back to and are left alone (0°, 0° is not a site).
  - The "About this setting" column shows the pointed or focused key; with
    none, a summary of the category (how many settings, which differ from
    the defaults), never an empty placeholder.
  - The command palette and links open a category at one key
    (app.settingsFocus): the field is scrolled into view and focused.
-->
<script lang="ts">
  import { tick, untrack } from 'svelte';
  import type { ConfigValue } from '../api/types';
  import { useApp } from '../app/state.svelte';
  import ConfirmDialog from '../components/ConfirmDialog.svelte';
  import Control from '../components/Control.svelte';
  import Icon from '../components/Icon.svelte';
  import KeyHint from '../components/KeyHint.svelte';
  import SearchField from '../components/SearchField.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { formatValue, isDefault, matchesQuery } from '../components/settings';
  import { tooltip } from '../components/tooltip';
  import { int } from '../format/number';
  import {
    CATEGORIES,
    CATEGORY_BY_ID,
    CONNECTION_KEYS,
    keyFacts,
    keysOf,
    type SettingsCategoryId,
    settingsAttention,
  } from './categories';
  import About from './pages/About.svelte';
  import Appearance from './pages/Appearance.svelte';
  import Catalogues from './pages/Catalogues.svelte';
  import DataStorage from './pages/DataStorage.svelte';
  import Instrument from './pages/Instrument.svelte';
  import ObserverSite from './pages/ObserverSite.svelte';
  import Photometry from './pages/Photometry.svelte';
  import PlateSolving from './pages/PlateSolving.svelte';
  import Privacy from './pages/Privacy.svelte';
  import SettingsBlock from './SettingsBlock.svelte';

  const app = useApp();

  let query = $state('');
  let body: HTMLElement | undefined = $state();
  let list: HTMLElement | undefined = $state();
  let filterWrap: HTMLElement | undefined = $state();
  let helpKey: string | null = $state(null);
  let flashKey: string | null = $state(null);

  const category = $derived(app.settingsCategory);
  const def = $derived(CATEGORY_BY_ID[category]);
  const meta = $derived(app.configMeta ?? {});
  const values = $derived(app.configValues ?? {});
  const attention = $derived(settingsAttention(app.configValues, app.siteCheck));
  const attentionOf = (id: SettingsCategoryId) => attention.filter((a) => a.category === id);

  // -- Filter ------------------------------------------------------------------------
  const filtering = $derived(query.trim().length > 0);
  const matchCount = (id: SettingsCategoryId) =>
    keysOf(meta, id).filter((k) => matchesQuery(k, meta[k], query)).length;
  const counts = $derived(
    filtering ? Object.fromEntries(CATEGORIES.map((c) => [c.id, matchCount(c.id)])) as Record<SettingsCategoryId, number> : null,
  );
  const connectionMatches = $derived(
    filtering ? CONNECTION_KEYS.filter((k) => k in meta && matchesQuery(k, meta[k], query)).length : 0,
  );
  const total = $derived(counts ? Object.values(counts).reduce((a, b) => a + b, 0) + connectionMatches : 0);

  // -- Saved / changed elsewhere --------------------------------------------------------
  let now = $state(Date.now());
  $effect(() => {
    const t = setInterval(() => (now = Date.now()), 500);
    return () => clearInterval(t);
  });
  const labelOf = (k: string) => meta[k]?.label ?? k;
  const saved = $derived(app.lastConfigSave && now - app.lastConfigSave.t < 2500 ? app.lastConfigSave : null);
  const remote = $derived(app.lastRemoteConfig && now - app.lastRemoteConfig.t < 6000 ? app.lastRemoteConfig : null);
  const stamp = (t: number) => `${new Date(t).toISOString().slice(11, 19)} UTC`;

  // -- Category list keyboard ---------------------------------------------------------
  function select(id: SettingsCategoryId, focus = false): void {
    query = '';
    app.setSettingsCategory(id);
    body?.scrollTo({ top: 0 });
    if (focus) void tick().then(() => list?.querySelector<HTMLElement>(`[data-cat="${id}"]`)?.focus());
  }

  function onListKey(e: KeyboardEvent): void {
    const i = CATEGORIES.findIndex((c) => c.id === category);
    let next = -1;
    if (e.key === 'ArrowDown') next = Math.min(CATEGORIES.length - 1, i + 1);
    else if (e.key === 'ArrowUp') next = Math.max(0, i - 1);
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = CATEGORIES.length - 1;
    if (next < 0) return;
    e.preventDefault();
    select(CATEGORIES[next].id, true);
  }

  // -- "/" focuses the filter ------------------------------------------------------------
  $effect(() =>
    app.shortcuts.handle('settings.filter', () => filterWrap?.querySelector<HTMLInputElement>('input')?.focus()),
  );

  // -- Bring a key into view (palette, links) -------------------------------------------
  $effect(() => {
    const f = app.settingsFocus;
    if (!f) return;
    untrack(() => {
      query = '';
      void reveal(f.key);
    });
  });

  async function reveal(key: string): Promise<void> {
    for (let attempt = 0; attempt < 10; attempt++) {
      await tick();
      const row = body?.querySelector<HTMLElement>(`[data-key="${CSS.escape(key)}"]`);
      if (row) {
        row.scrollIntoView({ block: 'center' });
        const target = row.querySelector<HTMLElement>('input, button:not([aria-disabled="true"]), [role="button"], [tabindex="0"]');
        target?.focus({ preventScroll: true });
        helpKey = key;
        flashKey = key;
        setTimeout(() => {
          if (flashKey === key) flashKey = null;
        }, 1600);
        return;
      }
      await new Promise((r) => requestAnimationFrame(r));
    }
  }

  $effect(() => {
    if (!body) return;
    for (const el of body.querySelectorAll('.flash')) el.classList.remove('flash');
    if (flashKey) body.querySelector(`[data-key="${CSS.escape(flashKey)}"]`)?.classList.add('flash');
  });

  // -- Help column ------------------------------------------------------------------------
  function trackHelp(e: Event): void {
    const row = (e.target as HTMLElement | null)?.closest?.('[data-key]');
    const key = row?.getAttribute('data-key');
    if (key && key in meta) helpKey = key;
  }
  const facts = $derived(helpKey && meta[helpKey] ? keyFacts(helpKey, meta[helpKey], values[helpKey]) : null);

  // -- Restore defaults (Q-C6) --------------------------------------------------------------
  const restorable = $derived(
    keysOf(meta, category).filter((k) => {
      const m = meta[k] as (typeof meta)[string] & { personal?: boolean };
      return !m.read_only && !m.personal && m.type !== 'list' && m.type !== 'object' && !isDefault(values[k], m);
    }),
  );
  /** The category at a glance, for the help column when no key is pointed at. */
  const summary = $derived.by(() => {
    const keys = keysOf(meta, category);
    const editable = keys.filter((k) => !meta[k].read_only);
    const personal = keys.filter((k) => (meta[k] as (typeof meta)[string] & { personal?: boolean }).personal);
    return { total: keys.length, editable: editable.length, changed: restorable, personal };
  });
  let restoreOpen = $state(false);

  async function restoreDefaults(): Promise<void> {
    const keys = restorable;
    const before: Record<string, ConfigValue> = {};
    const changes: Record<string, ConfigValue> = {};
    for (const k of keys) {
      before[k] = values[k];
      changes[k] = meta[k].default;
    }
    await app.patchConfig(changes);
    app.undo.push({
      title: `${def.label}: ${int(keys.length)} ${keys.length === 1 ? 'setting' : 'settings'} back to the defaults`,
      detail: keys.map(labelOf).slice(0, 4).join(', ') + (keys.length > 4 ? '…' : ''),
      undo: () => app.patchConfig(before),
    });
  }
</script>

<div class="host">
<div class="settings" class:no-help={!filtering && category === 'about'}>
  <nav class="cats" aria-label="Settings categories">
    <div class="cats-head">
      <h2 class="screen-title">Settings</h2>
    </div>
    <div class="filter" bind:this={filterWrap}>
      <KeyHint keys={app.shortcuts.keyFor('settings.filter') ?? '/'} place="end" />
      <SearchField
        label="Filter settings"
        placeholder="Filter settings  /"
        bind:value={query}
        width="100%"
        count={filtering ? `${int(total)}` : null}
      />
    </div>
    <div class="list" role="tablist" aria-orientation="vertical" aria-label="Categories" bind:this={list} tabindex="-1">
      {#each CATEGORIES as c (c.id)}
        {@const marks = attentionOf(c.id)}
        <button
          type="button"
          role="tab"
          class="cat"
          class:selected={!filtering && c.id === category}
          data-cat={c.id}
          aria-selected={!filtering && c.id === category}
          aria-controls="settings-panel"
          tabindex={c.id === category ? 0 : -1}
          aria-label={marks.length ? `${c.label}, needs attention: ${marks.map((m) => m.text).join('; ')}` : c.label}
          onclick={() => select(c.id)}
          onkeydown={onListKey}
          use:tooltip={{ text: marks.length ? marks.map((m) => m.text).join(' · ') : c.intro, placement: 'right' }}
        >
          <Icon name={c.icon} size="s" />
          <span class="cat-label">{c.label}</span>
          {#if counts && counts[c.id] > 0}
            <span class="count num">{counts[c.id]}</span>
          {:else if marks.length}
            <span class="mark lvl-{marks.some((m) => m.level === 'attention') ? 'attention' : 'info'}" aria-hidden="true"></span>
          {/if}
        </button>
      {/each}
    </div>
  </nav>

  <div class="form" id="settings-panel" role="tabpanel" aria-labelledby="settings-title">
    <header class="form-head">
      {#if filtering}
        <h2 class="title" id="settings-title">
          {total ? `${int(total)} ${total === 1 ? 'setting matches' : 'settings match'}` : 'No setting matches'} “{query.trim()}”
        </h2>
      {:else}
        <Icon name={def.icon} size="m" />
        <h2 class="title" id="settings-title">{def.label}</h2>
      {/if}
      <span class="spacer"></span>
      <span class="status" aria-live="polite">
        {#if saved}
          <span class="saved"><span class="ok-dot" aria-hidden="true"></span>Saved · {saved.keys.map(labelOf).join(', ')}</span>
        {:else if remote}
          <span class="remote">
            {remote.source === 'file' ? 'Changed in the configuration file' : 'Changed in another window'}:
            {remote.keys.map(labelOf).slice(0, 3).join(', ')}{remote.keys.length > 3 ? '…' : ''} · {stamp(remote.t)}
          </span>
        {/if}
      </span>
      {#if !filtering && category !== 'about'}
        <Control
          label="Restore defaults…"
          size="s"
          variant="ghost"
          tooltip="bottom"
          tooltipText={restorable.length
            ? `${int(restorable.length)} ${restorable.length === 1 ? 'setting differs' : 'settings differ'} from the defaults`
            : 'Every setting of this category is at its default'}
          disabledReason={restorable.length ? null : 'every setting here is at its default'}
          onclick={() => (restoreOpen = true)}
        />
      {/if}
    </header>
    {#if !filtering}<p class="intro">{def.intro}</p>{/if}
    {#if !filtering && attentionOf(category).length}
      <ul class="attention" aria-label="Needs attention">
        {#each attentionOf(category) as a (a.text)}
          <li><StatusBadge variant="alert" level={a.level} label={a.text} live={false} /></li>
        {/each}
      </ul>
    {/if}

    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="body" bind:this={body} onfocusin={trackHelp} onpointerover={trackHelp}>
      {#if filtering}
        {#if total === 0}
          <p class="none">Try another word: a label, a FITS keyword, a unit, or a key such as “site.latitude”.</p>
        {/if}
        {#each CATEGORIES.filter((c) => c.id !== 'about' && (counts?.[c.id] ?? 0) > 0) as c (c.id)}
          <section class="result">
            <h3 class="result-title">
              <Icon name={c.icon} size="s" />
              {c.label}
            </h3>
            {#if c.id === 'observer_site'}<ObserverSite {query} />
            {:else if c.id === 'instrument'}<Instrument {query} />
            {:else if c.id === 'plate_solving'}<PlateSolving {query} />
            {:else if c.id === 'catalogues'}<Catalogues {query} />
            {:else if c.id === 'photometry'}<Photometry {query} />
            {:else if c.id === 'data_storage'}<DataStorage {query} />
            {:else if c.id === 'privacy_diagnostics'}<Privacy {query} />
            {:else if c.id === 'appearance'}<Appearance {query} />{/if}
          </section>
        {/each}
        {#if connectionMatches}
          <section class="result">
            <h3 class="result-title"><Icon name="nav-connection" size="s" /> Connection screen</h3>
            <SettingsBlock
              keys={CONNECTION_KEYS}
              {query}
              hideEmpty
              reasons={Object.fromEntries(CONNECTION_KEYS.map((k) => [k, 'Set on the Connection screen (F1): Link and Planetarium cards']))}
            />
          </section>
        {/if}
      {:else if category === 'observer_site'}<ObserverSite />
      {:else if category === 'instrument'}<Instrument />
      {:else if category === 'plate_solving'}<PlateSolving />
      {:else if category === 'catalogues'}<Catalogues />
      {:else if category === 'photometry'}<Photometry />
      {:else if category === 'data_storage'}<DataStorage />
      {:else if category === 'privacy_diagnostics'}<Privacy />
      {:else if category === 'appearance'}<Appearance />
      {:else}<About />{/if}
    </div>
  </div>

  <aside class="help" aria-label="About this setting">
    <h3 class="help-title">About this setting</h3>
    {#if facts}
      <p class="h-label">{facts.label}</p>
      {#if facts.help}<p class="h-help">{facts.help}</p>{/if}
      <dl class="h-facts">
        <dt>Key</dt>
        <dd class="mono">{facts.key}</dd>
        {#each facts.facts as f (f.label)}
          <dt>{f.label}</dt>
          <dd class:mono={f.mono}>{f.value}</dd>
        {/each}
      </dl>
      {#if facts.usedBy.length}
        <p class="h-sub">Used by</p>
        <ul class="h-used">
          {#each facts.usedBy as u (u)}<li>{u}</li>{/each}
        </ul>
      {/if}
    {:else if !filtering && category !== 'about'}
      <p class="h-label">{def.label}</p>
      <dl class="h-facts">
        <dt>Settings</dt>
        <dd class="num">{int(summary.total)}{summary.editable !== summary.total ? ` · ${int(summary.total - summary.editable)} read-only` : ''}</dd>
        <dt>Changed</dt>
        <dd>{summary.changed.length ? `${int(summary.changed.length)} from the defaults` : 'none: every setting at its default'}</dd>
      </dl>
      {#if summary.changed.length}
        <ul class="h-used">
          {#each summary.changed.slice(0, 8) as k (k)}<li>{labelOf(k)}</li>{/each}
          {#if summary.changed.length > 8}<li>and {int(summary.changed.length - 8)} more</li>{/if}
        </ul>
      {/if}
      {#if summary.personal.length}
        <p class="h-help">{summary.personal.map(labelOf).join(', ')}: your own values, with no default to go back to.</p>
      {/if}
      <p class="h-hint">Point at or focus a setting for its key, default, range and where ARGOS uses it.</p>
    {:else}
      <p class="h-help">Point at or focus a setting to see its key, its default, its range and where ARGOS uses it.</p>
    {/if}
  </aside>
</div>
</div>

<ConfirmDialog
  bind:open={restoreOpen}
  title="Restore the {def.label} defaults?"
  confirmLabel="Restore defaults"
  onconfirm={restoreDefaults}
>
  <p>{int(restorable.length)} {restorable.length === 1 ? 'setting goes' : 'settings go'} back to the shipped value:</p>
  <ul class="restore-list">
    {#each restorable.slice(0, 8) as k (k)}
      <li>{labelOf(k)}: <span class="mono">{formatValue(values[k], meta[k], k)}</span> → <span class="mono">{formatValue(meta[k].default, meta[k], k)}</span></li>
    {/each}
    {#if restorable.length > 8}<li>and {int(restorable.length - 8)} more</li>{/if}
  </ul>
  <p>Undo is offered for a few seconds afterwards.</p>
</ConfirmDialog>

<style>
  .host {
    container: settings-screen / inline-size;
    height: 100%;
    min-height: 0;
  }
  .settings {
    display: grid;
    grid-template-columns: 208px minmax(0, 1fr) 260px;
    height: 100%;
    min-height: 0;
    background: var(--bg);
  }
  .settings.no-help {
    grid-template-columns: 208px minmax(0, 1fr);
  }
  .no-help .help {
    display: none;
  }
  @container settings-screen (max-width: 1339px) {
    .settings {
      grid-template-columns: 208px minmax(0, 1fr);
    }
    .help {
      display: none;
    }
  }

  /* -- Category list -- */
  .cats {
    display: flex;
    flex-direction: column;
    min-height: 0;
    border-right: var(--border-w) solid var(--border);
    background: var(--bg-2);
  }
  .cats-head {
    display: flex;
    align-items: center;
    height: var(--toolbar-h);
    padding: 0 var(--space-4);
    border-bottom: var(--border-w) solid var(--border);
  }
  .screen-title {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  .filter {
    position: relative;
    padding: var(--space-3) var(--space-3) var(--space-2);
  }
  .list {
    display: flex;
    flex-direction: column;
    gap: 1px;
    padding: 0 var(--space-2) var(--space-3);
    overflow: auto;
    outline: none;
  }
  .cat {
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: 32px;
    padding: 0 var(--space-2) 0 var(--space-3);
    border: none;
    border-radius: var(--radius-s);
    background: none;
    color: var(--text-muted);
    font: inherit;
    font-size: var(--text-s);
    text-align: left;
    cursor: pointer;
  }
  .cat:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  /* Selected: neutral fill and a 2 px --fg edge (the brass of this screen is the rail entry). */
  .cat.selected {
    background: var(--surface);
    color: var(--fg);
    font-weight: var(--weight-medium);
    box-shadow: inset 2px 0 0 var(--fg);
  }
  .cat:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -2px;
  }
  .cat-label {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .count {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  /* One shape per level (BRAND 8), as StatusBadge: attention = an upright
     mark (a bar over a dot) in --warning; info = a hollow ring. */
  .mark {
    flex: none;
    position: relative;
  }
  .mark.lvl-info {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-round);
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
  }
  .mark.lvl-attention {
    width: 3px;
    height: 7px;
    margin: 0 3px 4px;
    border-radius: 1px;
    background: var(--warning);
  }
  .mark.lvl-attention::after {
    content: '';
    position: absolute;
    left: 0;
    top: 8px;
    width: 3px;
    height: 3px;
    border-radius: 1px;
    background: var(--warning);
  }

  /* -- Form column -- */
  .form {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
  }
  .form-head {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: var(--toolbar-h);
    padding: 0 var(--space-5);
    border-bottom: var(--border-w) solid var(--border);
    color: var(--fg-muted);
  }
  .title {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .spacer {
    flex: 1;
  }
  .status {
    min-width: 0;
    overflow: hidden;
    color: var(--text-muted);
    font-size: var(--text-xs);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .saved {
    color: var(--fg);
  }
  .ok-dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-right: 6px;
    border-radius: var(--radius-round);
    background: var(--success);
    vertical-align: 1px;
  }
  .intro {
    margin: 0;
    padding: var(--space-3) var(--space-5) 0;
    max-width: calc(var(--page-max-w) + 2 * var(--space-5));
    color: var(--text-muted);
    font-size: var(--text-s);
    line-height: var(--leading-normal);
  }
  .attention {
    margin: var(--space-2) var(--space-5) 0;
    padding: 0;
    max-width: var(--page-max-w);
    list-style: none;
  }
  .attention {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
  .body {
    /* Positioned, so absolutely placed descendants (visually-hidden labels)
       are clipped by this scroller instead of growing the document. */
    position: relative;
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: var(--space-4) var(--space-5) var(--space-6);
    scrollbar-color: var(--border) transparent;
  }
  .body :global(.flash) {
    outline: var(--border-w) solid var(--fg-muted);
    outline-offset: 2px;
    border-radius: var(--radius-s);
  }
  .none {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .result + .result {
    margin-top: var(--space-6);
  }
  .result-title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: 0 0 var(--space-3);
    color: var(--fg);
    font-size: var(--text-m);
    font-weight: var(--weight-semibold);
  }

  /* -- Help column (Q-C8) -- */
  .help {
    min-height: 0;
    overflow: auto;
    padding: 0 var(--space-4) var(--space-4);
    border-left: var(--border-w) solid var(--border);
    background: var(--bg-2);
  }
  .help-title {
    display: flex;
    align-items: center;
    height: var(--toolbar-h);
    margin: 0 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .h-label {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-m);
    font-weight: var(--weight-medium);
  }
  .h-help {
    margin: var(--space-1) 0 0;
    color: var(--text-muted);
    font-size: var(--text-s);
    line-height: var(--leading-relaxed);
  }
  .h-facts {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr);
    gap: var(--space-1) var(--space-3);
    margin: var(--space-3) 0 0;
    font-size: var(--text-s);
  }
  .h-facts dt {
    color: var(--text-muted);
  }
  .h-facts dd {
    margin: 0;
    color: var(--fg);
    overflow-wrap: anywhere;
  }
  .mono {
    font-family: var(--font-mono);
    font-size: var(--text-s);
  }
  .h-sub {
    margin: var(--space-3) 0 var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .h-used {
    margin: 0;
    padding-left: var(--space-4);
    color: var(--fg);
    font-size: var(--text-s);
    line-height: var(--leading-normal);
  }
  .h-hint {
    margin: var(--space-4) 0 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-normal);
  }
  .restore-list {
    margin: var(--space-2) 0;
    padding-left: var(--space-5);
    font-size: var(--text-s);
  }
</style>

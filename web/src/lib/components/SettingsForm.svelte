<!--
  Settings form generated from the server's config meta (web/spec/README.md
  3.1 and 3.4; A8 `GET /api/config`): the Settings screen's category forms
  and the side sheets over Observe (D12) render this one component, so a key
  has one form and one save model everywhere.

  - Which keys: a `category` (in the server's order), or an explicit `keys`
    list (a sheet's subset), filtered by `query` (the Settings filter).
    Advanced keys (Q-C4) sit under a disclosure, opened automatically while
    a filter matches one of them.
  - Save model: immediate apply on commit, ONE `PATCH /api/config` per commit
    (`patch`), refused with the server's words for that key (`fields`);
    warnings ("does not exist, it will be created") stay under the field.
  - Sync: `values` follows the server (the `config` event of any client);
    a field holding a draft is not overwritten, it says "Changed elsewhere"
    with Reload (commit.svelte.ts).
  - "Changed from default": a bar on the row and [Reset] (Undo when `undo`
    is given). Read-only keys show their value with the reason
    (`reasons[key]`, else "Read-only here"); dependent keys are unavailable
    with the reason (settings.ts dependencyReason).
  - Paths: [browse] opens the in-app FilePicker over `list` (A11); without
    `list` the path is typed only.
  - `custom` renders the keys of `customKeys` (saved sites, a gain table).
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { ConfigValue, KeyMeta } from '../api/types';
  import FilePicker from './FilePicker.svelte';
  import type { FsLister } from './filepicker';
  import Icon from './Icon.svelte';
  import SettingField from './SettingField.svelte';
  import { dependencyReason, pathMode, type SettingsPatch, selectKeys } from './settings';
  import type { UndoQueue } from './undo.svelte';

  interface Props {
    meta: Record<string, KeyMeta>;
    values: Record<string, ConfigValue>;
    patch: SettingsPatch;
    category?: string;
    keys?: readonly string[];
    query?: string;
    /** Group heading (a sheet shows its category title in its own header). */
    title?: string;
    /** Why a key cannot be changed here; null = available (overrides the built-in rules). */
    reasons?: Record<string, string | null>;
    /** Text of empty nullable fields, by key ("Profile: 60 000"). */
    placeholders?: Record<string, string>;
    list?: FsLister | null;
    undo?: UndoQueue | null;
    custom?: Snippet<[string, KeyMeta, ConfigValue | undefined]> | null;
    customKeys?: readonly string[];
    showAdvanced?: boolean;
    /** The advanced keys in the main list, without their own disclosure (the form is already inside one). */
    inlineAdvanced?: boolean;
    onsaved?: (key: string) => void;
    /** Specimen only: freeze fields in a state. */
    pins?: Record<string, { phase?: 'dirty' | 'sending' | 'applied' | 'refused' | 'elsewhere' | 'invalid'; text?: string; message?: string }>;
    empty?: string;
  }

  let {
    meta,
    values,
    patch,
    category,
    keys,
    query = '',
    title,
    reasons = {},
    placeholders = {},
    list = null,
    undo = null,
    custom = null,
    customKeys = [],
    showAdvanced = $bindable(false),
    inlineAdvanced = false,
    onsaved,
    pins = {},
    empty,
  }: Props = $props();

  const uid = `sf-${Math.random().toString(36).slice(2, 9)}`;
  const basic = $derived(selectKeys(meta, { category, keys, query, advanced: inlineAdvanced ? undefined : false }));
  const advanced = $derived(inlineAdvanced ? [] : selectKeys(meta, { category, keys, query, advanced: true }));
  const advancedOpen = $derived(showAdvanced || (!!query.trim() && advanced.length > 0));

  function reasonFor(key: string): string | null {
    if (key in reasons) return reasons[key];
    return dependencyReason(key, values);
  }

  // -- One FilePicker for the form's path keys ----------------------------------------------

  let picking: { key: string; start: string; set: (v: string) => void } | null = $state(null);
  let pickerOpen = $state(false);
  const browse = $derived(
    list
      ? (key: string, current: string, set: (v: string) => void) => {
          picking = { key, start: current || String(meta[key]?.default ?? ''), set };
          pickerOpen = true;
        }
      : null,
  );
</script>

{#snippet field(key: string)}
  <SettingField
    {key}
    meta={meta[key]}
    value={values[key]}
    {patch}
    reason={reasonFor(key)}
    {browse}
    {undo}
    placeholder={placeholders[key] ?? null}
    custom={customKeys.includes(key) ? custom : null}
    {onsaved}
    pin={pins[key] ?? null}
  />
{/snippet}

<section class="settings-form" aria-labelledby={title ? `${uid}-title` : undefined}>
  {#if title}<h3 class="title" id="{uid}-title">{title}</h3>{/if}
  {#each basic as key (key)}
    {@render field(key)}
  {/each}
  {#if advanced.length}
    <button
      type="button"
      class="disclosure"
      class:closed={!advancedOpen}
      aria-expanded={advancedOpen}
      aria-controls="{uid}-advanced"
      onclick={() => (showAdvanced = !advancedOpen)}
    >
      <span class="chevron" aria-hidden="true"><Icon name="disclosure" size="s" /></span>
      Advanced
      <span class="count num">{advanced.length}</span>
    </button>
    {#if advancedOpen}
      <div id="{uid}-advanced" class="advanced">
        {#each advanced as key (key)}
          {@render field(key)}
        {/each}
      </div>
    {/if}
  {/if}
  {#if !basic.length && !advanced.length}
    <p class="empty">{empty ?? (query ? `No setting matches “${query}”.` : 'No settings here.')}</p>
  {/if}
</section>

{#if list && picking && meta[picking.key]}
  <FilePicker
    bind:open={pickerOpen}
    mode={pathMode(picking.key, meta[picking.key])}
    title="Choose {meta[picking.key].label.toLowerCase()}"
    start={picking.start}
    {list}
    onchoose={(p) => picking?.set(p)}
    onclose={() => (picking = null)}
  />
{/if}

<style>
  .settings-form {
    container: settings / inline-size;
    min-width: 0;
    max-width: var(--page-max-w);
  }
  .settings-form > :global(.setting:first-child) {
    border-top: none;
  }
  .title {
    margin: 0 0 var(--space-2);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .disclosure {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    height: 32px;
    margin: 0;
    padding: 0 var(--space-2);
    border: none;
    border-top: var(--border-w) solid var(--border-soft);
    background: none;
    color: var(--fg);
    font: inherit;
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
    text-align: left;
    cursor: pointer;
  }
  .disclosure:hover {
    background: var(--hover-bg);
  }
  .disclosure:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -2px;
  }
  .chevron {
    display: inline-flex;
    color: var(--fg-muted);
    transition: transform var(--duration-fast) var(--ease-standard);
  }
  .closed .chevron {
    transform: rotate(-90deg);
  }
  .count {
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-regular);
  }
  .empty {
    margin: 0;
    padding: var(--space-3) 0;
    border-top: var(--border-w) solid var(--border-soft);
    color: var(--text-muted);
    font-size: var(--text-s);
  }
</style>

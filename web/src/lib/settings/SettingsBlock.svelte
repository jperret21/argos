<!--
  One group of a Settings category: the shared SettingsForm (lib/components)
  bound to the app's configuration. The keys come from the server's config
  meta; values follow every client's commits through the `config` event
  (a field holding a draft says "Changed elsewhere" instead of being
  overwritten); each commit is one PATCH /api/config, refused with that
  key's words; Reset offers Undo in the app's one Undo queue; path keys
  browse with the in-app FilePicker over GET /api/fs/list.

  When the command palette or a link asks for a key (app.settingsFocus) and
  that key is an advanced one of this group, the Advanced disclosure opens.
-->
<script lang="ts">
  import { untrack, type Snippet } from 'svelte';
  import type { ConfigValue, KeyMeta } from '../api/types';
  import { useApp } from '../app/state.svelte';
  import SettingsForm from '../components/SettingsForm.svelte';

  interface Props {
    keys: readonly string[];
    title?: string;
    /** One line under the title (what the group writes, where it is used). */
    caption?: string;
    query?: string;
    reasons?: Record<string, string | null>;
    placeholders?: Record<string, string>;
    custom?: Snippet<[string, KeyMeta, ConfigValue | undefined]> | null;
    customKeys?: readonly string[];
    /** Hide the group when no key of it matches (filter mode). */
    hideEmpty?: boolean;
    /** Show the advanced keys without their disclosure (already inside one). */
    openAdvanced?: boolean;
  }

  let {
    keys,
    title,
    caption,
    query = '',
    reasons = {},
    placeholders = {},
    custom = null,
    customKeys = [],
    hideEmpty = false,
    openAdvanced = false,
  }: Props = $props();

  const app = useApp();
  const meta = $derived(app.configMeta ?? {});
  const values = $derived(app.configValues ?? {});
  const present = $derived(keys.filter((k) => k in meta));
  const matching = $derived(
    query.trim()
      ? present.filter((k) => {
          const m = meta[k];
          const hay = [k, m.label, m.help, m.unit ?? '', ...m.used_by].join(' ').toLowerCase();
          return query
            .toLowerCase()
            .split(/\s+/)
            .filter(Boolean)
            .every((w) => hay.includes(w));
        })
      : present,
  );

  let showAdvanced = $state(untrack(() => openAdvanced));
  $effect(() => {
    const f = app.settingsFocus;
    if (f && present.includes(f.key) && meta[f.key]?.advanced) showAdvanced = true;
  });

  const patch = (changes: Record<string, ConfigValue>) => app.patchConfig(changes);
</script>

{#if !(hideEmpty && !matching.length)}
  <div class="block">
    {#if title}
      <div class="head">
        <h3 class="title">{title}</h3>
        {#if caption}<p class="caption">{caption}</p>{/if}
      </div>
    {/if}
    {#if app.configMeta}
      <SettingsForm
        {meta}
        {values}
        {patch}
        keys={present}
        {query}
        {reasons}
        {placeholders}
        list={app.listFiles}
        undo={app.undo}
        {custom}
        {customKeys}
        bind:showAdvanced
        inlineAdvanced={openAdvanced}
      />
    {:else}
      <p class="loading">Waiting for the server's configuration…</p>
    {/if}
  </div>
{/if}

<style>
  .block {
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
  .loading {
    margin: 0;
    padding: var(--space-3) 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
</style>

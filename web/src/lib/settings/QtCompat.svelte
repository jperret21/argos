<!--
  "Qt app compatibility" (design review): the keys only the Qt app reads
  (its theme and image rotation, the legacy saturation and linearity copies)
  in one closed disclosure at the end of a category, so they never sit next
  to the web's own Theme, Image rotation or Saturation. They stay editable
  or read-only as the server says, and searchable: the Settings filter and
  the command palette open the disclosure when they point at one of them.
-->
<script lang="ts">
  import { useApp } from '../app/state.svelte';
  import Icon from '../components/Icon.svelte';
  import SettingsBlock from './SettingsBlock.svelte';

  interface Props {
    keys: readonly string[];
    /** One line inside, above the keys. */
    caption: string;
    query?: string;
  }
  let { keys, caption, query = '' }: Props = $props();

  const app = useApp();
  const uid = `qt-${Math.random().toString(36).slice(2, 8)}`;
  let open = $state(false);
  $effect(() => {
    const f = app.settingsFocus;
    if (f && keys.includes(f.key)) open = true;
  });
  const shown = $derived(open || !!query.trim());
  const present = $derived(keys.filter((k) => k in (app.configMeta ?? {})));
</script>

{#if present.length}
  {#if query.trim()}
    <SettingsBlock title="Qt app compatibility" {keys} {query} hideEmpty openAdvanced />
  {:else}
    <section class="qt">
      <button
        type="button"
        class="disclosure"
        class:closed={!shown}
        aria-expanded={shown}
        aria-controls={uid}
        onclick={() => (open = !open)}
      >
        <span class="chevron" aria-hidden="true"><Icon name="disclosure" size="s" /></span>
        Qt app compatibility
        <span class="count num">{present.length}</span>
      </button>
      {#if shown}
        <div id={uid} class="inner">
          <p class="caption">{caption}</p>
          <SettingsBlock {keys} openAdvanced />
        </div>
      {/if}
    </section>
  {/if}
{/if}

<style>
  .qt {
    max-width: var(--page-max-w);
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
    border-top: var(--border-w) solid var(--border);
    background: none;
    color: var(--text-muted);
    font: inherit;
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
    text-align: left;
    cursor: pointer;
  }
  .disclosure:hover {
    background: var(--hover-bg);
    color: var(--fg);
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
  .caption {
    margin: var(--space-1) 0 var(--space-2) var(--space-4);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>

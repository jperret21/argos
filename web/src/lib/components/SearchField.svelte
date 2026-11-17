<!--
  Compact search field for toolbars and drawer headers (24 px): the search
  glyph, the text, a clear button once something is typed. Escape clears the
  text first (when a layer is not closing on the same key). The label is the
  accessible name and the placeholder.
-->
<script lang="ts">
  import Icon from './Icon.svelte';
  import IconButton from './IconButton.svelte';

  interface Props {
    label: string;
    value: string;
    placeholder?: string;
    width?: string;
    /** "12 of 1 204": announced and shown at the right while a query is set. */
    count?: string | null;
    oninput?: (value: string) => void;
  }

  let { label, value = $bindable(), placeholder, width = '200px', count = null, oninput }: Props = $props();
  let input: HTMLInputElement | undefined = $state();

  function clear(): void {
    value = '';
    oninput?.('');
    input?.focus();
  }

  function onKeydown(e: KeyboardEvent): void {
    // No stopPropagation: Escape still reaches the registry, which aborts
    // mount motion from anywhere (D21).
    if (e.key === 'Escape' && value && !e.defaultPrevented) {
      e.preventDefault();
      clear();
    }
  }
</script>

<div class="search" style:width>
  <span class="glyph" aria-hidden="true"><Icon name="search" size="s" /></span>
  <input
    bind:this={input}
    type="search"
    aria-label={label}
    placeholder={placeholder ?? label}
    autocomplete="off"
    spellcheck="false"
    bind:value
    oninput={() => oninput?.(value)}
    onkeydown={onKeydown}
  />
  {#if value}
    {#if count}<span class="count num" aria-live="polite">{count}</span>{/if}
    <span class="clear">
      <IconButton icon="close" label="Clear the search" variant="ghost" size="s" tooltip="top" onclick={clear} />
    </span>
  {/if}
</div>

<style>
  .search {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 24px;
    min-width: 0;
    padding: 0 0 0 var(--space-2);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    transition: border-color var(--duration-fast) var(--ease-standard);
  }
  .search:hover {
    border-color: var(--fg-muted);
  }
  .search:focus-within {
    border-color: var(--focus-ring);
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 0;
  }

  .glyph {
    display: inline-flex;
    color: var(--fg-muted);
  }

  input {
    flex: 1;
    min-width: 0;
    height: 100%;
    padding: 0;
    border: none;
    background: transparent;
    color: var(--fg);
    font-size: var(--text-s);
    outline: none;
  }
  input::placeholder {
    color: var(--text-muted);
    opacity: 1;
  }
  /* The native clear button draws grey (Night Red): ours replaces it. */
  input::-webkit-search-cancel-button {
    display: none;
  }

  .count {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }

  .clear :global(.icon-button) {
    height: 22px;
    min-width: 22px;
    padding: 0 2px;
  }
</style>

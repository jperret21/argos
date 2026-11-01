<!--
  Right-rail card (Qt design.Card): an icon and a title, an optional status on
  the right of the header, then the body.

  `collapsible` turns the title into a disclosure button (aria-expanded): the
  rail is shorter than the four cards at laptop heights, and a folded card
  keeps its status visible in the header. With `persist`, the open state is
  remembered per viewer (localStorage, optional) under that key.
-->
<script lang="ts">
  import { type Snippet, untrack } from 'svelte';
  import { isBoolean, loadPref, savePref } from '../app/prefs';
  import Icon from './Icon.svelte';

  interface Props {
    title: string;
    icon: string;
    /** Right side of the header (usually a StatusBadge). */
    status?: Snippet;
    children: Snippet;
    collapsible?: boolean;
    open?: boolean;
    /** Remember the open state under this key (BRAND 11.1). */
    persist?: string;
    /** id of the section, for a caller that needs to reach it (focus, scroll). */
    anchor?: string;
  }

  let {
    title,
    icon,
    status,
    children,
    collapsible = false,
    open = $bindable(true),
    persist,
    anchor,
  }: Props = $props();

  // Restore the remembered state once, at creation (the key never changes).
  untrack(() => {
    if (persist) open = loadPref(`argos.card.${persist}`, isBoolean, open);
  });

  function toggle(): void {
    open = !open;
    if (persist) savePref(`argos.card.${persist}`, open);
  }
  const id = `card-${Math.random().toString(36).slice(2, 9)}`;
</script>

<section
  class="card"
  class:closed={collapsible && !open}
  id={anchor}
  aria-labelledby="{id}-title"
>
  <header>
    {#if collapsible}
      <button
        type="button"
        class="toggle"
        aria-expanded={open}
        aria-controls="{id}-body"
        onclick={toggle}
      >
        <span class="chevron"><Icon name="disclosure" size="s" /></span>
        <span class="glyph"><Icon name={icon} size="s" /></span>
        <h2 id="{id}-title">{title}</h2>
      </button>
    {:else}
      <span class="glyph"><Icon name={icon} size="s" /></span>
      <h2 id="{id}-title">{title}</h2>
    {/if}
    {#if status}<span class="status">{@render status()}</span>{/if}
  </header>
  {#if !collapsible || open}
    <div class="body" id="{id}-body">
      {@render children()}
    </div>
  {/if}
</section>

<style>
  .card {
    flex: none;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    background: var(--bg);
  }

  header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-height: 40px;
    padding: var(--space-1) var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
  }
  .closed header {
    border-bottom: none;
  }

  .toggle {
    display: flex;
    flex: 1;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
    height: 32px;
    margin-left: calc(-1 * var(--space-2));
    padding: 0 var(--space-1);
    border: none;
    border-radius: var(--radius-s);
    background: transparent;
    color: inherit;
    text-align: left;
    cursor: pointer;
  }
  .toggle:hover {
    background: var(--hover-bg);
  }
  .toggle:hover .chevron {
    color: var(--fg);
  }

  .chevron {
    display: inline-flex;
    color: var(--fg-muted);
    transition: transform var(--duration-fast) var(--ease-standard);
  }
  .closed .chevron {
    transform: rotate(-90deg);
  }

  .glyph {
    display: inline-flex;
    color: var(--fg-muted);
  }

  h2 {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
    line-height: var(--leading-tight);
    white-space: nowrap;
  }

  .status {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }

  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-4);
  }
</style>

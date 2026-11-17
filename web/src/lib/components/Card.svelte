<!--
  Right-rail card (Qt design.Card): an icon and a title, an optional status on
  the right of the header, then the body.

  `collapsible` turns the title into a disclosure button (aria-expanded): the
  rail is shorter than the four cards at laptop heights, and a folded card
  keeps its status visible in the header. With `persist`, the open state is
  remembered per viewer (localStorage, optional) under that key.

  `summary` (optional) is the one line a folded card keeps after its title
  ("2.0 s · gain 80 · IR"), so folding loses nothing a glance needs
  (web/lab/PROPOSAL.md section 6, lab RightPanel). It is shown only while the
  card is folded, muted, in mono, cut with an ellipsis; outside the
  disclosure button, so the button's name stays the title.
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
    /** One line after the title while the card is folded (collapsible only). */
    summary?: Snippet;
    children: Snippet;
    collapsible?: boolean;
    open?: boolean;
    /** Remember the open state under this key (BRAND 11.1). */
    persist?: string;
    /** id of the section, for a caller that needs to reach it (focus, scroll). */
    anchor?: string;
    /** Tighter header and body (set-up screens that must fit without scrolling). */
    dense?: boolean;
    /** The body fills the card's height (a table or a log that scrolls inside). */
    fill?: boolean;
  }

  let {
    title,
    icon,
    status,
    summary,
    children,
    collapsible = false,
    open = $bindable(true),
    persist,
    anchor,
    dense = false,
    fill = false,
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
  class:dense
  class:fill
  class:closed={collapsible && !open}
  class:summarised={!!summary && collapsible && !open}
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
    {#if summary && collapsible && !open}<span class="summary num">{@render summary()}</span>{/if}
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

  /* Folded with a summary: the title keeps its width, the summary takes the
     rest and is cut first. */
  .summarised .toggle {
    flex: 0 1 auto;
  }
  .summary {
    flex: 1 1 0;
    min-width: 0;
    margin-left: var(--space-2);
    overflow: hidden;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    text-overflow: ellipsis;
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

  .dense header {
    min-height: 34px;
  }
  .dense .body {
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
  }

  .fill {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .fill .body {
    flex: 1;
    min-height: 0;
  }
</style>

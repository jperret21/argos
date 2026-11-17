<!--
  The Run card's attention items (PROPOSAL 3.1 "Run card … attention items"; BRAND §13):
  the items needing the observer, most urgent first, at most `max` of them, each with its
  level by mark and word, its headline, when and which frame, the suggested view and
  Acknowledge (shared by every client). More than `max`: "n more" opens the whole list.
  Nothing open: nothing drawn (the card stays quiet when the run is fine).
-->
<script lang="ts">
  import type { AttentionItem, AttentionTarget } from '../../api/attention';
  import Button from '../../components/Button.svelte';
  import { clockUtc } from '../../format/time';
  import { actionOf, LEVEL_WORD, openItems, whenLine } from './model';
  import AttentionMark from './AttentionMark.svelte';

  interface Props {
    items: readonly AttentionItem[];
    pending?: ReadonlySet<string>;
    max?: number;
    onack: (id: string) => Promise<unknown> | void;
    onaction?: (to: AttentionTarget, item: AttentionItem) => void;
    /** Open the status bar's list (the whole run's items). */
    onlist?: () => void;
  }
  let { items, pending = new Set(), max = 3, onack, onaction, onlist }: Props = $props();

  const open = $derived(openItems(items));
  const shown = $derived(open.slice(0, max));
  const clock = (t: number) => clockUtc(t, false);
</script>

{#if open.length}
  <section class="att" aria-label="Attention: {open.length} open">
    <ul>
      {#each shown as a (a.id)}
        {@const act = actionOf(a)}
        <li class="l-{a.level}">
          <span class="head">
            <AttentionMark level={a.level} size={10} />
            <span class="lvl">{LEVEL_WORD[a.level]}</span>
            <span class="when num">{whenLine(a, clock)}{a.active ? '' : ' · cleared'}</span>
          </span>
          <span class="text num">{a.short}</span>
          <span class="acts">
            {#if act && onaction}<Button label={act.label} size="s" variant="ghost" onclick={() => onaction?.(act.to, a)} />{/if}
            <Button label="Acknowledge" size="s" busy={pending.has(a.id)} onclick={() => void Promise.resolve(onack(a.id)).catch(() => undefined)} />
          </span>
        </li>
      {/each}
    </ul>
    {#if open.length > shown.length && onlist}
      <button type="button" class="more" onclick={onlist}>{open.length - shown.length} more · open the list</button>
    {/if}
  </section>
{/if}

<style>
  .att {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  li {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas: 'head acts' 'text acts';
    align-items: center;
    column-gap: var(--space-2);
    padding: var(--space-2);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  li.l-critical {
    border: 2px solid var(--danger);
    padding: calc(var(--space-2) - 1px);
  }
  .head {
    grid-area: head;
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .lvl {
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .l-critical .lvl {
    font-weight: var(--weight-semibold);
  }
  .when {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .text {
    grid-area: text;
    min-width: 0;
    color: var(--fg);
    font-size: var(--text-s);
    overflow-wrap: anywhere;
  }
  .acts {
    grid-area: acts;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: var(--space-1);
  }
  .more {
    align-self: flex-start;
    padding: 0;
    border: none;
    background: none;
    color: var(--fg);
    font-size: var(--text-xs);
    text-decoration: underline;
    text-underline-offset: 2px;
    cursor: pointer;
  }
  .more:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 2px;
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
</style>

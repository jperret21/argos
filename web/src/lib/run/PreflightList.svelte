<!--
  The preflight checks (A64; spec 06 2.3.5; PROPOSAL 3.1 night checklist): one row per
  check, blocks first, each with its mark AND its word (OK / Note / Blocks), the check's
  name and the server's sentence verbatim. A block is what the server would refuse;
  a note never stops Start.
-->
<script lang="ts">
  import type { PreflightItem } from '../api/sequence';
  import LevelMark from './LevelMark.svelte';
  import { checkMessage, checkName, LEVEL_WORD, sortPreflight } from './run';

  let { items }: { items: readonly PreflightItem[] } = $props();
  const rows = $derived(sortPreflight(items));
</script>

{#if rows.length}
  <ul class="pre">
    <!-- Keyed by position: the server may send one id twice (a plan note and the plan's OK). -->
    {#each rows as it, i (i)}
      <li class="l-{it.level}">
        <LevelMark level={it.level} />
        <span class="word">{LEVEL_WORD[it.level]}</span>
        <span class="name">{checkName(it)}</span>
        <span class="msg" title={checkMessage(it) !== it.message ? it.message : undefined}>{checkMessage(it)}</span>
      </li>
    {/each}
  </ul>
{:else}
  <p class="none">The server reported no check.</p>
{/if}

<style>
  .pre {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: 12px auto auto minmax(0, 1fr);
    column-gap: var(--space-2);
    row-gap: 6px;
    align-items: start;
    font-size: var(--text-s);
  }
  li {
    display: contents;
  }
  /* The mark sits on the first line, whatever the message's length. */
  li :global(.mark) {
    margin-top: 3px;
  }
  .word {
    line-height: 18px;
  }
  .word {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .l-block .word,
  .l-note .word {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
  .name {
    color: var(--fg);
    white-space: nowrap;
  }
  .msg {
    color: var(--text-muted);
    overflow-wrap: anywhere;
  }
  .l-block .msg {
    color: var(--fg);
  }
  .none {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
</style>

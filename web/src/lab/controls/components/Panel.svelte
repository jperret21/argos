<!--
  Specimen panel (lab only): a figure number, a title, one line saying what
  the specimen proves, then the specimen. data-shot names it for the
  screenshot script.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    code: string;
    title: string;
    note?: string;
    shot?: string;
    /** Sunken bench (controls drawn on --bg-2, like a toolbar or the HUD). */
    bench?: boolean;
    children: Snippet;
    aside?: Snippet;
  }

  let { code, title, note, shot, bench = false, children, aside }: Props = $props();
</script>

<section class="panel" data-shot={shot}>
  <header>
    <span class="code">{code}</span>
    <h3>{title}</h3>
    {#if aside}<span class="aside">{@render aside()}</span>{/if}
  </header>
  {#if note}<p class="note">{note}</p>{/if}
  <div class="body" class:bench>
    {@render children()}
  </div>
</section>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
    padding: var(--space-3) var(--space-4) var(--space-4);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    background: var(--bg);
  }
  header {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    min-height: 18px;
  }
  .code {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
  }
  h3 {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-m);
    font-weight: var(--weight-semibold);
  }
  .aside {
    margin-left: auto;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .note {
    margin: -2px 0 var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-normal);
    text-wrap: pretty;
  }
  .body {
    min-width: 0;
  }
  .body.bench {
    padding: var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    --ctl-halo: var(--bg-2);
  }
</style>

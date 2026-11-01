<!--
  Compound card with snippets: the caller passes `badge` (status in the
  header), `summary` (one line shown when folded) and the body. Folding
  animates grid-template-rows 0fr -> 1fr, which every engine interpolates
  (interpolate-size / calc-size(auto) are Chromium-only); the duration token
  is 0 with reduced motion. The card is a size container, so its content can
  reflow by the card's width, wherever it is placed (rail, drawer, sheet).
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import Icon from '../../../lib/components/Icon.svelte';

  interface Props {
    title: string;
    icon: string;
    open?: boolean;
    badge?: Snippet;
    summary?: Snippet;
    children: Snippet;
    /** Container name, for @container rules of the content. */
    container?: string;
  }

  let { title, icon, open = $bindable(true), badge, summary, children, container = 'card' }: Props = $props();
  const id = $props.id();
</script>

<section class="card" class:open style:container-name={container}>
  <header>
    <button class="fold" aria-expanded={open} aria-controls="{id}-body" onclick={() => (open = !open)}>
      <span class="chev"><Icon name="disclosure" size={16} /></span>
      <Icon name={icon} size={16} />
      <span class="title">{title}</span>
    </button>
    {#if !open && summary}<span class="summary num">{@render summary()}</span>{/if}
    <span class="grow"></span>
    {#if badge}{@render badge()}{/if}
  </header>
  <div class="body" id="{id}-body">
    <div class="inner">{@render children()}</div>
  </div>
</section>

<style>
  .card {
    container-type: inline-size;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    background: var(--bg);
  }
  header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: 36px;
    padding: 0 var(--space-3) 0 var(--space-1);
  }
  .fold {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    height: 28px;
    padding: 0 var(--space-2);
    border: 0;
    border-radius: var(--radius-s);
    background: none;
    color: var(--fg-muted);
    cursor: pointer;
  }
  .fold:hover {
    background: var(--hover-bg);
  }
  .title {
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  .chev {
    display: inline-flex;
    transform: rotate(-90deg);
    transition: transform var(--duration-fast) var(--ease-standard);
  }
  .open .chev {
    transform: none;
  }
  .summary {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .grow {
    flex: 1;
  }
  .body {
    display: grid;
    grid-template-rows: 0fr;
    transition: grid-template-rows var(--duration-base) var(--ease-out);
  }
  .open .body {
    grid-template-rows: 1fr;
  }
  .inner {
    min-height: 0;
    overflow: hidden;
  }
  .open .inner {
    padding: 0 var(--space-4) var(--space-4);
    border-top: var(--border-w) solid var(--border-soft);
    padding-top: var(--space-3);
  }
</style>

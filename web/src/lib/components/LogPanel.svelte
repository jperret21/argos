<!--
  A log region outside a drawer (the Connection screen's log, 02 W1): a
  header with the title (Card title style: it is a top-level region beside
  the cards), the topics it keeps, the log tools, then the list. Same store
  and components as the drawer's Log tab, filtered on `topics` (null = every
  topic; it may change, e.g. the Connection log's "all topics" switch).

    <LogPanel store={app.log} title="Connection log"
              topics={['connection', 'discovery', 'planetarium']} persist="argos.connection.log" />
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import { LogFilter, type LogStore } from '../app/log.svelte';
  import Icon from './Icon.svelte';
  import LogControls from './LogControls.svelte';
  import LogView from './LogView.svelte';

  interface Props {
    store: LogStore;
    title: string;
    topics?: readonly string[] | null;
    /** Remember the level filter under this key. */
    persist?: string;
    empty?: string;
    /** Extra buttons at the right of the header (e.g. "Open the full log"). */
    actions?: Snippet;
    filter?: LogFilter;
    /** The lines count as seen while shown (the status-bar badge clears). */
    markSeen?: boolean;
  }

  let { store, title, topics = null, persist, empty, actions, filter: given, markSeen = false }: Props = $props();
  // The filter is created once (`persist` is fixed for a panel); its topics follow the prop.
  // svelte-ignore state_referenced_locally
  const filter = given ?? new LogFilter({ topics, persist });
  $effect(() => {
    filter.topics = topics;
  });
</script>

<section class="panel" aria-label={title}>
  <header>
    <Icon name="log" size="s" />
    <h2>{title}</h2>
    {#if topics?.length}<span class="topics">{topics.join(' · ')}</span>{/if}
    <span class="tools"><LogControls {store} {filter} /></span>
    {#if actions}{@render actions()}{/if}
  </header>
  <LogView {store} {filter} {empty} label={title} {markSeen} />
</section>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    min-height: 0;
    height: 100%;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    background: var(--bg-2);
  }

  header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-height: 36px;
    padding: 0 var(--space-1) 0 var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--fg-muted);
  }

  /* Card title typography (Sans 600, 14 px): a region beside the cards, not a sub-section. */
  h2 {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
    line-height: var(--leading-tight);
    white-space: nowrap;
  }

  .topics {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }

  .tools {
    display: flex;
    flex: 1;
    justify-content: flex-end;
    min-width: 0;
  }
</style>

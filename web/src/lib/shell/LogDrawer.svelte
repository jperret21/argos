<!--
  Activity log drawer, fed by /ws/events "log" messages plus client-side
  failures. Opens under the image (the viewer shrinks, nothing is covered).
  Follows the newest line unless the observer has scrolled up to read.
-->
<script lang="ts">
  import { tick } from 'svelte';
  import type { LogEntry } from '../api/events.svelte';
  import { useApp } from '../app/state.svelte';
  import IconButton from '../components/IconButton.svelte';
  import Icon from '../components/Icon.svelte';

  const app = useApp();
  let list: HTMLOListElement | undefined = $state();
  let follow = true;

  const LEVEL_TAG: Record<LogEntry['level'], string> = {
    info: 'INFO',
    warning: 'WARN',
    error: 'ERROR',
  };

  /** "21:34:05" in UTC (the column header says UTC). */
  function hhmmss(iso: string): string {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '--:--:--';
    return d.toISOString().slice(11, 19);
  }

  function onScroll(): void {
    if (!list) return;
    follow = list.scrollHeight - list.scrollTop - list.clientHeight < 24;
  }

  $effect(() => {
    void app.events.logs.length;
    if (!follow || !list) return;
    void tick().then(() => list?.scrollTo({ top: list.scrollHeight }));
  });
</script>

<section class="drawer" aria-label="Activity log">
  <header>
    <Icon name="log" size="s" />
    <h2>Activity log</h2>
    <span class="meta num">{app.events.logs.length} lines · UTC</span>
    <span class="actions">
      <IconButton
        icon="clear"
        label="Clear the log"
        variant="ghost"
        size="s"
        tooltip="top"
        disabled={app.events.logs.length === 0}
        onclick={() => app.events.clearLogs()}
      />
      <IconButton
        icon="close"
        label="Close the log"
        variant="ghost"
        size="s"
        tooltip="top"
        onclick={() => app.setLogOpen(false)}
      />
    </span>
  </header>
  {#if app.events.logs.length === 0}
    <p class="empty">
      Nothing logged yet. Server events (including the last 200 before this window opened),
      warnings and failed commands appear here.
    </p>
  {:else}
    <ol bind:this={list} onscroll={onScroll}>
      {#each app.events.logs as entry (entry.id)}
        <li class="level-{entry.level}">
          <time class="num" datetime={entry.t}>{hhmmss(entry.t)}</time>
          <span class="tag">{LEVEL_TAG[entry.level]}</span>
          <span class="msg">{entry.message}</span>
        </li>
      {/each}
    </ol>
  {/if}
</section>

<style>
  .drawer {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    border-top: var(--border-w) solid var(--border);
    background: var(--bg-2);
  }

  header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: 32px;
    padding: 0 var(--space-1) 0 var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--fg-muted);
  }

  h2 {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-semibold);
  }

  .meta {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }

  .actions {
    display: flex;
    margin-left: auto;
  }

  ol {
    flex: 1;
    min-height: 0;
    margin: 0;
    padding: var(--space-1) 0;
    overflow-y: auto;
    list-style: none;
    font-family: var(--font-mono);
    font-size: var(--text-s);
    line-height: 20px;
  }

  li {
    display: grid;
    grid-template-columns: 64px 48px minmax(0, 1fr);
    gap: var(--space-3);
    padding: 0 var(--space-4);
  }
  li:hover {
    background: var(--bg);
  }

  time {
    color: var(--text-muted);
  }

  .tag {
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    line-height: 20px;
  }
  .level-info .tag {
    color: var(--log-info);
  }
  .level-warning .tag {
    color: var(--log-warning);
  }
  .level-error .tag {
    color: var(--log-error);
  }

  .msg {
    color: var(--fg);
    overflow-wrap: anywhere;
  }

  .empty {
    margin: 0;
    padding: var(--space-4);
    color: var(--text-muted);
    font-size: var(--text-s);
  }
</style>

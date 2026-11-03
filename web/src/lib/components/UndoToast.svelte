<!--
  One Undo toast (web/spec/README.md 3.3 and 3.8; undo.svelte.ts): the
  change is already applied; [Undo] reverts it for a few seconds.

  - The time left is a ring (BRAND 2.6: a ring is elapsed time, linear),
    neutral ink, never brass, with the seconds in words ("4 s"); quarters
    under reduced motion.
  - Pointer over the toast or focus inside pauses the window ("Paused").
  - Undo is a text button (BRAND 7); busy while the inverse runs; a failure
    keeps the toast with the server's words and [Retry].
  - role="status": announced politely; the information is also in the place
    where the change was made, so closing the toast loses nothing.
-->
<script lang="ts">
  import Control from './Control.svelte';
  import { reducedMotion } from './motion.svelte';
  import Ring from './Ring.svelte';
  import type { UndoEntry, UndoQueue } from './undo.svelte';

  interface Props {
    queue: UndoQueue;
    entry: UndoEntry;
    /** Draw in place without ticking (gallery). */
    preview?: boolean;
  }

  let { queue, entry, preview = false }: Props = $props();

  let now = $state(performance.now());
  $effect(() => {
    if (preview || entry.state !== 'open' || entry.pausedLeft !== null) return;
    let raf = 0;
    const tick = () => {
      now = performance.now();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  });

  // In preview the queue's own clock decides (the gallery freezes it).
  const fraction = $derived(queue.elapsed(entry.id, preview ? undefined : now));
  const left = $derived(queue.secondsLeft(entry.id, preview ? undefined : now));
  const paused = $derived(entry.pausedLeft !== null);
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div
  class="toast state-{entry.state}"
  role="status"
  onpointerenter={() => queue.pause(entry.id)}
  onpointerleave={() => queue.resume(entry.id)}
  onfocusin={() => queue.pause(entry.id)}
  onfocusout={(e) => {
    const next = e.relatedTarget as Node | null;
    if (!next || !(e.currentTarget as HTMLElement).contains(next)) queue.resume(entry.id);
  }}
>
  <span class="mark" aria-hidden="true"></span>
  <div class="text">
    <p class="title">{entry.title}</p>
    {#if entry.state === 'failed'}
      <p class="detail error">Could not undo: {entry.error}</p>
    {:else if entry.state === 'undone'}
      <p class="detail">Undone</p>
    {:else if entry.detail}
      <p class="detail">{entry.detail}</p>
    {/if}
  </div>
  {#if entry.state === 'open' || entry.state === 'undoing'}
    <span class="time num" aria-hidden="true">
      <span class="ring-box">
        <Ring size={16} value={fraction} track stepped={reducedMotion()} tone="muted" />
      </span>
      {paused ? 'Paused' : `${left} s`}
    </span>
  {/if}
  {#if entry.state !== 'undone'}
    <Control
      label={entry.state === 'failed' ? 'Retry' : 'Undo'}
      size="xs"
      busy={entry.state === 'undoing'}
      tooltip="none"
      onclick={() => void queue.undo(entry.id)}
    />
  {/if}
  <Control
    icon="close"
    label="Dismiss"
    variant="ghost"
    size="xs"
    tooltip="none"
    disabledReason={entry.state === 'undoing' ? 'wait until it finishes' : null}
    onclick={() => queue.dismiss(entry.id)}
  />
</div>

<style>
  .toast {
    --mark: var(--fg-muted);
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto auto auto;
    align-items: center;
    gap: var(--space-3);
    width: 400px;
    max-width: calc(100vw - 2 * var(--space-4));
    padding: var(--space-2) var(--space-2) var(--space-2) var(--space-4);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--surface);
    box-shadow: var(--shadow-2);
    color: var(--fg);
    pointer-events: auto;
    animation: enter var(--duration-base) var(--ease-out);
  }
  .state-failed {
    --mark: var(--danger);
  }
  .state-undone {
    --mark: var(--success);
  }
  .mark {
    align-self: start;
    width: 8px;
    height: 8px;
    margin-top: 5px;
    border-radius: var(--radius-round);
    background: var(--mark);
  }
  .text {
    min-width: 0;
  }
  .title,
  .detail {
    margin: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .title {
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
    line-height: var(--leading-tight);
    white-space: nowrap;
  }
  .detail {
    margin-top: 2px;
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--leading-tight);
  }
  .detail.error {
    color: var(--fg);
  }
  .time {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-width: 7ch;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .ring-box {
    position: relative;
    display: inline-block;
    width: 16px;
    height: 16px;
  }
  @keyframes enter {
    from {
      opacity: 0;
      transform: translateY(4px);
    }
  }
</style>

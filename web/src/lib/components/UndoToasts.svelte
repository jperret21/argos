<!--
  The Undo toasts of one queue, stacked bottom right above the status bar
  (where the shell's Toasts sit, so both read as one column). The shell or a
  screen owns the queue (`new UndoQueue()`) and pushes to it after applying a
  reversible change.
-->
<script lang="ts">
  import type { UndoQueue } from './undo.svelte';
  import UndoToast from './UndoToast.svelte';

  interface Props {
    queue: UndoQueue;
  }

  let { queue }: Props = $props();
</script>

<div class="undo-toasts" aria-live="polite">
  {#each queue.entries as entry (entry.id)}
    <UndoToast {queue} {entry} />
  {/each}
</div>

<style>
  .undo-toasts {
    position: fixed;
    right: var(--space-4);
    bottom: calc(var(--statusbar-h) + var(--space-4));
    z-index: var(--z-toast);
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: var(--space-2);
    pointer-events: none;
  }
</style>

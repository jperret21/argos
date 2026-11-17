<!--
  Toasts for the lab (the app has lib/shell/Toasts bound to its own state):
  bottom right, above the status bar, token surfaces, an optional action
  (Undo). Never the only carrier of information (spec 3.8).
-->
<script lang="ts">
  import { fly } from 'svelte/transition';
  import { reducedMotion } from '../model/env.svelte';
  import { ws } from '../model/app.svelte';
</script>

<div class="toasts" aria-live="polite">
  {#each ws.toasts as t (t.id)}
    <div class="toast tone-{t.tone}" transition:fly={{ y: 6, duration: reducedMotion() ? 0 : 180 }}>
      <span class="dot" aria-hidden="true"></span>
      <span class="text">{t.text}</span>
      {#if t.action}
        <button
          type="button"
          onclick={() => {
            t.action?.run();
            ws.toasts = ws.toasts.filter((x) => x.id !== t.id);
          }}>{t.action.label}</button
        >
      {/if}
    </div>
  {/each}
</div>

<style>
  .toasts {
    position: fixed;
    right: var(--space-4);
    bottom: calc(var(--lab-statusbar-h) + var(--space-3));
    z-index: var(--z-toast);
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    align-items: flex-end;
    pointer-events: none;
  }
  .toast {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    max-width: 440px;
    padding: var(--space-2) var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg);
    box-shadow: var(--shadow-2);
    color: var(--fg);
    font-size: var(--text-s);
    pointer-events: auto;
  }
  .dot {
    width: 7px;
    height: 7px;
    flex: none;
    border-radius: var(--radius-round);
    background: var(--status-idle);
  }
  .tone-ok .dot {
    background: var(--status-ok);
  }
  .tone-warn .dot {
    background: var(--status-busy);
  }
  button {
    height: 24px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font-size: var(--text-xs);
    cursor: pointer;
  }
</style>

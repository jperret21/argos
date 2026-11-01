<!--
  Unobtrusive notifications (API errors, notable events): bottom right, at
  most three, merged when identical, dismissed automatically. Errors are
  also written to the activity log, so closing a toast loses nothing.
-->
<script lang="ts">
  import { useApp } from '../app/state.svelte';
  import IconButton from '../components/IconButton.svelte';

  const app = useApp();
</script>

<div class="toasts" aria-live="polite">
  {#each app.toasts as t (t.id)}
    <div class="toast level-{t.level}" role={t.level === 'error' ? 'alert' : 'status'}>
      <span class="mark" aria-hidden="true"></span>
      <div class="text">
        <p class="title">
          {t.title}
          {#if t.count > 1}<span class="count num">×{t.count}</span>{/if}
        </p>
        {#if t.message}<p class="message">{t.message}</p>{/if}
      </div>
      <IconButton
        icon="close"
        label="Dismiss"
        variant="ghost"
        size="s"
        tooltip="none"
        onclick={() => app.dismissToast(t.id)}
      />
    </div>
  {/each}
</div>

<style>
  .toasts {
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

  .toast {
    --mark: var(--accent);
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: start;
    gap: var(--space-3);
    width: 360px;
    max-width: calc(100vw - 2 * var(--space-4));
    padding: var(--space-3) var(--space-2) var(--space-3) var(--space-4);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--surface);
    box-shadow: var(--shadow-2);
    pointer-events: auto;
    animation: enter var(--duration-base) var(--ease-out);
  }
  .level-warning {
    --mark: var(--warning);
  }
  .level-error {
    --mark: var(--danger);
  }

  .mark {
    width: 8px;
    height: 8px;
    margin-top: 5px;
    border-radius: var(--radius-round);
    background: var(--mark);
  }

  .text {
    min-width: 0;
  }

  p {
    margin: 0;
  }

  .title {
    color: var(--fg);
    font-size: var(--text-s);
    font-weight: var(--weight-semibold);
    line-height: var(--leading-normal);
  }

  .count {
    margin-left: var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-regular);
  }

  /* Long device errors are clamped here; the activity log keeps them whole. */
  .message {
    display: -webkit-box;
    margin-top: 2px;
    overflow: hidden;
    color: var(--text-muted);
    font-size: var(--text-s);
    line-height: var(--leading-normal);
    overflow-wrap: anywhere;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
    line-clamp: 3;
  }

  @keyframes enter {
    from {
      opacity: 0;
      transform: translateY(4px);
    }
  }
</style>

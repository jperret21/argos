<!--
  Unobtrusive notifications (API errors, notable events): bottom right, at
  most three, merged when identical, dismissed automatically. Errors are
  also written to the activity log, so closing a toast loses nothing.
  The Undo toasts of the app's one queue (wave 2: remove a saved site,
  reset a setting, reset all layouts) sit in the same column, above.
  On Settings the column moves to the bottom left of the form column
  (design review): the right-hand side holds the actions of the rows and
  tables (Save current site, Reset, Clear…), which a toast must not cover
  right after the change it offers to undo. On Observe the column sits at the
  bottom left of the viewer stage, above the scale bar (`app.toastAnchor`), never
  over the rail's lowest controls (Slew, Abort, the Sync confirmation).
-->
<script lang="ts">
  import { useApp } from '../app/state.svelte';
  import Button from '../components/Button.svelte';
  import IconButton from '../components/IconButton.svelte';
  import UndoToast from '../components/UndoToast.svelte';
  import AttentionMark from './attention/AttentionMark.svelte';

  /** The kept end of a file name shown shortened in the middle. */
  const TAIL = 14;
  const fileHead = (name: string) => (name.length > TAIL ? name.slice(0, -TAIL) : '');
  const fileTail = (name: string) => (name.length > TAIL ? name.slice(-TAIL) : name);

  const app = useApp();
</script>

<div
  class="toasts"
  class:in-settings={app.section === 'configuration'}
  class:on-stage={app.section === 'imaging' && !!app.toastAnchor}
  style:left={app.section === 'imaging' && app.toastAnchor ? `${app.toastAnchor.left}px` : undefined}
  style:bottom={app.section === 'imaging' && app.toastAnchor ? `${app.toastAnchor.bottom}px` : undefined}
  aria-live="polite"
>
  {#each app.undo.entries as entry (entry.id)}
    <UndoToast queue={app.undo} {entry} />
  {/each}
  {#each app.toasts as t (t.id)}
    <div class="toast level-{t.level}" class:with-action={!!t.action} role={t.level === 'error' ? 'alert' : 'status'}>
      <!-- The attention vocabulary's shapes (BRAND §8): error = filled disc, warning = bar over
           dot, info = hollow ring; Night Red tells them apart without hue. -->
      <span class="mark"><AttentionMark level={t.level === 'error' ? 'critical' : t.level === 'warning' ? 'attention' : 'info'} size={10} /></span>
      <div class="text">
        <p class="title">
          {t.title}
          {#if t.count > 1}<span class="count num">×{t.count}</span>{/if}
        </p>
        {#if t.message && !t.action}<p class="message">{t.message}</p>{/if}
      </div>
      {#if t.action}
        <Button label={t.action.label} size="s" onclick={() => (t.action?.run(), app.dismissToast(t.id))} />
      {/if}
      <IconButton
        icon="close"
        label="Dismiss"
        variant="ghost"
        size="s"
        tooltip="none"
        onclick={() => app.dismissToast(t.id)}
      />
      {#if t.message && t.action}
        <!-- With an action: the message on its own full-width line under the title row. A
             file name stays on one line, shortened in the middle (its end, the extension
             and the time stamp, stays), never broken at a hyphen. -->
        {#if t.file}
          <p class="message below file">
            <span class="visually-hidden">{t.message}</span><span class="head" aria-hidden="true">{fileHead(t.message)}</span><span class="tail" aria-hidden="true">{fileTail(t.message)}</span>
          </p>
        {:else}
          <p class="message below">{t.message}</p>
        {/if}
      {/if}
    </div>
  {/each}
</div>

<style>
  /* W8: the action (Reveal in Finder) sits between the title and Dismiss, on one row; the
     message goes under it, full width. */
  .toast.with-action {
    grid-template-columns: auto minmax(0, 1fr) auto auto;
  }
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
  /* Settings: bottom left of the form column (rail + 208 px category list). */
  .toasts.in-settings {
    right: auto;
    left: calc(var(--sidebar-w) + 208px + var(--space-5));
    align-items: flex-start;
  }
  /* Observe: the bottom left of the viewer stage (left / bottom set inline). */
  .toasts.on-stage {
    right: auto;
    flex-direction: column-reverse;
    align-items: flex-start;
  }

  .toast {
    /* Info: a neutral mark (BRAND 8: toasts are not part of the brass budget). */
    --mark: var(--fg-muted);
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
    display: inline-flex;
    margin-top: 4px;
    color: var(--mark, var(--fg-muted));
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
  .message.below {
    grid-column: 2 / -1;
    margin-top: calc(-1 * var(--space-2));
  }
  .message.file {
    display: flex;
    min-width: 0;
    padding-right: var(--space-2);
    white-space: nowrap;
  }
  .file .head {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .file .tail {
    flex: none;
  }

  @keyframes enter {
    from {
      opacity: 0;
      transform: translateY(4px);
    }
  }
</style>

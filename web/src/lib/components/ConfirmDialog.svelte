<!--
  Confirmation (README 3.3, 01 section 2.3.12): replaces QMessageBox.question.
  Title = the question ("Park the mount?"), message = what will happen, two
  text buttons: [cancelLabel] [confirmLabel], the confirming one on the
  right. Focus starts on Cancel, Escape = Cancel.

  - `destructive`: the confirm button is drawn in the danger style (outline
    --danger, label --fg at rest) and the dialog is an alertdialog.
  - `onconfirm` may return a promise: the confirm button turns busy, the
    dialog stays open and cannot be dismissed until it settles; a rejection
    is shown inline in words (the action's own toast and log line still
    apply), so the observer can retry or cancel.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import Button from './Button.svelte';
  import Dialog from './Dialog.svelte';
  import type { CloseReason } from './layers';

  interface Props {
    open?: boolean;
    title: string;
    message?: string;
    /** Rich body instead of `message`. */
    children?: Snippet;
    confirmLabel: string;
    cancelLabel?: string;
    destructive?: boolean;
    onconfirm: () => void | Promise<unknown>;
    oncancel?: () => void;
    returnFocus?: HTMLElement | null;
    preview?: boolean;
    /** Gallery: show the busy state / an inline error without running anything. */
    busy?: boolean;
    error?: string | null;
  }

  let {
    open = $bindable(false),
    title,
    message,
    children,
    confirmLabel,
    cancelLabel = 'Cancel',
    destructive = false,
    onconfirm,
    oncancel,
    returnFocus = null,
    preview = false,
    busy: busyProp = false,
    error: errorProp = null,
  }: Props = $props();

  const uid = `cfm-${Math.random().toString(36).slice(2, 9)}`;
  let running = $state(false);
  let failure: string | null = $state(null);
  const busy = $derived(busyProp || running);
  const error = $derived(errorProp ?? failure);

  $effect(() => {
    if (open) failure = null;
  });

  async function confirm(): Promise<void> {
    if (busy) return;
    failure = null;
    const result = onconfirm();
    if (!(result instanceof Promise)) {
      open = false;
      return;
    }
    running = true;
    try {
      await result;
      open = false;
    } catch (err) {
      failure = err instanceof Error ? err.message : String(err);
    } finally {
      running = false;
    }
  }

  function cancel(): void {
    if (busy) return;
    open = false;
    oncancel?.();
  }

  function onclose(reason: CloseReason): void {
    if (reason !== 'action') oncancel?.();
  }
</script>

<Dialog
  bind:open
  {title}
  size="s"
  role={destructive ? 'alertdialog' : 'dialog'}
  describedby="{uid}-msg"
  dismissible={!busy}
  {returnFocus}
  {preview}
  {onclose}
>
  <div id="{uid}-msg" class="message">
    {#if children}{@render children()}{:else if message}<p>{message}</p>{/if}
  </div>
  {#if error}
    <p class="error" role="alert"><span class="mark" aria-hidden="true"></span>{error}</p>
  {/if}
  {#snippet footer()}
    <Button label={cancelLabel} disabledReason={busy ? 'wait until it finishes' : null} data-autofocus onclick={cancel} />
    <Button
      label={confirmLabel}
      variant={destructive ? 'danger' : 'primary'}
      {busy}
      onclick={() => void confirm()}
    />
  {/snippet}
</Dialog>

<style>
  .message {
    color: var(--fg);
  }

  .error {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    margin: var(--space-3) 0 0;
    padding: var(--space-2) var(--space-3);
    border: var(--border-w) solid var(--danger);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-s);
    overflow-wrap: anywhere;
  }
  .mark {
    flex: none;
    width: 7px;
    height: 7px;
    border-radius: var(--radius-round);
    background: var(--danger);
    transform: translateY(-1px);
  }
</style>

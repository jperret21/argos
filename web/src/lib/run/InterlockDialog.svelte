<!--
  The interlock question (D2, README 3.3): a mount command refused with `409 run_active`
  while a sequence runs. What the command would do to the run, then the one way through:
  [Keep running] [Pause the run and slew]. Pausing to slew is a physical action hard to undo
  at night (BRAND 7): a hold-to-confirm control (40 px, icon and label, secondary, no brass
  fill); Enter / Space open its inline two-button confirmation. The jog's way through only
  pauses the run (nothing moves): a plain secondary button. Focus on Keep running, Escape
  keeps running; a refusal of the retry stays in the dialog in words. One instance per
  screen, fed by a MountInterlock (interlock.svelte.ts) that every mount control goes through.
-->
<script lang="ts">
  import Button from '../components/Button.svelte';
  import Dialog from '../components/Dialog.svelte';
  import HoldButton from '../components/HoldButton.svelte';
  import { interlockText, type MountInterlock, type PendingInterlock } from './interlock.svelte';

  interface Props {
    lock: MountInterlock;
    /** Gallery: draw this request in place. */
    preview?: PendingInterlock | null;
    /** The sub in progress (s), named in the words; null when unknown. */
    exposureS?: number | null;
  }
  let { lock, preview = null, exposureS = null }: Props = $props();

  const uid = `ilk-${Math.random().toString(36).slice(2, 9)}`;
  const p = $derived(preview ?? lock.pending);
  const text = $derived(p ? interlockText(p, exposureS) : null);
  let open = $state(false);
  let busy = $state(false);
  let failure: string | null = $state(null);
  $effect(() => {
    open = !!p;
    if (p) failure = null;
  });

  function keep(): void {
    if (busy) return;
    open = false;
    lock.cancel();
  }

  async function through(): Promise<void> {
    busy = true;
    failure = null;
    try {
      await lock.confirm();
    } catch (err) {
      failure = err instanceof Error ? err.message : String(err);
      throw err;
    } finally {
      busy = false;
    }
  }
</script>

{#if text && p}
  <Dialog
    bind:open
    title={text.title}
    size="s"
    role="alertdialog"
    describedby="{uid}-msg"
    dismissible={!busy}
    preview={!!preview}
    onclose={(reason) => {
      if (reason !== 'action') lock.cancel();
    }}
  >
    <div id="{uid}-msg" class="message"><p>{text.body}</p></div>
    {#if failure}
      <p class="error" role="alert"><span class="mark" aria-hidden="true"></span>{failure}</p>
    {/if}
    {#snippet footer()}
      <!-- Top-aligned: the hold control carries its caption under it; Keep running sits level
           with the control, not with the pair. -->
      <span class="keep"><Button label="Keep running" disabledReason={busy ? 'wait until it finishes' : null} data-autofocus onclick={keep} /></span>
      {#if p.pauseOnly}
        <Button label={text.confirm} {busy} onclick={() => void through().catch(() => {})} />
      {:else}
        <HoldButton
          icon="goto"
          label={text.confirm}
          size="l"
          verb={text.holdVerb}
          confirmTitle={`${text.confirm}?`}
          confirmBody="The sub in progress is saved first; the run stays paused until you resume it."
          confirmAction={text.confirm}
          cancelLabel="Keep running"
          busyLabel="Pausing the run…"
          onconfirm={through}
        />
      {/if}
    {/snippet}
  </Dialog>
{/if}

<style>
  .keep {
    display: inline-flex;
    align-items: center;
    align-self: flex-start;
    height: var(--control-h-l);
  }
  .message p {
    margin: 0;
    color: var(--fg);
    line-height: 1.5;
  }
  .error {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: var(--space-3) 0 0;
    color: var(--fg);
    font-size: var(--text-s);
  }
  .error .mark {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--danger);
  }
</style>

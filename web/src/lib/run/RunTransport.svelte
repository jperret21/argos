<!--
  The run transport (spec 06 2.2 rows 1.9 #1-3, 2.3.2, 2.3.6, 2.4; Q-P2, Q-P7; M76):
  [Start sequence ▾] [Pause | Resume] [Stop], always visible.

  - Start (primary, deliberate): disabled with the reason only when the server would refuse
    (a block, an invalid step, a run already active: run.ts startBlock); its menu holds
    "Start at a time…" (StartAtPopover), which never starts by itself.
  - Pause holds at the frame boundary (no confirmation: Resume undoes it); while pausing the
    button already reads Resume, so the request shows at once (P16).
  - Stop asks first (ConfirmDialog, focus on Keep running): what is discarded, what is saved
    and where, the end-of-run action not applied; a scheduled start is cancelled the same way.
  - No single key starts, pauses or stops a run; Escape never stops one (spec 2.4).
  - A refusal is written under the transport in the server's words (and handed to `onerror`
    for the toast and the log).
-->
<script lang="ts">
  import type { SequenceState } from '../api/sequence';
  import ConfirmDialog from '../components/ConfirmDialog.svelte';
  import IconButton from '../components/IconButton.svelte';
  import type { MenuChoice } from '../components/menu';
  import SplitButton from '../components/SplitButton.svelte';
  import { clockUtc } from '../format/time';
  import { isActive, stopDialog } from './run';
  import StartAtPopover from './StartAtPopover.svelte';

  interface Props {
    seq: SequenceState | null;
    now: number;
    /** Why Start cannot run (run.ts startBlock); null: it can. */
    startReason?: string | null;
    /** A transit's coverage start, prefilled in "Start at". */
    suggestedStart?: number | null;
    /** The draft's own start time (plan `start_at_utc`): Start then schedules it, and says so. */
    draftStartAt?: number | null;
    /** null: start now; a time: start then (Q-P2). */
    onstart: (at: number | null) => Promise<unknown> | void;
    onpause: () => Promise<unknown> | void;
    onresume: () => Promise<unknown> | void;
    onstop: () => Promise<unknown> | void;
    onerror?: (message: string) => void;
    /** Gallery: the Stop dialog / Start at popover drawn in place. */
    previewStop?: boolean;
    previewStartAt?: string | null;
  }
  let { seq, now, startReason = null, suggestedStart = null, draftStartAt = null, onstart, onpause, onresume, onstop, onerror, previewStop = false, previewStartAt = null }: Props = $props();

  let busy = $state<'start' | 'pause' | 'resume' | null>(null);
  let failure = $state<string | null>(null);
  let stopOpen = $state(false);
  let startAtOpen = $state(false);
  let anchor: HTMLElement | undefined = $state();

  $effect(() => {
    if (previewStop) stopOpen = true;
    if (previewStartAt !== null) startAtOpen = true;
  });

  const phase = $derived(seq?.state ?? 'idle');
  const active = $derived(isActive(seq));
  const scheduled = $derived(phase === 'waiting');
  const pauseSide = $derived(phase === 'paused' || phase === 'pausing' ? 'resume' : 'pause');
  const dialog = $derived(seq ? stopDialog(seq) : null);
  /** The draft's time, while it is still ahead: the main part schedules it, written on the button. */
  const at = $derived(draftStartAt !== null && draftStartAt > now ? draftStartAt : null);
  const items = $derived([{ id: 'start-at', label: 'Start at a time…', icon: 'start', detail: 'UTC; the server waits', disabledReason: startReason }]);

  async function act(kind: 'start' | 'pause' | 'resume', fn: () => Promise<unknown> | void): Promise<void> {
    if (busy) return;
    busy = kind;
    failure = null;
    try {
      await fn();
    } catch (err) {
      failure = err instanceof Error ? err.message : String(err);
      onerror?.(failure);
    } finally {
      busy = null;
    }
  }

  const pauseReason = $derived(
    phase === 'stopping' ? 'The run is stopping' : scheduled ? 'The run has not started yet' : !active ? 'No sequence is running' : null,
  );
  const stopReason = $derived(phase === 'stopping' ? 'The run is stopping' : !active && !scheduled ? 'No sequence is running' : null);
</script>

<div class="transport" role="group" aria-label="Sequence">
  <span class="start" bind:this={anchor}>
    <SplitButton
      icon="start"
      label="Start sequence"
      text="Start sequence"
      variant="primary"
      size="s"
      detail={at !== null ? `at ${clockUtc(at, false)} UTC` : undefined}
      {items}
      menuLabel="Start options"
      busy={busy === 'start'}
      disabledReason={startReason}
      onaction={() => act('start', () => onstart(at))}
      onselect={(it: MenuChoice) => {
        if (it.id === 'start-at') startAtOpen = true;
      }}
    />
  </span>
  {#if pauseSide === 'resume'}
    <IconButton icon="start" label="Resume" showLabel size="s" busy={busy === 'resume'} disabledReason={pauseReason} tooltipText={phase === 'pausing' ? 'Cancel the pause: the run goes on' : 'Resume the run'} onclick={() => act('resume', onresume)} />
  {:else}
    <IconButton icon="pause" label="Pause" size="s" busy={busy === 'pause'} disabledReason={pauseReason} tooltipText="Pause at the end of this frame; Resume releases it" onclick={() => act('pause', onpause)} />
  {/if}
  <IconButton icon="stop" label={scheduled ? 'Cancel start…' : 'Stop…'} showLabel size="s" variant="danger" busy={phase === 'stopping'} disabledReason={stopReason} onclick={() => (stopOpen = true)} />
</div>
{#if failure}
  <p class="refused" role="alert"><span class="mark" aria-hidden="true"></span>{failure}</p>
{/if}

<StartAtPopover bind:open={startAtOpen} {anchor} {now} suggested={suggestedStart} blocked={startReason} preview={previewStartAt !== null} initial={previewStartAt} onschedule={(t) => onstart(t)} />

{#if dialog}
  <ConfirmDialog
    bind:open={stopOpen}
    title={dialog.title}
    message={dialog.message}
    confirmLabel={dialog.confirm}
    cancelLabel={dialog.cancel}
    destructive
    preview={previewStop}
    onconfirm={() => onstop()}
  />
{/if}

<style>
  .transport {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  .start {
    display: inline-flex;
  }
  .refused {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: var(--space-1) 0 0;
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .mark {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--danger);
    flex: none;
  }
</style>

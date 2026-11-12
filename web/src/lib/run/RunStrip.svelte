<!--
  The run strip (spec 06 2.3.2, 2.4 "Finished"; P14, P15, P16; M76), under the Plan
  toolbar while a run is engaged and after it ends:

  - Line 1: the true-proportion progress (RunProgress: frames on a time axis, autofocus
    notches, now marker) and the run in words (run.ts stripLine: step, frames, pass, ETA,
    end time; the state's own words lead when pausing, paused, in autofocus, stopping,
    scheduled).
  - Line 2: the newest saved sub (file, HFD, FWHM, stars, UTC) and a link to the log.
  - After the run: the outcome in words (complete / stopped by the observer / stopped by
    an error, the server's sentence verbatim), until dismissed.
  Nothing renders when there is no run and no outcome to show.
-->
<script lang="ts">
  import type { SequenceState } from '../api/sequence';
  import RunProgress from '../charts/mini/RunProgress.svelte';
  import IconButton from '../components/IconButton.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { fixed, int } from '../format/number';
  import { clockUtc } from '../format/time';
  import type { SavedSub } from './sequence.svelte';
  import { endAt, isEngaged, outcomeText, stateChip, stripLine } from './run';

  interface Props {
    seq: SequenceState | null;
    now: number;
    frameTimes?: readonly number[];
    lastSaved?: SavedSub | null;
    /** Autofocus passes of this run (unix s). */
    marks?: readonly number[];
    /** The autofocus sweep's progress (A36), while the run is in autofocus. */
    afStep?: { done: number; total: number } | null;
    /** Show the outcome of the run that ended (SequenceStore.outcomeVisible). */
    showOutcome?: boolean;
    ondismiss?: () => void;
    onlog?: () => void;
  }
  let { seq, now, frameTimes = [], lastSaved = null, marks = [], afStep = null, showOutcome = true, ondismiss, onlog }: Props = $props();

  const engaged = $derived(isEngaged(seq));
  const chip = $derived(stateChip(seq));
  const end = $derived(seq && engaged ? endAt(seq, now) : null);
  const start = $derived(seq?.started_t ?? seq?.start_at_t ?? null);
  const line = $derived(seq && engaged ? stripLine(seq, now, afStep) : '');
  const result = $derived(seq && seq.state === 'idle' && showOutcome ? seq.last_result : null);
  const metrics = $derived.by(() => {
    const l = lastSaved;
    if (!l) return '';
    const b: string[] = [];
    if (l.hfd !== null) b.push(`HFD ${fixed(l.hfd, 2)} px`); // as the status bar (BRAND 5)
    if (l.fwhm !== null) b.push(`FWHM ${fixed(l.fwhm, 2)} px`);
    if (l.stars !== null) b.push(`${int(l.stars)} stars`);
    b.push(`${clockUtc(l.t)} UTC`);
    return b.join(' · ');
  });
</script>

{#if seq && engaged}
  <div class="strip" role="region" aria-label="Sequence progress">
    <div class="l1">
      <!-- The state is the live part (announced on change); the line updates every frame and is not. -->
      <StatusBadge tone={chip.tone} label={chip.label} plain />
      {#if seq.state !== 'waiting'}
        <span class="bar">
          <RunProgress done={seq.frames_done} total={seq.frames_total} {start} end={end ?? start} {now} times={frameTimes} n={frameTimes.length} {marks} width={0} height={8} />
        </span>
      {/if}
      <span class="text" title={line}>{line}</span>
    </div>
    {#if lastSaved}
      <div class="l2">
        <span class="k">last</span>
        <span class="file num" title={lastSaved.name}>{lastSaved.name}</span>
        <span class="m">{metrics}</span>
        <span class="grow"></span>
        {#if onlog}<IconButton icon="log" label="Open the log" size="s" variant="ghost" onclick={onlog} />{/if}
      </div>
    {/if}
  </div>
{:else if result}
  <div class="strip ended" role="status">
    <div class="l1">
      <StatusBadge tone={chip.tone} label={chip.label} plain live={false} />
      <span class="text">{outcomeText(result)}</span>
      <span class="grow"></span>
      {#if ondismiss}<IconButton icon="close" label="Dismiss the outcome" size="s" variant="ghost" onclick={ondismiss} />{/if}
    </div>
  </div>
{/if}

<style>
  .strip {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: var(--space-1) var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    background: var(--bg);
    min-width: 0;
  }
  .l1,
  .l2 {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-height: 24px;
    min-width: 0;
  }
  .bar {
    display: flex;
    flex: 0 1 240px;
    min-width: 80px;
  }
  .text {
    color: var(--fg);
    font-size: var(--text-s);
    font-variant-numeric: var(--numeric);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
    flex: 1 1 auto;
  }
  .ended .text {
    flex: 0 1 auto;
  }
  .l2 {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .k {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .file {
    color: var(--fg);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
    flex: 0 1 auto;
  }
  .m {
    white-space: nowrap;
    font-variant-numeric: var(--numeric);
  }
  .grow {
    flex: 1;
  }
</style>

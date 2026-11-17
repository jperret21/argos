<!--
  Job strip (web/spec/07-review-analysis.md WF-F, README 3.7, 4.2): the one-line progress of
  the long jobs a screen starts (a re-run, an export, a session open, a file solve), made to
  sit in a toolbar row in place of the identity text while a job runs.

  - Running: spinner, what it does ("Re-running photometry"), "37 / 195 frames", the ETA from
    the observed rate, an optional detail ("field rot +0.4°"), the server's stage text, a
    2 px determinate bar along the bottom edge, and [stop Cancel] (icon + label, BRAND 7)
    when the job can be cancelled; "Cancelling…" until the server confirms.
  - Several jobs: the newest one shows, "+N" says how many others run (their names in the
    tooltip); nothing is hidden silently.
  - Finished: the outcome stays in words (Done + the result, Failed + the server's exact
    message as role="alert", Cancelled) with the caller's actions (Open, Reveal) and a
    Dismiss, until the observer dismisses it or another job starts.
  Every state is a word, so the strip reads the same in Night Red; no brass (the bar is
  --fg-muted, BRAND 3).
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import { isActive, progressFraction, type JobEntry } from '../app/jobs';
  import IconButton from './IconButton.svelte';
  import { countText, etaText, stripJob } from './jobstrip';
  import { tooltip } from './tooltip';

  interface Props {
    /** Jobs this strip may show (the store's list, oldest first). */
    jobs: readonly JobEntry[];
    /** Only these kinds (null: every job given). */
    kinds?: readonly string[] | null;
    /** What a job is, in words ("Re-running photometry"). */
    title: (job: JobEntry) => string;
    /** Unit of the count ("frames"); "" for a bare count. */
    unit?: (job: JobEntry) => string;
    /** One more fact while it runs ("field rot +0.4°"), or null. */
    detail?: (job: JobEntry) => string | null;
    /** The result in words when done ("195 frames, 7 curves → photometry_rerun_…/"). */
    resultText?: (job: JobEntry) => string | null;
    /** Buttons shown when the job is done (Open, Reveal). */
    actions?: Snippet<[JobEntry]>;
    oncancel?: (id: string) => void;
    ondismiss?: (id: string) => void;
    /** Wall clock (pass a ticking value so the ETA moves). */
    now?: number;
    /** Accessible name of the strip ("Review jobs"). */
    label?: string;
  }

  let {
    jobs,
    kinds = null,
    title,
    unit = () => '',
    detail = () => null,
    resultText = () => null,
    actions,
    oncancel,
    ondismiss,
    now = Date.now(),
    label = 'Jobs',
  }: Props = $props();

  const pick = $derived(stripJob(jobs, kinds));
  const job = $derived(pick.job);
  const running = $derived(job ? isActive(job) : false);
  const fraction = $derived(job ? progressFraction(job) : null);
  const othersText = $derived.by(() => {
    if (!pick.others || !job) return '';
    const active = jobs.filter((j) => isActive(j) && j.id !== job.id && (!kinds || kinds.includes(j.kind)));
    return active.map((j) => title(j)).join('\n');
  });

  const WORDS: Record<JobEntry['state'], string> = {
    queued: 'Queued',
    running: 'Running',
    done: 'Done',
    failed: 'Failed',
    cancelled: 'Cancelled',
  };
</script>

{#if job}
  {@const count = running ? countText(job, unit(job)) : null}
  {@const eta = running && !job.cancelling ? etaText(job, now) : null}
  {@const extra = running ? detail(job) : null}
  {@const stage = job.cancelling && running ? 'Stopping at the next safe point…' : (job.message ?? job.stage)}
  <div
    class="strip state-{job.state}"
    class:running
    role={job.state === 'failed' ? 'alert' : 'status'}
    aria-label={label}
    aria-busy={running || undefined}
    data-job-kind={job.kind}
    data-job-state={job.state}
  >
    <span class="mark" aria-hidden="true">
      {#if running}
        <svg class="spinner" viewBox="0 0 24 24"><path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" /></svg>
      {:else}
        <span class="dot"></span>
      {/if}
    </span>
    <span class="title">{title(job)}</span>
    {#if running}
      {#if job.cancelling}<span class="word">Cancelling</span>{:else if job.state === 'queued'}<span class="word">Queued</span>{/if}
      {#if count}<span class="sep" aria-hidden="true">·</span><span class="num">{count}</span>{/if}
      {#if eta}<span class="sep" aria-hidden="true">·</span><span class="num eta">{eta}</span>{/if}
      {#if extra}<span class="sep" aria-hidden="true">·</span><span class="num">{extra}</span>{/if}
      {#if stage}<span class="sep" aria-hidden="true">·</span><span class="stage">{stage}</span>{/if}
    {:else}
      <span class="word">{WORDS[job.state]}</span>
      {#if job.state === 'done'}
        {@const r = resultText(job) ?? job.message}
        {#if r}<span class="sep" aria-hidden="true">·</span><span class="stage">{r}</span>{/if}
      {:else if job.state === 'failed'}
        <span class="sep" aria-hidden="true">·</span><span class="stage error">{job.error?.message ?? job.message ?? 'Failed without a message.'}</span>
      {:else if job.message}
        <span class="sep" aria-hidden="true">·</span><span class="stage">{job.message}</span>
      {/if}
    {/if}
    <span class="spacer"></span>
    {#if pick.others > 0}
      <span class="others num" use:tooltip={{ text: `Also running:\n${othersText}`, placement: 'bottom' }}>+{pick.others}</span>
    {/if}
    {#if job.cancelError}<span class="note">Cancel refused: {job.cancelError}</span>{/if}
    <span class="buttons">
      {#if running && oncancel}
        <IconButton
          icon="stop"
          label="Cancel"
          showLabel
          size="s"
          variant="secondary"
          glyphTone="danger"
          busy={job.cancelling}
          disabledReason={job.cancellable ? null : 'this job cannot be cancelled'}
          onclick={() => oncancel?.(job.id)}
        />
      {/if}
      {#if job.state === 'done' && actions}{@render actions(job)}{/if}
      {#if !running && ondismiss}
        <IconButton icon="close" label="Dismiss" variant="ghost" size="s" tooltip="bottom" onclick={() => ondismiss?.(job.id)} />
      {/if}
    </span>
    {#if running}
      <span
        class="bar"
        class:indeterminate={fraction === null}
        role="progressbar"
        aria-label="{title(job)} progress"
        aria-valuemin={fraction === null ? undefined : 0}
        aria-valuemax={fraction === null ? undefined : 100}
        aria-valuenow={fraction === null ? undefined : Math.round(fraction * 100)}
        aria-valuetext={count ?? stage ?? undefined}
      >
        {#if fraction !== null}<span class="fill" style:width="{fraction * 100}%"></span>{/if}
      </span>
    {/if}
  </div>
{/if}

<style>
  .strip {
    container-type: inline-size;
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
    height: var(--control-h-s, 30px);
    padding: 0 var(--space-1) 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-s);
    white-space: nowrap;
    overflow: hidden;
  }
  .state-failed {
    border-color: var(--danger);
  }
  .mark {
    display: inline-flex;
    flex: none;
    width: 16px;
    height: 16px;
    align-items: center;
    justify-content: center;
    color: var(--fg-muted);
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-round);
  }
  .state-done .dot {
    background: var(--success);
  }
  .state-failed .dot {
    background: var(--danger);
  }
  .state-cancelled .dot {
    box-shadow: inset 0 0 0 1.5px var(--fg-muted);
  }
  .spinner {
    width: 16px;
    height: 16px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.5;
    stroke-linecap: round;
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .spinner {
      animation: none;
    }
  }
  /*
   * In a narrow toolbar the stage text goes first, then the ETA, then the title shortens
   * (ellipsis); the count and the buttons (Cancel, Dismiss) always stay. The strip is its own
   * size container: its parent gives it a width (flex: 1 1 0 in a toolbar).
   */
  /* The job's name is short ("Re-run", "Export") and never cut: the result words give way. */
  .title {
    flex: none;
    min-width: 4ch;
    overflow: hidden;
    text-overflow: ellipsis;
    font-weight: var(--weight-medium);
  }
  .word {
    flex: none;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .sep {
    flex: none;
    color: var(--text-muted);
  }
  .num {
    flex: none;
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
    color: var(--fg);
  }
  /* While it runs the stage is the frame's name: it goes first; a finished job keeps its result. */
  @container (max-width: 440px) {
    .running .stage,
    .running .sep:has(+ .stage) {
      display: none;
    }
  }
  @container (max-width: 360px) {
    .eta,
    .sep:has(+ .eta) {
      display: none;
    }
  }
  .stage {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-muted);
  }
  .stage.error {
    color: var(--fg);
  }
  .spacer {
    flex: 1;
    min-width: var(--space-2);
  }
  .others {
    padding: 0 var(--space-1);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .note {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .buttons {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: var(--space-1);
  }
  .buttons :global(.icon-button) {
    height: 24px;
  }
  .bar {
    position: absolute;
    inset: auto 0 0 0;
    height: 2px;
    overflow: hidden;
    background: var(--border-soft);
  }
  .fill {
    position: absolute;
    inset: 0 auto 0 0;
    background: var(--fg-muted);
  }
  .bar.indeterminate {
    background: var(--border-soft);
  }
</style>

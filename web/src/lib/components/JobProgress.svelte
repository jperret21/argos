<!--
  Progress of a long job (README 3.7, 4.2): an inline row where the job was
  started (discovery under "Discover", a re-run in the Review job strip).

  - queued / running: what it does now (stage, message), a determinate bar
    when the total is known ("2 of 3"), the spinner otherwise, the elapsed
    time, and [stop Cancel] when the job can be cancelled.
  - cancelling: "Cancelling…" until the server confirms (never claimed done).
  - done: a success mark, the result in words, `actions` (Open, Reveal…).
  - failed: a danger mark and the server's exact message (role="alert").
  - cancelled: a ring and "Cancelled".
  Every state is a word, so the row reads the same in Night Red. No brass:
  the bar is --fg-muted on --bg-2 (brass is for focus and deliberate
  actions, BRAND 3).
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import { isActive, jobDuration, type JobEntry, progressFraction } from '../app/jobs';
  import IconButton from './IconButton.svelte';

  interface Props {
    job: JobEntry;
    /** What the job is, in words ("Discovery", "Re-run photometry"). */
    title: string;
    /** Result in words when done ("Found 2 devices"). Default: the job's message. */
    resultText?: string | null;
    oncancel?: (id: string) => void;
    ondismiss?: (id: string) => void;
    onretry?: () => void;
    /** Buttons shown when done (Open, Reveal). */
    actions?: Snippet;
    /** Wall clock for the elapsed time (re-render once a second by passing a ticking value). */
    now?: number;
    /** 'row': full width under a control; 'strip': compact, in a toolbar. */
    variant?: 'row' | 'strip';
  }

  let {
    job,
    title,
    resultText = null,
    oncancel,
    ondismiss,
    onretry,
    actions,
    now = Date.now(),
    variant = 'row',
  }: Props = $props();

  const running = $derived(isActive(job));
  const fraction = $derived(progressFraction(job));
  const elapsed = $derived(jobDuration(job, now));
  const stageText = $derived(job.message ?? job.stage ?? (job.state === 'queued' ? 'Waiting to start' : 'Working'));

  const STATE_WORDS: Record<JobEntry['state'], string> = {
    queued: 'Queued',
    running: 'Running',
    done: 'Done',
    failed: 'Failed',
    cancelled: 'Cancelled',
  };
  const word = $derived(job.cancelling && running ? 'Cancelling' : STATE_WORDS[job.state]);
</script>

<div
  class="job {variant} state-{job.state}"
  class:cancelling={job.cancelling}
  role={job.state === 'failed' ? 'alert' : 'status'}
  aria-busy={running || undefined}
>
  <span class="mark" aria-hidden="true">
    {#if running}
      <svg class="spinner" viewBox="0 0 24 24"><path d="M12 3.75a8.25 8.25 0 1 1 -8.25 8.25" /></svg>
    {:else}
      <span class="dot"></span>
    {/if}
  </span>

  <div class="main">
    <div class="line">
      <span class="title">{title}</span>
      <span class="word">{word}</span>
      {#if running}
        <span class="stage">{job.cancelling ? 'Stopping at the next safe point…' : stageText}</span>
      {:else if job.state === 'done'}
        <span class="stage">{resultText ?? job.message ?? ''}</span>
      {:else if job.state === 'failed'}
        <span class="stage error">{job.error?.message ?? job.message ?? 'Failed without a message.'}</span>
      {/if}
      <span class="spacer"></span>
      {#if running && fraction !== null && job.total !== null}
        <span class="count num">{job.done} of {job.total}</span>
      {/if}
      {#if elapsed}<span class="time num">{running && fraction !== null ? `· ${elapsed}` : elapsed}</span>{/if}
    </div>
    {#if running && variant === 'row'}
      <div
        class="bar"
        class:indeterminate={fraction === null}
        role="progressbar"
        aria-label="{title} progress"
        aria-valuemin={fraction === null ? undefined : 0}
        aria-valuemax={fraction === null ? undefined : 100}
        aria-valuenow={fraction === null ? undefined : Math.round(fraction * 100)}
        aria-valuetext={fraction === null ? stageText : `${job.done} of ${job.total}`}
      >
        {#if fraction !== null}<span class="fill" style:width="{fraction * 100}%"></span>{/if}
      </div>
    {/if}
    {#if job.cancelError}
      <p class="note">Cancel refused: {job.cancelError}</p>
    {/if}
  </div>

  <div class="buttons">
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
    {#if job.state === 'done' && actions}{@render actions()}{/if}
    {#if job.state === 'failed' && onretry}
      <IconButton icon="refresh" label="Retry" showLabel size="s" onclick={() => onretry?.()} />
    {/if}
    {#if !running && ondismiss}
      <IconButton
        icon="close"
        label="Dismiss"
        variant="ghost"
        size="s"
        tooltip="top"
        onclick={() => ondismiss?.(job.id)}
      />
    {/if}
  </div>
</div>

<style>
  .job {
    display: grid;
    grid-template-columns: 16px minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-3);
    min-height: 40px;
    padding: var(--space-2) var(--space-2) var(--space-2) var(--space-3);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .job.strip {
    min-height: 30px;
    padding: 0 var(--space-1) 0 var(--space-2);
  }
  .state-failed {
    border-color: var(--danger);
  }

  .mark {
    display: inline-flex;
    width: 16px;
    height: 16px;
    align-items: center;
    justify-content: center;
    align-self: start;
    margin-top: 2px;
    color: var(--fg-muted);
  }
  .strip .mark {
    align-self: center;
    margin-top: 0;
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

  .main {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .line {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    min-width: 0;
  }
  .title {
    font-weight: var(--weight-medium);
    white-space: nowrap;
  }
  .word {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .stage {
    min-width: 0;
    overflow: hidden;
    color: var(--fg);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .row .stage.error {
    white-space: normal;
    overflow-wrap: anywhere;
  }
  .spacer {
    flex: 1;
  }
  .count,
  .time {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }

  .bar {
    position: relative;
    height: 4px;
    overflow: hidden;
    border-radius: var(--radius-s);
    background: var(--surface);
  }
  .fill {
    position: absolute;
    inset: 0 auto 0 0;
    background: var(--fg-muted);
  }
  /* Indeterminate: a quiet track (the spinner carries the motion). */
  .bar.indeterminate {
    background: var(--border-soft);
  }

  .note {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }

  .buttons {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
  }
  .buttons :global(.icon-button) {
    height: 26px;
  }
</style>

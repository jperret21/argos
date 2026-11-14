<!--
  Run card in Observe (PROPOSAL 3.1 "Run card", owner D2; promoted from
  src/lab/workspace/observe/cards/RunCard.svelte, PROPOSAL section 6, W6): "is my run
  fine?" in one place, on the server's `sequence` record (A63) and the run's saved subs.

  - Header: the state in a word (run.ts stateChip); folded, n / N and the end time.
  - What runs: object, step k of N, filter, exposure, gain, pass.
  - Frames n / N with the progress on a time axis (RunProgress: the fill lags the now marker
    when the run is slow or paused) and the true percentage.
  - The LAST-FRAME AGE against the observed cadence (AgeMeter: hatched and "overdue" past
    max(2 x cadence, cadence + 60 s)), the liveness signal: a frozen run looks healthy
    between frames otherwise.
  - Ends (UTC, from the server's time left at the newest frame), next autofocus, end of run.
  - Pause (no confirmation: it holds at a frame boundary and Resume undoes it), Stop (the
    spec's dialog, D4, Q-P7: what is discarded, saved and where).
  - Scheduled: when it starts, and Cancel start (asked first). After the run: the outcome
    in words, the server's sentence verbatim (the wrap-up is wave 6b). Idle: a link to Plan.
  The attention items and the wrap-up are wave 6b (the record already carries what they need).
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { SequenceState } from '../api/sequence';
  import AgeMeter from '../charts/mini/AgeMeter.svelte';
  import RunProgress from '../charts/mini/RunProgress.svelte';
  import { observedCadence } from '../charts/conditions';
  import Button from '../components/Button.svelte';
  import Card from '../components/Card.svelte';
  import ConfirmDialog from '../components/ConfirmDialog.svelte';
  import IconButton from '../components/IconButton.svelte';
  import Readouts, { type ReadoutItem } from '../components/Readouts.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { fixed, seconds } from '../format/number';
  import { clockUtc, duration } from '../format/time';
  import { cadenceEnd, endAction, endAt, folderName, isActive, nextAutofocusParts, outcomeOf, outcomeText, stateChip, stopDialog, timeLeft } from '../run/run';

  interface Props {
    seq: SequenceState | null;
    /** Unix s, ticking once per second (a clock, not an animation). */
    now: number;
    /** Save times of this run's subs (SequenceStore.frameTimes). */
    frameTimes?: readonly number[];
    /** Autofocus passes of this run (unix s). */
    marks?: readonly number[];
    open?: boolean;
    onpause: () => Promise<unknown> | void;
    onresume: () => Promise<unknown> | void;
    onstop: () => Promise<unknown> | void;
    /** Go to Plan (F3). */
    onplan?: () => void;
    onerror?: (message: string) => void;
    /** Hide the outcome of the run that ended (the card leaves Observe until the next run). */
    ondismiss?: () => void;
    /** Gallery: the Stop dialog drawn in place. */
    previewStop?: boolean;
    /** Wave 6b: the run's open attention items (RunAttention), under the readouts. */
    attention?: Snippet;
    /** Wave 6b (D2): the end-of-night wrap-up (WrapUp), in place of the outcome line. */
    ended?: Snippet;
  }
  let { seq, now, frameTimes = [], marks = [], open = $bindable(true), onpause, onresume, onstop, onplan, onerror, ondismiss, previewStop = false, attention, ended }: Props = $props();

  let busy = $state<'pause' | 'resume' | null>(null);
  let failure = $state<string | null>(null);
  let stopOpen = $state(false);
  $effect(() => {
    if (previewStop) stopOpen = true;
  });

  const chip = $derived(stateChip(seq));
  const st = $derived(seq?.state ?? 'idle');
  const active = $derived(isActive(seq));
  const n = $derived(frameTimes.length);
  // The server's observed cadence (pauses and autofocus excluded), else the client's median, else the plan's.
  const cadence = $derived(seq?.observed_cadence_s ?? observedCadence(frameTimes, n) ?? seq?.cadence_s ?? null);
  const cadenceWord = $derived(seq?.observed_cadence_s != null || observedCadence(frameTimes, n) !== null ? 'observed, median' : seq?.cadence_s != null ? 'planned' : 'after 2 frames');
  // DATE-OBS of the newest sub (the clock of the cadence).
  const lastAt = $derived.by(() => {
    const mine = n ? frameTimes[n - 1] : null;
    const srv = seq?.last_frame_t ?? null;
    return mine === null ? srv : srv === null ? mine : Math.max(mine, srv);
  });
  // Frames are expected while the camera works for the run (not paused, not in autofocus).
  const expecting = $derived(st === 'running' || st === 'pausing');
  const end = $derived(seq ? endAt(seq, now) : null);
  const left = $derived(seq ? timeLeft(seq, now) : null);
  const late = $derived(seq ? cadenceEnd(seq, now, cadence, lastAt) : null);
  const pct = $derived(seq && seq.frames_total > 0 ? Math.round((seq.frames_done / seq.frames_total) * 100) : 0);
  const dialog = $derived(seq ? stopDialog(seq) : null);
  const result = $derived(seq && st === 'idle' ? seq.last_result : null);

  const items = $derived<ReadoutItem[]>(
    seq
      ? [
          {
            k: 'Ends',
            v: late !== null ? clockUtc(late, false) : end !== null ? clockUtc(end, false) : '—',
            unit: end !== null || late !== null ? 'UTC' : undefined,
            // Never "in 0 s" while frames remain: the server's estimate lags the first frames;
            // the frames left × the cadence then.
            note:
              st === 'paused' && left !== null
                ? `if resumed now · ${duration(left)} left`
                : late !== null
                  ? `in ≈ ${duration(late - now)} · from cadence`
                  : left !== null && left <= 0 && seq.frames_done < seq.frames_total
                  ? 'after this frame · server estimate passed'
                  : left !== null
                    ? `in ${duration(left)} · server estimate`
                    : 'after the first frames',
            key: true,
          },
          (() => {
            const af = nextAutofocusParts(seq, cadence);
            return { k: 'Next autofocus', ...af, muted: seq.autofocus_every_n === 0, word: !/\d/.test(af.v) };
          })(),
          { k: 'End of run', v: endAction(seq.on_complete) ?? 'nothing', muted: !endAction(seq.on_complete), word: true },
          { k: 'Cadence', v: cadence !== null ? fixed(cadence, 1) : '—', unit: cadence !== null ? 's' : undefined, note: cadenceWord },
        ]
      : [],
  );

  async function act(kind: 'pause' | 'resume', fn: () => Promise<unknown> | void): Promise<void> {
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

  const stepLine = $derived.by(() => {
    if (!seq) return '';
    const b: string[] = [];
    // Steps counted among the enabled ones (a skipped step is not "of N", design review W6a).
    const plan = seq.plan?.steps ?? null;
    if (seq.step_index !== null && plan) {
      const on = plan.map((s, i) => [s, i] as const).filter(([s]) => s.enabled && s.count > 0);
      const k = on.findIndex(([, i]) => i === seq.step_index);
      b.push(`step ${k >= 0 ? k + 1 : seq.step_index + 1} of ${on.length || plan.length}`);
    } else if (seq.step_index !== null) b.push(`step ${seq.step_index + 1}${seq.steps_total ? ` of ${seq.steps_total}` : ''}`);
    if (seq.step) {
      b.push(seq.step.frame_type === 'Light' || seq.step.frame_type === 'Flat' ? seq.step.filter_name || '—' : seq.step.frame_type);
      b.push(seconds(seq.step.exposure_s)); // as the HUD and the Camera card
      b.push(`gain ${seq.step.gain}`);
    }
    if (seq.repeat !== null && seq.repeat > 1 && seq.pass_index !== null) b.push(`pass ${seq.pass_index} of ${seq.repeat}`);
    return b.join(' · ');
  });
</script>

{#snippet status()}
  <StatusBadge tone={chip.tone} label={chip.label} />
{/snippet}
{#snippet summary()}
  {#if seq && (active || st === 'waiting')}
    <span class="num">{seq.frames_done} / {seq.frames_total}{end !== null ? ` · ends ${clockUtc(end, false)} UTC` : ''}</span>
  {/if}
{/snippet}

<Card title="Run" icon="nav-sequencer" collapsible bind:open {status} {summary}>
  <div class="run">
    {#if !seq || (st === 'idle' && !result)}
      <p class="idle">No sequence is running. Plan one, then start it from Plan.</p>
      {#if onplan}<div class="actions"><Button label="Open Plan" size="s" onclick={onplan} /></div>{/if}
    {:else if result && ended}
      {@render ended()}
    {:else if result}
      <p class="outcome o-{outcomeOf(result)}"><span class="mark" aria-hidden="true"></span>{outcomeText(result)}</p>
      {#if result.run_root ?? seq.run_root}
        <p class="meta">Session {folderName(result.run_root ?? seq.run_root)}</p>
      {/if}
      {#if ondismiss || onplan}
        <div class="actions">
          {#if onplan}<Button label="Open Plan" size="s" variant="ghost" onclick={onplan} />{/if}
          <span class="grow"></span>
          {#if ondismiss}<Button label="Dismiss" size="s" variant="ghost" onclick={ondismiss} />{/if}
        </div>
      {/if}
    {:else}
      <p class="what">
        <span class="obj">{seq.object_name ?? '—'}</span>
        <span class="meta">{stepLine}</span>
      </p>

      {#if st === 'waiting'}
        <p class="note">Starts at <b>{seq.start_at_t !== null ? clockUtc(seq.start_at_t, false) : '—'}</b> UTC{seq.start_at_t !== null && seq.start_at_t > now ? `, in ${duration(seq.start_at_t - now)}` : ''} · {seq.frames_total} frames planned</p>
      {:else}
        <div class="frames">
          <span class="count num"><b>{seq.frames_done}</b> / {seq.frames_total}</span>
          <RunProgress done={seq.frames_done} total={seq.frames_total} start={seq.started_t} end={end ?? seq.started_t} {now} times={frameTimes} {n} {marks} width={0} height={6} />
          <span class="pct num">{pct} %</span>
        </div>
        <div class="age">
          <span class="k" title="Since the newest sub started (its DATE-OBS)">Last frame</span>
          <AgeMeter age={lastAt !== null ? Math.max(0, now - lastAt) : null} {cadence} {expecting} width={120} />
          {#if st === 'paused'}<span class="meta">paused: no frame expected</span>{:else if st === 'autofocus'}<span class="meta">autofocus pass in progress</span>{/if}
        </div>
        <Readouts {items} cols={2} />
      {/if}
      {#if attention}{@render attention()}{/if}

      <div class="actions">
        {#if st === 'waiting'}
          <IconButton icon="stop" label="Cancel start…" showLabel size="s" variant="danger" onclick={() => (stopOpen = true)} />
        {:else}
          {#if st === 'paused' || st === 'pausing'}
            <IconButton icon="start" label="Resume" showLabel size="s" busy={busy === 'resume'} tooltipText={st === 'pausing' ? 'Cancel the pause: the run goes on' : 'Resume the run'} onclick={() => act('resume', onresume)} />
          {:else}
            <IconButton icon="pause" label="Pause" showLabel size="s" busy={busy === 'pause'} disabledReason={st === 'stopping' ? 'The run is stopping' : null} tooltipText="Pause at the end of this frame" onclick={() => act('pause', onpause)} />
          {/if}
          <IconButton icon="stop" label="Stop…" showLabel size="s" variant="danger" busy={st === 'stopping'} disabledReason={st === 'stopping' ? 'The run is stopping' : null} onclick={() => (stopOpen = true)} />
        {/if}
        <span class="grow"></span>
        {#if st === 'pausing'}<span class="meta">pausing at the end of this frame</span>{/if}
      </div>
      {#if failure}<p class="refused" role="alert"><span class="mark" aria-hidden="true"></span>{failure}</p>{/if}
    {/if}
  </div>
</Card>

{#if dialog}
  <ConfirmDialog bind:open={stopOpen} title={dialog.title} message={dialog.message} confirmLabel={dialog.confirm} cancelLabel={dialog.cancel} destructive preview={previewStop} onconfirm={() => onstop()} />
{/if}

<style>
  .run {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .idle,
  .note,
  .outcome {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-s);
  }
  .idle {
    color: var(--text-muted);
  }
  .note {
    font-variant-numeric: var(--numeric);
  }
  .note b {
    font-weight: var(--weight-medium);
  }
  .what {
    margin: 0;
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    column-gap: var(--space-2);
  }
  .obj {
    color: var(--fg);
    font-size: var(--text-l);
    font-weight: var(--weight-semibold);
  }
  .meta {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .frames {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-3);
  }
  .count {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-l);
  }
  .count b {
    color: var(--fg);
    font-size: var(--readout-key);
    font-weight: var(--weight-medium);
  }
  .pct {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
  .age {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
  .k {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    min-width: 76px;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .grow {
    flex: 1;
  }
  .outcome,
  .refused {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
  }
  .refused {
    margin: 0;
    color: var(--fg);
    font-size: var(--text-xs);
  }
  .mark {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    align-self: center;
  }
  .o-completed .mark {
    background: var(--status-ok);
  }
  .o-stopped .mark {
    box-shadow: inset 0 0 0 1.5px var(--status-idle);
  }
  .o-failed .mark,
  .refused .mark {
    background: var(--danger);
  }
</style>

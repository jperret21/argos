<!--
  "Start at hh:mm" (Q-P2, P7): the sequence starts at a UTC time and the server waits.
  The field takes a 24-hour UTC time; under it, in words, when that is (the date when it
  is tomorrow: never a silent shift), how long from now and the computer's local time.
  Prefilled with a transit's coverage start when there is one. Nothing is sent until
  "Schedule the start" is pressed; an invalid time is refused in words.
-->
<script lang="ts">
  import Button from '../components/Button.svelte';
  import Popover from '../components/Popover.svelte';
  import TextField from '../components/TextField.svelte';
  import { clockUtc } from '../format/time';
  import { browserOffsetMin, zoneLabel } from '../charts/visibility';
  import { hhmm, parseStartAt } from './run';

  interface Props {
    open?: boolean;
    anchor?: HTMLElement | null;
    now: number;
    /** Prefill (unix s): a transit's coverage start. */
    suggested?: number | null;
    /** Why Start cannot run (the same refusal as Start). */
    blocked?: string | null;
    onschedule: (t: number) => Promise<unknown> | void;
    /** Minutes east of UTC for the local hint (default: the browser's zone). */
    offsetMin?: number | null;
    preview?: boolean;
    /** Gallery: the field's text. */
    initial?: string | null;
  }
  let { open = $bindable(false), anchor = null, now, suggested = null, blocked = null, onschedule, offsetMin = null, preview = false, initial = null }: Props = $props();

  let text = $state('');
  let busy = $state(false);
  let failure = $state<string | null>(null);
  $effect(() => {
    if (open) {
      text = initial ?? (suggested !== null ? hhmm(suggested) : '');
      failure = null;
    }
  });

  const parsed = $derived(text.trim() ? parseStartAt(text, now) : null);
  const local = $derived.by(() => {
    if (!parsed?.ok) return null;
    const off = offsetMin ?? browserOffsetMin(parsed.t);
    return off ? `${clockUtc(parsed.t + off * 60, false)} local (${zoneLabel(off)})` : null;
  });

  async function schedule(): Promise<void> {
    if (!parsed?.ok || busy || blocked) return;
    busy = true;
    failure = null;
    try {
      await onschedule(parsed.t);
      open = false;
    } catch (err) {
      failure = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
    }
  }
</script>

<Popover bind:open {anchor} title="Start at a time" width={320} placement="bottom-end" {preview}>
  <form
    class="sa"
    onsubmit={(e) => {
      e.preventDefault();
      void schedule();
    }}
  >
    <TextField
      label="Start at (UTC)"
      bind:value={text}
      mono
      placeholder="hh:mm"
      autocomplete="off"
      inputmode="numeric"
      error={parsed && !parsed.ok ? parsed.error : null}
      hint={parsed?.ok ? `${parsed.text}${local ? ` · ${local}` : ''}` : 'The server waits, then starts the plan as it is now.'}
    />
    {#if suggested !== null}
      <p class="note">Transit coverage starts at {hhmm(suggested)} UTC.</p>
    {/if}
    {#if failure}
      <p class="err" role="alert">{failure}</p>
    {/if}
    <div class="row">
      <Button label="Schedule the start" variant="primary" size="s" type="submit" {busy} disabledReason={blocked ?? (parsed?.ok ? null : 'type a UTC time first')} />
    </div>
  </form>
</Popover>

<style>
  .sa {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .note {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .err {
    margin: 0;
    padding: var(--space-1) var(--space-2);
    border: var(--border-w) solid var(--danger);
    border-radius: var(--radius-s);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .row {
    display: flex;
    justify-content: flex-end;
  }
</style>

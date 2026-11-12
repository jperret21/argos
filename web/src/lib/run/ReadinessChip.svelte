<!--
  Readiness chip (spec 06 2.3.5, M76): "Ready" | "Ready · 1 note" | "Blocked · camera",
  its mark by level (LevelMark) and its words always; it opens the Preflight popover
  (PreflightList), which can check again. The server stays the authority (A64): the chip
  repeats what it found, it does not decide.
-->
<script lang="ts">
  import type { Preflight, PreflightItem } from '../api/sequence';
  import { duration } from '../format/time';
  import Button from '../components/Button.svelte';
  import Icon from '../components/Icon.svelte';
  import Popover from '../components/Popover.svelte';
  import Spinner from '../components/Spinner.svelte';
  import LevelMark from './LevelMark.svelte';
  import PreflightList from './PreflightList.svelte';
  import { readiness, runChecks } from './run';

  interface Props {
    /** The A64 answer (checks and the run's totals). */
    preflight?: Preflight | null;
    /** Or the checks alone. */
    items?: readonly PreflightItem[] | null;
    /** The last check failed (the server's words). */
    error?: string | null;
    checking?: boolean;
    onrefresh?: () => void;
    /** A run is engaged (its state word, "Running", "Paused"…): the checks are the running plan's,
     *  its own "running" line is left out. */
    running?: boolean | string;
    open?: boolean;
    /** Gallery: the popover drawn in place under the chip. */
    preview?: boolean;
  }
  let { preflight = null, items: given = null, error = null, checking = false, onrefresh, running = false, open = $bindable(false), preview = false }: Props = $props();

  const items = $derived(runChecks(given ?? preflight?.checks ?? null, running !== false && running !== ''));
  const r = $derived(readiness(items, running));
  const gb = (b: number) => `${(b / 1e9).toFixed(1)} GB`;
  /** The run the checks were made for: frames, duration, disk. */
  const facts = $derived.by(() => {
    const p = preflight;
    if (!p) return null;
    const b: string[] = [];
    if (p.frames_total !== null) b.push(`${p.frames_total} frames`);
    if (p.estimate_s !== null) b.push(`≈ ${duration(p.estimate_s)}`);
    if (p.bytes_needed !== null) b.push(`${gb(p.bytes_needed)} needed${p.bytes_free !== null ? `, ${gb(p.bytes_free)} free` : ''}`);
    return b.length ? b.join(' · ') : null;
  });
  const id = `preflight-${Math.random().toString(36).slice(2, 8)}`;
  let btn: HTMLButtonElement | undefined = $state();
</script>

<span class="wrap">
  <button
    type="button"
    class="chip l-{r.level}"
    bind:this={btn}
    aria-haspopup="dialog"
    aria-expanded={open}
    aria-controls={id}
    aria-label="Readiness: {r.label}. Open the preflight checks"
    onclick={() => (open = !open)}
  >
    <LevelMark level={r.level} />
    <span class="label">{r.label}</span>
    <span class="chev" aria-hidden="true"><Icon name="disclosure" size={12} /></span>
  </button>
  <Popover bind:open anchor={btn} title="Preflight" {id} width={360} placement="bottom-end" {preview}>
    {#if error}
      <p class="err" role="alert"><LevelMark level="block" />{error}</p>
    {/if}
    {#if facts}<p class="facts num">{facts}</p>{/if}
    {#if items}
      <PreflightList {items} />
    {:else if !error}
      <p class="none">Not checked yet.</p>
    {/if}
    {#snippet footer()}
      <span class="foot">
        <span class="note">Checked by the server; a note never stops Start.</span>
        {#if onrefresh}<Button label="Check again" size="s" busy={checking} onclick={onrefresh} />{/if}
        {#if checking && !onrefresh}<Spinner />{/if}
      </span>
    {/snippet}
  </Popover>
</span>

<style>
  .wrap {
    display: inline-flex;
    flex-direction: column;
    align-items: flex-end;
    gap: var(--space-1);
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: var(--control-h-s);
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg);
    font: inherit;
    font-size: var(--text-s);
    white-space: nowrap;
    cursor: pointer;
  }
  .chip:hover {
    background: var(--hover-bg);
  }
  .chip:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  .chip.l-block {
    border-color: var(--danger);
  }
  .chev {
    display: inline-flex;
    color: var(--fg-muted);
  }
  .err {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: 0 0 var(--space-2);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .facts {
    margin: 0 0 var(--space-2);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .none {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
  }
  .foot {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
  }
  .note {
    flex: 1;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
</style>

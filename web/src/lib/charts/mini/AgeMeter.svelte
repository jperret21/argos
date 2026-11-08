<!--
  Age of the last frame against the observed cadence: the liveness signal
  between two frames (promoted from src/lab/charts/mini/AgeMeter.svelte, web/lab/
  PROPOSAL.md principle 2 and section 6, W3). The bar is elapsed time on a fixed
  scale of three cadences, with ticks at 1x and at the overdue limit
  (max(2 x cadence, cadence + 60 s)); past the limit, while frames are expected,
  it is hatched and the word "overdue" appears (never colour alone). It steps
  once per second: a clock, not an animation.
-->
<script lang="ts">
  import { duration } from '../../format/time';
  import { overdueAfter } from '../conditions';

  interface Props {
    /** Seconds since the last frame (null: none yet). */
    age: number | null;
    /** Observed cadence, seconds (null: unknown). */
    cadence: number | null;
    /** Frames are expected now (live view): only then can the age be overdue. */
    expecting?: boolean;
    width?: number;
    showText?: boolean;
  }
  let { age, cadence, expecting = true, width = 64, showText = true }: Props = $props();

  const limit = $derived(overdueAfter(cadence));
  const scale = $derived(cadence ? Math.max(3 * cadence, limit * 1.15) : 180);
  const fill = $derived(age === null ? 0 : Math.min(1, age / scale));
  const overdue = $derived(expecting && age !== null && age > limit);
  const text = $derived(
    age === null
      ? 'No frame yet'
      : `Last frame ${duration(age)} ago${cadence ? `, expected every ${duration(cadence)}` : ''}${overdue ? ', overdue' : ''}`,
  );
</script>

<span class="age" class:overdue role="img" aria-label={text}>
  <span class="bar" style:width="{width}px" aria-hidden="true">
    <i class="fill" style:width="{fill * 100}%"></i>
    {#if cadence}
      <i class="tick" style:left="{(cadence / scale) * 100}%"></i>
      <i class="tick limit" style:left="{(limit / scale) * 100}%"></i>
    {/if}
  </span>
  {#if showText}
    <span class="txt num">{age === null ? '—' : duration(age)}{overdue ? ' · overdue' : ''}</span>
  {/if}
</span>

<style>
  .age {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .bar {
    position: relative;
    display: inline-block;
    height: 6px;
    border: var(--border-w) solid var(--border);
    border-radius: 1px;
    background: var(--bg-2);
    overflow: hidden;
  }
  .fill {
    position: absolute;
    inset: 0 auto 0 0;
    background: var(--fg-muted);
  }
  /* Hatching (BRAND 2 exception, owner D11): overdue reads without hue. */
  .overdue .fill {
    background: repeating-linear-gradient(135deg, var(--warning) 0 2px, transparent 2px 4px);
  }
  .tick {
    position: absolute;
    top: -1px;
    bottom: -1px;
    width: 1px;
    background: var(--fg-muted);
  }
  .tick.limit {
    background: var(--warning);
  }
  .txt {
    color: var(--fg);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .overdue .txt {
    font-weight: var(--weight-medium);
  }
</style>

<!--
  Age of the last frame against the observed cadence: the liveness signal
  between two frames (functional-spaces 4.6). The bar is elapsed time on a
  fixed scale of 3 cadences, with ticks at 1x and 2x; past the stale limit
  it is hatched and the word "stale" appears (never colour alone). It
  steps once per (simulated) second: it is a clock, not an animation.
-->
<script lang="ts">
  import { duration } from '../core/format';

  interface Props {
    age: number | null;
    cadence: number | null;
    /** Seconds after which the run is "stale" (default max(2 cadence, cadence + 60)). */
    staleAfter?: number;
    width?: number;
    showText?: boolean;
  }
  let { age, cadence, staleAfter, width = 64, showText = true }: Props = $props();

  const limit = $derived(staleAfter ?? (cadence ? Math.max(2 * cadence, cadence + 60) : 120));
  const scale = $derived(cadence ? Math.max(3 * cadence, limit * 1.15) : 180);
  const frac = $derived(age === null ? 0 : Math.min(1, age / scale));
  const stale = $derived(age !== null && age > limit);
</script>

<span class="age" class:stale role="img" aria-label={age === null ? 'No frame yet' : `Last frame ${duration(age)} ago${cadence ? `, expected every ${duration(cadence)}` : ''}${stale ? ', stale' : ''}`}>
  <span class="bar" style:width="{width}px" aria-hidden="true">
    <i class="fill" style:width="{frac * 100}%"></i>
    {#if cadence}
      <i class="tick" style:left="{(cadence / scale) * 100}%"></i>
      <i class="tick limit" style:left="{(limit / scale) * 100}%"></i>
    {/if}
  </span>
  {#if showText}
    <span class="txt num">{age === null ? '—' : duration(age)}{stale ? ' · stale' : ''}</span>
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
    border: 1px solid var(--border);
    border-radius: 1px;
    background: var(--bg-2);
    overflow: hidden;
  }
  .fill {
    position: absolute;
    inset: 0 auto 0 0;
    background: var(--fg-muted);
  }
  .stale .fill {
    background: repeating-linear-gradient(135deg, var(--warning) 0 2px, transparent 2px 4px);
  }
  .tick {
    position: absolute;
    top: -1px;
    bottom: -1px;
    width: 1px;
    background: var(--fg);
    opacity: 0.6;
  }
  .tick.limit {
    background: var(--warning);
    opacity: 1;
  }
  .txt {
    color: var(--fg);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .stale .txt {
    color: var(--fg);
    font-weight: var(--weight-medium);
  }
</style>

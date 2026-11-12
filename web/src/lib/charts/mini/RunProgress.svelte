<!--
  Run progress (promoted from src/lab/charts/mini/RunProgress.svelte, web/lab/PROPOSAL.md
  section 6, W6; one implementation for the run strip, the Run card and the status chip).

  - With frame times: the width is TIME (planned start to planned end), the frames taken
    are coverage segments (gaps past the overdue limit split them, progress.ts), autofocus
    passes are notches, the now marker is a 1 px line: a pause or a slow cadence shows as
    the fill lagging the marker.
  - Without them (a client that joined mid-run before the saves were read back): the
    width is FRAMES, done / total as a true proportion, no now marker (none would be true).
  - Neutral inks (BRAND 8: run progress bars are not brass); the words are the
    accessible name (role="img"), the bar is never the only carrier.
-->
<script lang="ts">
  import { coverageSegments, percentOf, progressText } from './progress';

  interface Props {
    done: number;
    total: number;
    /** Planned start and end (unix s); with `times`, the bar is a time axis. */
    start?: number | null;
    end?: number | null;
    now?: number | null;
    /** Saved frames' times (unix s, prefix of length `n`). */
    times?: ArrayLike<number> | null;
    n?: number;
    /** Autofocus passes (unix s). */
    marks?: readonly number[];
    /** CSS px; 0 = fill the container. */
    width?: number;
    height?: number;
    label?: string;
  }
  let { done, total, start = null, end = null, now = null, times = null, n = 0, marks = [], width = 120, height = 6, label }: Props = $props();

  const timed = $derived(!!times && n > 0 && start !== null && end !== null && end > start);
  const segs = $derived(timed && times ? coverageSegments(times, n).map(([a, b]) => [percentOf(a, start as number, end as number), percentOf(b, start as number, end as number)]) : []);
  const frac = $derived(total > 0 ? Math.min(1, Math.max(0, done / total)) : 0);
  const text = $derived(label ?? progressText(done, total, marks.length));
</script>

<span class="prog" class:fill={width === 0} style:width={width ? `${width}px` : undefined} style:height="{height}px" role="img" aria-label={text}>
  {#if timed}
    {#each segs as s, i (i)}
      <i class="seg" style:left="{s[0]}%" style:width="{Math.max(0.5, s[1] - s[0])}%"></i>
    {/each}
    {#each marks as m (m)}
      <i class="mark" style:left="{percentOf(m, start as number, end as number)}%"></i>
    {/each}
    {#if now !== null}<i class="now" style:left="{percentOf(now, start as number, end as number)}%"></i>{/if}
  {:else}
    <i class="seg" style:left="0" style:width="{frac * 100}%"></i>
  {/if}
</span>

<style>
  .prog {
    position: relative;
    display: inline-block;
    border: var(--border-w) solid var(--border);
    border-radius: 1px;
    background: var(--bg-2);
    overflow: hidden;
    flex: none;
    vertical-align: middle;
  }
  .prog.fill {
    display: block;
    width: 100%;
    flex: 1 1 auto;
  }
  .seg {
    position: absolute;
    top: 0;
    bottom: 0;
    background: var(--fg-muted);
  }
  .mark {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 1px;
    background: var(--bg-2);
  }
  .now {
    position: absolute;
    top: -1px;
    bottom: -1px;
    width: 1px;
    background: var(--fg);
  }
</style>

<!--
  Run progress as frames, not as a smooth percentage: the done part, the
  planned part, autofocus pauses as notches, and the newest frame as a
  1 px edge. Width is time (planned start to end), so a pause or a slow
  cadence shows as the fill lagging the now marker.
-->
<script lang="ts">
  interface Props {
    start: number;
    end: number;
    now: number;
    /** Times of the frames taken (prefix of length n). */
    times: ArrayLike<number>;
    n: number;
    marks?: number[];
    width?: number;
    height?: number;
  }
  let { start, end, now, times, n, marks = [], width = 120, height = 6 }: Props = $props();

  const pos = (t: number) => Math.max(0, Math.min(1, (t - start) / (end - start))) * 100;
  /** Coverage segments: contiguous frames (gap < 150 s). */
  const segs = $derived.by(() => {
    const out: [number, number][] = [];
    let i0 = 0;
    for (let i = 1; i <= n; i++) {
      if (i === n || times[i] - times[i - 1] > 150) {
        if (n) out.push([pos(times[i0]), pos(times[i - 1])]);
        i0 = i;
      }
    }
    return out;
  });
</script>

<span class="prog" style:width="{width}px" style:height="{height}px" aria-hidden="true">
  {#each segs as s, i (i)}
    <i class="seg" style:left="{s[0]}%" style:width="{Math.max(0.5, s[1] - s[0])}%"></i>
  {/each}
  {#each marks as m (m)}
    <i class="mark" style:left="{pos(m)}%"></i>
  {/each}
  <i class="now" style:left="{pos(now)}%"></i>
</span>

<style>
  .prog {
    position: relative;
    display: inline-block;
    border: 1px solid var(--border);
    border-radius: 1px;
    background: var(--bg-2);
    overflow: hidden;
    flex: none;
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

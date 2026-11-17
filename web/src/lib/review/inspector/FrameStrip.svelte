<!--
  R2's frame strip (W7 design review, BRAND 11.1 band rule): the band a landscape frame
  leaves under itself carries the session's target light curve on the session's time axis,
  this frame's time marked, each point a way to its frame (click; PageUp / PageDown step
  as before). It ties R2 back to R1 and uses dead space instead of black. Below 120 px of
  band it is one summary row (frame k / n, Δt from the previous light, HFD, the target's
  value). Neutral ink, the target's brass for its points (BRAND 10), recorder-flagged and
  suspect points hollow, the current frame ringed in the highlight ink.
-->
<script lang="ts" module>
  export interface StripPoint {
    /** Mid-exposure, unix s. */
    t: number;
    mag: number;
    /** Hollow: suspect, saturated or flagged by the recorder. */
    hollow: boolean;
    /** The light frame's path (a click opens it), or null when its FITS is missing. */
    path: string | null;
  }
</script>

<script lang="ts">
  import { DASH, fixed } from '../../format/number';
  import { clockUtc } from '../../format/time';

  interface Props {
    points: readonly StripPoint[];
    /** This frame's mid-exposure (unix s), or null. */
    current: number | null;
    height: number;
    /** "Frame 10 / 195" and the summary row's other words. */
    summary: { position: string | null; dt: number | null; hfd: number | null; name: string };
    onpick?: (path: string) => void;
  }

  let { points, current, height, summary, onpick }: Props = $props();
  let width = $state(0);

  const PAD = { l: 50, r: 18, t: 22, b: 18 };
  const compact = $derived(height < 120 || points.length < 2);
  const finite = $derived(points.filter((p) => Number.isFinite(p.t) && Number.isFinite(p.mag)));
  const range = $derived.by(() => {
    if (!finite.length) return null;
    const good = finite.filter((p) => !p.hollow);
    const ys = (good.length ? good : finite).map((p) => p.mag).sort((a, b) => a - b);
    const q = (f: number) => ys[Math.min(ys.length - 1, Math.max(0, Math.round(f * (ys.length - 1))))];
    const lo = ys.length >= 50 ? q(0.005) : ys[0];
    const hi = ys.length >= 50 ? q(0.995) : ys[ys.length - 1];
    const pad = Math.max(0.02, (hi - lo) * 0.08);
    const ts = finite.map((p) => p.t);
    return { t0: Math.min(...ts), t1: Math.max(...ts), lo: lo - pad, hi: hi + pad };
  });
  const X = (t: number) => (range ? PAD.l + ((t - range.t0) / Math.max(1, range.t1 - range.t0)) * Math.max(1, width - PAD.l - PAD.r) : 0);
  // Magnitudes: bright up.
  const Y = (m: number) => (range ? PAD.t + ((m - range.lo) / Math.max(1e-6, range.hi - range.lo)) * Math.max(1, height - PAD.t - PAD.b) : 0);
  const clampY = (m: number) => Math.min(height - PAD.b, Math.max(PAD.t, Y(m)));
  const currentPoint = $derived(current === null ? null : (finite.reduce<StripPoint | null>((best, p) => (best === null || Math.abs(p.t - current) < Math.abs(best.t - current) ? p : best), null) ?? null));

  function pick(e: MouseEvent): void {
    if (!range || !onpick) return;
    const rect = (e.currentTarget as SVGElement).getBoundingClientRect();
    const x = e.clientX - rect.left;
    let best: StripPoint | null = null;
    for (const p of finite) if (p.path && (best === null || Math.abs(X(p.t) - x) < Math.abs(X(best.t) - x))) best = p;
    if (best?.path && Math.abs(X(best.t) - x) <= 12) onpick(best.path);
  }
</script>

<div class="strip" style:height="{height}px" bind:clientWidth={width} role="group" aria-label="Session strip: the target's light curve, this frame marked">
  {#if compact}
    <div class="row num">
      <span>{summary.position ? `Frame ${summary.position}` : DASH}</span>
      <span>Δt {summary.dt !== null ? `${fixed(summary.dt, 1)} s` : DASH}</span>
      <span>HFD {fixed(summary.hfd, 2)} px</span>
      <span>{summary.name} {currentPoint ? fixed(currentPoint.mag, 3) : DASH}</span>
    </div>
  {:else if range && width > 0}
    <span class="title"><span class="name">{summary.name}</span> <span class="num">{currentPoint ? `${fixed(currentPoint.mag, 3)} · ${clockUtc(currentPoint.t)} UTC` : DASH}</span><span class="hint">click a point to open its frame</span></span>
    <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
    <svg {width} {height} onclick={pick}>
      <text class="tick" x={PAD.l - 6} y={Y(range.lo + (range.hi - range.lo) * 0.08) + 3} text-anchor="end">{fixed(range.lo + (range.hi - range.lo) * 0.08, 2)}</text>
      <text class="tick" x={PAD.l - 6} y={Y(range.hi - (range.hi - range.lo) * 0.08) + 3} text-anchor="end">{fixed(range.hi - (range.hi - range.lo) * 0.08, 2)}</text>
      <text class="tick" x={PAD.l} y={height - 4}>{clockUtc(range.t0, false)}</text>
      <text class="tick" x={width - PAD.r} y={height - 4} text-anchor="end">{clockUtc(range.t1, false)}</text>
      {#if currentPoint}
        <line class="now" x1={X(currentPoint.t)} x2={X(currentPoint.t)} y1={PAD.t - 4} y2={height - PAD.b} />
      {/if}
      {#each finite as p, i (i)}
        {#if p.mag < range.lo || p.mag > range.hi}
          <path class="off" d="M{X(p.t) - 3} {p.mag < range.lo ? PAD.t + 5 : height - PAD.b - 5}L{X(p.t)} {p.mag < range.lo ? PAD.t : height - PAD.b}L{X(p.t) + 3} {p.mag < range.lo ? PAD.t + 5 : height - PAD.b - 5}" />
        {:else}
          <circle class:hollow={p.hollow} cx={X(p.t)} cy={clampY(p.mag)} r="2.5" />
        {/if}
      {/each}
      {#if currentPoint && currentPoint.mag >= range.lo && currentPoint.mag <= range.hi}
        <circle class="ring" cx={X(currentPoint.t)} cy={clampY(currentPoint.mag)} r="6" />
      {/if}
    </svg>
  {/if}
</div>

<style>
  .strip {
    position: relative;
    flex: none;
    overflow: hidden;
    border-top: var(--border-w) solid var(--border);
    background: var(--chart-surface, var(--bg));
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    height: 100%;
    padding: 0 var(--space-3);
    color: var(--fg);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .title {
    position: absolute;
    top: 3px;
    left: 50px;
    right: 18px;
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    color: var(--fg);
    font-size: var(--text-xs);
    pointer-events: none;
    white-space: nowrap;
  }
  .title .hint {
    margin-left: auto;
    color: var(--text-muted);
    font-size: var(--text-2xs);
  }
  svg {
    display: block;
    cursor: pointer;
  }
  .tick {
    fill: var(--chart-text, var(--text-muted));
    font-family: var(--font-mono);
    font-size: 10px;
  }
  circle {
    fill: var(--chart-1);
  }
  circle.hollow {
    fill: none;
    stroke: var(--chart-1);
    stroke-width: 1.25;
  }
  .off {
    fill: none;
    stroke: var(--chart-1);
    stroke-width: 1.25;
  }
  .now {
    stroke: var(--chart-highlight);
    stroke-dasharray: 4 3;
    stroke-width: 1;
  }
  circle.ring {
    fill: none;
    stroke: var(--chart-highlight);
    stroke-width: 1.5;
  }
</style>

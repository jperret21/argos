<!--
  Focuser travel gauge: two scales, like the coarse and fine dials of an
  instrument. Promoted from src/lab/controls/instruments/FocuserGauge.svelte
  (web/lab/PROPOSAL.md 3.3 "Focuser card", 6, W3).

  - Overview (top hairline): the whole travel, 0 to MaxStep, a bracket for
    the window drawn below and a tick at the position: "where am I in the
    travel" (a 100 000-step travel at 1:1 would make a 100-step move 0.4 px).
  - Local scale: one minor tick per STEP SIZE, a longer one every five, a
    label every ten, so one tap of In / Out moves the needle by exactly one
    tick: the tick spacing IS the step.
  - Needle = the last POLLED position (2 Hz while moving): it jumps, it never
    glides between polls. Hollow triangle = the commanded target (queued taps
    included), the travel still to do dashed. Diamond = best focus of the
    last autofocus.
  - The window re-centres (at once) when the needle leaves its middle 60 %.
  Neutral inks only (no brass: the card's one brass mark is the running
  autofocus), so Night Red stays red and the brass budget holds.
-->
<script lang="ts">
  import { int } from '../../format/number';

  interface Props {
    /** Polled position; null = offline (scale only). */
    position: number | null;
    /** Commanded target (queued taps included), or null. */
    target?: number | null;
    /** MaxStep (travel 0 … max). */
    max: number | null;
    /** Step size: one minor tick. */
    step: number;
    /** Best focus of the last autofocus. */
    afBest?: number | null;
  }

  let { position, target = null, max, step, afBest = null }: Props = $props();

  let width = $state(376);
  const H = 58;
  const PAD = 10;
  const BASE = 38;

  const offline = $derived(position === null);
  const travel = $derived(max !== null && max > 0 ? max : Math.max(step * 40, (position ?? 0) * 2, 1));
  const pos = $derived(position ?? travel / 2);

  // Window: 40 steps of the current step size, re-centred when the needle nears an edge.
  const span = $derived(Math.min(travel, Math.max(1, step) * 40));
  let center = $state(-1);
  $effect(() => {
    const half = span / 2;
    const inside = center >= 0 && Math.abs(pos - center) <= half * 0.6 && center - half >= 0 && center + half <= travel;
    if (!inside) {
      const c = Math.round(pos / step) * step;
      center = Math.min(travel - half, Math.max(half, c));
    }
  });
  const lo = $derived(center - span / 2);
  const hi = $derived(center + span / 2);
  const inner = $derived(Math.max(10, width - 2 * PAD));
  const x = (v: number) => PAD + ((v - lo) / (hi - lo || 1)) * inner;
  const ox = (v: number) => PAD + (Math.min(travel, Math.max(0, v)) / travel) * inner;

  // Minor tick per step, a longer one every 5, a label every 10 (at least about
  // 64 px apart at rail width), never within 24 px of an edge.
  const tickList = $derived.by(() => {
    const out: { v: number; major: boolean; label: boolean }[] = [];
    if (!(step > 0) || center < 0) return out;
    const first = Math.ceil(lo / step) * step;
    for (let v = first; v <= hi + 1e-6 && out.length < 200; v += step) {
      const k = Math.round(v / step);
      const px = x(v);
      out.push({ v, major: k % 5 === 0, label: k % 10 === 0 && px > PAD + 24 && px < PAD + inner - 24 });
    }
    return out;
  });

  const inView = (v: number | null | undefined): v is number => v !== null && v !== undefined && v >= lo && v <= hi;
  const clampX = (v: number) => Math.min(PAD + inner, Math.max(PAD, x(v)));
  const label = $derived(
    offline
      ? 'Focuser travel: offline'
      : `Focuser travel: position ${int(position)} of ${max !== null ? int(max) : 'unknown'}${
          target !== null && target !== position ? `, moving to ${int(target)}` : ''
        }${afBest !== null ? `, last autofocus best ${int(afBest)}` : ''}`,
  );
</script>

<div class="gauge" class:offline bind:clientWidth={width}>
  <svg {width} height={H} viewBox="0 0 {width} {H}" role="img" aria-label={label}>
    <!-- Overview: the whole travel -->
    <line class="ov" x1={PAD} y1="4.5" x2={PAD + inner} y2="4.5" />
    {#if !offline}
      <path class="ov-bracket" d="M{ox(lo)} 1.5 V7.5 M{ox(hi)} 1.5 V7.5 M{ox(lo)} 4.5 H{ox(hi)}" />
      <line class="ov-pos" x1={ox(pos)} y1="0.5" x2={ox(pos)} y2="8.5" />
    {/if}

    <!-- Local scale: one minor tick per step -->
    <line class="base" x1={PAD} y1={BASE + 0.5} x2={PAD + inner} y2={BASE + 0.5} />
    {#each tickList as t (t.v)}
      <line
        class="tick"
        class:major={t.major}
        x1={Math.round(x(t.v)) + 0.5}
        y1={BASE + 1}
        x2={Math.round(x(t.v)) + 0.5}
        y2={BASE + (t.major ? 8 : 4)}
      />
      {#if t.label && !offline}
        <text class="tl" x={x(t.v)} y={BASE + 17} text-anchor="middle">{int(t.v)}</text>
      {/if}
    {/each}

    {#if !offline}
      <!-- Travel still to do -->
      {#if target !== null && target !== position}
        <line class="travel" x1={clampX(pos)} y1={BASE - 4.5} x2={clampX(target)} y2={BASE - 4.5} />
      {/if}

      <!-- Best focus of the last autofocus -->
      {#if inView(afBest)}
        {@const left = afBest < pos}
        <path class="af" d="M{x(afBest)} {BASE - 27} l3.5 3.5 l-3.5 3.5 l-3.5 -3.5 z" />
        <!-- The word sits on the side away from the needle, so neither hides the other. -->
        <text class="afl" x={x(afBest) + (left ? -7 : 7)} y={BASE - 20} text-anchor={left ? 'end' : 'start'}>AF</text>
      {/if}

      <!-- Commanded target -->
      {#if inView(target) && target !== position}
        <path class="target" d="M{x(target)} {BASE - 1} l-5 -8 h10 z" />
      {/if}

      <!-- Needle: the last polled position -->
      {#if inView(pos)}
        <line class="needle" x1={Math.round(x(pos)) + 0.5} y1={BASE - 20} x2={Math.round(x(pos)) + 0.5} y2={BASE + 8} />
        <circle class="hub" cx={Math.round(x(pos)) + 0.5} cy={BASE - 20} r="2.25" />
      {/if}
    {/if}
  </svg>
</div>

<style>
  .gauge {
    width: 100%;
    min-width: 0;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
  }
  svg {
    display: block;
  }
  .ov {
    stroke: var(--border);
    stroke-width: 1;
  }
  .ov-bracket {
    fill: none;
    stroke: var(--fg-muted);
    stroke-width: 1;
  }
  .ov-pos {
    stroke: var(--fg);
    stroke-width: 1.5;
  }
  .base,
  .tick {
    stroke: var(--border);
    stroke-width: 1;
  }
  .tick.major {
    stroke: var(--fg-muted);
  }
  .tl,
  .afl {
    fill: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-variant-numeric: var(--numeric);
  }
  .travel {
    stroke: var(--fg-muted);
    stroke-width: 1;
    stroke-dasharray: 2 2;
  }
  .af {
    fill: var(--fg-muted);
  }
  .target {
    fill: none;
    stroke: var(--fg);
    stroke-width: 1.5;
    stroke-linejoin: round;
  }
  .needle {
    stroke: var(--fg);
    stroke-width: 2;
  }
  .hub {
    fill: var(--fg);
  }
  .offline .base,
  .offline .tick {
    stroke: var(--border-soft);
  }
</style>

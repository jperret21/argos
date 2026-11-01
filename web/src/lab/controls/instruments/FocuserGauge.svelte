<!--
  Focuser travel gauge (proposal): two scales, like a coarse and a fine dial.

  - Overview (top hairline): the whole travel, 0 to max, with a bracket for
    the window shown below and a tick at the position. Answers "where am I
    in the travel" (a 100,000-step travel drawn at 1:1 would make a 100-step
    move invisible: 0.4 px).
  - Local scale: one minor tick per STEP SIZE, a labelled tick every five,
    so one tap of In / Out moves the needle by exactly one tick. The scale
    follows the step selector: the tick spacing IS the step.
  - Needle = last POLLED position (2 Hz while moving); it jumps, it never
    glides between polls. Hollow brass triangle = commanded target, with the
    travel still to do dashed. Diamond = best focus of the last autofocus.
  - The window re-centres (instantly) when the needle leaves its middle 60 %.
  Tokens only, so Night Red is red-only.
-->
<script lang="ts">
  import { grouped } from '../format';

  interface Props {
    position: number;
    target: number | null;
    max: number;
    step: number;
    afBest?: number | null;
    offline?: boolean;
  }

  let { position, target, max, step, afBest = null, offline = false }: Props = $props();

  let width = $state(368);
  const H = 58;
  const PAD = 10;
  const BASE = 38;

  // Window: 40 steps of the current step size, re-centred when the needle nears an edge.
  const span = $derived(Math.min(max, step * 40));
  let center = $state(0);
  $effect(() => {
    const half = span / 2;
    const inside = Math.abs(position - center) <= half * 0.6;
    if (!inside || center === 0) {
      const c = Math.round(position / step) * step;
      center = Math.min(max - half, Math.max(half, c));
    }
  });
  const lo = $derived(center - span / 2);
  const hi = $derived(center + span / 2);
  const inner = $derived(width - 2 * PAD);
  const x = (v: number) => PAD + ((v - lo) / (hi - lo)) * inner;
  const ox = (v: number) => PAD + (v / max) * inner;

  // Minor tick per step, a longer one every 5, a label every 10 (at least ~64 px
  // apart at rail width) and never within 24 px of an edge.
  const tickList = $derived.by(() => {
    const out: { v: number; major: boolean; label: boolean }[] = [];
    const first = Math.ceil(lo / step) * step;
    for (let v = first; v <= hi + 1e-6; v += step) {
      const k = Math.round(v / step);
      const px = x(v);
      out.push({ v, major: k % 5 === 0, label: k % 10 === 0 && px > PAD + 24 && px < PAD + inner - 24 });
    }
    return out;
  });

  const inView = (v: number | null) => v !== null && v >= lo && v <= hi;
  const clampX = (v: number) => Math.min(PAD + inner, Math.max(PAD, x(v)));
</script>

<div class="gauge" class:offline bind:clientWidth={width}>
  <svg {width} height={H} viewBox="0 0 {width} {H}" role="img" aria-label="Focuser travel: position {grouped(position)} of {grouped(max)}{target !== null ? `, moving to ${grouped(target)}` : ''}">
    <!-- Overview: whole travel -->
    <line class="ov" x1={PAD} y1="4.5" x2={PAD + inner} y2="4.5" />
    <path class="ov-bracket" d="M{ox(lo)} 1.5 V7.5 M{ox(hi)} 1.5 V7.5 M{ox(lo)} 4.5 H{ox(hi)}" />
    {#if !offline}<line class="ov-pos" x1={ox(position)} y1="0.5" x2={ox(position)} y2="8.5" />{/if}

    <!-- Local scale -->
    <line class="base" x1={PAD} y1={BASE + 0.5} x2={PAD + inner} y2={BASE + 0.5} />
    {#each tickList as t (t.v)}
      <line class="tick" class:major={t.major} x1={Math.round(x(t.v)) + 0.5} y1={BASE + 1} x2={Math.round(x(t.v)) + 0.5} y2={BASE + (t.major ? 7 : 4)} />
      {#if t.label}
        <text class="tl" x={x(t.v)} y={BASE + 16} text-anchor="middle">{grouped(t.v)}</text>
      {/if}
    {/each}

    {#if !offline}
      <!-- Travel still to do -->
      {#if target !== null && target !== position}
        <line class="travel" x1={clampX(position)} y1={BASE - 4.5} x2={clampX(target)} y2={BASE - 4.5} />
      {/if}

      <!-- Best focus of the last autofocus -->
      {#if afBest !== null && inView(afBest)}
        <path class="af" d="M{x(afBest)} {BASE - 26} l3.5 3.5 l-3.5 3.5 l-3.5 -3.5 z" />
        <text class="afl" x={x(afBest) + 7} y={BASE - 19}>AF</text>
      {/if}

      <!-- Commanded target -->
      {#if target !== null && inView(target)}
        <path class="target" d="M{x(target)} {BASE - 1} l-5 -8 h10 z" />
      {/if}

      <!-- Needle: last polled position -->
      {#if inView(position)}
        <line class="needle" x1={Math.round(x(position)) + 0.5} y1={BASE - 20} x2={Math.round(x(position)) + 0.5} y2={BASE + 8} />
        <circle class="hub" cx={Math.round(x(position)) + 0.5} cy={BASE - 20} r="2.25" />
      {/if}
    {/if}
  </svg>
</div>

<style>
  .gauge {
    width: 100%;
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
  .base {
    stroke: var(--border);
    stroke-width: 1;
  }
  .tick {
    stroke: var(--border);
    stroke-width: 1;
  }
  .tick.major {
    stroke: var(--fg-muted);
  }
  .tl {
    fill: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 10px;
    font-variant-numeric: var(--numeric);
  }
  .travel {
    stroke: var(--fg-muted);
    stroke-width: 1;
    stroke-dasharray: 2 2;
  }
  .af {
    fill: var(--cyan);
  }
  .afl {
    fill: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 10px;
  }
  .target {
    fill: none;
    stroke: var(--accent);
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

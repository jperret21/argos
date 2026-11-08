<!--
  Image HUD (promoted from the HUD of src/lab/workspace/observe/Viewer.svelte, web/lab/
  PROPOSAL.md 3.1 and 6, W3: chips and cursor; the compass and the arcminute scale bar
  wait for field identification, W4). Screen space over the viewer: the image rotation
  stays a display choice, the chips never turn with it. Opaque chips (--elev-hud) so they
  read over any star field; nothing here takes the pointer except where noted.

  - Top left, over the image: what the frame ON SCREEN is (viewer/hud.ts frameChips).
  - Bottom right: the cursor readout X, Y (frame px, un-rotated), value (raw ADU), and
    RA / Dec once a WCS exists (owner decision D6: it sits where the eye is; the status bar
    no longer repeats it), with a 64-bin mini histogram and the black / white levels when
    the band does not show the levels (Focus mode, or the band hidden).
  - Top centre, while a separator is dragged: what the layout costs (band, image size,
    black margins), so the space rule stays visible (PROPOSAL 2.5).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import Icon from '../components/Icon.svelte';
  import { readInks, type ChartInks } from '../charts/ink';
  import type { CursorReadout, HudChip, MiniHistogram } from './hud';

  interface Props {
    chips: readonly HudChip[];
    cursor: CursorReadout | null;
    /** Shown only when the band does not show the levels. */
    mini: MiniHistogram | null;
    /** The image on screen (CSS px in the stage; may extend past it). */
    rect: { left: number; top: number; width: number; height: number } | null;
    stage: { width: number; height: number };
    /** While a separator is dragged: the layout cost in words. */
    dragReadout?: string | null;
    /** Rebuild the canvas inks when the theme changes. */
    theme?: unknown;
    /** The frame has a WCS (field identified, W4): RA / Dec are part of the readout. */
    solved?: boolean;
  }

  let { chips, cursor, mini, rect, stage, dragReadout = null, theme, solved = false }: Props = $props();

  // The instruction shows only until the first pointing; afterwards the last values stay,
  // muted, so no permanent text sits over the image (design review W3).
  let last: CursorReadout | null = $state(null);
  $effect(() => {
    if (cursor) last = cursor;
  });
  const shownCursor = $derived(cursor ?? last);

  const left = $derived(Math.max(0, rect?.left ?? 0) + 8);
  const top = $derived(Math.max(0, rect?.top ?? 0) + 8);
  const right = $derived(Math.max(8, stage.width - Math.min(stage.width, (rect?.left ?? 0) + (rect?.width ?? stage.width)) + 8));
  const bottom = $derived(Math.max(8, stage.height - Math.min(stage.height, (rect?.top ?? 0) + (rect?.height ?? stage.height)) + 8));

  // -- Mini histogram (canvas, neutral bars, the levels in brass: they are the levels) --
  let canvas: HTMLCanvasElement | undefined = $state();
  let ink: ChartInks | null = null;
  const W = 120;
  const H = 26;

  function draw(): void {
    const m = mini;
    if (!canvas || !m || !ink) return;
    const dpr = typeof devicePixelRatio === 'number' ? devicePixelRatio : 1;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const n = m.counts.length;
    let max = 1;
    for (let i = 0; i < n; i++) max = Math.max(max, m.counts[i]);
    const lmax = Math.log10(max + 1);
    const bw = W / n;
    ctx.fillStyle = ink.fgMuted.a(0.85);
    for (let i = 0; i < n; i++) {
      const c = m.counts[i];
      if (c <= 0) continue;
      const h = Math.max(1, (Math.log10(c + 1) / lmax) * (H - 2));
      ctx.fillRect(i * bw, H - h, Math.max(1, bw - 0.5), h);
    }
    ctx.strokeStyle = ink.accent.a();
    ctx.lineWidth = 1.25;
    for (const f of [m.black, m.white]) {
      if (!Number.isFinite(f)) continue;
      const x = Math.round(Math.min(1, Math.max(0, f)) * (W - 1)) + 0.5;
      ctx.setLineDash(f < 0 || f > 1 ? [2, 2] : []);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, H);
      ctx.stroke();
    }
    ctx.setLineDash([]);
  }

  $effect(() => {
    void theme;
    void canvas;
    untrack(() => {
      if (canvas) ink = readInks(canvas);
      draw();
    });
  });
  $effect(() => {
    void mini;
    untrack(draw);
  });
</script>

{#if chips.length}
  <div class="hud tl" style:left="{left}px" style:top="{top}px" data-hud="chips">
    {#each chips as c (c.id)}
      <span class="chip" class:state={c.kind === 'state'} class:num={c.kind === 'num' || c.kind === 'state'} class:muted={c.muted} title={c.title}>
        {#if c.dot}<span class="dot {c.dot}" aria-hidden="true"></span>{/if}
        {#if c.icon}<Icon name={c.icon} size={14} />{/if}
        {c.text}
      </span>
    {/each}
  </div>
{/if}

{#if dragReadout}
  <div class="hud tc" role="status"><span class="chip strong num">{dragReadout}</span></div>
{/if}

<div class="hud br" style:right="{right}px" style:bottom="{bottom}px" data-hud="cursor">
  <div class="readout num" class:idle={!cursor} aria-live="off">
    {#if shownCursor}
      <span><b>X</b>{shownCursor.x}</span><span><b>Y</b>{shownCursor.y}</span>
      <span><b>ADU</b>{shownCursor.value}</span>
      {#if shownCursor.ra && shownCursor.dec}
        <span><b>RA</b>{shownCursor.ra}</span><span><b>Dec</b>{shownCursor.dec}</span>
      {/if}
    {:else}
      <span class="hint">Point at the image: X, Y, ADU{solved ? ', RA, Dec' : ''}</span>
    {/if}
  </div>
  {#if mini}
    <div class="mini" role="img" aria-label="Histogram of this frame with the black and white levels">
      <canvas bind:this={canvas} style:width="{W}px" style:height="{H}px" aria-hidden="true"></canvas>
    </div>
  {/if}
</div>

<style>
  .hud {
    position: absolute;
    z-index: 2;
    display: flex;
    align-items: center;
    gap: var(--space-1);
    pointer-events: none;
  }
  .tl {
    max-width: calc(100% - 16px);
    flex-wrap: wrap;
  }
  .tc {
    top: var(--space-6);
    left: 50%;
    transform: translateX(-50%);
  }
  .br {
    align-items: stretch;
    gap: 0;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    box-shadow: var(--elev-hud);
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 20px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    white-space: nowrap;
    box-shadow: var(--elev-hud);
  }
  .chip :global(.icon) {
    color: var(--fg-muted);
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .chip.state {
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .chip.muted {
    color: var(--text-muted);
  }
  .chip.strong {
    height: 26px;
    padding: 0 var(--space-3);
    border-color: var(--border);
    font-size: var(--text-s);
  }
  .dot {
    width: 6px;
    height: 6px;
    border-radius: var(--radius-round);
  }
  .dot.live {
    background: var(--accent);
  }
  .dot.busy {
    background: var(--warning);
  }
  .readout.idle {
    color: var(--text-muted);
  }
  .readout {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: 32px;
    padding: 0 var(--space-3);
    color: var(--fg);
    font-size: var(--text-xs);
    white-space: nowrap;
  }
  .readout span {
    min-width: 0;
  }
  .readout b {
    margin-right: var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
  }
  .hint {
    color: var(--text-muted);
    font-family: var(--font-ui);
  }
  .mini {
    display: flex;
    align-items: center;
    padding: 2px 6px;
    border-left: var(--border-w) solid var(--border-soft);
  }
  .mini canvas {
    display: block;
  }
</style>
